"""
Import job execution (PH8.5, extended for large files, queued in Phase 5).

A small import runs inside the upload request: the response already carries
the finished job, which is the fastest feedback a tester can get.  A large one
cannot: at the measured rate (~25 queries per row) a 20,000-row school file
takes minutes, and the platform closes a request long before that.  Those jobs
are queued and the client polls ``GET /data-import/jobs/{id}/`` until the job
is terminal.

Where a queued job runs depends on the deployment.  With
``IMPORT_QUEUE_ENABLED`` set and a reachable Redis, it goes to the ``imports``
RQ queue and a separate worker process (``manage.py rqworker imports``) runs
it, so a redeploy or a sleeping web instance cannot end it.  Otherwise it runs
in the bounded thread pool in this process, which is where it ran before
Phase 5: the queue buys durability, and its absence never costs the import.

Re-uploading is safe (importers update an existing record in place), so a job
lost to a process restart is retried by uploading the file again.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import logging

from django.conf import settings
from django.db import connections
from django.utils import timezone

from .constants import ImportErrorCode, ImportType, JobStatus, RecordStatus

logger = logging.getLogger(__name__)

#: RQ queue served by ``manage.py rqworker imports``.  The same name is in
#: ``settings.RQ_QUEUES``, which is what the worker reads.
IMPORT_QUEUE = "imports"

#: How long a job may sit non-terminal before it is treated as lost.
#:
#: A queued job can vanish: the free Redis tier expires when it is idle, and
#: Redis dropping the job key leaves the ImportJob row in ``processing`` with
#: a client polling it forever.  Reaping is deliberately far beyond the worst
#: real runtime — 20,000 rows, the upload cap, is about four minutes — so a job
#: that is genuinely still being worked on is never touched.
STALE_JOB_AFTER = timedelta(minutes=30)

#: Bounded on purpose: a burst of uploads queues instead of opening unbounded
#: threads and database connections.  Two concurrent jobs also keep one heavy
#: import from starving the whole process.
#
# This is only the fallback path now; the queue drains at the worker's own
# pace.  Both paths stay bounded for the same reason.
#
# shortcut: the queue behind the executor is unbounded, so a burst of uploads
# waits in ``pending`` instead of being rejected.  Add a per-user cap on
# queued jobs if a deployment ever has many uploaders at once.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="aegis-import")


def _close_old_connections():
    """
    Give a worker thread its own clean database connection state.

    ``django.db.close_old_connections`` re-checks each connection against the
    original autocommit setting, which is off inside an atomic block — so it
    would close a connection a test is mid-transaction on.  Production workers
    never run inside a caller's atomic block; tests call :func:`process_job`
    directly, so the atomic block is skipped there instead.
    """
    for connection in connections.all(initialized_only=True):
        if not connection.in_atomic_block:
            connection.close_if_unusable_or_obsolete()


def dispatch_domain_processing(job, records, headers):
    """
    Route parsed rows to the matching domain importer.

    grades / attendance / students / guidance_records all write real
    records via their importers.  Should a future import type ever be
    added without an importer, the file is parsed but nothing is
    stored, and the job says so instead of reporting a completed
    import.
    """
    from .importers.attendance import AttendanceImporter
    from .importers.grades import GradeImporter
    from .importers.guidance import GuidanceRecordsImporter
    from .importers.students import StudentImporter

    if job.import_type == ImportType.GRADES:
        GradeImporter(job, records, job.uploaded_by).process(headers)
        return
    if job.import_type == ImportType.ATTENDANCE:
        AttendanceImporter(job, records, job.uploaded_by).process(headers)
        return
    if job.import_type == ImportType.STUDENTS:
        StudentImporter(job, records, job.uploaded_by).process(headers)
        return
    if job.import_type == ImportType.GUIDANCE_RECORDS:
        GuidanceRecordsImporter(job, records, job.uploaded_by).process(headers)
        return

    # No domain importer for this type.  The rows parsed cleanly, but
    # nothing is written, so nothing may be reported as SUCCESS: that
    # would let an admin conclude the records reached the database.
    # Rows are SKIPPED and the job fails with an explicit reason, which
    # also keeps it out of the successful-import audit.
    skip_message = (
        "Parsed but not stored: this import type has no domain importer "
        "yet, so no records were written."
    )
    for record in records:
        record.status = RecordStatus.SKIPPED
        record.error_message = skip_message
        record.save()
    job.total_rows = len(records)
    job.processed_rows = 0
    job.error_rows = 0
    job.error_log = [
        {
            "code": ImportErrorCode.UNSUPPORTED_IMPORT_TYPE,
            "message": (
                f"No importer is available for '{job.import_type}', so the "
                "file was parsed but no records were imported."
            ),
        }
    ]
    job.status = JobStatus.FAILED
    job.save()


def process_records(job, records, headers):
    """Run an import in this thread, then audit it if it completed."""
    dispatch_domain_processing(job, records, headers)

    # PH10.9: audit exactly ONE IMPORT event, only once the import
    # genuinely completed.  FAILED/PARTIAL jobs are not audited as
    # successful; the hook is fire-and-forget (PH10.7 principle).
    if job.status == JobStatus.COMPLETED:
        from apps.audit.import_export_hooks import audit_successful_import

        audit_successful_import(job)


def process_job(job_id, headers):
    """
    Worker body for one queued job.

    Called by the RQ worker, by the fallback executor, and directly by tests.
    It opens its own database connection state (``close_old_connections``)
    because the request that queued it has already returned, and because an
    RQ worker reuses one process across many jobs.
    """
    from .models import ImportJob

    _close_old_connections()
    try:
        job = ImportJob.objects.get(pk=job_id)
        records = list(job.records.order_by("row_number"))
        process_records(job, records, headers)
    except ImportJob.DoesNotExist:
        return
    except Exception:
        # A background failure has no response to travel on: record it on the
        # job so the client sees a failed job instead of polling forever.  The
        # traceback goes to the log only — no row content is ever logged.
        logger.exception("Import job %s failed in the worker", job_id)
        job = ImportJob.objects.filter(pk=job_id).first()
        if job is not None:
            job.status = JobStatus.FAILED
            if not job.error_log:
                job.error_log = [
                    {
                        "code": ImportErrorCode.INTERNAL_PIPELINE_ERROR,
                        "message": "The import could not be processed.",
                    }
                ]
            job.save()
    finally:
        _close_old_connections()


def _import_queue():
    """
    The RQ queue this deployment serves, or None when it serves none.

    None covers every way there is no queue to hand a job to — the deployment
    did not switch one on, django-rq is not installed, its configuration names
    no queue — and the caller falls back to a thread.  A queue that exists but
    cannot be reached is not caught here: ``get_queue`` does not connect, so
    the failure surfaces from ``enqueue`` below.
    """
    if not getattr(settings, "IMPORT_QUEUE_ENABLED", False):
        return None
    try:
        import django_rq
    except ImportError:
        logger.warning(
            "IMPORT_QUEUE_ENABLED is set but django-rq is not installed, so "
            "large imports run in the web process. Install django-rq or unset "
            "the flag."
        )
        return None
    try:
        return django_rq.get_queue(IMPORT_QUEUE)
    except Exception:
        logger.warning(
            "No '%s' queue is configured, so large imports run in the web "
            "process. Check RQ_QUEUES and REDIS_URL.",
            IMPORT_QUEUE,
        )
        return None


def enqueue_job(job_id, headers):
    """
    Hand one job to the import queue.

    Returns True only when the queue accepted it.  Every other outcome returns
    False so the caller can run the job in this process: Redis being down
    costs the durability guarantee, never the import.
    """
    queue = _import_queue()
    if queue is None:
        return False
    try:
        # str(): RQ serializes job arguments, and the worker looks the job up
        # by primary key.
        queue.enqueue(process_job, str(job_id), headers)
    except Exception:
        logger.exception(
            "Could not queue import job %s; running it in the web process",
            job_id,
        )
        return False
    return True


def reap_stale_jobs():
    """
    Fail jobs no worker can still be running, and return how many.

    A queued job whose Redis key vanished leaves the ImportJob row in
    ``processing`` and the client polling it forever, which is the failure mode
    D6 asks this deployment to close.  The cutoff is far beyond the worst
    measured runtime (see ``STALE_JOB_AFTER``), so an import that is still
    running is never marked failed underneath the worker doing it.

    Called from the endpoint the client polls, so the client's own poll is what
    turns a lost job terminal.  Idempotent: a reaped job is terminal, and
    terminal statuses are not selected again.
    """
    from .models import ImportJob

    cutoff = timezone.now() - STALE_JOB_AFTER
    stale = ImportJob.objects.filter(
        status__in=(JobStatus.PENDING, JobStatus.PROCESSING),
        updated_at__lt=cutoff,
    )
    reaped = 0
    for job in stale:
        job.status = JobStatus.FAILED
        job.error_log = list(job.error_log) + [
            {
                "code": ImportErrorCode.JOB_QUEUE_LOST,
                "message": (
                    "The import stopped before it finished and no worker is "
                    "running it. Upload the file again to retry."
                ),
            }
        ]
        job.save()
        reaped += 1
    if reaped:
        logger.warning("Failed %s import job(s) that stopped without finishing", reaped)
    return reaped


def run_in_background(job_id, headers):
    """
    Queue a job, or run it in this process when there is no queue to use.

    The fallback is deliberate (D6): Redis on the free tier expires when it is
    idle, and an import must still be processed when that happens.
    """
    if not enqueue_job(job_id, headers):
        _executor.submit(process_job, job_id, headers)

