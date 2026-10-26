"""
Student master-data importer + account provisioning (Phase 8.7).

Consumes normalized rows (CSV or XLSX) and, per row, atomically writes the
User + StudentProfile + Enrollment triplet required for an official student
master list:

    student_id   (required)  StudentProfile.student_id school code
    first_name   (required)
    last_name    (required)
    email        (required)  login identity; immutable on updates
    grade_level  (required)  name ("Grade 7") or level number ("7")
    section      (required)  section name within the selected academic year
    academic_year(optional)  year name; defaults to the current year
    date_of_birth(optional)  YYYY-MM-DD
    guardian_contact (optional)
    enrollment_date (optional) YYYY-MM-DD; defaults to today

Password / role columns are rejected outright (the file is not a credential
container and the imported role is always server-controlled).

Key security properties:
- temporary credentials are cryptographically random (``secrets``), pass
  the standard Django password validators, and exist only as a local value
  before being stored as a Django password hash; the plaintext never
  survives, is never returned, logged, or written into ImportRecord.data.
- every row's User/StudentProfile/Enrollment writes run inside one
  ``transaction.atomic()`` block: a failed row leaves no orphans.
- ``must_change_password`` is set on every provisioned account so the
  student must complete an initial password change before normal access.
- credential handoff is a school operational decision OUTSIDE this import;
  this module never emits, returns, or references the temporary plaintext
  after hashing.
"""

import re
import secrets
from datetime import datetime

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import StudentProfile, User
from apps.academics.models import AcademicYear, Enrollment, GradeLevel, Section

from ..constants import ImportErrorCode, RecordStatus
from .base import (
    InFileDuplicateTracker,
    RowError,
    STUDENT_ALLOWED_COLUMNS,
    STUDENT_FORBIDDEN_COLUMNS,
    STUDENT_FORBIDDEN_PASSWORD_COLUMNS,
    STUDENT_REQUIRED_COLUMNS,
    column_value,
    recompute_job_counters,
    validate_headers,
)

#: student_id charset (school codes): starts alphanumeric, then letters /
#: digits / dot / underscore / hyphen.  Maximum 20 chars.
_STUDENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,19}$")

#: Max length of the first/last name (User model CharField default).
_NAME_MAX_LENGTH = 150

#: Max length of guardian_contact (StudentProfile CharField).
_GUARDIAN_MAX_LENGTH = 255

#: Attempts to generate a validator-conforming temporary password.
_TEMP_PASSWORD_ATTEMPTS = 5

#: Error code for internal/race failures that must not leak internals.
_GENERIC_ROW_MESSAGE = "The row could not be processed."


def _generate_temporary_password(hint_user):
    """Return a fresh cryptographically-random temporary password.

    The value is generated from ``secrets`` (never derived from student
    data) and must satisfy the standard Django password validators.  The
    caller stores it ONLY as a Django password hash and discards the
    plaintext immediately.
    """
    for _ in range(_TEMP_PASSWORD_ATTEMPTS):
        candidate = secrets.token_urlsafe(12)
        try:
            validate_password(candidate, user=hint_user)
        except DjangoValidationError:
            continue
        return candidate
    raise RowError(
        ImportErrorCode.PROVISIONING_FAILED,
        "A secure temporary credential could not be generated.",
    )


def _normalize_email(email):
    """Normalize following the existing UserManager rule (domain lowercase)."""
    return User.objects.normalize_email(email)


