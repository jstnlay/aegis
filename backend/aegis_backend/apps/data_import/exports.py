"""
Controlled export service (Phase 8.8; FR-016 advisory kind added with
TC-FAC-20).

Builds server-authorized, role-scoped querysets for the authorized export
kinds (grades / attendance / students, plus the faculty-only advisory class
summary) and renders them to CSV or XLSX.  Exports always operate on
server-authorized querysets — never fetch unrestricted rows and filter
afterward.

Design lock-ins:
- Students export is admin-only and anonymized by default (no email, DOB,
  guardian contact, password, hash, or temporary credentials).
- Supported formats are CSV and XLSX only (no PDF, no .xls).
- Fixed column maps.  No arbitrary column selection, no generic
  export-everything endpoint.
- Deterministic ordering so identical DB state yields identical output.
- CSV injection neutralization on leading ``=`` ``+`` ``-`` ``@``.
- Safe, sanitized filenames; no CRLF/header injection.
"""

import csv
import io
import re
from urllib.parse import quote

from apps.academics.models import Grade
from apps.attendance.models import AttendanceRecord

from .constants import ExportErrorCode, ExportFormat, ExportType, MAX_EXPORT_ROWS

# ---------------------------------------------------------------------------
# CSV injection / filename sanitization
# ---------------------------------------------------------------------------

_CSV_FORMULA_RE = re.compile(r"^[=+\-@\t\r]")

#: Characters never allowed in a generated export filename.
_UNSAFE_FILENAME_RE = re.compile(r"[^\w.\-]")

#: Centralized export column maps, in stable order.
GRADE_EXPORT_COLUMNS = [
    "student_id",
    "student_name",
    "grade_level",
    "section",
    "subject_code",
    "subject_name",
    "grading_period",
    "score",
    "letter_grade",
    "remarks",
    "status",
    "encoded_by",
]

ATTENDANCE_EXPORT_COLUMNS = [
    "student_id",
    "student_name",
    "section",
    "date",
    "status",
    "recorded_by",
]

# Admin-only, anonymized-by-default column set.
STUDENT_EXPORT_COLUMNS = [
    "student_id",
    "student_name",
    "grade_level",
    "section",
    "enrollment_date",
    "is_active",
]

# Faculty-only advisory class summary (FR-016 / TC-FAC-20). One row per
# student in the caller's own class, with that student's attendance counts
# and grade aggregate over the same scope.
ADVISORY_EXPORT_COLUMNS = [
    "student_id",
    "student_name",
    "grade_level",
    "section",
    "attendance_present",
    "attendance_late",
    "attendance_absent",
    "attendance_total",
    "grades_recorded",
    "grade_average",
]

# FR-032 / TC-GUI-09: the guidance report file. One row per reported fact,
# grouped by section, so the export reads as the same document the JSON
# endpoint describes rather than as a table dump of one model.
GUIDANCE_REPORT_COLUMNS = ["section", "item", "detail", "date"]

_COLUMN_MAP = {
    ExportType.GRADES: GRADE_EXPORT_COLUMNS,
    ExportType.ATTENDANCE: ATTENDANCE_EXPORT_COLUMNS,
    ExportType.STUDENTS: STUDENT_EXPORT_COLUMNS,
    ExportType.ADVISORY: ADVISORY_EXPORT_COLUMNS,
    ExportType.GUIDANCE_REPORT: GUIDANCE_REPORT_COLUMNS,
}

# ---------------------------------------------------------------------------
# Round-trip (re-importable) exports (PH12 — TC-ADM-03/04/05, FR-037).
#
# The QA cycle-3 log failed each "import an exported file" row because the
# exporter's human-readable columns are not the importer's schema (e.g. the
# attendance export carries ``recorded_by``/``student_name`` while
# ATTENDANCE_ALLOWED_COLUMNS is the four required columns only).  A round-trip
# export emits exactly the columns the matching importer accepts
# (``importers/base.py``), so the exported file re-imports without edits.
# Server-controlled columns (``recorded_by``, ``counselor``) stay out by the
# same anti-forgery rule the importer enforces.
# ---------------------------------------------------------------------------

#: Grades importer schema: required + optional (see GRADE_ALLOWED_COLUMNS).
GRADE_ROUNDTRIP_COLUMNS = [
    "student_id",
    "grading_period",
    "score",
    "subject_assignment",
    "section",
    "subject_code",
    "letter_grade",
    "remarks",
]

#: Attendance importer schema (see ATTENDANCE_ALLOWED_COLUMNS).
ATTENDANCE_ROUNDTRIP_COLUMNS = ["student_id", "section", "date", "status"]

