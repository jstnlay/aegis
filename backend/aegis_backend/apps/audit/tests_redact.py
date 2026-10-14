"""
Phase 10.2 test suite — Redaction + Safe Serialization.

Covers: model-specific allowlists, value normalization, safe field
extraction, exact changes structure, sensitive-field exclusion,
and unknown-model handling.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.audit.redact import (
    MODEL_ALLOWLISTS,
    get_allowed_fields,
    normalize_value,
    safe_serialize_fields,
)
from apps.audit.serializers import compute_changes

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

class PH10_2TestBase(TestCase):
    """Minimal shared fixtures for all PH10.2 redaction tests."""

    def setUp(self):
        today = date.today()
        past = today - timedelta(days=60)
        far_future = today + timedelta(days=365)

        # -- Users & profiles ------------------------------------------------
        self.faculty_user = User.objects.create_user(
            email="faculty-redact@example.com",
            password="pass12345",
            first_name="Fac",
            last_name="ulty",
            role="faculty",
        )
        self.student_user = User.objects.create_user(
            email="student-redact@example.com",
            password="pass12345",
            first_name="Stu",
            last_name="Dent",
            role="student",
        )
        self.guidance_user = User.objects.create_user(
            email="guidance-redact@example.com",
            password="pass12345",
            first_name="Gui",
            last_name="Dance",
            role="guidance",
        )

        from apps.accounts.models import (
            FacultyProfile,
            GuidanceProfile,
            StudentProfile,
        )

        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user,
            employee_id="FAC-RED-001",
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="STU-RED-001",
            enrollment_date=past,
        )
        self.guidance_profile = GuidanceProfile.objects.create(
            user=self.guidance_user,
            employee_id="GDE-RED-001",
        )

        # -- Academic scaffolding --------------------------------------------
        from apps.academics.models import (
            AcademicYear,
            GradeLevel,
            GradingPeriod,
            Section,
            Subject,
            SubjectAssignment,
        )

        self.academic_year = AcademicYear.objects.create(
            name="AY-RED-2025-2026",
            start_date=date(2025, 6, 1),
            end_date=date(2026, 5, 31),
            is_current=True,
        )
        self.grade_level = GradeLevel.objects.create(
            name="Grade 7",
            level_number=7,
        )
        self.section = Section.objects.create(
            name="RedactSection",
            grade_level=self.grade_level,
            academic_year=self.academic_year,
        )
        self.subject = Subject.objects.create(
            name="Math",
            code="MATH-RED",
            grade_level=self.grade_level,
        )
        self.subject_assignment = SubjectAssignment.objects.create(
            subject=self.subject,
            faculty=self.faculty_profile,
            section=self.section,
            academic_year=self.academic_year,
        )
        self.grading_period = GradingPeriod.objects.create(
            academic_year=self.academic_year,
            name="Q1",
            order=1,
            start_date=date(2025, 6, 1),
            end_date=date(2025, 8, 31),
        )

        # -- Enrollment (required by Grade.clean) ----------------------------
        from apps.academics.models import Enrollment

        Enrollment.objects.create(
            student=self.student_profile,
            section=self.section,
            academic_year=self.academic_year,
            date_enrolled=past,
        )

        # -- Domain model instances ------------------------------------------

        from apps.academics.models import Grade
        from apps.assessments.models import Assessment, AssessmentResult
        from apps.attendance.models import AttendanceRecord
        from apps.guidance.models import (
            BehavioralNote,
            ConsultationRecord,
            Intervention,
            RiskAlert,
        )

        self.grade = Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=Decimal("80.00"),
            letter_grade="B",
            status="draft",
            encoded_by=self.faculty_profile,
        )

        self.attendance = AttendanceRecord.objects.create(
            student=self.student_profile,
            section=self.section,
            date=past,
            status="present",
            recorded_by=self.faculty_profile,
        )

        self.behavioral_note = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="Displayed exemplary behavior during group work.",
            date_recorded=past,
        )

        self.consultation = ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=past,
            session_time="10:00:00",
            session_type="individual_counseling",
            concern_categories=["academic"],
            session_notes="Initial consultation to discuss academic performance.",
            recommendations="Recommend after-school tutoring sessions.",
            priority_level="medium",
            status="ongoing",
        )

        self.risk_alert = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="low",
            risk_factors=["attendance_pattern", "declining_grades"],
            source="manual",
            status="active",
            assigned_counselor=self.guidance_profile,
            generated_at=datetime.now(),
        )

        self.intervention = Intervention.objects.create(
            student=self.student_profile,
            risk_alert=self.risk_alert,
            assigned_counselor=self.guidance_profile,
            plan_start_date=past,
            target_review_date=far_future,
            status="active",
        )

        self.assessment = Assessment.objects.create(
            title="Midterm Exam",
            assessment_type="academic",
            creator_role="faculty",
            created_by=self.faculty_user,
            is_published=False,
        )

        self.assessment_result = AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={"q1": "A", "q2": "B"},
            score=Decimal("25.00"),
            total_possible=Decimal("50.00"),
            percentage=Decimal("50.00"),
            status="in_progress",
        )

        # -- Convenience shortcut --------------------------------------------
        self._Grade = Grade


# ---------------------------------------------------------------------------
# 1. Grade: score, letter_grade, status included
# ---------------------------------------------------------------------------

class GradeRedactionTest(PH10_2TestBase):

    def test_grade_score_included(self):
        old = safe_serialize_fields("academics.Grade", self.grade)
        self.assertIn("score", old)
        self.assertEqual(old["score"], 80.0)

    def test_grade_letter_grade_included(self):
        old = safe_serialize_fields("academics.Grade", self.grade)
        self.assertIn("letter_grade", old)
        self.assertEqual(old["letter_grade"], "B")

    def test_grade_status_included(self):
        old = safe_serialize_fields("academics.Grade", self.grade)
        self.assertIn("status", old)
        self.assertEqual(old["status"], "draft")


# ---------------------------------------------------------------------------
# 2. AttendanceRecord: status included
# ---------------------------------------------------------------------------

class AttendanceRedactionTest(PH10_2TestBase):

    def test_attendance_status_included(self):
        data = safe_serialize_fields(
            "attendance.AttendanceRecord", self.attendance,
        )
        self.assertIn("status", data)
        self.assertEqual(data["status"], "present")


# ---------------------------------------------------------------------------
# 3. BehavioralNote: note_type included, note_text excluded
# ---------------------------------------------------------------------------

class BehavioralNoteRedactionTest(PH10_2TestBase):

    def test_note_type_included(self):
        data = safe_serialize_fields(
            "guidance.BehavioralNote", self.behavioral_note,
        )
        self.assertIn("note_type", data)
        self.assertEqual(data["note_type"], "positive")

    def test_note_text_excluded(self):
        data = safe_serialize_fields(
            "guidance.BehavioralNote", self.behavioral_note,
        )
        self.assertNotIn("note_text", data)


# ---------------------------------------------------------------------------
# 4. ConsultationRecord: status + priority included; session_notes
#    and recommendations excluded
# ---------------------------------------------------------------------------

class ConsultationRecordRedactionTest(PH10_2TestBase):

    def test_status_included(self):
        data = safe_serialize_fields(
            "guidance.ConsultationRecord", self.consultation,
        )
        self.assertIn("status", data)
        self.assertEqual(data["status"], "ongoing")

    def test_priority_level_included(self):
        data = safe_serialize_fields(
            "guidance.ConsultationRecord", self.consultation,
        )
        self.assertIn("priority_level", data)
        self.assertEqual(data["priority_level"], "medium")

    def test_session_notes_excluded(self):
        data = safe_serialize_fields(
            "guidance.ConsultationRecord", self.consultation,
        )
        self.assertNotIn("session_notes", data)

    def test_recommendations_excluded(self):
        data = safe_serialize_fields(
            "guidance.ConsultationRecord", self.consultation,
        )
        self.assertNotIn("recommendations", data)


# ---------------------------------------------------------------------------
# 5. RiskAlert: risk_level + status included; risk_factors excluded
# ---------------------------------------------------------------------------

class RiskAlertRedactionTest(PH10_2TestBase):

    def test_risk_level_included(self):
        data = safe_serialize_fields(
            "guidance.RiskAlert", self.risk_alert,
        )
        self.assertIn("risk_level", data)
        self.assertEqual(data["risk_level"], "low")

    def test_status_included(self):
        data = safe_serialize_fields(
            "guidance.RiskAlert", self.risk_alert,
        )
        self.assertIn("status", data)
        self.assertEqual(data["status"], "active")

    def test_risk_factors_excluded(self):
        data = safe_serialize_fields(
            "guidance.RiskAlert", self.risk_alert,
        )
        self.assertNotIn("risk_factors", data)


# ---------------------------------------------------------------------------
# 6. Intervention: status included
# ---------------------------------------------------------------------------

class InterventionRedactionTest(PH10_2TestBase):

    def test_status_included(self):
        data = safe_serialize_fields(
            "guidance.Intervention", self.intervention,
        )
        self.assertIn("status", data)
        self.assertEqual(data["status"], "active")


# ---------------------------------------------------------------------------
# 7. Assessment: title + is_published included
# ---------------------------------------------------------------------------

class AssessmentRedactionTest(PH10_2TestBase):

    def test_title_included(self):
        data = safe_serialize_fields(
            "assessments.Assessment", self.assessment,
        )
        self.assertIn("title", data)
        self.assertEqual(data["title"], "Midterm Exam")

    def test_is_published_included(self):
        data = safe_serialize_fields(
            "assessments.Assessment", self.assessment,
        )
        self.assertIn("is_published", data)
        self.assertFalse(data["is_published"])


# ---------------------------------------------------------------------------
# 8. AssessmentResult: status included; answers + score excluded
# ---------------------------------------------------------------------------

class AssessmentResultRedactionTest(PH10_2TestBase):

    def test_status_included(self):
        data = safe_serialize_fields(
            "assessments.AssessmentResult", self.assessment_result,
        )
        self.assertIn("status", data)
        self.assertEqual(data["status"], "in_progress")

    def test_answers_excluded(self):
        data = safe_serialize_fields(
            "assessments.AssessmentResult", self.assessment_result,
        )
        self.assertNotIn("answers", data)

    def test_score_excluded(self):
        data = safe_serialize_fields(
            "assessments.AssessmentResult", self.assessment_result,
        )
        self.assertNotIn("score", data)


# ---------------------------------------------------------------------------
# 9. Exact changes structure: top-level old/new, flat primitives
# ---------------------------------------------------------------------------

class ChangesStructureTest(PH10_2TestBase):

    def _get_fresh_grade(self):
        return self._Grade.objects.get(pk=self.grade.pk)

    def test_top_level_keys_are_old_and_new(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(status="submitted")
        new = self._get_fresh_grade()
        changes = compute_changes("academics.Grade", self.grade, new)
        self.assertIn("old", changes)
        self.assertIn("new", changes)
        self.assertEqual(set(changes.keys()), {"old", "new"})

    def test_values_are_flat_primitives(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(status="submitted")
        new = self._get_fresh_grade()
        changes = compute_changes("academics.Grade", self.grade, new)
        for section in ("old", "new"):
            for key, val in changes[section].items():
                self.assertIsInstance(val, (str, int, float, bool, type(None)))


# ---------------------------------------------------------------------------
# 10. Only changed fields included
# ---------------------------------------------------------------------------

class OnlyChangedFieldsTest(PH10_2TestBase):

    def test_only_changed_fields_appear(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(
            score=Decimal("95.00"), status="finalized",
        )
        new = self._Grade.objects.get(pk=self.grade.pk)
        changes = compute_changes("academics.Grade", self.grade, new)
        self.assertEqual(set(changes["old"].keys()), {"score", "status"})
        self.assertEqual(set(changes["new"].keys()), {"score", "status"})
        self.assertNotIn("letter_grade", changes["old"])
        self.assertNotIn("letter_grade", changes["new"])


# ---------------------------------------------------------------------------
# 11. No-change result returns None
# ---------------------------------------------------------------------------

class NoChangeTest(PH10_2TestBase):

    def test_no_change_returns_none(self):
        changes = compute_changes(
            "academics.Grade", self.grade, self.grade,
        )
        self.assertIsNone(changes)


# ---------------------------------------------------------------------------
# 12. Unknown/unallowlisted model: no field leakage
# ---------------------------------------------------------------------------

class UnknownModelTest(PH10_2TestBase):
    """
    A model absent from ``MODEL_ALLOWLISTS`` serializes to nothing.

    ``accounts.User`` used to be the example here. PH11 gave it a narrow
    ``(role, is_active)`` entry so an administrator's account-management write
    can be diffed (TC-ADM-10), so the unallowlisted example is now
    ``accounts.FacultyProfile``. The property under test is unchanged — and the
    new User entry is pinned to exactly those two fields in
    ``AccountsUserAllowlistTest`` below.
    """

    def test_unallowlisted_model_returns_empty(self):
        data = safe_serialize_fields(
            "accounts.FacultyProfile", self.faculty_profile,
        )
        self.assertEqual(data, {})

    def test_unallowlisted_model_changes_returns_none(self):
        changes = compute_changes(
            "accounts.FacultyProfile", self.faculty_profile, self.faculty_profile,
        )
        self.assertIsNone(changes)


class AccountsUserAllowlistTest(PH10_2TestBase):
    """PH11: ``accounts.User`` is allowlisted, but only for role-based access."""

    def test_exactly_role_and_is_active(self):
        self.assertEqual(
            get_allowed_fields("accounts.User"), ("role", "is_active"),
        )
        self.assertEqual(
            set(safe_serialize_fields("accounts.User", self.faculty_user)),
            {"role", "is_active"},
        )

    def test_identity_and_credential_fields_are_never_serialized(self):
        self.faculty_user.email = "changed@example.com"
        self.faculty_user.username = "changed"
        self.faculty_user.first_name = "Changed"
        self.faculty_user.last_name = "Name"
        self.faculty_user.set_password("newpassword123")
        self.faculty_user.is_superuser = True

        data = safe_serialize_fields("accounts.User", self.faculty_user)

        for forbidden in (
            "password", "email", "username", "first_name", "last_name",
            "is_superuser",
        ):
            self.assertNotIn(forbidden, data)


# ---------------------------------------------------------------------------
# 13. Sensitive-field regression: passwords/tokens/secrets never serialized
# ---------------------------------------------------------------------------

class SensitiveFieldRegressionTest(PH10_2TestBase):

    def test_user_password_not_in_output(self):
        data = safe_serialize_fields("accounts.User", self.faculty_user)
        self.assertNotIn("password", data)
        self.assertNotIn("password_hash", data)
        self.assertNotIn("hashed_password", data)

    def test_user_tokens_not_in_output(self):
        data = safe_serialize_fields("accounts.User", self.faculty_user)
        for key in data:
            self.assertNotIn("token", key.lower())
            self.assertNotIn("secret", key.lower())
            self.assertNotIn("key", key.lower())


# ---------------------------------------------------------------------------
# 14. Value normalization: UUID, date, datetime, Decimal
# ---------------------------------------------------------------------------

class ValueNormalizationTest(PH10_2TestBase):

    def test_uuid_normalized_to_string(self):
        result = normalize_value("id", self.grade)
        self.assertIsInstance(result, str)
        uuid.UUID(result)

    def test_date_normalized_to_iso(self):
        result = normalize_value("date", self.attendance)
        self.assertIsInstance(result, str)
        date.fromisoformat(result)

    def test_datetime_normalized_to_iso(self):
        result = normalize_value("generated_at", self.risk_alert)
        self.assertIsInstance(result, str)
        datetime.fromisoformat(result)

    def test_decimal_normalized_to_float(self):
        result = normalize_value("score", self.grade)
        self.assertIsInstance(result, float)
        self.assertAlmostEqual(result, 80.0, places=2)

    def test_string_passthrough(self):
        result = normalize_value("letter_grade", self.grade)
        self.assertEqual(result, "B")

    def test_boolean_passthrough(self):
        result = normalize_value("is_published", self.assessment)
        self.assertFalse(result)

    def test_none_passthrough(self):
        obj = type("Mock", (), {"some_field": None})()
        result = normalize_value("some_field", obj)
        self.assertIsNone(result)

    def test_grade_letter_grade_serialized(self):
        data = safe_serialize_fields("academics.Grade", self.grade)
        self.assertEqual(data["letter_grade"], "B")

    def test_grade_status_serialized(self):
        data = safe_serialize_fields("academics.Grade", self.grade)
        self.assertEqual(data["status"], "draft")

    def test_assessment_title_serialized(self):
        data = safe_serialize_fields(
            "assessments.Assessment", self.assessment,
        )
        self.assertEqual(data["title"], "Midterm Exam")

    def test_assessment_result_status_serialized(self):
        data = safe_serialize_fields(
            "assessments.AssessmentResult", self.assessment_result,
        )
        self.assertEqual(data["status"], "in_progress")
