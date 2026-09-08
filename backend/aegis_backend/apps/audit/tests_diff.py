"""
Phase 10.3 test suite — Canonical Audit Diff Utility.

Covers: compute_diff API, snapshot comparison, change detection,
input validation, immutability, and backwards-compatibility wrapper.
"""

from datetime import date, datetime, timedelta

from django.utils import timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.audit.diff import compute_diff
from apps.audit.redact import safe_serialize_fields
from apps.audit.serializers import compute_changes

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared fixtures (same structure as PH10.2 for reuse consistency)
# ---------------------------------------------------------------------------

class PH10_3TestBase(TestCase):
    """Minimal shared fixtures for all PH10.3 diff tests."""

    def setUp(self):
        today = date.today()
        past = today - timedelta(days=60)
        far_future = today + timedelta(days=365)

        # -- Users & profiles ------------------------------------------------
        self.faculty_user = User.objects.create_user(
            email="faculty-diff@example.com",
            password="pass12345",
            first_name="Fac",
            last_name="ulty",
            role="faculty",
        )
        self.student_user = User.objects.create_user(
            email="student-diff@example.com",
            password="pass12345",
            first_name="Stu",
            last_name="Dent",
            role="student",
        )

        from apps.accounts.models import FacultyProfile, StudentProfile

        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user,
            employee_id="FAC-DIF-001",
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="STU-DIF-001",
            enrollment_date=past,
        )

        # -- Academic scaffolding --------------------------------------------
        from apps.academics.models import (
            AcademicYear,
            Enrollment,
            GradeLevel,
            GradingPeriod,
            Section,
            Subject,
            SubjectAssignment,
        )

        self.academic_year = AcademicYear.objects.create(
            name="AY-DIF-2025-2026",
            start_date=date(2025, 6, 1),
            end_date=date(2026, 5, 31),
            is_current=True,
        )
        self.grade_level = GradeLevel.objects.create(
            name="Grade 7",
            level_number=7,
        )
        self.section = Section.objects.create(
            name="DiffSection",
            grade_level=self.grade_level,
            academic_year=self.academic_year,
        )
        self.subject = Subject.objects.create(
            name="Math",
            code="MATH-DIF",
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

        Enrollment.objects.create(
            student=self.student_profile,
            section=self.section,
            academic_year=self.academic_year,
            date_enrolled=past,
        )

        # -- Domain model instances ------------------------------------------

        from apps.academics.models import Grade
        from apps.assessments.models import Assessment, AssessmentResult

        self.grade = Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=Decimal("80.00"),
            letter_grade="B",
            status="draft",
            encoded_by=self.faculty_profile,
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
# 1. Single changed field
# ---------------------------------------------------------------------------

class SingleChangedFieldTest(PH10_3TestBase):

    def test_single_field_change(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(status="submitted")
        new = self._Grade.objects.get(pk=self.grade.pk)

        result = compute_diff(self.grade, new)

        self.assertEqual(result, {
            "old": {"status": "draft"},
            "new": {"status": "submitted"},
        })


# ---------------------------------------------------------------------------
# 2. Multiple changed fields
# ---------------------------------------------------------------------------

class MultipleChangedFieldsTest(PH10_3TestBase):

    def test_two_fields_change(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(
            score=Decimal("95.00"), status="finalized",
        )
        new = self._Grade.objects.get(pk=self.grade.pk)

        result = compute_diff(self.grade, new)

        self.assertEqual(result["old"]["score"], 80.0)
        self.assertEqual(result["new"]["score"], 95.0)
        self.assertEqual(result["old"]["status"], "draft")
        self.assertEqual(result["new"]["status"], "finalized")


# ---------------------------------------------------------------------------
# 3. Unchanged fields omitted
# ---------------------------------------------------------------------------

class UnchangedFieldsOmittedTest(PH10_3TestBase):

    def test_unchanged_letter_grade_not_in_output(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(status="submitted")
        new = self._Grade.objects.get(pk=self.grade.pk)

        result = compute_diff(self.grade, new)

        self.assertNotIn("letter_grade", result["old"])
        self.assertNotIn("letter_grade", result["new"])


# ---------------------------------------------------------------------------
# 4. No changes → None
# ---------------------------------------------------------------------------

class NoChangeReturnsNoneTest(PH10_3TestBase):

    def test_same_instance_returns_none(self):
        result = compute_diff(self.grade, self.grade)
        self.assertIsNone(result)

    def test_identical_values_returns_none(self):
        other = self._Grade.objects.get(pk=self.grade.pk)
        result = compute_diff(self.grade, other)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 5. Sensitive fields never appear
# ---------------------------------------------------------------------------

class SensitiveFieldsNeverAppearTest(PH10_3TestBase):

    def test_note_text_not_in_behavioral_note_diff(self):
        from apps.guidance.models import BehavioralNote

        note = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="Should never appear in audit diff.",
            date_recorded=date.today() - timedelta(days=30),
        )
        BehavioralNote.objects.filter(pk=note.pk).update(note_type="warning")
        new_note = BehavioralNote.objects.get(pk=note.pk)

        result = compute_diff(note, new_note)

        for key in result["old"]:
            self.assertNotIn("note_text", key)
        for key in result["new"]:
            self.assertNotIn("note_text", key)

    def test_session_notes_not_in_consultation_diff(self):
        from apps.accounts.models import GuidanceProfile

        gu = User.objects.create_user(
            email="counselor-diff@example.com",
            password="pass12345",
            first_name="C",
            last_name="ounselor",
            role="guidance",
        )
        gp = GuidanceProfile.objects.create(user=gu, employee_id="GDE-DIF-001")

        from apps.guidance.models import ConsultationRecord

        cr = ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=gp,
            session_date=date.today() - timedelta(days=30),
            session_time="10:00:00",
            session_type="individual_counseling",
            concern_categories=["academic"],
            session_notes="Sensitive session notes.",
            recommendations="Sensitive recommendations.",
            priority_level="low",
            status="ongoing",
        )
        ConsultationRecord.objects.filter(pk=cr.pk).update(status="completed")
        new_cr = ConsultationRecord.objects.get(pk=cr.pk)

        result = compute_diff(cr, new_cr)

        for section in ("old", "new"):
            for key in result[section]:
                self.assertNotIn("session_notes", key)
                self.assertNotIn("recommendations", key)

    def test_risk_factors_not_in_risk_alert_diff(self):
        from apps.accounts.models import GuidanceProfile
        from apps.guidance.models import RiskAlert

        gu = User.objects.create_user(
            email="counselor2-diff@example.com",
            password="pass12345",
            first_name="C2",
            last_name="ounselor2",
            role="guidance",
        )
        gp = GuidanceProfile.objects.create(user=gu, employee_id="GDE-DIF-002")

        ra = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="low",
            risk_factors=["sensitive_factor_1"],
            source="manual",
            status="active",
            assigned_counselor=gp,
            generated_at=timezone.now(),
        )
        RiskAlert.objects.filter(pk=ra.pk).update(risk_level="high")
        new_ra = RiskAlert.objects.get(pk=ra.pk)

        result = compute_diff(ra, new_ra)

        for section in ("old", "new"):
            for key in result[section]:
                self.assertNotIn("risk_factors", key)


# ---------------------------------------------------------------------------
# 6. Unknown / unallowlisted model → None
# ---------------------------------------------------------------------------

class UnknownModelTest(PH10_3TestBase):

    def test_unallowlisted_model_returns_none(self):
        result = compute_diff(self.faculty_user, self.faculty_user)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 7. Same instance / identical snapshots → None
# ---------------------------------------------------------------------------

class SameInstanceTest(PH10_3TestBase):

    def test_same_object_returns_none(self):
        result = compute_diff(self.assessment, self.assessment)
        self.assertIsNone(result)

    def test_different_objects_same_values_returns_none(self):
        other = self._Grade.objects.get(pk=self.grade.pk)
        result = compute_diff(self.grade, other)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 8. Mismatched model types → TypeError
# ---------------------------------------------------------------------------

class MismatchedModelTypesTest(PH10_3TestBase):

    def test_mismatched_types_raises_type_error(self):
        with self.assertRaises(TypeError):
            compute_diff(self.grade, self.assessment)

    def test_allowlisted_and_unallowlisted_raises_type_error(self):
        from apps.guidance.models import BehavioralNote
        note = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="Test",
            date_recorded=date.today() - timedelta(days=30),
        )
        with self.assertRaises(TypeError):
            compute_diff(self.grade, note)