# Admin round-trip student file: the official student list the importer
# requires, so identity columns (email, first_name, last_name) are present
# here.  This is the "more than anonymized" variant of the design lock-in
# above: it stays admin-only and arrives only through the opt-in
# ``?schema=reimport`` request on the admin-only students export.
# shortcut: no consent gate on identity columns; upgrade when the TC-ADM-17
# explicit-consent decision lands (see constants.py PH8.8 consent note).
STUDENT_ROUNDTRIP_COLUMNS = [
    "student_id",
    "first_name",
    "last_name",
    "email",
    "grade_level",
    "section",
    "enrollment_date",
    "guardian_contact",
    "date_of_birth",
]

#: Guidance-records importer schema (see GUIDANCE_ALLOWED_COLUMNS).
GUIDANCE_ROUNDTRIP_COLUMNS = [
    "student_id",
    "session_date",
    "session_time",
    "session_type",
    "concern_categories",
    "session_notes",
    "priority_level",
    "recommendations",
    "next_session_date",
    "status",
]

_ROUNDTRIP_COLUMN_MAP = {
    ExportType.GRADES: GRADE_ROUNDTRIP_COLUMNS,
    ExportType.ATTENDANCE: ATTENDANCE_ROUNDTRIP_COLUMNS,
    ExportType.STUDENTS: STUDENT_ROUNDTRIP_COLUMNS,
    ExportType.GUIDANCE_RECORDS: GUIDANCE_ROUNDTRIP_COLUMNS,
}


def columns_for(export_type, reimport=False):
    """Look up the render columns for a kind and (optional) round-trip schema."""
    if reimport:
        return _ROUNDTRIP_COLUMN_MAP[export_type]
    return _COLUMN_MAP[export_type]


class ExportError(Exception):
    """Raised when an export cannot be produced (maps to a 4xx/5xx response)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def sanitize_export_cell(value):
    """
    Neutralize leading CSV-injection characters in a single cell.

    Returns the value unchanged unless it begins with ``=`` ``+`` ``-``
    ``@`` tab or CR, in which case a single leading quote is prepended.
    """
    if not value:
        return value
    if _CSV_FORMULA_RE.match(value):
        return "'" + value
    return value


def _format(value):
    """Normalize a raw DB value to a display string (or None)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def safe_export_filename(export_type, file_format, variant=None):
    """
    Build a sanitized, static export filename for the given kind/format.

    ``variant`` (e.g. ``"reimport"``) disambiguates the round-trip schema from
    the default file, so a tester never uploads the wrong-flavor export.
    Filenames are fully server-controlled (no client input), so header/CRLF
    injection is impossible by construction; the sanitizer guards the
    generated name against any stray control characters regardless.
    """
    slug = str(export_type).lower()
    ext = str(file_format).lower()
    base = f"aegis_{slug}_export"
    if variant:
        base = f"{base}_{variant}"
    cleaned = _UNSAFE_FILENAME_RE.sub("_", base).strip("._")
    return f"{cleaned}.{ext}"


def build_content_disposition(filename):
    """
    Build a Content-Disposition header value for a download.

    Uses RFC 5987 ``filename*=`` for safe Unicode transmission and a plain
    ``filename=`` fallback.  A CRLF-free, fully controlled filename makes
    header injection impossible.
    """
    filename = filename.replace('"', "_").replace("\r", "").replace("\n", "")
    encoded = quote(filename)
    return f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded}"


def _profile(user):
    """Return the role-specific profile object for a user, or None."""
    try:
        if user.role == "faculty":
            return user.faculty_profile
        if user.role == "student":
            return user.student_profile
        if user.role == "parent":
            return user.parent_profile
        if user.role == "guidance":
            return user.guidance_profile
    except Exception:
        return None
    return None


def _linked_student_ids(user):
    """Return the set of StudentProfile IDs linked to a parent user."""
    from apps.accounts.models import ParentStudentLink

    try:
        parent_profile = user.parent_profile
    except Exception:
        return set()
    return set(
        ParentStudentLink.objects.filter(parent=parent_profile).values_list(
            "student_id", flat=True
        )
    )


def _faculty_section_ids(faculty_profile):
    """Return section IDs a faculty may access (adviser or assigned subject)."""
    from apps.academics.models import Section

    advised = Section.objects.filter(adviser=faculty_profile).values_list("id", flat=True)
    assigned = faculty_profile.subject_assignments.values_list("section_id", flat=True)
    return set(advised) | set(assigned)


