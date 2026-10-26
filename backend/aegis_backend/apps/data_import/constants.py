"""
Import foundation constants (Phase 8).

Authoritative, single-source definitions for the data-import surface:
file types, import types, job/record statuses, role-import permissions,
upload limits, and security-error codes.

Locked design decisions:
- Excel support is XLSX-only (confirmed with project owner). Legacy
  binary ``.xls`` files are rejected. ``openpyxl`` is the ONLY Excel
  library in use.
- Uploaded files are untrusted input; size and format are validated
  before any parsing.
- V1 adds no task queue (no Celery/Redis): a small file finishes in the
  upload request, a larger one in the in-process worker pool. See spec
  G.8 / ASM-04.
"""

from pathlib import Path


# ---------------------------------------------------------------------------
# File types
# ---------------------------------------------------------------------------


class FileType:
    """Supported structured import file formats."""

    CSV = "csv"
    XLSX = "xlsx"

    CHOICES = ((CSV, "CSV"), (XLSX, "XLSX"))

    # XLSX-ONLY decision: legacy binary .xls is intentionally unsupported.
    ALL = frozenset((CSV, XLSX))


#: Canonical file extensions for uploaded import files (lowercase).
ALLOWED_EXTENSIONS = frozenset({".csv", ".xlsx"})


# ---------------------------------------------------------------------------
# Import types
# ---------------------------------------------------------------------------


class ImportType:
    """Structured import categories supported by the approved scope."""

    GRADES = "grades"
    ATTENDANCE = "attendance"
    STUDENTS = "students"
    GUIDANCE_RECORDS = "guidance_records"

    CHOICES = (
        (GRADES, "Grades"),
        (ATTENDANCE, "Attendance"),
        (STUDENTS, "Students"),
        (GUIDANCE_RECORDS, "Guidance Records"),
    )


# ---------------------------------------------------------------------------
# Import job / record statuses  (spec §E.7)
# ---------------------------------------------------------------------------