# ---------------------------------------------------------------------------
# 9. None inputs → None
# ---------------------------------------------------------------------------

class NoneInputTest(PH10_3TestBase):

    def test_none_old_returns_none(self):
        result = compute_diff(None, self.grade)
        self.assertIsNone(result)

    def test_none_new_returns_none(self):
        result = compute_diff(self.grade, None)
        self.assertIsNone(result)

    def test_both_none_returns_none(self):
        result = compute_diff(None, None)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 10. Normalized data types compare correctly
# ---------------------------------------------------------------------------

class NormalizedDataTypeTest(PH10_3TestBase):

    def test_decimal_score_compared_as_float(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(
            score=Decimal("95.00"),
        )
        new = self._Grade.objects.get(pk=self.grade.pk)
        result = compute_diff(self.grade, new)

        self.assertEqual(result["old"]["score"], 80.0)
        self.assertEqual(result["new"]["score"], 95.0)
        self.assertIsInstance(result["old"]["score"], float)
        self.assertIsInstance(result["new"]["score"], float)

    def test_boolean_is_published_compared(self):
        self.assessment.is_published = True
        self.assessment.save()
        self.assessment.refresh_from_db()

        other = self._Grade  # force a fresh read
        from apps.assessments.models import Assessment
        new_assessment = Assessment.objects.get(pk=self.assessment.pk)

        result = compute_diff(
            Assessment.objects.get(pk=self.assessment.pk),
            new_assessment,
        )
        self.assertIsNone(result)

        # Actually change it
        Assessment.objects.filter(pk=self.assessment.pk).update(
            is_published=True,
        )
        new_assessment = Assessment.objects.get(pk=self.assessment.pk)
        # Re-fetch old with original value
        old_assessment = Assessment.objects.get(pk=self.assessment.pk)

        # Since we updated the DB, re-read old too — use a fresh copy
        # Simulate: old had is_published=False, new has True
        # We need two distinct instances with different values
        Assessment.objects.filter(pk=self.assessment.pk).update(
            is_published=False,
        )
        old_assessment = Assessment.objects.get(pk=self.assessment.pk)
        Assessment.objects.filter(pk=self.assessment.pk).update(
            is_published=True,
        )
        new_assessment = Assessment.objects.get(pk=self.assessment.pk)

        result = compute_diff(old_assessment, new_assessment)
        self.assertIsNotNone(result)
        self.assertFalse(result["old"]["is_published"])
        self.assertTrue(result["new"]["is_published"])


# ---------------------------------------------------------------------------
# 11. Output has no nested per-field old/new objects
# ---------------------------------------------------------------------------

class FlatStructureTest(PH10_3TestBase):

    def test_no_nested_per_field_old_new(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(
            score=Decimal("95.00"), status="finalized",
        )
        new = self._Grade.objects.get(pk=self.grade.pk)

        result = compute_diff(self.grade, new)

        self.assertEqual(set(result.keys()), {"old", "new"})
        for section in ("old", "new"):
            for key, val in result[section].items():
                self.assertIsInstance(val, (str, int, float, bool, type(None)))
                self.assertNotIsInstance(val, dict)


# ---------------------------------------------------------------------------
# 12. Instances are not mutated
# ---------------------------------------------------------------------------

class ImmutabilityTest(PH10_3TestBase):

    def test_old_instance_not_mutated(self):
        old_score = self.grade.score
        old_status = self.grade.status

        self._Grade.objects.filter(pk=self.grade.pk).update(
            score=Decimal("95.00"), status="finalized",
        )
        new = self._Grade.objects.get(pk=self.grade.pk)

        compute_diff(self.grade, new)

        self.assertEqual(self.grade.score, old_score)
        self.assertEqual(self.grade.status, old_status)

    def test_new_instance_not_mutated(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(
            score=Decimal("95.00"), status="finalized",
        )
        new = self._Grade.objects.get(pk=self.grade.pk)
        new_score = new.score
        new_status = new.status

        compute_diff(self.grade, new)

        self.assertEqual(new.score, new_score)
        self.assertEqual(new.status, new_status)


# ---------------------------------------------------------------------------
# 13. Backwards-compatibility: compute_changes still works
# ---------------------------------------------------------------------------

class BackwardsCompatibilityTest(PH10_3TestBase):

    def test_compute_changes_via_serializers(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(status="submitted")
        new = self._Grade.objects.get(pk=self.grade.pk)

        result = compute_changes("academics.Grade", self.grade, new)

        self.assertEqual(result, {
            "old": {"status": "draft"},
            "new": {"status": "submitted"},
        })

    def test_compute_changes_returns_none_for_same_instance(self):
        result = compute_changes("academics.Grade", self.grade, self.grade)
        self.assertIsNone(result)

    def test_compute_changes_returns_none_for_unknown_model(self):
        result = compute_changes(
            "accounts.User", self.faculty_user, self.faculty_user,
        )
        self.assertIsNone(result)

    def test_compute_changes_with_mismatched_model_name_raises_value_error(self):
        with self.assertRaises(ValueError):
            compute_changes("academics.Grade", self.assessment, self.assessment)


# ---------------------------------------------------------------------------
# 14. Non-model objects handled safely
# ---------------------------------------------------------------------------

class NonModelObjectTest(PH10_3TestBase):

    def test_plain_dict_returns_none(self):
        result = compute_diff({"key": "value"}, {"key": "other"})
        self.assertIsNone(result)

    def test_plain_object_returns_none(self):
        result = compute_diff(object(), object())
        self.assertIsNone(result)
