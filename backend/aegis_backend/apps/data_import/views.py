"""
Data-import view layer (Phase 8.2 / 8.4).

ImportJobViewSet:
- POST   /api/v1/data-import/jobs/        create + synchronously process
- GET    /api/v1/data-import/jobs/        list own jobs
- GET    /api/v1/data-import/jobs/{id}/    retrieve job + per-row records

Only Faculty (grades/attendance) and Admin participate. Creation is
throttled with DataImportRateThrottle and gated by the role-authority
matrix. No raw contents, stack traces, or filesystem paths are exposed.

PH8.4 adds XLSX support: the view detects the actual file type from
content bytes (ZIP magic), not the client-supplied extension alone.
"""

from django.db import transaction
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.throttling import DataImportRateThrottle, ExportRateThrottle

from .constants import (
    ExportErrorCode,
    ExportFormat,
    ExportType,
    FileType,
    ImportErrorCode,
    ImportType,
    JobStatus,
    RecordStatus,
)
from .csv_pipeline import CsvValidationError, validate_raw_csv
from .exports import (
    ExportError,
    build_content_disposition,
    build_export_payload,
    export_queryset_for,
    rows_for_queryset,
    safe_export_filename,
)
from .models import ImportJob, ImportRecord
from .serializers import (
    ImportJobCreateSerializer,
    ImportJobSerializer,
    ImportJobStatusSerializer,
)
from .xlsx_pipeline import XlsxValidationError, validate_raw_xlsx

#: Roles allowed to list/retrieve import jobs.
_ALLOWED_ROLES = frozenset(("admin", "faculty"))

#: ZIP magic bytes used for content-based file type detection.
_ZIP_MAGIC = b"PK\x03\x04"

#: Real domain model each export kind operates on (PH10.9 export audit).
#: Exports have no ExportJob model of their own; the audit points at the
#: actual dataset being exported.  No model name is invented.
EXPORT_DOMAIN_MODELS = {
    ExportType.GRADES: "academics.Grade",
    ExportType.ATTENDANCE: "attendance.AttendanceRecord",
    ExportType.STUDENTS: "accounts.StudentProfile",
}


def _detect_file_type(uploaded_file):
    """
    Detect the actual file type from the first bytes of the uploaded file.

    Uses ZIP magic bytes (``PK\\x03\\x04``) to identify XLSX content
    regardless of the client-supplied extension.  Falls back to CSV
    for non-ZIP content.  The file pointer is always reset to the
    beginning before returning.
    """
    uploaded_file.seek(0)
    head = uploaded_file.read(4)
    uploaded_file.seek(0)
    if head == _ZIP_MAGIC:
        return FileType.XLSX
    return FileType.CSV


