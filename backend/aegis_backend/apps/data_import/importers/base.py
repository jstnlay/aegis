"""
Shared import-processing plumbing (Phase 8.5 / 8.6).

Both the grade and attendance importers share the same row-outcome
mechanics:

- header validation (required + unknown column policy)
- deterministic, safe per-row error messages
- in-file duplicate detection (prevents self-duplicates in one upload)
- accurate counter recomputation from the actual ImportRecord statuses

No domain business rules live here; importers express domain validation
through the existing models/serializers and only classify each row's
outcome.  All outward error messages are hand-picked and never contain
SQL, tracebacks, filesystem paths, or internal object reprs.
"""

from ..constants import ImportErrorCode, JobStatus, RecordStatus


class RowError(Exception):
    """A single validated row failed; carry a code + safe message.

    The message is always a human-written, stable string (no internals).
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


#: Required columns for grade imports.
GRADE_REQUIRED_COLUMNS = ("student_id", "subject_assignment", "grading_period", "score")

#: Optional columns for grade imports.
GRADE_OPTIONAL_COLUMNS = ("letter_grade", "remarks")

#: Required columns for attendance imports.
ATTENDANCE_REQUIRED_COLUMNS = ("student_id", "section", "date", "status")

#: Columns that are explicitly forbidden in attendance imports (attribution
#: is server-controlled; a client-supplied value would be forgery).
ATTENDANCE_FORBIDDEN_COLUMNS = ("recorded_by",)

GRADE_ALLOWED_COLUMNS = frozenset(GRADE_REQUIRED_COLUMNS + GRADE_OPTIONAL_COLUMNS)
ATTENDANCE_ALLOWED_COLUMNS = frozenset(ATTENDANCE_REQUIRED_COLUMNS)

# ---------------------------------------------------------------------------
# PH8.7 — Student master-data import schema.
#
# The import file is the official student list, NOT a credential container:
# password / role / identity-owner columns are never accepted.  LRN and
# middle_name are not part of the current StudentProfile/User models or the
# approved specification, so they are rejected as unknown columns rather
# than silently inventing new requirements.
# ---------------------------------------------------------------------------

#: Required columns for student imports.
STUDENT_REQUIRED_COLUMNS = (
    "student_id",
    "first_name",
    "last_name",
    "email",
    "grade_level",
    "section",
)

#: Optional columns for student imports.
STUDENT_OPTIONAL_COLUMNS = (
    "academic_year",
    "date_of_birth",
    "guardian_contact",
    "enrollment_date",
)

#: Password-related columns are rejected outright: a student file must never
#: carry plaintext credentials (or anything pretending to be one).
STUDENT_FORBIDDEN_PASSWORD_COLUMNS = frozenset(
    {
        "password",
        "default_password",
        "temp_password",
        "temporary_password",
        "password1",
        "password2",
        "passwd",
    }
)

#: Role columns are rejected outright: the imported account role is always
#: server-controlled (student).
STUDENT_FORBIDDEN_COLUMNS = frozenset({"role"})

STUDENT_ALLOWED_COLUMNS = frozenset(STUDENT_REQUIRED_COLUMNS + STUDENT_OPTIONAL_COLUMNS)


def validate_headers(headers, *, required, allowed=None, forbidden=()):
    """
    Validate the parsed header row against a documented import schema.

    Returns ``None`` on success, or a ``RowError`` describing the first
    problem.  ``required`` columns must all be present; ``allowed`` is the
    full acceptable set (unknown columns are rejected); ``forbidden``
    columns trigger an explicit rejection even if ``allowed`` is None.
    """
    missing = [c for c in required if c not in headers]
    if missing:
        return RowError(
            ImportErrorCode.MISSING_REQUIRED_COLUMN,
            "Missing required column(s): " + ", ".join(sorted(missing)),
        )

    if allowed is not None:
        unknown = [c for c in headers if c not in allowed]
        if unknown:
            return RowError(
                ImportErrorCode.UNKNOWN_COLUMN,
                "Unknown column(s) not supported by this import: "
                + ", ".join(sorted(unknown)),
            )

    for col in forbidden:
        if col in headers:
            return RowError(
                ImportErrorCode.UNKNOWN_COLUMN,
                f"Column {col!r} is not accepted and must be removed.",
            )

    return None


def column_value(row, name):
    """Return a trimmed, whitespace-collapsed value for a row column."""
    value = row.get(name, "")
    if value is None:
        return ""
    return str(value).strip()


class InFileDuplicateTracker:
    """Detect duplicate logical keys within a single uploaded file.

    Grade rows are keyed by (student_id, subject_assignment,
    grading_period); attendance rows by (student_id, date).  The second
    occurrence is rejected so an upload cannot silently create duplicates.
    """

    def __init__(self):
        self._seen = set()

    def is_dup(self, key):
        return key in self._seen

    def mark(self, key):
        self._seen.add(key)


def recompute_job_counters(job, records):
    """
    Set job counters exactly from the actual ImportRecord statuses and
    derive the terminal job status.

    ``records`` must already be saved/persisted so ``status`` is the real
    outcome.  A row only counts as processed (SUCCESS) after its database
    write succeeded (the importer guarantees this ordering).
    """
    total = len(records)
    processed = sum(1 for r in records if r.status == RecordStatus.SUCCESS)
    errors = sum(1 for r in records if r.status == RecordStatus.ERROR)

    job.total_rows = total
    job.processed_rows = processed
    job.error_rows = errors

    if processed == total and total > 0:
        job.status = JobStatus.COMPLETED
    elif processed > 0:
        job.status = JobStatus.PARTIAL
    else:
        job.status = JobStatus.FAILED
    job.save()
