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

from ..constants import ImportErrorCode, ImportType, JobStatus, RecordStatus


class RowError(Exception):
    """A single validated row failed; carry a code + safe message.

    The message is always a human-written, stable string (no internals).
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


#: Columns always required in a grade import.  A row names its subject
#: assignment either by UUID (``subject_assignment``) or by the school's own
#: keys (``section`` + ``subject_code``); see ``GradeImporter``.
GRADE_REQUIRED_COLUMNS = ("student_id", "grading_period", "score")

#: Optional columns for grade imports.
GRADE_OPTIONAL_COLUMNS = (
    "subject_assignment",
    "section",
    "subject_code",
    "letter_grade",
    "remarks",
)

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

# ---------------------------------------------------------------------------
# PH11 — Guidance-records import schema.
#
# The file carries counseling session records only.  Attribution is
# server-controlled exactly like attendance's ``recorded_by``: a client-
# supplied counselor column would let an upload forge who ran a session.
# ``session_notes`` is required because an empty consultation record has no
# content to import.
# ---------------------------------------------------------------------------

#: Required columns for guidance-records imports.
GUIDANCE_REQUIRED_COLUMNS = (
    "student_id",
    "session_date",
    "session_time",
    "session_type",
    "concern_categories",
    "session_notes",
    "priority_level",
)

#: Optional columns for guidance-records imports.
GUIDANCE_OPTIONAL_COLUMNS = (
    "recommendations",
    "next_session_date",
    "status",
)

#: Attribution is server-controlled (same rule as attendance's recorded_by).
GUIDANCE_FORBIDDEN_COLUMNS = ("counselor", "recorded_by")

GUIDANCE_ALLOWED_COLUMNS = frozenset(
    GUIDANCE_REQUIRED_COLUMNS + GUIDANCE_OPTIONAL_COLUMNS
)


# ---------------------------------------------------------------------------
# Import templates (PH11)
#
# Served by GET /data-import/templates/{import_type}/.  The UI renders this
# table and generates the downloadable CSV header from it, so the file a
# tester downloads is validated against exactly the schema the importer
# enforces — there is no second copy of the header row to drift.
#
# A template ships headers only.  It deliberately contains no example row:
# an invented student_id or score would either be written to the database as
# a record that never happened, or fail validation and teach the tester the
# wrong thing.  The tester supplies real values.
# ---------------------------------------------------------------------------

#: column name -> (required?, hint shown to the tester).
_TEMPLATES: dict[str, dict[str, tuple[bool, str]]] = {
    ImportType.GRADES: {
        "student_id": (True, "Student's school code, as shown in the Students export."),
        "grading_period": (True, "Grading period name, e.g. Term 2 (or its UUID)."),
        "score": (True, "Numeric score from 0 to 100."),
        "subject_assignment": (
            False,
            "Subject assignment UUID. Use this, or give section + subject_code.",
        ),
        "section": (
            False,
            "Section name, e.g. Grade 8 - Bonifacio (or its UUID). "
            "Required when subject_assignment is not given.",
        ),
        "subject_code": (
            False,
            "Subject code, e.g. ENG. Required when subject_assignment is not given.",
        ),
        "letter_grade": (False, "Optional letter grade."),
        "remarks": (False, "Optional remarks."),
    },
    ImportType.ATTENDANCE: {
        "student_id": (True, "Student's school code, as shown in the Students export."),
        "section": (True, "Section name, e.g. Grade 8 - Bonifacio (or its UUID)."),
        "date": (True, "Attendance date, YYYY-MM-DD. Cannot be in the future."),
        "status": (True, "One of: present, late, absent."),
    },
    ImportType.STUDENTS: {
        "student_id": (True, "Unique student school code."),
        "first_name": (True, "Student's first name."),
        "last_name": (True, "Student's last name."),
        "email": (True, "Unique email address. Duplicates are rejected."),
        "grade_level": (True, "Grade level, e.g. 7."),
        "section": (True, "Section name, e.g. Bonifacio."),
        "academic_year": (False, "Academic year label, e.g. 2026-2027."),
        "date_of_birth": (False, "YYYY-MM-DD."),
        "guardian_contact": (False, "Guardian contact number."),
        "enrollment_date": (False, "YYYY-MM-DD."),
    },
    ImportType.GUIDANCE_RECORDS: {
        "student_id": (True, "Student's school code, as shown in the Students export."),
        "session_date": (True, "Session date, YYYY-MM-DD. Cannot be in the future."),
        "session_time": (True, "Session time, 24-hour HH:MM."),
        "session_type": (
            True,
            "One of: individual_counseling, group, parent_conference, follow_up.",
        ),
        "concern_categories": (
            True,
            "Pipe-separated categories: academic|behavioral|emotional|family|bullying|other.",
        ),
        "session_notes": (True, "Session notes. Cannot be empty."),
        "priority_level": (True, "One of: high, medium, low."),
        "recommendations": (False, "Optional recommendations."),
        "next_session_date": (False, "Optional next session date, YYYY-MM-DD."),
        "status": (False, "One of: ongoing, completed, follow_up. Defaults to ongoing."),
    },
}

#: Server-controlled columns that are never accepted in an uploaded file.
TEMPLATE_FORBIDDEN_COLUMNS: dict[str, tuple[str, ...]] = {
    ImportType.GRADES: (),
    ImportType.ATTENDANCE: ATTENDANCE_FORBIDDEN_COLUMNS,
    ImportType.STUDENTS: tuple(
        sorted(STUDENT_FORBIDDEN_COLUMNS | STUDENT_FORBIDDEN_PASSWORD_COLUMNS)
    ),
    ImportType.GUIDANCE_RECORDS: GUIDANCE_FORBIDDEN_COLUMNS,
}


def template_columns(import_type):
    """Return the ordered ``[{"name", "required", "hint"}, ...]`` template."""
    return [
        {"name": name, "required": required, "hint": hint}
        for name, (required, hint) in _TEMPLATES[import_type].items()
    ]


def template_header(import_type):
    """Return the exact header row the downloadable CSV starts with."""
    return [name for name, (required, _) in _TEMPLATES[import_type].items() if required] + [
        name for name, (required, _) in _TEMPLATES[import_type].items() if not required
    ]


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


def memo(cache, key, produce):
    """
    Compute a value once per import job.

    A class sheet repeats the same student, section, subject and term on many
    rows.  Re-resolving one of those per row costs a query per row for no
    benefit, so importers pass a per-job dict here.  Failures are not cached:
    ``produce`` raises before anything is stored.
    """
    if key not in cache:
        cache[key] = produce()
    return cache[key]


class InFileDuplicateTracker:
    """Detect duplicate logical keys within a single uploaded file.

    Grade rows are keyed by the resolved (student, subject assignment,
    grading period); attendance rows by (student_id, date); guidance rows by
    (student_id, session_date, session_time).  The second occurrence is
    rejected so an upload cannot silently overwrite the row it just wrote.
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