class JobStatus:
    """ImportJob lifecycle statuses."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"

    CHOICES = (
        (PENDING, "Pending"),
        (PROCESSING, "Processing"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
        (PARTIAL, "Partial"),
    )


class RecordStatus:
    """ImportRecord per-row result statuses."""

    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"

    CHOICES = (
        (SUCCESS, "Success"),
        (ERROR, "Error"),
        (SKIPPED, "Skipped"),
    )


# ---------------------------------------------------------------------------
# Role authority matrix (approved: FR-012, FR-013, FR-037)
# ---------------------------------------------------------------------------
#
#   role      | grades      | attendance  | students  | guidance_records
#   ----------+-------------+-------------+-----------+-----------------
#   faculty   | own subjects| advisory    | —         | —
#   admin     | ✓           | ✓           | ✓         | ✓
#
# Faculty authority is data-scoped (their own subject assignments /
# advisory sections), enforced per import type at validation time.


#: Import types only admins may submit.
ADMIN_ONLY_IMPORT_TYPES = frozenset({ImportType.STUDENTS, ImportType.GUIDANCE_RECORDS})

#: Import types an authenticated user may submit *before* data-scope checks.
ALL_FACULTY_IMPORT_TYPES = frozenset({ImportType.GRADES, ImportType.ATTENDANCE})
ALL_ADMIN_IMPORT_TYPES = frozenset(
    {ImportType.GRADES, ImportType.ATTENDANCE, ImportType.STUDENTS, ImportType.GUIDANCE_RECORDS}
)


# ---------------------------------------------------------------------------
# Upload limits
# ---------------------------------------------------------------------------
#
# First-line rejection happens at the server/body level
# (DATA_UPLOAD_MAX_MEMORY_SIZE in settings). Per-file enforcement during
# validation uses MAX_IMPORT_FILE_SIZE below.

#: Maximum accepted import file size in bytes (10 MB).
MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024

#: Maximum total rows accepted per import job. Sized for a real school file
#: (a whole school's attendance for a month, or its grades for a term); the
#: file-size cap above still applies.
MAX_IMPORT_ROWS = 20000

#: Rows a request processes before handing the rest to a worker thread.
#: At or below this, the POST response already carries the finished job, which
#: keeps small uploads instant. Above it the request would outlive the
#: platform's HTTP timeout, so the job is queued and the client polls for it:
#: a 5,000-row file takes about a minute, and no request stays open that long.
IMPORT_SYNC_ROW_LIMIT = 200

# CSV-specific safe defaults (vs. Excel coercion surprises).
CSV_MAX_COLUMNS = 60

# XLSX-specific safe defaults.
#: Visible worksheets allowed when the request does NOT name one. A request
#: may name a worksheet instead (``sheet`` form field), which picks it
#: explicitly; sheets are still never merged or guessed at.
XLSX_MAX_WORKSHEETS = 1
XLSX_MAX_COLUMNS = 256


# ---------------------------------------------------------------------------
# Import error codes
# ---------------------------------------------------------------------------
#
# Stable machine-readable codes shared by the pipeline, per-row error
# messages, and the public API. No raw exception text or file contents
# are ever echoed back to clients.

class ImportErrorCode:
    INVALID_FILE_EXTENSION = "INVALID_FILE_EXTENSION"
    INVALID_FILE_CONTENT = "INVALID_FILE_CONTENT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_EMPTY = "FILE_EMPTY"
    UNSUPPORTED_IMPORT_TYPE = "UNSUPPORTED_IMPORT_TYPE"
    UNEXPECTED_CSV_QUOTING = "UNEXPECTED_CSV_QUOTING"
    BAD_COLUMN_COUNT = "BAD_COLUMN_COUNT"
    MALFORMED_HEADER = "MALFORMED_HEADER"
    MISSING_REQUIRED_COLUMN = "MISSING_REQUIRED_COLUMN"
    UNKNOWN_COLUMN = "UNKNOWN_COLUMN"
    DATA_SCOPE_DENIED = "DATA_SCOPE_DENIED"
    DUPLICATE_ROW = "DUPLICATE_ROW"
    DUPLICATE_ENTITY = "DUPLICATE_ENTITY"
    ROW_NOT_PROCESSED = "ROW_NOT_PROCESSED"
    JOB_INVALID_STATE = "JOB_INVALID_STATE"
    INTERNAL_PIPELINE_ERROR = "INTERNAL_PIPELINE_ERROR"
    # XLSX-specific error codes
    INVALID_WORKBOOK = "INVALID_WORKBOOK"
    MULTIPLE_WORKSHEETS = "MULTIPLE_WORKSHEETS"
    WORKSHEET_NOT_FOUND = "WORKSHEET_NOT_FOUND"
    EMPTY_WORKSHEET = "EMPTY_WORKSHEET"
    #: A row matched a ``finalized`` grade. Finalized grades are locked: the
    #: importer never overwrites a locked academic record.
    FINALIZED_GRADE_LOCKED = "FINALIZED_GRADE_LOCKED"
    # Domain-level (PH8.5 grade / PH8.6 attendance) row error codes
    INVALID_STUDENT = "INVALID_STUDENT"
    INVALID_ENROLLMENT = "INVALID_ENROLLMENT"
    INACTIVE_ENROLLMENT = "INACTIVE_ENROLLMENT"
    INVALID_SUBJECT_ASSIGNMENT = "INVALID_SUBJECT_ASSIGNMENT"
    INVALID_GRADING_PERIOD = "INVALID_GRADING_PERIOD"
    INVALID_GRADE_VALUE = "INVALID_GRADE_VALUE"
    ACADEMIC_YEAR_MISMATCH = "ACADEMIC_YEAR_MISMATCH"
    FACULTY_SCOPE_DENIED = "FACULTY_SCOPE_DENIED"
    INVALID_ACADEMIC_YEAR = "INVALID_ACADEMIC_YEAR"
    INVALID_SECTION = "INVALID_SECTION"
    INVALID_ATTENDANCE_DATE = "INVALID_ATTENDANCE_DATE"
    INVALID_ATTENDANCE_STATUS = "INVALID_ATTENDANCE_STATUS"
    # PH8.7 student import / account-provisioning row error codes
    INVALID_STUDENT_ID = "INVALID_STUDENT_ID"
    DUPLICATE_STUDENT_ID = "DUPLICATE_STUDENT_ID"
    INVALID_EMAIL = "INVALID_EMAIL"
    DUPLICATE_EMAIL = "DUPLICATE_EMAIL"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    INVALID_GRADE_LEVEL = "INVALID_GRADE_LEVEL"
    INVALID_DATE = "INVALID_DATE"
    INVALID_ENROLLMENT_DATE = "INVALID_ENROLLMENT_DATE"
    DUPLICATE_ENROLLMENT = "DUPLICATE_ENROLLMENT"
    ACCOUNT_CONFLICT = "ACCOUNT_CONFLICT"
    FORBIDDEN_COLUMN = "FORBIDDEN_COLUMN"
    PASSWORD_FIELD_FORBIDDEN = "PASSWORD_FIELD_FORBIDDEN"
    PROVISIONING_FAILED = "PROVISIONING_FAILED"
    # PH11 guidance-records import row error codes
    INVALID_SESSION_TYPE = "INVALID_SESSION_TYPE"
    INVALID_SESSION_TIME = "INVALID_SESSION_TIME"
    INVALID_SESSION_DATE = "INVALID_SESSION_DATE"
    INVALID_CONCERN_CATEGORY = "INVALID_CONCERN_CATEGORY"
    INVALID_PRIORITY_LEVEL = "INVALID_PRIORITY_LEVEL"
    INVALID_SESSION_STATUS = "INVALID_SESSION_STATUS"
    INVALID_CONCERN_LIST = "INVALID_CONCERN_LIST"
    NO_COUNSELOR = "NO_COUNSELOR"


# ---------------------------------------------------------------------------
# Endpoint layout (spec §H.1)
# ---------------------------------------------------------------------------
#
#   /api/v1/data-import/jobs/          GET, POST (Faculty + Admin)
#   /api/v1/data-import/jobs/{id}/     GET
#   Import type: grades | attendance | students (+ guidance_records admin)
#


def max_file_size_display():
    """Human-readable max upload size for docs/errors."""
    return f"{MAX_IMPORT_FILE_SIZE // (1024 * 1024)} MB"


def sanitized_filename(filename):
    """
    Return only the basename + lowercase extension for an uploaded file.

    Used for logging/storage metadata so that client-supplied path
    components never reach the filesystem or logs.
    """
    name = Path(filename or "").name
    return name[:255] if name else ""


# ---------------------------------------------------------------------------
# Controlled export constants (Phase 8.8)
# ---------------------------------------------------------------------------
#
# Export kinds supported by the controlled-export surface.  The
# administrator authority list is grades, attendance, students, and (PH12 /
# TC-ADM-05) guidance_records.  Students is admin-only by default.  There is
# no consent model in the codebase; consent handling is explicitly excluded
# from PH8.8 (the reimport variant carries identity columns — see exports.py).


class ExportType:
    """Authorized export kinds."""

    GRADES = "grades"
    ATTENDANCE = "attendance"
    STUDENTS = "students"
    # FR-016 / TC-FAC-20: the advisory class summary is a per-student
    # aggregate over a faculty member's own class, not a table dump. It is
    # deliberately outside `ALL`: that set is the administrator authority
    # list, and "advisory class" has no meaning outside a faculty profile.
    ADVISORY = "advisory"
    # FR-032 / TC-GUI-09: an individual student guidance report. Like
    # ADVISORY this is one subject rather than a table of many, and it is
    # outside `ALL` for the same reason - `ALL` is the administrator authority
    # list, and this export is scoped to a guidance counselor's own student.
    GUIDANCE_REPORT = "guidance_report"
    # PH12 / TC-ADM-05: the round-trip guidance-records file. Like the
    # guidance-records import itself (ADMIN_ONLY_IMPORT_TYPES) this is an
    # administrator authority surface, so it lives inside `ALL`.
    GUIDANCE_RECORDS = "guidance_records"

    CHOICES = (
        (GRADES, "Grades"),
        (ATTENDANCE, "Attendance"),
        (STUDENTS, "Students"),
        (ADVISORY, "Advisory class summary"),
        (GUIDANCE_REPORT, "Student guidance report"),
        (GUIDANCE_RECORDS, "Guidance records"),
    )

    ALL = frozenset((GRADES, ATTENDANCE, STUDENTS, GUIDANCE_RECORDS))


class ExportFormat:
    """Supported controlled-export file formats."""

    CSV = "csv"
    XLSX = "xlsx"

    CHOICES = ((CSV, "CSV"), (XLSX, "XLSX"))
    ALL = frozenset((CSV, XLSX))


#: Maximum rows returned in a single controlled export (defense-in-depth).
MAX_EXPORT_ROWS = 5000

#: Canonical file extensions for controlled exports (lowercase).
EXPORT_EXTENSIONS = frozenset({".csv", ".xlsx"})


# ---------------------------------------------------------------------------
# Export role authority matrix (PH8.8)
# ---------------------------------------------------------------------------
#
#   role      | grades export | attendance export | students export | advisory
#   ----------+---------------+---------------+----------------+----------
#   faculty   | own subjects  | advisory/assigned | —              | own class
#   admin     | ✓             | ✓                 | ✓              | —
#   guidance  | read-only*    | read-only*        | —              | —
#   student   | own rows      | own rows          | —              | —
#   parent    | linked child  | linked child      | —              | —
#
# *Guidance scope matches existing guidance read behavior.
# Students export is admin-only. The advisory export is faculty-only: it is
# an aggregate of exactly one class, and nobody else's class exists.

ADMIN_ONLY_EXPORT_TYPES = frozenset({ExportType.STUDENTS})
ALL_ADMIN_EXPORT_TYPES = frozenset(ExportType.ALL)
ALL_FACULTY_EXPORT_TYPES = frozenset(
    {ExportType.GRADES, ExportType.ATTENDANCE, ExportType.ADVISORY}
)


# ---------------------------------------------------------------------------
# Export error codes (PH8.8)
# ---------------------------------------------------------------------------


class ExportErrorCode:
    """Stable machine-readable codes for controlled-export errors."""

    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    UNSUPPORTED_EXPORT_TYPE = "UNSUPPORTED_EXPORT_TYPE"
    EXPORT_TOO_LARGE = "EXPORT_TOO_LARGE"
    EXPORT_EMPTY = "EXPORT_EMPTY"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INTERNAL_EXPORT_ERROR = "INTERNAL_EXPORT_ERROR"


# ---------------------------------------------------------------------------
# Export endpoint layout (PH8.8)
# ---------------------------------------------------------------------------
#
#   /api/v1/data-import/exports/grades/      GET (?file_format=csv|xlsx)
#   /api/v1/data-import/exports/attendance/  GET (?file_format=csv|xlsx)
#   /api/v1/data-import/exports/students/    GET (?file_format=csv|xlsx) [admin]