def _ordered_grades(qs):
    return qs.order_by(
        "student__user__last_name",
        "student__user__first_name",
        "grading_period__order",
        "subject_assignment__subject__code",
    )


def _ordered_attendance(qs):
    return qs.order_by(
        "student__user__last_name",
        "student__user__first_name",
        "date",
    )


def _ordered_students(qs):
    return qs.order_by(
        "user__last_name",
        "user__first_name",
        "student_id",
    )


def _grades_queryset_for(user):
    """Build a server-authorized Grade queryset for the given user."""
    qs = Grade.objects.select_related(
        "student__user",
        "student__grade_level",
        "subject_assignment__subject",
        "subject_assignment__section",
        "grading_period",
        "encoded_by__user",
    )
    if user.role == "admin":
        return _ordered_grades(qs)
    if user.role == "guidance":
        # Matches the existing full-read guidance behavior.
        return _ordered_grades(qs)
    if user.role == "faculty":
        fp = _profile(user)
        if fp is None:
            return Grade.objects.none()
        return _ordered_grades(qs.filter(subject_assignment__faculty=fp))
    if user.role == "student":
        sp = _profile(user)
        if sp is None:
            return Grade.objects.none()
        return _ordered_grades(qs.filter(student=sp))
    if user.role == "parent":
        ids = _linked_student_ids(user)
        if not ids:
            return Grade.objects.none()
        return _ordered_grades(qs.filter(student_id__in=ids))
    return Grade.objects.none()


def _attendance_queryset_for(user):
    """Build a server-authorized AttendanceRecord queryset for the given user."""
    qs = AttendanceRecord.objects.select_related(
        "student__user",
        "student__grade_level",
        "section",
        "recorded_by__user",
    )
    if user.role == "admin":
        return _ordered_attendance(qs)
    if user.role == "guidance":
        # Matches the existing full-read guidance behavior.
        return _ordered_attendance(qs)
    if user.role == "faculty":
        fp = _profile(user)
        if fp is None:
            return AttendanceRecord.objects.none()
        section_ids = _faculty_section_ids(fp)
        if not section_ids:
            return AttendanceRecord.objects.none()
        return _ordered_attendance(qs.filter(section_id__in=section_ids))
    if user.role == "student":
        sp = _profile(user)
        if sp is None:
            return AttendanceRecord.objects.none()
        return _ordered_attendance(qs.filter(student=sp))
    if user.role == "parent":
        ids = _linked_student_ids(user)
        if not ids:
            return AttendanceRecord.objects.none()
        return _ordered_attendance(qs.filter(student_id__in=ids))
    return AttendanceRecord.objects.none()


def _student_queryset():
    """Build the admin-only anonymized student export queryset."""
    from apps.accounts.models import StudentProfile

    return _ordered_students(
        StudentProfile.objects.select_related("user", "grade_level", "section")
    )


def _guidance_record_queryset():
    """
    Build the admin-only ConsultationRecord export queryset.

    The guidance-records import (`ImportJobViewSet` limits that import to
    admins, `ADMIN_ONLY_IMPORT_TYPES`) carries counseling sessions, so its
    export is admin-scoped on the same term: a counselor's own sessions stay
    reachable through the guidance report export instead.
    """
    from apps.guidance.models import ConsultationRecord

    return (
        ConsultationRecord.objects.all()
        .select_related("student__user")
        .order_by("session_date", "session_time", "student__student_id")
    )


def _advisory_queryset_for(user):
    """
    Build the faculty-only advisory class summary queryset.

    One annotated row per student in the sections the caller advises or
    teaches — the same scope the faculty roster uses. Every aggregate is
    restricted to that class, so a student who also appears in another
    faculty's section does not contribute their rows here.

    A student with no attendance rows gets real zero counts (the class has
    recorded none); a student with no scored grades gets a blank average,
    never `0.00`, because "no grades recorded" and "an average of zero" are
    different facts.
    """
    from django.db.models import Avg, Count, Q

    from apps.accounts.models import StudentProfile
    from apps.attendance.models import AttendanceRecord

    fp = _profile(user)
    if fp is None:
        return StudentProfile.objects.none()

    section_ids = _faculty_section_ids(fp)
    if not section_ids:
        return StudentProfile.objects.none()

    attendance_scope = Q(attendance_records__section_id__in=section_ids)
    grade_scope = Q(grades__subject_assignment__faculty=fp)

    return (
        StudentProfile.objects.filter(
            enrollments__section_id__in=section_ids,
            enrollments__is_active=True,
        )
        .distinct()
        .select_related("user", "grade_level", "section")
        .annotate(
            attendance_present=Count(
                "attendance_records",
                filter=attendance_scope
                & Q(attendance_records__status=AttendanceRecord.Status.PRESENT),
                distinct=True,
            ),
            attendance_late=Count(
                "attendance_records",
                filter=attendance_scope
                & Q(attendance_records__status=AttendanceRecord.Status.LATE),
                distinct=True,
            ),
            attendance_absent=Count(
                "attendance_records",
                filter=attendance_scope
                & Q(attendance_records__status=AttendanceRecord.Status.ABSENT),
                distinct=True,
            ),
            attendance_total=Count(
                "attendance_records", filter=attendance_scope, distinct=True
            ),
            grades_recorded=Count(
                "grades", filter=grade_scope, distinct=True
            ),
            grade_average=Avg("grades__score", filter=grade_scope, distinct=True),
        )
        .order_by("user__last_name", "user__first_name", "student_id")
    )


