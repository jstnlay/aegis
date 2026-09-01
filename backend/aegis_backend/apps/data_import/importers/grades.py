"""
Grade importer (Phase 8.5).

Consumes normalized rows (CSV or XLSX) and writes real ``Grade`` records
through the existing domain path: ``Grade.full_clean()`` runs the SEC-013
enrollment / grading-period / academic-year integrity checks already in
the model, so this importer does not re-implement them.

Accepted columns::

    student_id        (required)  StudentProfile.student_id school code
    subject_assignment (required)  SubjectAssignment UUID
    grading_period    (required)  GradingPeriod UUID
    score             (required)  numeric 0-100
    letter_grade      (optional)
    remarks           (optional)

Business rules enforced here (as the domain defines them):
- resolve real StudentProfile / SubjectAssignment / GradingPeriod
- faculty may only import grades for their OWN subject assignments
- score must be within the domain range (0-100)
- in-file duplicate rows are rejected
- existing Grade (student, subject_assignment, grading_period) is rejected
- SEC-013 relationship checks run via ``Grade.full_clean()``
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.models import Grade, GradingPeriod, SubjectAssignment

from ..constants import ImportErrorCode, RecordStatus
from .base import (
    GRADE_ALLOWED_COLUMNS,
    GRADE_REQUIRED_COLUMNS,
    InFileDuplicateTracker,
    RowError,
    column_value,
    recompute_job_counters,
    validate_headers,
)


class GradeImporter:
    """Process grade import rows for a single ImportJob."""

    def __init__(self, job, records, user):
        self.job = job
        self.records = records  # list aligned with result.rows
        self.user = user

    def process(self, headers):
        """
        Validate headers, then each row, writing Grade records.

        Returns nothing; updates each ImportRecord and the job in place.
        """
        header_error = validate_headers(
            headers,
            required=GRADE_REQUIRED_COLUMNS,
            allowed=GRADE_ALLOWED_COLUMNS,
        )
        if header_error is not None:
            self._fail_all(header_error)
            return

        faculty_id = self._faculty_profile_id()
        tracker = InFileDuplicateTracker()

        for record in self.records:
            try:
                self._process_row(record, faculty_id, tracker)
            except RowError as exc:
                record.status = RecordStatus.ERROR
                record.error_message = exc.message
                record.mapped_to_model = ""
                record.mapped_to_id = None
            except Exception:
                # Any unexpected failure in a single row is isolated: mark it
                # ERROR with a safe message; never crash the whole job.
                record.status = RecordStatus.ERROR
                record.error_message = "The row could not be processed."
                record.mapped_to_model = ""
                record.mapped_to_id = None
            record.save()

        recompute_job_counters(self.job, self.records)

    # ------------------------------------------------------------------ #

    def _faculty_profile_id(self):
        if self.user.role != "faculty":
            return None
        try:
            return self.user.faculty_profile.id
        except Exception:
            return None

    def _process_row(self, record, faculty_id, tracker):
        row = record.data

        student_id = column_value(row, "student_id")
        subject_assignment_uuid = column_value(row, "subject_assignment")
        grading_period_uuid = column_value(row, "grading_period")
        score_raw = column_value(row, "score")

        if not student_id:
            raise RowError(ImportErrorCode.MISSING_REQUIRED_COLUMN, "student_id is required.")
        if not subject_assignment_uuid:
            raise RowError(ImportErrorCode.MISSING_REQUIRED_COLUMN, "subject_assignment is required.")
        if not grading_period_uuid:
            raise RowError(ImportErrorCode.MISSING_REQUIRED_COLUMN, "grading_period is required.")
        if score_raw == "":
            raise RowError(ImportErrorCode.MISSING_REQUIRED_COLUMN, "score is required.")

        # --- student resolution -----------------------------------------
        student = self._resolve_student(student_id)

        # --- subject assignment + faculty scope -------------------------
        subject_assignment = self._resolve_assignment(subject_assignment_uuid)
        if faculty_id is not None and subject_assignment.faculty_id != faculty_id:
            raise RowError(
                ImportErrorCode.FACULTY_SCOPE_DENIED,
                "You are not authorized to import grades for this subject assignment.",
            )

        # --- grading period ---------------------------------------------
        grading_period = self._resolve_grading_period(grading_period_uuid)

        # --- score / optional fields ------------------------------------
        score = self._parse_score(score_raw)
        letter_grade = column_value(row, "letter_grade") or None
        remarks = column_value(row, "remarks") or None

        # --- in-file duplicate ------------------------------------------
        dup_key = (student_id, subject_assignment_uuid, grading_period_uuid)
        if tracker.is_dup(dup_key):
            raise RowError(
                ImportErrorCode.DUPLICATE_ROW,
                "This row duplicates another row in the same file "
                "(same student, subject assignment, and grading period).",
            )
        tracker.mark(dup_key)

        # --- existing grade ---------------------------------------------
        if Grade.objects.filter(
            student=student,
            subject_assignment=subject_assignment,
            grading_period=grading_period,
        ).exists():
            raise RowError(
                ImportErrorCode.DUPLICATE_ENTITY,
                "A grade already exists for this student, subject assignment, "
                "and grading period.",
            )

        grade = Grade(
            student=student,
            subject_assignment=subject_assignment,
            grading_period=grading_period,
            score=score,
            letter_grade=letter_grade,
            remarks=remarks,
            encoded_by=subject_assignment.faculty
            if faculty_id is None
            else self.user.faculty_profile,
            status=Grade.StatusChoices.DRAFT,
        )
        with transaction.atomic():
            # full_clean runs SEC-013: grading period academic-year match +
            # active enrollment integrity.  A ValidationError becomes a safe
            # row-level error (we never surface internal tracebacks).
            try:
                grade.full_clean()
            except ValidationError as exc:
                raise self._map_full_clean_error(exc)
            grade.save()

        record.status = RecordStatus.SUCCESS
        record.mapped_to_model = "Grade"
        record.mapped_to_id = grade.pk
        record.error_message = ""

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

    def _resolve_assignment(self, subject_assignment_uuid):
        try:
            return SubjectAssignment.objects.select_related(
                "faculty", "section", "academic_year"
            ).get(pk=subject_assignment_uuid)
        except SubjectAssignment.DoesNotExist:
            raise RowError(
                ImportErrorCode.INVALID_SUBJECT_ASSIGNMENT,
                "Subject assignment not found.",
            )
        except Exception:
            raise RowError(ImportErrorCode.INVALID_SUBJECT_ASSIGNMENT, "Invalid subject assignment.")

    def _resolve_grading_period(self, grading_period_uuid):
        try:
            return GradingPeriod.objects.get(pk=grading_period_uuid)
        except GradingPeriod.DoesNotExist:
            raise RowError(
                ImportErrorCode.INVALID_GRADING_PERIOD,
                "Grading period not found.",
            )
        except Exception:
            raise RowError(ImportErrorCode.INVALID_GRADING_PERIOD, "Invalid grading period.")

    def _map_full_clean_error(self, exc):
        """Map a Grade.full_clean() ValidationError to a safe RowError."""
        message_dict = getattr(exc, "message_dict", {})
        if "grading_period" in message_dict:
            return RowError(
                ImportErrorCode.ACADEMIC_YEAR_MISMATCH,
                "Grading period does not belong to the same academic year "
                "as the subject assignment.",
            )
        if "student" in message_dict:
            return RowError(
                ImportErrorCode.INVALID_ENROLLMENT,
                "Student is not actively enrolled in the section for this "
                "subject assignment's academic year.",
            )
        if "score" in message_dict:
            return RowError(
                ImportErrorCode.INVALID_GRADE_VALUE,
                "Score must be between 0 and 100.",
            )
        return RowError(ImportErrorCode.ROW_NOT_PROCESSED, "The row could not be processed.")

    def _parse_score(self, score_raw):
        from decimal import Decimal, InvalidOperation

        try:
            score = Decimal(score_raw)
        except (InvalidOperation, ValueError):
            raise RowError(ImportErrorCode.INVALID_GRADE_VALUE, "Score must be a number between 0 and 100.")
        if score < 0 or score > 100:
            raise RowError(ImportErrorCode.INVALID_GRADE_VALUE, "Score must be between 0 and 100.")
        return score

    # ------------------------------------------------------------------ #

    def _fail_all(self, header_error):
        for record in self.records:
            record.status = RecordStatus.ERROR
            record.error_message = header_error.message
            record.mapped_to_model = ""
            record.mapped_to_id = None
            record.save()
        recompute_job_counters(self.job, self.records)