class ImportJobViewSet(viewsets.ModelViewSet):
    """Create, list, and retrieve import jobs with per-row results."""

    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return ImportJobCreateSerializer
        if self.action == "list":
            return ImportJobStatusSerializer
        return ImportJobSerializer

    def get_throttles(self):
        if self.action == "create":
            return [DataImportRateThrottle()]
        return []

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = ImportJob.objects.select_related("uploaded_by").prefetch_related("records")
        if self.action == "retrieve" and user.role == "faculty":
            # Faculty may only retrieve their own jobs.
            return qs.filter(uploaded_by=user)
        if user.role in _ALLOWED_ROLES:
            return qs
        return ImportJob.objects.none()

    def list(self, request, *args, **kwargs):
        if request.user.role not in _ALLOWED_ROLES:
            return Response(
                {"detail": "You do not have permission to view import jobs."},
                status=status.HTTP_403_FORBIDDEN,
            )
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        if request.user.role not in _ALLOWED_ROLES:
            return Response(
                {"detail": "You do not have permission to view import jobs."},
                status=status.HTTP_403_FORBIDDEN,
            )
        job = self.get_object()
        if request.user.role == "faculty" and job.uploaded_by_id != request.user.pk:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(job)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        import_type = serializer.validated_data["import_type"]

        # Detect actual file type from content bytes, not the extension.
        file_type = _detect_file_type(uploaded_file)

        job = ImportJob.objects.create(
            uploaded_by=request.user,
            file=uploaded_file,
            file_type=file_type,
            import_type=import_type,
            status=JobStatus.PENDING,
        )

        try:
            self._run_job(job, uploaded_file, file_type)
        except Exception:
            # Never leak internal state to the client.
            job.status = JobStatus.FAILED
            if not job.error_log:
                job.error_log = [
                    {"code": ImportErrorCode.INTERNAL_PIPELINE_ERROR, "message": "The import could not be processed."}
                ]
            job.save()
            # Re-raise so the framework returns a generic 500 envelope.
            raise

        # PH10.9: audit exactly ONE IMPORT event, only once the import
        # genuinely completed.  FAILED/PARTIAL jobs are not audited as
        # successful; the hook is fire-and-forget (PH10.7 principle).
        if job.status == JobStatus.COMPLETED:
            from apps.audit.import_export_hooks import audit_successful_import

            audit_successful_import(job)

        out = ImportJobSerializer(job, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    def _run_job(self, job, uploaded_file, file_type):
        """Synchronous pipeline for a pending job (CSV or XLSX)."""
        from .csv_pipeline import safe_filename

        filename = safe_filename(getattr(uploaded_file, "name", ""))
        job.status = JobStatus.PROCESSING
        job.save()

        try:
            if file_type == FileType.XLSX:
                result = validate_raw_xlsx(uploaded_file, filename)
            else:
                result = validate_raw_csv(uploaded_file, filename)
        except (CsvValidationError, XlsxValidationError) as exc:
            job.status = JobStatus.FAILED
            job.error_log = [{"code": exc.code, "message": exc.message}]
            job.save()
            return

        rows = result.rows
        if not rows:
            # Valid headers but no data rows: treat as a completed, empty job.
            job.status = JobStatus.COMPLETED
            job.total_rows = 0
            job.processed_rows = 0
            job.error_rows = 0
            job.save()
            return

        # Persist an ImportRecord per parsed row.  Statuses are provisional
        # here; the domain importer classifies each row and may rewrite them.
        records = [
            ImportRecord(
                job=job,
                row_number=index,
                data=row_data,
                status=RecordStatus.ERROR,
                error_message="",
            )
            for index, row_data in enumerate(rows, start=1)
        ]
        with transaction.atomic():
            ImportRecord.objects.bulk_create(records)

        # Re-read persisted records (ordered) so mapped_to_id/mapped_to_model
        # updates are applied to real rows.
        records = list(job.records.order_by("row_number"))

        self._dispatch_domain_processing(job, records, result.headers)

    def _dispatch_domain_processing(self, job, records, headers):
        """
        Route parsed rows to the matching domain importer.

        grades / attendance / students write real records via their
        importers.  guidance_records has no domain importer yet; for that
        type alone we preserve the legacy parse-only behavior so existing
        admin imports still complete.
        """
        from .importers.attendance import AttendanceImporter
        from .importers.grades import GradeImporter
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

        # Legacy parse-only path for not-yet-implemented domain types.
        for record in records:
            record.status = RecordStatus.SUCCESS
            record.error_message = ""
            record.save()
        job.total_rows = len(records)
        job.processed_rows = len(records)
        job.error_rows = 0
        job.status = JobStatus.COMPLETED
        job.save()


# ---------------------------------------------------------------------------
# Controlled exports (Phase 8.8)
# ---------------------------------------------------------------------------
#
# GET /api/v1/data-import/exports/grades/      ?file_format=csv|xlsx
# GET /api/v1/data-import/exports/attendance/  ?file_format=csv|xlsx
# GET /api/v1/data-import/exports/students/    ?file_format=csv|xlsx  [admin]
#
# All exports operate on server-authorized querysets built by
# ``export_queryset_for``.  No unrestricted fetching; no generic
# export-everything endpoint; no arbitrary column selection.  Supported
# formats are CSV and XLSX only.


class ExportViewMixin(APIView):
    """Shared controlled-export response handling."""

    export_type = None

    permission_classes = [IsAuthenticated]
    throttle_classes = [ExportRateThrottle]

    def _param(self, name, default=None):
        return self.request.query_params.get(name, default)

    def get(self, request, *args, **kwargs):
        file_format = (self._param("file_format") or "").lower()
        if file_format not in ExportFormat.ALL:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": ExportErrorCode.UNSUPPORTED_FORMAT,
                        "message": "Unsupported file format. Use 'csv' or 'xlsx'.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            qs = export_queryset_for(self.export_type, request.user)
        except ExportError as exc:
            return self._export_error(exc)
        except Exception:
            # Never leak internals.
            return self._export_error(
                ExportError(
                    ExportErrorCode.INTERNAL_EXPORT_ERROR,
                    "The export could not be generated.",
                )
            )

        try:
            rows = rows_for_queryset(self.export_type, qs)
        except ExportError as exc:
            return self._export_error(exc)
        except Exception:
            # Never leak internals on materialization failure either.
            return self._export_error(
                ExportError(
                    ExportErrorCode.INTERNAL_EXPORT_ERROR,
                    "The export could not be generated.",
                )
            )
        try:
            payload = build_export_payload(self.export_type, rows, file_format)
        except ExportError as exc:
            return self._export_error(exc)
        except Exception:
            return self._export_error(
                ExportError(
                    ExportErrorCode.INTERNAL_EXPORT_ERROR,
                    "The export could not be generated.",
                )
            )

        filename = safe_export_filename(self.export_type, file_format)
        content_type = (
            "text/csv; charset=utf-8"
            if file_format == ExportFormat.CSV
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response = HttpResponse(payload, content_type=content_type)
        response["Content-Disposition"] = build_content_disposition(filename)

        # PH10.9: audit exactly ONE EXPORT event only after the export
        # payload was generated successfully.  The event references the
        # REAL domain model of the exported dataset (exports have no job
        # model); the hook is fire-and-forget (PH10.7 principle) so a
        # failed audit write never changes the outcome.
        from apps.audit.import_export_hooks import audit_successful_export

        audit_successful_export(EXPORT_DOMAIN_MODELS[self.export_type])

        return response

    def _export_error(self, exc):
        return Response(
            {
                "success": False,
                "error": {"code": exc.code, "message": exc.message},
            },
            status=self._error_status(exc.code),
        )

    @staticmethod
    def _error_status(code):
        if code in (ExportErrorCode.PERMISSION_DENIED,):
            return status.HTTP_403_FORBIDDEN
        if code == ExportErrorCode.EXPORT_TOO_LARGE:
            return status.HTTP_400_BAD_REQUEST
        if code == ExportErrorCode.INTERNAL_EXPORT_ERROR:
            return status.HTTP_500_INTERNAL_SERVER_ERROR
        return status.HTTP_400_BAD_REQUEST


class GradesExportView(ExportViewMixin):
    """GET /api/v1/data-import/exports/grades/"""

    export_type = ExportType.GRADES


class AttendanceExportView(ExportViewMixin):
    """GET /api/v1/data-import/exports/attendance/"""

    export_type = ExportType.ATTENDANCE


class StudentsExportView(ExportViewMixin):
    """GET /api/v1/data-import/exports/students/ (admin only)"""

    export_type = ExportType.STUDENTS