def _student_full_name(sp):
    return sp.user.get_full_name().strip() or sp.student_id


def grade_rows(queryset):
    """Yield ordered, sanitized row dicts for a Grade queryset."""
    for g in queryset:
        yield {
            "student_id": g.student.student_id,
            "student_name": _student_full_name(g.student),
            "grade_level": g.student.grade_level.name if g.student.grade_level else "",
            "subject_assignment": g.subject_assignment_id,
            "section": g.subject_assignment.section.name,
            "subject_code": g.subject_assignment.subject.code,
            "subject_name": g.subject_assignment.subject.name,
            "grading_period": g.grading_period.name,
            "score": g.score,
            "letter_grade": _format(g.letter_grade),
            "remarks": g.remarks,
            "status": g.status,
            "encoded_by": g.encoded_by.user.get_full_name().strip()
            if g.encoded_by and g.encoded_by.user
            else "",
        }


def attendance_rows(queryset):
    """Yield ordered, sanitized row dicts for an AttendanceRecord queryset."""
    for a in queryset:
        yield {
            "student_id": a.student.student_id,
            "student_name": _student_full_name(a.student),
            "section": a.section.name,
            "date": a.date.isoformat(),
            "status": a.status,
            "recorded_by": a.recorded_by.user.get_full_name().strip()
            if a.recorded_by and a.recorded_by.user
            else "",
        }


def student_rows(queryset):
    """Yield ordered, sanitized, anonymized row dicts for a StudentProfile queryset."""
    for sp in queryset:
        yield {
            "student_id": sp.student_id,
            "student_name": _student_full_name(sp),
            "grade_level": sp.grade_level.name if sp.grade_level else "",
            "section": sp.section.name if sp.section else "",
            "enrollment_date": sp.enrollment_date.isoformat() if sp.enrollment_date else "",
            "is_active": sp.is_active,
        }


def advisory_rows(queryset):
    """Yield per-student advisory class summary rows (FR-016 / TC-FAC-20)."""
    for sp in queryset:
        average = sp.grade_average
        yield {
            "student_id": sp.student_id,
            "student_name": _student_full_name(sp),
            "grade_level": sp.grade_level.name if sp.grade_level else "",
            "section": sp.section.name if sp.section else "",
            "attendance_present": sp.attendance_present,
            "attendance_late": sp.attendance_late,
            "attendance_absent": sp.attendance_absent,
            "attendance_total": sp.attendance_total,
            "grades_recorded": sp.grades_recorded,
            # Blank rather than 0.00 when nothing is scored yet.
            "grade_average": "" if average is None else f"{average:.2f}",
        }


def student_roundtrip_rows(queryset):
    """Admin round-trip student rows carrying the importer's identity columns."""
    for sp in queryset:
        yield {
            "student_id": sp.student_id,
            "first_name": sp.user.first_name,
            "last_name": sp.user.last_name,
            "email": sp.user.email,
            "grade_level": sp.grade_level.name if sp.grade_level else "",
            "section": sp.section.name if sp.section else "",
            "enrollment_date": sp.enrollment_date,
            "guardian_contact": sp.guardian_contact or "",
            "date_of_birth": sp.date_of_birth if sp.date_of_birth else "",
        }


def guidance_rows(queryset):
    """Consultation-record rows matching the guidance-records import schema."""
    for cr in queryset:
        yield {
            "student_id": cr.student.student_id,
            "session_date": cr.session_date,
            "session_time": cr.session_time if cr.session_time else "",
            "session_type": cr.session_type,
            "concern_categories": "|".join(
                str(c) for c in (cr.concern_categories or [])
            ),
            "session_notes": cr.session_notes,
            "priority_level": cr.priority_level,
            "recommendations": cr.recommendations or "",
            "next_session_date": cr.next_session_date if cr.next_session_date else "",
            "status": cr.status,
        }


