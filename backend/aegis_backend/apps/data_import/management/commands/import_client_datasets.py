"""
Load the client school's Electronic Class Record workbooks through the import
pipeline.

The school sends one workbook per class, named for its grade level, at the
repository root.  Each workbook carries the roster, the grades and the
teacher's remarks, and the pipeline reads one dataset per upload -- so each
workbook is uploaded twice: once as ``students`` and once as ``grades``.

This command runs those uploads the way the admin screen does: the same
parser, the same importers, the same job records, so what it writes is what
an upload of the same file writes.  It exists so a deployment can be loaded
without eight manual uploads; the school itself uploads through the screen.

The roster is loaded before the grades for every class: a grade resolves its
learner through an active enrollment, and the roster import is what creates
one.

Usage:
    python manage.py import_client_datasets
    python manage.py import_client_datasets --email admin.qa@aegis.local
"""

from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User

from apps.data_import.constants import FileType, ImportType, JobStatus, RecordStatus
from apps.data_import.models import ImportJob, ImportRecord
from apps.data_import.runner import process_records
from apps.data_import.xlsx_pipeline import XlsxValidationError, validate_raw_xlsx

#: The client workbooks, in the order they are loaded.
CLIENT_WORKBOOKS = (
    "GRADE-7-LATEST-SEPTEMBER-4-2026.xlsx",
    "GRADE-8-LATEST-SEPTEMBER-4-2026.xlsx",
    "GRADE-9-LATEST-SEPTEMBER-4-2026.xlsx",
    "GRADE-10-LATEST-SEPTEMBER-4-2026.xlsx",
)

#: The repository root, where the school drops the workbooks.  This module
#: lives at ``backend/aegis_backend/apps/data_import/management/commands/``,
#: so the root is six levels up.
REPO_ROOT = Path(__file__).resolve().parents[6]

#: Every workbook is uploaded twice, roster first.
DATASETS = ((ImportType.STUDENTS, "roster"), (ImportType.GRADES, "grades"))


class Command(BaseCommand):
    help = (
        "Load the client school's Electronic Class Record workbooks as "
        "Students and Grades import jobs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            dest="email",
            help=(
                "The account that owns the import jobs. "
                "Defaults to the first administrator account."
            ),
        )
        parser.add_argument(
            "--path",
            action="append",
            dest="paths",
            help="A workbook to load. Repeatable. Defaults to the four client workbooks.",
        )

    def handle(self, *args, **options):
        uploader = self._resolve_uploader(options.get("email"))
        workbooks = self._resolve_workbooks(options.get("paths"))

        failures = 0
        for path in workbooks:
            for import_type, label in DATASETS:
                job = self._run_import(uploader, path, import_type)
                status = "OK " if job.error_rows == 0 else "ERR"
                self.stdout.write(
                    f"{status} {path.name} as {label}: status={job.status} "
                    f"rows={job.total_rows} imported={job.processed_rows} "
                    f"errors={job.error_rows}"
                )
                if job.error_rows:
                    failures += 1
                    for record in job.records.filter(status=RecordStatus.ERROR)[:5]:
                        self.stdout.write(
                            f"     row {record.row_number}: {record.error_message}"
                        )

        if failures:
            raise CommandError(
                f"{failures} import(s) reported row errors; see the output above."
            )

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _resolve_uploader(self, email):
        if email:
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                raise CommandError(f"No user with email {email!r}.")
            return user
        admin = User.objects.filter(role=User.Role.ADMIN).order_by("created_at").first()
        if admin is None:
            raise CommandError(
                "No administrator account exists; the import jobs need an "
                "uploader. Create one and pass it with --email."
            )
        return admin

    def _resolve_workbooks(self, paths):
        if paths:
            resolved = [Path(path) for path in paths]
        else:
            resolved = [REPO_ROOT / name for name in CLIENT_WORKBOOKS]
        missing = [path for path in resolved if not path.is_file()]
        if missing:
            raise CommandError(
                "Workbook(s) not found: "
                + ", ".join(str(path) for path in missing)
            )
        return resolved

    # ------------------------------------------------------------------
    # One upload
    # ------------------------------------------------------------------

    def _run_import(self, uploader, path, import_type):
        with open(path, "rb") as handle:
            job = ImportJob.objects.create(
                uploaded_by=uploader,
                file=File(handle, name=path.name),
                file_type=FileType.XLSX,
                import_type=import_type,
                status=JobStatus.PENDING,
            )

        job.status = JobStatus.PROCESSING
        job.save(update_fields=["status", "updated_at"])

        try:
            with open(path, "rb") as handle:
                result = validate_raw_xlsx(
                    handle,
                    path.name,
                    import_type=import_type,
                )
        except XlsxValidationError as exc:
            job.status = JobStatus.FAILED
            job.error_log = [{"code": exc.code, "message": exc.message}]
            job.save(update_fields=["status", "error_log", "completed_at", "updated_at"])
            self.stderr.write(f"{path.name}: the file was rejected: {exc.message}")
            return job

        with transaction.atomic():
            ImportRecord.objects.bulk_create(
                [
                    ImportRecord(
                        job=job,
                        row_number=index,
                        data=row_data,
                        status=RecordStatus.ERROR,
                        error_message="",
                    )
                    for index, row_data in enumerate(result.rows, start=1)
                ]
            )

        if not result.rows:
            # Valid headers but no data rows: the same completed, empty job
            # the upload screen writes.
            job.status = JobStatus.COMPLETED
            job.total_rows = 0
            job.save(update_fields=["status", "total_rows", "updated_at"])
            return job

        records = list(job.records.order_by("row_number"))
        process_records(job, records, result.headers)
        return job