class StudentImporter:
    """Process student master-data rows for a single ImportJob."""

    def __init__(self, job, records, user):
        self.job = job
        self.records = records  # list aligned with result.rows
        self.user = user

    # ------------------------------------------------------------------
    # Public driver
    # ------------------------------------------------------------------

    def process(self, headers):
        forbidden_password = [
            c for c in STUDENT_FORBIDDEN_PASSWORD_COLUMNS if c in headers
        ]
        if forbidden_password:
            self._fail_all(
                RowError(
                    ImportErrorCode.PASSWORD_FIELD_FORBIDDEN,
                    "The file contains password-related column(s): "
                    + ", ".join(sorted(forbidden_password))
                    + ". Student import files never carry credentials.",
                )
            )
            return

        forbidden_role = [c for c in STUDENT_FORBIDDEN_COLUMNS if c in headers]
        if forbidden_role:
            self._fail_all(
                RowError(
                    ImportErrorCode.FORBIDDEN_COLUMN,
                    "Column 'role' is not accepted; the imported account "
                    "role is always student.",
                )
            )
            return

        header_error = validate_headers(
            headers,
            required=STUDENT_REQUIRED_COLUMNS,
            allowed=STUDENT_ALLOWED_COLUMNS,
        )
        if header_error is not None:
            self._fail_all(header_error)
            return

        tracker = InFileDuplicateTracker()
        for record in self.records:
            try:
                self._process_row(record, tracker)
            except RowError as exc:
                record.status = RecordStatus.ERROR
                record.error_message = exc.message
            except Exception:  # noqa: BLE001 - never leak internals
                record.status = RecordStatus.ERROR
                record.error_message = _GENERIC_ROW_MESSAGE
            record.save()

        recompute_job_counters(self.job, self.records)

    def _fail_all(self, error):
        """Header-level rejection: every row errors, job FAILED."""
        for record in self.records:
            record.status = RecordStatus.ERROR
            record.error_message = error.message
            record.save()
        # TC-FAC-12/14: a header rejection fails the file before any row is
        # processed, so the per-row messages alone leave the history reading
        # "0 of 0 rows" with no reason.  Record the reason on the job itself.
        self.job.error_log = [{"code": error.code, "message": error.message}]
        recompute_job_counters(self.job, self.records)

    # ------------------------------------------------------------------
    # Per-row orchestration
    # ------------------------------------------------------------------

    def _process_row(self, record, tracker):
        row = record.data

        student_id = column_value(row, "student_id")
        first_name = column_value(row, "first_name")
        last_name = column_value(row, "last_name")
        email_raw = column_value(row, "email")

        self._validate_required_values(
            student_id, first_name, last_name, email_raw
        )
        self._validate_student_id(student_id)
        self._validate_names(first_name, last_name)
        email = self._normalize_and_validate_email(email_raw)

        # In-file duplicate detection (deterministic, before any writes).
        _id_key = ("student_id", student_id.casefold())
        _email_key = ("email", email.casefold())
        if tracker.is_dup(_id_key):
            raise RowError(
                ImportErrorCode.DUPLICATE_STUDENT_ID,
                "student_id appears more than once in the file.",
            )
        if tracker.is_dup(_email_key):
            raise RowError(
                ImportErrorCode.DUPLICATE_EMAIL,
                "email appears more than once in the file.",
            )
        tracker.mark(_id_key)
        tracker.mark(_email_key)

        ay = self._resolve_academic_year(column_value(row, "academic_year"))
        grade = self._resolve_grade_level(column_value(row, "grade_level"))
        section = self._resolve_section(column_value(row, "section"), ay, grade)
        dob = self._resolve_dob(column_value(row, "date_of_birth"))
        guardian = self._resolve_guardian(column_value(row, "guardian_contact"))
        enroll_date = self._resolve_enrollment_date(
            column_value(row, "enrollment_date")
        )

        profile = self._resolve_student_profile(student_id)
        if profile is not None:
            self._process_update(record, profile, email, first_name, last_name, dob, guardian, ay, grade, section, enroll_date)
            return

        existing_user = self._resolve_user_by_email(email)
        if existing_user is not None:
            self._guard_existing_user(existing_user)
            self._create_profile_for_user(
                record, existing_user, student_id, grade, section, dob, guardian, enroll_date, ay
            )
            return

        self._provision_new_account(
            record, student_id, email, first_name, last_name, grade, section, dob, guardian, enroll_date, ay
        )

    # ------------------------------------------------------------------
    # Field validation / resolution
    # ------------------------------------------------------------------

    def _validate_required_values(self, student_id, first_name, last_name, email):
        if not student_id:
            raise RowError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN,
                "student_id is required.",
            )
        if not first_name:
            raise RowError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN,
                "first_name is required.",
            )
        if not last_name:
            raise RowError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN,
                "last_name is required.",
            )
        if not email:
            raise RowError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN,
                "email is required.",
            )

    def _validate_student_id(self, student_id):
        if len(student_id) > 20 or not _STUDENT_ID_RE.match(student_id):
            raise RowError(
                ImportErrorCode.INVALID_STUDENT_ID,
                "student_id must be 1-20 letters, digits, dot, dash or underscore.",
            )

    def _validate_names(self, first_name, last_name):
        if len(first_name) > _NAME_MAX_LENGTH or len(last_name) > _NAME_MAX_LENGTH:
            raise RowError(
                ImportErrorCode.INVALID_STUDENT_ID,
                "name fields exceed the maximum length.",
            )

    def _normalize_and_validate_email(self, email):
        if len(email) > 254:
            raise RowError(ImportErrorCode.INVALID_EMAIL, "email is too long.")
        normalized = _normalize_email(email)
        try:
            validate_email(normalized)
        except DjangoValidationError:
            raise RowError(
                ImportErrorCode.INVALID_EMAIL,
                "email must be a valid email address.",
            )
        return normalized

    def _resolve_academic_year(self, raw):
        if not raw:
            ay = AcademicYear.objects.filter(is_current=True).first()
            if ay is None:
                raise RowError(
                    ImportErrorCode.INVALID_ACADEMIC_YEAR,
                    "No current academic year is configured and no "
                    "academic_year was provided.",
                )
            return ay
        ay = AcademicYear.objects.filter(name__iexact=raw).first()
        if ay is None:
            raise RowError(
                ImportErrorCode.INVALID_ACADEMIC_YEAR,
                "academic_year does not match a known academic year.",
            )
        return ay

    def _resolve_grade_level(self, raw):
        grade = None
        if raw.isdigit():
            grade = GradeLevel.objects.filter(level_number=int(raw)).first()
        else:
            grade = GradeLevel.objects.filter(name__iexact=raw).first()
        if grade is None:
            raise RowError(
                ImportErrorCode.INVALID_GRADE_LEVEL,
                "grade_level does not match a known grade level.",
            )
        return grade

    def _resolve_section(self, raw, ay, grade):
        candidates = list(
            Section.objects.filter(name__iexact=raw, academic_year=ay)
        )
        if not candidates:
            raise RowError(
                ImportErrorCode.INVALID_SECTION,
                "section does not exist in the selected academic year.",
            )
        if len(candidates) == 1:
            if candidates[0].grade_level_id != grade.id:
                raise RowError(
                    ImportErrorCode.INVALID_GRADE_LEVEL,
                    "grade_level does not match the section's grade level.",
                )
            return candidates[0]
        match = next(
            (c for c in candidates if c.grade_level_id == grade.id), None
        )
        if match is None:
            raise RowError(
                ImportErrorCode.INVALID_GRADE_LEVEL,
                "grade_level does not match the section's grade level.",
            )
        return match

    def _resolve_dob(self, raw):
        if not raw:
            return None
        parsed = self._parse_date(raw, ImportErrorCode.INVALID_DATE, "date_of_birth")
        if parsed > timezone.localdate():
            raise RowError(
                ImportErrorCode.INVALID_DATE, "date_of_birth cannot be in the future."
            )
        return parsed

    def _resolve_guardian(self, raw):
        from apps.accounts.validators import validate_guardian_contact

        if not raw:
            return None
        if len(raw) > _GUARDIAN_MAX_LENGTH:
            raise RowError(
                ImportErrorCode.INVALID_STUDENT_ID,
                "guardian_contact exceeds the maximum length.",
            )
        try:
            validate_guardian_contact(raw)
        except ValueError:
            raise RowError(
                ImportErrorCode.INVALID_STUDENT,
                "guardian_contact must be a phone number of 7-15 digits.",
            )
        return raw

    def _resolve_enrollment_date(self, raw):
        if not raw:
            return timezone.localdate()
        return self._parse_date(
            raw, ImportErrorCode.INVALID_ENROLLMENT_DATE, "enrollment_date"
        )

    def _parse_date(self, raw, code, label):
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            raise RowError(code, f"{label} must use the YYYY-MM-DD format.")

    # ------------------------------------------------------------------
    # Identity resolution
    # ------------------------------------------------------------------

    def _resolve_student_profile(self, student_id):
        return StudentProfile.objects.filter(student_id__iexact=student_id).first()

    def _resolve_user_by_email(self, email):
        return User.objects.filter(email__iexact=email).first()

    def _guard_existing_user(self, user):
        if user.role != User.Role.STUDENT:
            raise RowError(
                ImportErrorCode.ACCOUNT_CONFLICT,
                "email already belongs to a non-student account.",
            )
        if StudentProfile.objects.filter(user=user).exists():
            raise RowError(
                ImportErrorCode.DUPLICATE_EMAIL,
                "email already belongs to another student.",
            )

    # ------------------------------------------------------------------
    # Update path (existing student)
    # ------------------------------------------------------------------

    def _process_update(self, record, profile, email, first_name, last_name, dob, guardian, ay, grade, section, enroll_date):
        if profile.user.email.casefold() != email.casefold():
            raise RowError(
                ImportErrorCode.IDENTITY_CONFLICT,
                "email does not match the existing student record; the "
                "login identity cannot be changed through import.",
            )
        self._check_enrollment_conflict(profile, ay, section)
        try:
            with transaction.atomic():
                self._update_identity(profile, first_name, last_name, dob, guardian, grade, section)
                self._reconcile_enrollment(profile, ay, section, enroll_date)
        except RowError:
            raise
        self._mark_success(record, profile)

    def _check_enrollment_conflict(self, profile, ay, section):
        conflict = (
            Enrollment.objects.filter(student=profile, academic_year=ay)
            .exclude(section=section)
            .exists()
        )
        if conflict:
            raise RowError(
                ImportErrorCode.DUPLICATE_ENROLLMENT,
                "Student is already enrolled in a different section for "
                "this academic year.",
            )

    def _update_identity(self, profile, first_name, last_name, dob, guardian, grade, section):
        user = profile.user
        user_changed = False
        if user.first_name != first_name or user.last_name != last_name:
            user.first_name = first_name
            user.last_name = last_name
            user_changed = True
        profile_changed = False
        if (
            profile.date_of_birth != dob
            or profile.guardian_contact != guardian
            or profile.grade_level_id != grade.id
            or profile.section_id != section.id
        ):
            profile.date_of_birth = dob
            profile.guardian_contact = guardian
            profile.grade_level = grade
            profile.section = section
            profile_changed = True
        if user_changed:
            user.save(update_fields=["first_name", "last_name"])
        if profile_changed:
            profile.save()

    def _reconcile_enrollment(self, profile, ay, section, enroll_date):
        existing = (
            Enrollment.objects.filter(
                student=profile, academic_year=ay, section=section
            )
            .first()
        )
        if existing is not None:
            if not existing.is_active:
                existing.is_active = True
                existing.save(update_fields=["is_active"])
            return existing
        return Enrollment.objects.create(
            student=profile,
            section=section,
            academic_year=ay,
            date_enrolled=enroll_date,
        )

    # ------------------------------------------------------------------
    # Create paths
    # ------------------------------------------------------------------

    def _create_profile_for_user(self, record, user, student_id, grade, section, dob, guardian, enroll_date, ay):
        try:
            with transaction.atomic():
                profile = StudentProfile.objects.create(
                    user=user,
                    student_id=student_id,
                    grade_level=grade,
                    section=section,
                    date_of_birth=dob,
                    guardian_contact=guardian,
                    enrollment_date=enroll_date,
                )
                Enrollment.objects.create(
                    student=profile,
                    section=section,
                    academic_year=ay,
                    date_enrolled=enroll_date,
                )
        except RowError:
            raise
        self._mark_success(record, profile)

    def _provision_new_account(self, record, student_id, email, first_name, last_name, grade, section, dob, guardian, enroll_date, ay):
        # Build an unsaved hint user so the validator similarity checks run.
        hint_user = User(
            email=email, first_name=first_name, last_name=last_name,
            role=User.Role.STUDENT,
        )
        temp_password = _generate_temporary_password(hint_user)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    password=temp_password,
                    first_name=first_name,
                    last_name=last_name,
                    role=User.Role.STUDENT,
                    is_active=True,
                )
                user.must_change_password = True
                user.save(update_fields=["must_change_password"])
                profile = StudentProfile.objects.create(
                    user=user,
                    student_id=student_id,
                    grade_level=grade,
                    section=section,
                    date_of_birth=dob,
                    guardian_contact=guardian,
                    enrollment_date=enroll_date,
                )
                Enrollment.objects.create(
                    student=profile,
                    section=section,
                    academic_year=ay,
                    date_enrolled=enroll_date,
                )
        except RowError:
            raise
        # Plaintext temporary credential is out of scope here by design:
        # it only ever existed as ``temp_password`` in this frame.
        self._mark_success(record, profile)

    def _mark_success(self, record, profile):
        record.status = RecordStatus.SUCCESS
        record.error_message = ""
        record.mapped_to_model = "StudentProfile"
        record.mapped_to_id = profile.pk