_ROW_BUILDERS = {
    ExportType.GRADES: grade_rows,
    ExportType.ATTENDANCE: attendance_rows,
    ExportType.STUDENTS: student_rows,
    ExportType.ADVISORY: advisory_rows,
}

_ROUNDTRIP_ROW_BUILDERS = {
    ExportType.GRADES: grade_rows,
    ExportType.ATTENDANCE: attendance_rows,
    ExportType.STUDENTS: student_roundtrip_rows,
    ExportType.GUIDANCE_RECORDS: guidance_rows,
    # ADVISORY is an aggregate, not a re-importable table, and it has no
    # importer.  It maps to itself so a request that leaves `schema` unset
    # still resolves when it reaches this builder set (see `_rows_for`).
    ExportType.ADVISORY: advisory_rows,
}


def _rows_for(export_type, queryset, reimport=False):
    """
    Pick the row builder for a kind.

    The two maps differ only where a kind has both a readable and a
    re-importable shape; every other kind resolves to the same builder, so a
    missing key here would be a programming error, not a user error.
    """
    builders = _ROUNDTRIP_ROW_BUILDERS if reimport else _ROW_BUILDERS
    return builders[export_type](queryset)


def rows_for_queryset(export_type, queryset, reimport=False):
    """Return the full list of ordered row dictionaries for a queryset."""
    return list(_rows_for(export_type, queryset, reimport))


def render_csv(export_type, rows, columns=None):
    """
    Render an ordered, sanitized CSV payload (UTF-8 + BOM) with a stable
    header row.
    """
    columns = columns if columns is not None else _COLUMN_MAP[export_type]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([sanitize_export_cell(_format(row.get(col, ""))) for col in columns])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def render_xlsx(export_type, rows, columns=None):
    """
    Render an ordered XLSX payload (openpyxl) with a stable header row.
    """
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    columns = columns if columns is not None else _COLUMN_MAP[export_type]
    wb = Workbook()
    ws = wb.active
    ws.title = "Export"
    ws.append(columns)
    for row in rows:
        ws.append([_format(row.get(col, "")) for col in columns])
    # Freeze the header row for usability and stable column width.
    ws.freeze_panes = "A2"
    for idx in range(1, len(columns) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 22
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_export_payload(export_type, rows, file_format, columns=None):
    """Return the raw file bytes for the given format."""
    if file_format == ExportFormat.CSV:
        return render_csv(export_type, rows, columns)
    return render_xlsx(export_type, rows, columns)


def export_queryset_for(export_type, user):
    """
    Return the server-authorized, ordered queryset for an export kind+user.

    Raises ExportError with PERMISSION_DENIED when the role is not authorized
    for the kind, and EXPORT_TOO_LARGE when the authorized scope exceeds the
    row cap.
    """
    if export_type == ExportType.GRADES:
        qs = _grades_queryset_for(user)
    elif export_type == ExportType.ATTENDANCE:
        qs = _attendance_queryset_for(user)
    elif export_type == ExportType.STUDENTS:
        if user.role != "admin":
            raise ExportError(
                ExportErrorCode.PERMISSION_DENIED,
                "Student export is available to administrators only.",
            )
        qs = _student_queryset()
    elif export_type == ExportType.GUIDANCE_RECORDS:
        if user.role != "admin":
            raise ExportError(
                ExportErrorCode.PERMISSION_DENIED,
                "The guidance-records export is available to administrators only.",
            )
        qs = _guidance_record_queryset()
    elif export_type == ExportType.ADVISORY:
        # Faculty-only: an advisory class summary is an aggregate of exactly
        # one faculty member's own class, so there is nothing for another
        # role (including admin) to read.
        if user.role != "faculty":
            raise ExportError(
                ExportErrorCode.PERMISSION_DENIED,
                "The advisory class summary is available to faculty only.",
            )
        qs = _advisory_queryset_for(user)
    else:
        raise ExportError(
            ExportErrorCode.UNSUPPORTED_EXPORT_TYPE,
            "Unsupported export kind.",
        )

    if qs.count() > MAX_EXPORT_ROWS:
        raise ExportError(
            ExportErrorCode.EXPORT_TOO_LARGE,
            f"The export exceeds the maximum of {MAX_EXPORT_ROWS} rows.",
        )
    return qs
