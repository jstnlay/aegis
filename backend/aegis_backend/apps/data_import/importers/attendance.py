"""
Attendance importer (Phase 8.6).

Consumes normalized rows (CSV or XLSX) and writes real ``AttendanceRecord``
records.  The enrollment / current-academic-year / faculty-section-scope /
duplicate rules below mirror the existing ``AttendanceRecordViewSet.create``
path exactly; the importer does not invent a second authorization system.

Accepted columns::

    student_id   (required)  StudentProfile.student_id school code
    section      (required)  section name ("Grade 8 - Bonifacio") or UUID
    date         (required)  YYYY-MM-DD (not in the future)
    status       (required)  present | late | absent

``recorded_by`` is FORBIDDEN: attribution is always server-controlled and
set to the authenticated faculty profile.

Re-uploading a record for the same student and date applies the corrected
status in place instead of rejecting the row: a school corrects a class sheet
and uploads it again.  The faculty-section scope check still runs first, so a
re-upload can never overwrite a section the uploader may not touch.

EVT-02 note: persistence is primary.  The attendance threshold notification
runs only AFTER the record is committed and any notification failure is
swallowed, so it can never roll back or fail a validated row.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.attendance.models import AttendanceRecord
from apps.academics.models import AcademicYear, Enrollment, SubjectAssignment

from ..constants import ImportErrorCode, RecordStatus
from .base import (
    ATTENDANCE_ALLOWED_COLUMNS,
    ATTENDANCE_FORBIDDEN_COLUMNS,
    ATTENDANCE_REQUIRED_COLUMNS,
    InFileDuplicateTracker,
    RowError,
    column_value,
    memo,
    recompute_job_counters,
    validate_headers,
)
from .resolution import resolve_section

#: Valid attendance statuses (AttendanceRecord.Status choices).
_VALID_STATUSES = frozenset(
    (AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE, AttendanceRecord.Status.ABSENT)
)


class AttendanceImporter:
    """Process attendance import rows for a single ImportJob."""

    def __init__(self, job, records, user):
        self.job = job
        self.records = records
        self.user = user
        #: One lookup per distinct student and section, not per row.
        self.cache = {}

    def process(self, headers):
        header_error = validate_headers(
            headers,
            required=ATTENDANCE_REQUIRED_COLUMNS,
            allowed=ATTENDANCE_ALLOWED_COLUMNS,
            forbidden=ATTENDANCE_FORBIDDEN_COLUMNS,
        )
        if header_error is not None:
            self._fail_all(header_error)
            return

        faculty_profile = self._faculty_profile()
        current_ay = AcademicYear.objects.filter(is_current=True).first()
        if current_ay is None:
            err = RowError(
                ImportErrorCode.INVALID_ACADEMIC_YEAR,
                "No current academic year is configured.",
            )
            self._fail_all(err)
            return

        tracker = InFileDuplicateTracker()

        for record in self.records:
            try:
                self._process_row(record, faculty_profile, current_ay, tracker)
            except RowError as exc:
                record.status = RecordStatus.ERROR
                record.error_message = exc.message
                record.mapped_to_model = ""
                record.mapped_to_id = None
            except Exception:
                record.status = RecordStatus.ERROR
                record.error_message = "The row could not be processed."
                record.mapped_to_model = ""
                record.mapped_to_id = None
            record.save()

        recompute_job_counters(self.job, self.records)

    # ------------------------------------------------------------------ #

    def _faculty_profile(self):
        if self.user.role != "faculty":
            return None
        try:
            return self.user.faculty_profile
        except Exception:
            return None

    def _process_row(self, record, faculty_profile, current_ay, tracker):
        row = record.data

        student_id = column_value(row, "student_id")
        section_raw = column_value(row, "section")
        date_raw = column_value(row, "date")
        status_raw = column_value(row, "status").lower()

        if not student_id:
            raise RowError(ImportErrorCode.MISSING_REQUIRED_COLUMN, "student_id is required.")
        if not section_raw:
            raise RowError(ImportErrorCode.MISSING_REQUIRED_COLUMN, "section is required.")
        if not date_raw:
            raise RowError(ImportErrorCode.MISSING_REQUIRED_COLUMN, "date is required.")
        if status_raw == "":
            raise RowError(ImportErrorCode.MISSING_REQUIRED_COLUMN, "status is required.")

        student = memo(self.cache, ("student", student_id), lambda: self._resolve_student(student_id))
        section = memo(
            self.cache,
            ("section", section_raw, current_ay.pk),
            lambda: resolve_section(section_raw, current_ay),
        )
        record_date = self._resolve_date(date_raw)
        self._resolve_status(status_raw)

        # --- active enrollment for the current academic year ------------
        if not Enrollment.objects.filter(
            student=student,
            section=section,
            academic_year=current_ay,
            is_active=True,
        ).exists():
            raise RowError(
                ImportErrorCode.INVALID_ENROLLMENT,
                "Student is not actively enrolled in the specified section "
                "for the current academic year.",
            )

        # --- faculty section scope --------------------------------------
        if faculty_profile is not None:
            has_access = (
                section.adviser_id == faculty_profile.id
                or SubjectAssignment.objects.filter(
                    faculty=faculty_profile,
                    section=section,
                    academic_year=current_ay,
                ).exists()
            )
            if not has_access:
                raise RowError(
                    ImportErrorCode.FACULTY_SCOPE_DENIED,
                    "You are not authorized to record attendance for this section.",
                )

        # --- in-file duplicate ------------------------------------------
        dup_key = (student_id, str(record_date))
        if tracker.is_dup(dup_key):
            raise RowError(
                ImportErrorCode.DUPLICATE_ROW,
                "This row duplicates another row in the same file "
                "(same student and date).",
            )
        tracker.mark(dup_key)

        # --- existing record --------------------------------------------
        # A re-upload of the same student and date updates the existing record
        # in place (see the module docstring); it is not an error.

        # --- server-controlled attribution -------------------------------
        # Faculty -> own profile.  Admin -> the section's adviser, else the
        # first faculty assigned to the section this year.  Unless an hon
        # attribution can be established, the row is rejected (never writes
        # a NULL / client-supplied recorded_by).
        recorded_by = faculty_profile
        if recorded_by is None:
            recorded_by = self._resolve_admin_recorded_by(section, current_ay)

        # --- primary operation: persist the record ----------------------
        with transaction.atomic():
            record_obj = AttendanceRecord.objects.filter(
                student=student, date=record_date
            ).first()
            if record_obj is None:
                record_obj = AttendanceRecord(
                    student=student,
                    section=section,
                    date=record_date,
                )
            record_obj.section = section
            record_obj.status = status_raw
            record_obj.recorded_by = recorded_by
            # full_clean() rejects future dates (domain rule).
            try:
                record_obj.full_clean()
            except ValidationError:
                raise RowError(
                    ImportErrorCode.INVALID_ATTENDANCE_DATE,
                    "Attendance date cannot be in the future.",
                )
            record_obj.save()

        record.status = RecordStatus.SUCCESS
        record.mapped_to_model = "AttendanceRecord"
        record.mapped_to_id = record_obj.pk
        record.error_message = ""

        # --- secondary: EVT-02 threshold notification -------------------
        # Runs AFTER commit.  Persistence is primary: a failure here is
        # swallowed (guarded at BOTH the call site and inside the method) so
        # it can never roll back the record nor flip this row to ERROR.
        if record_obj.status == AttendanceRecord.Status.ABSENT:
            try:
                self._notify_absence_threshold(record_obj, section, current_ay)
            except Exception:  # noqa: BLE001 - notification is non-critical
                pass

    # ------------------------------------------------------------------ #

    def _notify_absence_threshold(self, record_obj, section, current_ay):
        try:
            ABSENCE_THRESHOLD = 3  # matches apps.attendance.views
            absence_count = AttendanceRecord.objects.filter(
                student=record_obj.student,
                section__academic_year=section.academic_year,
                status=AttendanceRecord.Status.ABSENT,
            ).count()
            if absence_count < ABSENCE_THRESHOLD:
                return
            from apps.notifications.events import dispatch_event
            from apps.accounts.models import ParentStudentLink

            parent_links = ParentStudentLink.objects.filter(
                student=record_obj.student
            ).select_related("parent__user")
            recipients = [pl.parent.user for pl in parent_links]
            dedup_key = (
                f"attendance_threshold:{record_obj.student_id}:{section.academic_year_id}"
            )
            dispatch_event(
                "ATTENDANCE_THRESHOLD",
                recipients=recipients,
                sender=None,
                title="Attendance Alert",
                message=(
                    f"{record_obj.student.user.get_full_name()} has reached "
                    f"{absence_count} absences this academic year."
                ),
                link=f"/attendance/summary?student={record_obj.student_id}",
                deduplication_key=dedup_key,
            )
        except Exception:  # noqa: BLE001 - notification is non-critical
            # Deliberately swallow: attendance persistence is primary.
            pass

    def _resolve_admin_recorded_by(self, section, current_ay):
        if section.adviser_id is not None:
            return section.adviser
        fallback = (
            SubjectAssignment.objects.filter(
                section=section, academic_year=current_ay
            )
            .select_related("faculty")
            .first()
        )
        if fallback is not None:
            return fallback.faculty
        raise RowError(
            ImportErrorCode.ROW_NOT_PROCESSED,
            "No faculty can be attributed to this attendance record "
            "(section has no adviser or assigned faculty).",
        )

    # ------------------------------------------------------------------ #

    def _resolve_student(self, student_id):
        from apps.accounts.models import StudentProfile

        try:
            return StudentProfile.objects.get(student_id=student_id)
        except StudentProfile.DoesNotExist:
            raise RowError(
                ImportErrorCode.INVALID_STUDENT,
                f"No student found with student_id {student_id!r}.",
            )
        except Exception:
            raise RowError(ImportErrorCode.INVALID_STUDENT, "Invalid student identifier.")

    def _resolve_date(self, date_raw):
        from datetime import datetime

        try:
            parsed = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise RowError(
                ImportErrorCode.INVALID_ATTENDANCE_DATE,
                "date must use the YYYY-MM-DD format.",
            )
        if parsed > timezone.localdate():
            raise RowError(
                ImportErrorCode.INVALID_ATTENDANCE_DATE,
                "Attendance date cannot be in the future.",
            )
        return parsed

    def _resolve_status(self, status_raw):
        if status_raw not in _VALID_STATUSES:
            raise RowError(
                ImportErrorCode.INVALID_ATTENDANCE_STATUS,
                "status must be one of: present, late, absent.",
            )

    # ------------------------------------------------------------------ #

    def _fail_all(self, error):
        for record in self.records:
            record.status = RecordStatus.ERROR
            record.error_message = error.message
            record.mapped_to_model = ""
            record.mapped_to_id = None
            record.save()
        recompute_job_counters(self.job, self.records)
