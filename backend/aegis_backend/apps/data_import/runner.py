"""
Import job execution (PH8.5, extended for large files).

A small import runs inside the upload request: the response already carries
the finished job, which is the fastest feedback a tester can get.  A large one
cannot: at the measured rate (~25 queries per row) a 20,000-row school file
takes minutes, and the platform closes a request long before that.  Those jobs
are queued and executed by a bounded worker pool in the same process, and the
client polls ``GET /data-import/jobs/{id}/`` until the job is terminal.

Re-uploading is safe (importers update an existing record in place), so a job
lost to a process restart is retried by uploading the file again.

No new infrastructure is involved: a Render free instance runs one web
process, and gunicorn's sync worker keeps notifying the arbiter while a thread
works, so the worker is not killed for idleness.  If the deployment later adds
a real queue (Celery, RQ), this module is the one place to swap.
"""

from concurrent.futures import ThreadPoolExecutor
import logging

from django.db import connections

from .constants import ImportErrorCode, ImportType, JobStatus, RecordStatus

logger = logging.getLogger(__name__)

#: Bounded on purpose: a burst of uploads queues instead of opening unbounded
#: threads and database connections.  Two concurrent jobs also keep one heavy
#: import from starving the whole process.
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

    Called by the executor, and directly by tests.  It opens its own database
    connection state (``close_old_connections``) because the request that
    queued it has already returned.
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


def run_in_background(job_id, headers):
    """Queue a job for the worker pool."""
    _executor.submit(process_job, job_id, headers)
