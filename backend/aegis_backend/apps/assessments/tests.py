"""
Phase 6 test suite for AEGIS Assessments.

Covers: model validation, serializers, API endpoints, scoped querysets,
role-based permissions, assessment lifecycle, auto-grading, and notifications.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    FacultyProfile,
    GuidanceProfile,
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
)
from apps.academics.models import (
    AcademicYear,
    GradeLevel,
    GradingPeriod,
    Section,
)
from apps.assessments.models import Assessment, AssessmentQuestion, AssessmentResult
from apps.assessments.utils import auto_grade_assessment

User = get_user_model()


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class AssessmentsTestBase(TestCase):
    """Shared setUp for assessments tests."""

    def setUp(self):
        # --- Users ---
        self.admin_user = User.objects.create_user(
            email="admin_assess@test.com", password="pass12345",
            first_name="Admin", last_name="User", role="admin",
        )
        self.faculty_user = User.objects.create_user(
            email="faculty_assess@test.com", password="pass12345",
            first_name="Fac", last_name="ulty", role="faculty",
        )
        self.faculty2_user = User.objects.create_user(
            email="faculty2_assess@test.com", password="pass12345",
            first_name="Fac2", last_name="ulty2", role="faculty",
        )
        self.guidance_user = User.objects.create_user(
            email="guidance_assess@test.com", password="pass12345",
            first_name="Guid", last_name="ance", role="guidance",
        )
        self.guidance2_user = User.objects.create_user(
            email="guidance2_assess@test.com", password="pass12345",
            first_name="Guid2", last_name="ance2", role="guidance",
        )
        self.student_user = User.objects.create_user(
            email="student_assess@test.com", password="pass12345",
            first_name="Stu", last_name="dent", role="student",
        )
        self.student2_user = User.objects.create_user(
            email="student2_assess@test.com", password="pass12345",
            first_name="Stu2", last_name="dent2", role="student",
        )
        self.parent_user = User.objects.create_user(
            email="parent_assess@test.com", password="pass12345",
            first_name="Par", last_name="ent", role="parent",
        )

        # --- Profiles ---
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="EMP-FAC-001", department="Math",
        )
        self.faculty2_profile = FacultyProfile.objects.create(
            user=self.faculty2_user, employee_id="EMP-FAC-002", department="Science",
        )
        self.guidance_profile = GuidanceProfile.objects.create(
            user=self.guidance_user, employee_id="EMP-GUID-001",
        )
        self.guidance2_profile = GuidanceProfile.objects.create(
            user=self.guidance2_user, employee_id="EMP-GUID-002",
        )
        
        # --- Academic structure ---
        self.ay = AcademicYear.objects.create(
            name="2025-2026", start_date="2025-06-01",
            end_date="2026-03-31", is_current=True,
        )
        self.grade_level = GradeLevel.objects.create(
            name="Grade 7", level_number=7,
        )
        self.section = Section.objects.create(
            name="Einstein", grade_level=self.grade_level,
            academic_year=self.ay, adviser=self.faculty_profile,
        )
        self.section2 = Section.objects.create(
            name="Newton", grade_level=self.grade_level,
            academic_year=self.ay,
        )
        self.grading_period = GradingPeriod.objects.create(
            academic_year=self.ay, name="Q1", order=1,
            start_date="2025-06-01", end_date="2025-09-30",
        )
        
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user, student_id="STU-001",
            enrollment_date="2025-06-01", section=self.section,
            grade_level=self.grade_level, is_active=True,
        )
        self.student2_profile = StudentProfile.objects.create(
            user=self.student2_user, student_id="STU-002",
            enrollment_date="2025-06-01", section=self.section2,
            grade_level=self.grade_level, is_active=True,
        )
        self.parent_profile = ParentProfile.objects.create(
            user=self.parent_user, relationship_to_student="mother",
        )
        ParentStudentLink.objects.create(
            parent=self.parent_profile, student=self.student_profile, is_primary=True,
        )

        self.client = APIClient()


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class AssessmentModelTests(AssessmentsTestBase):
    """Test Assessment model validation and business rules."""

    def test_academic_assessment_requires_faculty_creator(self):
        """Academic assessments must be created by faculty."""
        assessment = Assessment(
            title="Math Quiz",
            assessment_type="academic",
            created_by=self.guidance_user,
        )
        with self.assertRaises(ValidationError) as ctx:
            assessment.full_clean()
        self.assertIn("created_by", ctx.exception.message_dict)

    def test_wellness_assessment_requires_guidance_creator(self):
        """Wellness assessments must be created by guidance."""
        assessment = Assessment(
            title="Wellness Check",
            assessment_type="wellness",
            created_by=self.faculty_user,
        )
        with self.assertRaises(ValidationError) as ctx:
            assessment.full_clean()
        self.assertIn("created_by", ctx.exception.message_dict)

    def test_behavioral_assessment_requires_guidance_creator(self):
        """Behavioral assessments must be created by guidance."""
        assessment = Assessment(
            title="Behavioral Survey",
            assessment_type="behavioral",
            created_by=self.faculty_user,
        )
        with self.assertRaises(ValidationError) as ctx:
            assessment.full_clean()
        self.assertIn("created_by", ctx.exception.message_dict)

    def test_deadline_must_be_in_future(self):
        """Deadline must be in the future."""
        past_deadline = timezone.now() - timezone.timedelta(days=1)
        assessment = Assessment(
            title="Math Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            deadline=past_deadline,
        )
        with self.assertRaises(ValidationError) as ctx:
            assessment.full_clean()
        self.assertIn("deadline", ctx.exception.message_dict)

    def test_published_at_set_on_first_publish(self):
        """published_at is set when first published."""
        assessment = Assessment.objects.create(
            title="Math Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=False,
        )
        self.assertIsNone(assessment.published_at)
        
        assessment.is_published = True
        assessment.save()
        self.assertIsNotNone(assessment.published_at)


class AssessmentQuestionModelTests(AssessmentsTestBase):
    """Test AssessmentQuestion model validation."""

    def setUp(self):
        super().setUp()
        self.assessment = Assessment.objects.create(
            title="Math Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
        )

    def test_multiple_choice_requires_at_least_two_options(self):
        """Multiple choice questions need at least 2 options."""
        question = AssessmentQuestion(
            assessment=self.assessment,
            question_text="What is 2+2?",
            question_type="multiple_choice",
            order=1,
            options=["4"],
        )
        with self.assertRaises(ValidationError) as ctx:
            question.full_clean()
        self.assertIn("options", ctx.exception.message_dict)

    def test_multiple_choice_correct_answer_must_be_in_options(self):
        """Multiple choice correct_answer must match one of the options."""
        question = AssessmentQuestion(
            assessment=self.assessment,
            question_text="What is 2+2?",
            question_type="multiple_choice",
            order=1,
            options=["3", "4", "5"],
            correct_answer="6",
        )
        with self.assertRaises(ValidationError) as ctx:
            question.full_clean()
        self.assertIn("correct_answer", ctx.exception.message_dict)

    def test_true_false_correct_answer_validation(self):
        """True/False correct_answer must be 'True' or 'False'."""
        question = AssessmentQuestion(
            assessment=self.assessment,
            question_text="The sky is blue.",
            question_type="true_false",
            order=1,
            correct_answer="Yes",
        )
        with self.assertRaises(ValidationError) as ctx:
            question.full_clean()
        self.assertIn("correct_answer", ctx.exception.message_dict)

    def test_likert_requires_options(self):
        """Likert questions need scale options."""
        question = AssessmentQuestion(
            assessment=self.assessment,
            question_text="How satisfied are you?",
            question_type="likert",
            order=1,
            options=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            question.full_clean()
        self.assertIn("options", ctx.exception.message_dict)

    def test_valid_multiple_choice_passes_validation(self):
        """A well-formed multiple choice question passes validation."""
        question = AssessmentQuestion(
            assessment=self.assessment,
            question_text="What is 2+2?",
            question_type="multiple_choice",
            order=1,
            options=["3", "4", "5"],
            correct_answer="4",
        )
        question.full_clean()  # Should not raise

    def test_essay_does_not_require_options(self):
        """Essay questions do not require options."""
        question = AssessmentQuestion(
            assessment=self.assessment,
            question_text="Explain your reasoning.",
            question_type="essay",
            order=1,
        )
        question.full_clean()  # Should not raise

    def test_true_false_valid_correct_answer(self):
        """True/False questions accept 'True' or 'False' as correct answer."""
        for answer in ["True", "False"]:
            question = AssessmentQuestion(
                assessment=self.assessment,
                question_text="The sky is blue.",
                question_type="true_false",
                order=1,
                correct_answer=answer,
            )
            question.full_clean()  # Should not raise


class AssessmentResultModelTests(AssessmentsTestBase):
    """Test AssessmentResult model validation."""

    def setUp(self):
        super().setUp()
        self.assessment = Assessment.objects.create(
            title="Math Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        self.assessment.target_sections.add(self.section)

    def test_answers_must_be_dict(self):
        """answers field must be a JSON object."""
        result = AssessmentResult(
            assessment=self.assessment,
            student=self.student_profile,
            answers=["not", "a", "dict"],
        )
        with self.assertRaises(ValidationError) as ctx:
            result.full_clean()
        self.assertIn("answers", ctx.exception.message_dict)

    def test_score_cannot_exceed_total_possible(self):
        """score cannot exceed total_possible."""
        result = AssessmentResult(
            assessment=self.assessment,
            student=self.student_profile,
            answers={},
            score=Decimal("150.00"),
            total_possible=Decimal("100.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            result.full_clean()
        self.assertIn("score", ctx.exception.message_dict)

    def test_completed_status_sets_completed_at(self):
        """completed_at is set automatically when status becomes completed."""
        result = AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={},
            status="completed",
        )
        self.assertIsNotNone(result.completed_at)

    def test_one_result_per_student_per_assessment(self):
        """Only one result per student per assessment is allowed."""
        AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={},
        )
        duplicate = AssessmentResult(
            assessment=self.assessment,
            student=self.student_profile,
            answers={},
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()


# ---------------------------------------------------------------------------
# Auto-grading tests
# ---------------------------------------------------------------------------


class AutoGradingTests(AssessmentsTestBase):
    """Test auto-grading functionality."""

    def setUp(self):
        super().setUp()
        self.assessment = Assessment.objects.create(
            title="Math Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        self.q1 = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="What is 2+2?",
            question_type="multiple_choice",
            order=1,
            options=["3", "4", "5"],
            correct_answer="4",
        )
        self.q2 = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="Is Python a programming language?",
            question_type="true_false",
            order=2,
            correct_answer="True",
        )
        self.q3 = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="Explain your reasoning.",
            question_type="essay",
            order=3,
        )

    def test_auto_grade_all_correct(self):
        """Auto-grade correctly when all MC/TF answers are correct."""
        result = AssessmentResult(
            assessment=self.assessment,
            student=self.student_profile,
            answers={
                str(self.q1.id): "4",
                str(self.q2.id): "True",
                str(self.q3.id): "This is my essay answer.",
            },
        )
        auto_grade_assessment(result)
        self.assertEqual(result.score, Decimal("2"))  # q1 + q2
        self.assertEqual(result.total_possible, Decimal("2"))  # Only MC/TF
        self.assertEqual(result.percentage, Decimal("100.00"))

    def test_auto_grade_partial_correct(self):
        """Auto-grade with some incorrect answers."""
        result = AssessmentResult(
            assessment=self.assessment,
            student=self.student_profile,
            answers={
                str(self.q1.id): "3",  # Wrong
                str(self.q2.id): "True",  # Correct
                str(self.q3.id): "Essay answer.",
            },
        )
        auto_grade_assessment(result)
        self.assertEqual(result.score, Decimal("1"))  # Only q2
        self.assertEqual(result.total_possible, Decimal("2"))
        self.assertEqual(result.percentage, Decimal("50.00"))

    def test_auto_grade_all_wrong(self):
        """Auto-grade with all incorrect answers gives zero score."""
        result = AssessmentResult(
            assessment=self.assessment,
            student=self.student_profile,
            answers={
                str(self.q1.id): "3",  # Wrong
                str(self.q2.id): "False",  # Wrong
            },
        )
        auto_grade_assessment(result)
        self.assertEqual(result.score, Decimal("0"))
        self.assertEqual(result.total_possible, Decimal("2"))
        self.assertEqual(result.percentage, Decimal("0.00"))

    def test_auto_grade_ignores_essay_and_likert(self):
        """Auto-grading ignores essay and likert questions."""
        likert_q = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="How do you feel?",
            question_type="likert",
            order=4,
            options=["Bad", "Neutral", "Good"],
        )

        result = AssessmentResult(
            assessment=self.assessment,
            student=self.student_profile,
            answers={
                str(self.q1.id): "4",
                str(self.q2.id): "True",
                str(self.q3.id): "Essay.",
                str(likert_q.id): "Good",
            },
        )
        auto_grade_assessment(result)
        # Should only count MC and TF
        self.assertEqual(result.score, Decimal("2"))
        self.assertEqual(result.total_possible, Decimal("2"))

    def test_unanswered_questions_score_zero(self):
        """Unanswered auto-gradable questions count toward total but not score."""
        result = AssessmentResult(
            assessment=self.assessment,
            student=self.student_profile,
            answers={},  # Nothing answered
        )
        auto_grade_assessment(result)
        self.assertEqual(result.score, Decimal("0"))
        self.assertEqual(result.total_possible, Decimal("2"))


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class AssessmentAPITests(AssessmentsTestBase):
    """Test Assessment API endpoints."""

    def test_faculty_can_create_academic_assessment(self):
        """Faculty can create academic assessments."""
        self.client.force_authenticate(user=self.faculty_user)
        data = {
            "title": "Math Midterm",
            "description": "Covers chapters 1-5",
            "assessment_type": "academic",
        }
        response = self.client.post("/api/v1/assessments/assessments/", data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(response.data["created_by"]), str(self.faculty_user.id))

    def test_faculty_cannot_create_wellness_assessment(self):
        """Faculty cannot create wellness assessments."""
        self.client.force_authenticate(user=self.faculty_user)
        data = {
            "title": "Wellness Check",
            "assessment_type": "wellness",
        }
        response = self.client.post("/api/v1/assessments/assessments/", data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_guidance_can_create_wellness_assessment(self):
        """Guidance can create wellness assessments."""
        self.client.force_authenticate(user=self.guidance_user)
        data = {
            "title": "Wellness Survey",
            "assessment_type": "wellness",
        }
        response = self.client.post("/api/v1/assessments/assessments/", data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_guidance_cannot_create_academic_assessment(self):
        """Guidance cannot create academic assessments."""
        self.client.force_authenticate(user=self.guidance_user)
        data = {
            "title": "Math Quiz",
            "assessment_type": "academic",
        }
        response = self.client.post("/api/v1/assessments/assessments/", data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_faculty_sees_only_own_assessments(self):
        """Faculty see only their own academic assessments."""
        # Create assessments by different faculty
        Assessment.objects.create(
            title="Faculty1 Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
        )
        Assessment.objects.create(
            title="Faculty2 Quiz",
            assessment_type="academic",
            created_by=self.faculty2_user,
        )
        
        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.get("/api/v1/assessments/assessments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Faculty1 Quiz")

    def test_student_sees_published_assigned_assessments_only(self):
        """Students see only published assessments assigned to them."""
        # Published, assigned to student's section
        a1 = Assessment.objects.create(
            title="Assigned Published",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        a1.target_sections.add(self.section)
        
        # Unpublished, assigned to student's section
        a2 = Assessment.objects.create(
            title="Assigned Unpublished",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=False,
        )
        a2.target_sections.add(self.section)
        
        # Published, not assigned
        a3 = Assessment.objects.create(
            title="Not Assigned Published",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        a3.target_sections.add(self.section2)
        
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/v1/assessments/assessments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Assigned Published")

    def test_parent_sees_childrens_published_assessments(self):
        """Parents see published assessments assigned to their children."""
        a1 = Assessment.objects.create(
            title="Child's Assessment",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        a1.target_sections.add(self.section)
        
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get("/api/v1/assessments/assessments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_cannot_delete_published_assessment(self):
        """Published assessments cannot be deleted."""
        assessment = Assessment.objects.create(
            title="Published Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        
        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.delete(f"/api/v1/assessments/assessments/{assessment.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_delete_unpublished_assessment(self):
        """Unpublished assessments can be deleted."""
        assessment = Assessment.objects.create(
            title="Draft Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=False,
        )
        
        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.delete(f"/api/v1/assessments/assessments/{assessment.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    @patch('apps.assessments.views.notify_assessment_deployment')
    def test_deploy_assessment_dispatches_notifications(self, mock_notify):
        """Deploying an assessment dispatches notifications."""
        assessment = Assessment.objects.create(
            title="Math Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=False,
        )
        AssessmentQuestion.objects.create(
            assessment=assessment,
            question_text="Question 1",
            question_type="essay",
            order=1,
        )

        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.post(f"/api/v1/assessments/assessments/{assessment.id}/deploy/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_notify.assert_called_once_with(assessment)

    def test_cannot_deploy_assessment_without_questions(self):
        """Cannot deploy assessment without questions."""
        assessment = Assessment.objects.create(
            title="Empty Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=False,
        )

        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.post(f"/api/v1/assessments/assessments/{assessment.id}/deploy/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_creator_faculty_cannot_deploy_assessment(self):
        """Faculty cannot deploy another faculty member's assessment."""
        assessment = Assessment.objects.create(
            title="Other Faculty Quiz",
            assessment_type="academic",
            created_by=self.faculty2_user,
            is_published=False,
        )
        AssessmentQuestion.objects.create(
            assessment=assessment,
            question_text="Question 1",
            question_type="essay",
            order=1,
        )

        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.post(f"/api/v1/assessments/assessments/{assessment.id}/deploy/")
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )


class AssessmentQuestionAPITests(AssessmentsTestBase):
    """Test AssessmentQuestion API endpoints."""

    def setUp(self):
        super().setUp()
        self.assessment = Assessment.objects.create(
            title="Math Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=False,
        )

    def test_creator_can_add_question_to_unpublished_assessment(self):
        """Assessment creator can add questions to unpublished assessments."""
        self.client.force_authenticate(user=self.faculty_user)
        data = {
            "assessment": str(self.assessment.id),
            "question_text": "What is 2+2?",
            "question_type": "multiple_choice",
            "order": 1,
            "options": ["3", "4", "5"],
            "correct_answer": "4",
        }
        response = self.client.post("/api/v1/assessments/assessment-questions/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_non_creator_faculty_cannot_add_question(self):
        """Faculty cannot add questions to another faculty member's assessment."""
        self.client.force_authenticate(user=self.faculty2_user)
        data = {
            "assessment": str(self.assessment.id),
            "question_text": "Hijacked question",
            "question_type": "essay",
            "order": 1,
        }
        response = self.client.post("/api/v1/assessments/assessment-questions/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_add_question(self):
        """Students cannot add questions to any assessment."""
        self.client.force_authenticate(user=self.student_user)
        data = {
            "assessment": str(self.assessment.id),
            "question_text": "Student question",
            "question_type": "essay",
            "order": 1,
        }
        response = self.client.post("/api/v1/assessments/assessment-questions/", data, format='json')
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST],
        )

    def test_cannot_add_question_to_published_assessment(self):
        """Cannot add questions to published assessments."""
        self.assessment.is_published = True
        self.assessment.save()
        
        self.client.force_authenticate(user=self.faculty_user)
        data = {
            "assessment": str(self.assessment.id),
            "question_text": "New Question",
            "question_type": "essay",
            "order": 1,
        }
        response = self.client.post("/api/v1/assessments/assessment-questions/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_cannot_see_correct_answer_in_published_assessment(self):
        """Students don't receive correct_answer for published assessments."""
        self.assessment.is_published = True
        self.assessment.save()
        self.assessment.target_sections.add(self.section)
        
        question = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="What is 2+2?",
            question_type="multiple_choice",
            order=1,
            options=["3", "4", "5"],
            correct_answer="4",
        )

        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(f"/api/v1/assessments/assessment-questions/{question.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("correct_answer", response.data)


class AnswerKeyVisibilityTests(AssessmentsTestBase):
    """correct_answer is author material: only the author and admins receive it.

    ``AssessmentQuestionSerializer.to_representation`` previously removed the
    answer key only for ``role == 'student'``. A parent is served a published
    assessment through the same nested ``questions`` field and therefore read
    back every answer. Measured before this contract was tightened, on one
    published assessment targeted at a linked child's section:

        guidance   correct_answer=['A']
        student    correct_answer=[<absent>]
        parent     correct_answer=['A']      <- the defect
        admin      correct_answer=['A']
    """

    def setUp(self):
        super().setUp()
        self.assessment = Assessment.objects.create(
            title="Well-Being Check",
            assessment_type="wellness",
            creator_role="guidance",
            created_by=self.guidance_user,
            time_limit_minutes=20,
            deadline=timezone.localdate() + timedelta(days=7),
        )
        self.assessment.target_sections.add(self.section)
        self.assessment.is_published = True
        self.assessment.published_at = timezone.now()
        self.assessment.save()

        self.mc_question = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="Which option applies?",
            question_type="multiple_choice",
            order=1,
            options=["Almost always", "Often", "Rarely"],
            correct_answer="Almost always",
        )
        self.tf_question = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="I feel safe travelling to school.",
            question_type="true_false",
            order=2,
            correct_answer="True",
        )

    # -- the reported defect --------------------------------------------

    def test_parent_does_not_receive_the_answer_key(self):
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(
            f"/api/v1/assessments/assessments/{self.assessment.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["questions"]), 2)
        for question in response.data["questions"]:
            with self.subTest(order=question["order"]):
                self.assertNotIn("correct_answer", question)

    def test_parent_does_not_receive_the_answer_key_from_the_question_endpoint(self):
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(
            f"/api/v1/assessments/assessment-questions/{self.mc_question.id}/"
        )

        # The question list queryset excludes a parent entirely, so this is a
        # 404 rather than a redacted payload. Pinned so a future queryset
        # change that does admit parents still has to redact the key.
        self.assertIn(
            response.status_code,
            (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND),
        )
        if response.status_code == status.HTTP_200_OK:
            self.assertNotIn("correct_answer", response.data)

    def test_student_does_not_receive_the_answer_key(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(
            f"/api/v1/assessments/assessments/{self.assessment.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for question in response.data["questions"]:
            self.assertNotIn("correct_answer", question)

    def test_non_author_faculty_does_not_receive_the_answer_key(self):
        """Faculty cannot read this wellness assessment at all."""
        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.get(
            f"/api/v1/assessments/assessments/{self.assessment.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_author_guidance_does_not_receive_the_answer_key(self):
        """A second counselor's queryset excludes this assessment."""
        self.client.force_authenticate(user=self.guidance2_user)
        response = self.client.get(
            f"/api/v1/assessments/assessments/{self.assessment.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # -- author and admin keep the key ----------------------------------

    def test_author_still_receives_the_answer_key(self):
        self.client.force_authenticate(user=self.guidance_user)
        response = self.client.get(
            f"/api/v1/assessments/assessments/{self.assessment.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        answers = {
            question["order"]: question.get("correct_answer")
            for question in response.data["questions"]
        }
        self.assertEqual(answers[1], "Almost always")
        self.assertEqual(answers[2], "True")

    def test_admin_still_receives_the_answer_key(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(
            f"/api/v1/assessments/assessments/{self.assessment.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        answers = {
            question["order"]: question.get("correct_answer")
            for question in response.data["questions"]
        }
        self.assertEqual(answers[1], "Almost always")
        self.assertEqual(answers[2], "True")

    def test_author_keeps_the_answer_key_on_an_unpublished_assessment(self):
        """Draft authoring needs the key too; this is not a published-only rule."""
        self.assessment.is_published = False
        self.assessment.save()

        self.client.force_authenticate(user=self.guidance_user)
        response = self.client.get(
            f"/api/v1/assessments/assessments/{self.assessment.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["questions"][0]["correct_answer"], "Almost always"
        )

    # -- non-author role still sees the rest of the question ------------

    def test_parent_still_receives_the_question_text_and_options(self):
        """
        Redaction must remove the answer only.

        A parent needs the stem and the options to help their child, so both
        remain in the payload.
        """
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(
            f"/api/v1/assessments/assessments/{self.assessment.id}/"
        )

        first = response.data["questions"][0]
        self.assertEqual(first["question_text"], "Which option applies?")
        self.assertEqual(first["question_type"], "multiple_choice")
        self.assertEqual(
            first["options"], ["Almost always", "Often", "Rarely"]
        )


class AssessmentQuestionValidationAPITests(AssessmentsTestBase):
    """AssessmentQuestion.clean() rules must be 400s, not HTTP 500s.

    ``AssessmentQuestion.save()`` calls ``full_clean()``, so every rule in
    ``clean()`` used to raise a ``django.core.exceptions.ValidationError`` from
    inside the request - unhandled by DRF, and therefore a 500. The serializer
    now enforces the same rules, so each of these payloads is rejected as a
    validation error with the field detail preserved.
    """

    def setUp(self):
        super().setUp()
        self.assessment = Assessment.objects.create(
            title="Wellness Check",
            assessment_type="wellness",
            created_by=self.guidance_user,
            is_published=False,
        )
        self.client.force_authenticate(user=self.guidance_user)

    def _post(self, **overrides):
        payload = {
            "assessment": str(self.assessment.id),
            "question_text": "How are you feeling today?",
            "question_type": "multiple_choice",
            "order": 1,
            "options": ["Good", "Okay", "Bad"],
            "correct_answer": "Good",
        }
        payload.update(overrides)
        return self.client.post(
            "/api/v1/assessments/assessment-questions/", payload, format="json"
        )

    def _assert_rejected(self, response, field):
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
            msg=f"expected 400, got {response.status_code}",
        )
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn(field, response.data["error"]["details"])

    def test_multiple_choice_with_a_single_option_is_rejected(self):
        response = self._post(options=["Only one"])
        self._assert_rejected(response, "options")
        self.assertEqual(AssessmentQuestion.objects.count(), 0)

    def test_multiple_choice_with_no_options_is_rejected(self):
        response = self._post(options=[])
        self._assert_rejected(response, "options")

    def test_multiple_choice_with_null_options_is_rejected(self):
        response = self._post(options=None)
        self._assert_rejected(response, "options")

    def test_multiple_choice_with_non_array_options_is_rejected(self):
        """The model requires a JSON array; a bare string must not pass."""
        response = self._post(options="Good, Okay, Bad")
        self._assert_rejected(response, "options")

    def test_multiple_choice_answer_outside_the_options_is_rejected(self):
        response = self._post(correct_answer="Excellent")
        self._assert_rejected(response, "correct_answer")

    def test_likert_without_scale_options_is_rejected(self):
        response = self._post(question_type="likert", options=None)
        self._assert_rejected(response, "options")

    def test_likert_with_one_scale_option_is_rejected(self):
        response = self._post(
            question_type="likert",
            options=["Strongly agree"],
            correct_answer=None,
        )
        self._assert_rejected(response, "options")

    def test_likert_with_two_scale_options_is_accepted(self):
        response = self._post(
            question_type="likert",
            options=["Agree", "Disagree"],
            correct_answer=None,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_true_false_with_a_free_text_answer_is_rejected(self):
        response = self._post(
            question_type="true_false", options=None, correct_answer="Yes"
        )
        self._assert_rejected(response, "correct_answer")

    def test_true_false_with_lowercase_answer_is_rejected(self):
        """The model compares against 'True'/'False' exactly."""
        response = self._post(
            question_type="true_false", options=None, correct_answer="true"
        )
        self._assert_rejected(response, "correct_answer")

    def test_true_false_with_a_valid_answer_is_accepted(self):
        response = self._post(
            question_type="true_false", options=None, correct_answer="True"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_duplicate_order_in_the_same_assessment_is_rejected(self):
        """(assessment, order) is unique_together - a repeat is a 400."""
        first = self._post()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        duplicate = self._post(question_text="A second question at order 1")
        self._assert_rejected(duplicate, "non_field_errors")
        self.assertEqual(AssessmentQuestion.objects.count(), 1)

    def test_the_same_order_in_a_different_assessment_is_accepted(self):
        first = self._post()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        other = Assessment.objects.create(
            title="Another Check",
            assessment_type="wellness",
            created_by=self.guidance_user,
            is_published=False,
        )
        response = self._post(assessment=str(other.id))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(AssessmentQuestion.objects.count(), 2)

    def test_a_valid_multiple_choice_question_is_still_accepted(self):
        """The happy path is unchanged by the added validation."""
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        question = AssessmentQuestion.objects.get()
        self.assertEqual(question.question_type, "multiple_choice")
        self.assertEqual(question.options, ["Good", "Okay", "Bad"])
        self.assertEqual(question.correct_answer, "Good")

    def test_an_essay_question_needs_no_options_and_no_answer(self):
        response = self._post(
            question_type="essay", options=None, correct_answer=None
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_patching_to_a_taken_order_is_rejected(self):
        first = self._post()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self._post(order=2, question_text="Second")
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)

        target = AssessmentQuestion.objects.get(order=2)
        response = self.client.patch(
            f"/api/v1/assessments/assessment-questions/{target.id}/",
            {"order": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        target.refresh_from_db()
        self.assertEqual(target.order, 2)

    def test_patching_other_fields_on_a_question_is_unaffected(self):
        """The unique check must not reject a patch that keeps its own order."""
        created = self._post()
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        question = AssessmentQuestion.objects.get()
        response = self.client.patch(
            f"/api/v1/assessments/assessment-questions/{question.id}/",
            {"question_text": "Reworded question"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        question.refresh_from_db()
        self.assertEqual(question.question_text, "Reworded question")


class AssessmentResultAPITests(AssessmentsTestBase):
    """Test AssessmentResult API endpoints."""

    def setUp(self):
        super().setUp()
        self.assessment = Assessment.objects.create(
            title="Math Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        self.assessment.target_sections.add(self.section)
        
        self.q1 = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="What is 2+2?",
            question_type="multiple_choice",
            order=1,
            options=["3", "4", "5"],
            correct_answer="4",
        )

    @patch('apps.assessments.views.notify_assessment_completion')
    def test_student_can_submit_assessment(self, mock_notify):
        """Students can submit assessments assigned to them."""
        self.client.force_authenticate(user=self.student_user)
        data = {
            "assessment": str(self.assessment.id),
            "answers": {
                str(self.q1.id): "4"
            },
        }
        response = self.client.post("/api/v1/assessments/assessment-results/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["score"], "1.00")
        self.assertEqual(response.data["total_possible"], "1.00")
        self.assertEqual(response.data["percentage"], "100.00")
        self.assertEqual(response.data["status"], "completed")
        self.assertIsNotNone(response.data["completed_at"])
        mock_notify.assert_called_once()

    def test_student_cannot_submit_duplicate_result(self):
        """Students cannot submit the same assessment twice."""
        AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={str(self.q1.id): "4"},
        )
        
        self.client.force_authenticate(user=self.student_user)
        data = {
            "assessment": str(self.assessment.id),
            "answers": {str(self.q1.id): "3"},
        }
        response = self.client.post("/api/v1/assessments/assessment-results/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_cannot_submit_unassigned_assessment(self):
        """Students cannot submit assessments not assigned to them."""
        # Assessment assigned to section2, not student_user's section
        assessment2 = Assessment.objects.create(
            title="Another Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        assessment2.target_sections.add(self.section2)
        
        self.client.force_authenticate(user=self.student_user)
        data = {
            "assessment": str(assessment2.id),
            "answers": {},
        }
        response = self.client.post("/api/v1/assessments/assessment-results/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creator_can_view_assessment_results(self):
        """Assessment creator can view results."""
        AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={str(self.q1.id): "4"},
        )
        
        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.get("/api/v1/assessments/assessment-results/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_student_sees_only_own_results(self):
        """Students see only their own results."""
        AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={str(self.q1.id): "4"},
        )
        AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student2_profile,
            answers={str(self.q1.id): "3"},
        )
        
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/v1/assessments/assessment-results/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(str(response.data["results"][0]["student"]), str(self.student_profile.id))

    def test_parent_sees_childrens_results(self):
        """Parents see their children's results."""
        AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={str(self.q1.id): "4"},
        )
        
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get("/api/v1/assessments/assessment-results/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)


# ---------------------------------------------------------------------------
# Target scoping tests
# ---------------------------------------------------------------------------


class AssessmentTargetScopingTests(AssessmentsTestBase):
    """Test assessment targeting behavior."""

    def test_explicit_student_targeting_overrides_section(self):
        """Explicitly targeted students receive assessment, even if sections also targeted."""
        assessment = Assessment.objects.create(
            title="Targeted Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        # Target specific student, even though their section is also added
        assessment.target_students.add(self.student_profile)
        assessment.target_sections.add(self.section)
        
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/v1/assessments/assessments/")
        self.assertEqual(len(response.data["results"]), 1)

    def test_empty_targets_shows_no_assessments(self):
        """Assessment with no targets is not visible to students."""
        assessment = Assessment.objects.create(
            title="No Target Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        # No targets added
        
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/v1/assessments/assessments/")
        self.assertEqual(len(response.data["results"]), 0)

    def test_section_targeting_includes_all_section_students(self):
        """When section is targeted, all students in that section see assessment."""
        assessment = Assessment.objects.create(
            title="Section Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        assessment.target_sections.add(self.section)
        
        # Both students in same section should see it
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/v1/assessments/assessments/")
        self.assertEqual(len(response.data["results"]), 1)


# ---------------------------------------------------------------------------
# SEC-008 — Completed result immutability tests
# ---------------------------------------------------------------------------


class SEC008ResultImmutabilityTests(AssessmentsTestBase):
    """SEC-008: Completed assessment results must be immutable."""

    def setUp(self):
        super().setUp()
        self.assessment = Assessment.objects.create(
            title="Math Quiz",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        self.assessment.target_sections.add(self.section)
        self.q1 = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="What is 2+2?",
            question_type="multiple_choice",
            order=1,
            options=["3", "4", "5"],
            correct_answer="4",
        )
        self.q2 = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="Is Python a language?",
            question_type="true_false",
            order=2,
            correct_answer="True",
        )

    def _create_completed_result(self):
        """Helper: create a completed result for student_profile."""
        return AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={str(self.q1.id): "4", str(self.q2.id): "True"},
            status=AssessmentResult.Status.COMPLETED,
            score=Decimal("2"),
            total_possible=Decimal("2"),
            percentage=Decimal("100.00"),
        )

    def _create_in_progress_result(self):
        """Helper: create an in-progress result for student_profile."""
        return AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={str(self.q1.id): "3"},
            status=AssessmentResult.Status.IN_PROGRESS,
        )

    # --- A. Draft result can be updated by authorized role ---
    def test_in_progress_result_can_be_updated(self):
        """In-progress result can still be updated by the owning student."""
        result = self._create_in_progress_result()
        self.client.force_authenticate(user=self.student_user)
        data = {"answers": {str(self.q1.id): "4", str(self.q2.id): "False"}}
        response = self.client.patch(
            f"/api/v1/assessments/assessment-results/{result.id}/",
            data, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertEqual(result.answers[str(self.q1.id)], "4")

    # --- B. Draft result can be deleted where previously allowed ---
    def test_in_progress_result_can_be_deleted(self):
        """In-progress result can be deleted by the owning student."""
        result = self._create_in_progress_result()
        self.client.force_authenticate(user=self.student_user)
        response = self.client.delete(
            f"/api/v1/assessments/assessment-results/{result.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AssessmentResult.objects.filter(id=result.id).exists())

    # --- C. Completion/finalization succeeds through legitimate workflow ---
    @patch("apps.assessments.views.notify_assessment_completion")
    def test_finalization_succeeds_via_submit(self, mock_notify):
        """Student submission auto-completes the result."""
        self.client.force_authenticate(user=self.student_user)
        data = {
            "assessment": str(self.assessment.id),
            "answers": {str(self.q1.id): "4", str(self.q2.id): "True"},
        }
        response = self.client.post(
            "/api/v1/assessments/assessment-results/", data, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "completed")
        self.assertIsNotNone(response.data["completed_at"])

    # --- D. Completed result PATCH is rejected ---
    def test_completed_result_patch_rejected(self):
        """PATCH on a completed result returns 400."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.student_user)
        data = {"answers": {str(self.q1.id): "3", str(self.q2.id): "False"}}
        response = self.client.patch(
            f"/api/v1/assessments/assessment-results/{result.id}/",
            data, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- E. Completed result PUT is rejected (if PUT exists) ---
    def test_completed_result_put_rejected(self):
        """PUT on a completed result returns 400."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.student_user)
        data = {
            "assessment": str(self.assessment.id),
            "answers": {str(self.q1.id): "3"},
        }
        response = self.client.put(
            f"/api/v1/assessments/assessment-results/{result.id}/",
            data, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- F. Completed result DELETE is rejected ---
    def test_completed_result_delete_rejected(self):
        """DELETE on a completed result returns 400."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.student_user)
        response = self.client.delete(
            f"/api/v1/assessments/assessment-results/{result.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(AssessmentResult.objects.filter(id=result.id).exists())

    # --- G. Cannot change completed -> draft via PATCH ---
    def test_cannot_reopen_completed_via_patch(self):
        """Client cannot change status from completed back to in_progress."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.student_user)
        data = {"status": "in_progress"}
        response = self.client.patch(
            f"/api/v1/assessments/assessment-results/{result.id}/",
            data, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        result.refresh_from_db()
        self.assertEqual(result.status, AssessmentResult.Status.COMPLETED)

    # --- H. Cannot change protected historical fields after completion ---
    def test_cannot_change_answers_after_completion(self):
        """Answers must remain unchanged on a completed result."""
        result = self._create_completed_result()
        original_answers = dict(result.answers)
        self.client.force_authenticate(user=self.student_user)
        data = {"answers": {str(self.q1.id): "3"}}
        response = self.client.patch(
            f"/api/v1/assessments/assessment-results/{result.id}/",
            data, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        result.refresh_from_db()
        self.assertEqual(result.answers, original_answers)

    # --- I. Authorized users can still READ completed results ---
    def test_student_can_read_own_completed_result(self):
        """Student can read their own completed result."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(
            f"/api/v1/assessments/assessment-results/{result.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "completed")

    def test_creator_can_read_completed_result(self):
        """Assessment creator can read completed results."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.get(
            f"/api/v1/assessments/assessment-results/{result.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_parent_can_read_child_completed_result(self):
        """Parent can read their child's completed result."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(
            f"/api/v1/assessments/assessment-results/{result.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # --- J. Unauthorized users remain blocked from reading results ---
    def test_other_student_cannot_read_result(self):
        """A different student cannot read another student's result."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.student2_user)
        response = self.client.get(
            f"/api/v1/assessments/assessment-results/{result.id}/"
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )

    # --- K. Repeated mutation attempts do not alter the stored result ---
    def test_repeated_patch_attempts_do_not_alter_result(self):
        """Multiple PATCH attempts on a completed result leave it unchanged."""
        result = self._create_completed_result()
        original_answers = dict(result.answers)
        original_score = result.score
        self.client.force_authenticate(user=self.student_user)
        for _ in range(3):
            data = {"answers": {str(self.q1.id): "999"}}
            self.client.patch(
                f"/api/v1/assessments/assessment-results/{result.id}/",
                data, format="json",
            )
        result.refresh_from_db()
        self.assertEqual(result.answers, original_answers)
        self.assertEqual(result.score, original_score)

    # --- L. Admin can still mutate completed results (admin override) ---
    def test_admin_can_update_completed_result(self):
        """Admin can update a completed result (admin override)."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.admin_user)
        data = {"answers": {str(self.q1.id): "999"}}
        response = self.client.patch(
            f"/api/v1/assessments/assessment-results/{result.id}/",
            data, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_delete_completed_result(self):
        """Admin can delete a completed result (admin override)."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(
            f"/api/v1/assessments/assessment-results/{result.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    # --- M. Faculty/guidance cannot mutate completed results ---
    def test_faculty_cannot_update_completed_result(self):
        """Faculty cannot update a completed result."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.faculty_user)
        data = {"answers": {str(self.q1.id): "999"}}
        response = self.client.patch(
            f"/api/v1/assessments/assessment-results/{result.id}/",
            data, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_faculty_cannot_delete_completed_result(self):
        """Faculty cannot delete a completed result."""
        result = self._create_completed_result()
        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.delete(
            f"/api/v1/assessments/assessment-results/{result.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- N. No unexpected migration introduced (verified by no model change) ---
    def test_completed_at_auto_set(self):
        """completed_at is set when status transitions to completed."""
        result = AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={},
            status=AssessmentResult.Status.IN_PROGRESS,
        )
        self.assertIsNone(result.completed_at)
        result.status = AssessmentResult.Status.COMPLETED
        result.save()
        result.refresh_from_db()
        self.assertIsNotNone(result.completed_at)


# ---------------------------------------------------------------------------
# FR-027 — AI chatbot-assisted question drafting
# ---------------------------------------------------------------------------


class QuestionDraftAPITests(AssessmentsTestBase):
    """`POST /assessments/question-drafts/` (FR-027, TC-GUI-04)."""

    URL = "/api/v1/assessments/question-drafts/"

    def _post(self, **overrides):
        payload = {
            "topic": "coping with exam stress",
            "question_type": "multiple_choice",
            "count": 3,
        }
        payload.update(overrides)
        return self.client.post(self.URL, payload, format="json")

    def test_guidance_receives_the_requested_number_of_drafts(self):
        self.client.force_authenticate(user=self.guidance_user)
        response = self._post()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        drafts = response.data["drafts"]
        self.assertEqual(len(drafts), 3)
        for draft in drafts:
            self.assertIn("coping with exam stress", draft["question_text"])
            # `correct_answer` is always None: these are self-report items, and
            # `AssessmentQuestion.clean()` only enforces an answer key when one
            # is given.
            self.assertIsNone(draft["correct_answer"])

    def test_likert_drafts_carry_the_agreement_scale(self):
        self.client.force_authenticate(user=self.guidance_user)
        response = self._post(question_type="likert", count=1)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        draft = response.data["drafts"][0]
        self.assertEqual(
            draft["options"],
            ["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"],
        )

    def test_multiple_choice_drafts_carry_the_frequency_scale(self):
        self.client.force_authenticate(user=self.guidance_user)
        response = self._post(question_type="multiple_choice", count=2)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for draft in response.data["drafts"]:
            self.assertEqual(
                draft["options"],
                ["Never", "Rarely", "Sometimes", "Often", "Always"],
            )
            # `AssessmentQuestion.clean()` requires a multiple_choice answer to
            # name one of the options, so a generated answer key would have to
            # be invented. Self-report frequency items have none.
            self.assertIsNone(draft["correct_answer"])

    def test_essay_drafts_have_no_options(self):
        self.client.force_authenticate(user=self.guidance_user)
        response = self._post(question_type="essay", count=2)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for draft in response.data["drafts"]:
            self.assertIsNone(draft["options"])

    def test_true_false_is_refused_by_name(self):
        """
        A generated true/false item would assert a fact the system cannot
        verify, so the type is refused rather than half-supported. The code is
        named because "unsupported" and "invalid" are different answers.
        """
        self.client.force_authenticate(user=self.guidance_user)
        response = self._post(question_type="true_false")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            "QUESTION_TYPE_UNSUPPORTED", response.data["error"]["details"]
        )

    def test_count_outside_the_accepted_range_is_rejected(self):
        self.client.force_authenticate(user=self.guidance_user)

        for count in (0, 21):
            response = self._post(count=count)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            # The project's exception envelope keeps the field errors in
            # `error.details`, so the field name is asserted where it lives.
            self.assertIn("count", response.data["error"]["details"])

    def test_topic_must_be_long_enough_to_mean_anything(self):
        self.client.force_authenticate(user=self.guidance_user)
        response = self._post(topic="x")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("topic", response.data["error"]["details"])

    def test_a_large_request_never_repeats_a_stem(self):
        """
        Rotating past the primary bank is why `MAX_DRAFTS` is not capped at the
        size of one bank: a counselor asking for many items should get many
        items, not the same six twice.
        """
        self.client.force_authenticate(user=self.guidance_user)
        response = self._post(count=15)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        texts = [draft["question_text"] for draft in response.data["drafts"]]
        self.assertEqual(len(texts), 15)
        self.assertEqual(len(set(texts)), 15)

    def test_every_generatable_type_can_fill_a_maximum_request(self):
        """
        Every shape holds at least MAX_DRAFTS stems, so a count the serializer
        accepts (1..20) can always be satisfied. The essay banks once held 16
        - counts 17-20 passed validation then failed at generation, which is
        the worst order to discover a limit in.
        """
        self.client.force_authenticate(user=self.guidance_user)
        for question_type in ("multiple_choice", "likert", "essay"):
            response = self._post(question_type=question_type, count=20)

            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK,
                f"{question_type} must satisfy a 20-draft request",
            )
            self.assertEqual(len(response.data["drafts"]), 20)

    def test_the_same_request_is_deterministic(self):
        """Two identical requests return identical drafts (NFR-007, TC-SYS-05)."""
        self.client.force_authenticate(user=self.guidance_user)

        first = self._post(count=6)
        second = self._post(count=6)

        self.assertEqual(first.data, second.data)

    def test_only_guidance_may_draft(self):
        """
        FR-027/028/029 sit in the Guidance Module. A faculty academic assessment
        is a different document, and `Assessment.clean()` already refuses a
        wellness assessment whose creator is not a guidance user — so letting
        anyone else generate would only produce drafts they could never add.
        """
        for user in (
            self.faculty_user,
            self.student_user,
            self.parent_user,
            self.admin_user,
        ):
            self.client.force_authenticate(user=user)
            response = self._post()
            self.assertEqual(
                response.status_code,
                status.HTTP_403_FORBIDDEN,
                f"{user.role} must not be able to draft questions",
            )

    def test_anonymous_is_rejected(self):
        self.assertEqual(self._post().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_drafting_writes_nothing(self):
        """The endpoint proposes; it does not create. Nothing may be persisted."""
        self.client.force_authenticate(user=self.guidance_user)
        before = (Assessment.objects.count(), AssessmentQuestion.objects.count())

        self.assertEqual(self._post(count=5).status_code, status.HTTP_200_OK)

        after = (Assessment.objects.count(), AssessmentQuestion.objects.count())
        self.assertEqual(before, after)

    @patch("apps.chatbot.classifier.predict")
    def test_a_confident_guidance_intent_selects_the_concern_bank(
        self, mock_predict
    ):
        """
        The chatbot's own classifier chooses the bank. `EXPRESS_CONCERN` maps to
        the concern bank, whose items are help-seeking and coping.
        """
        from apps.chatbot.taxonomy import ChatIntent

        mock_predict.return_value = (ChatIntent.EXPRESS_CONCERN, 0.91)
        self.client.force_authenticate(user=self.guidance_user)
        response = self._post(question_type="likert", count=1)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["family"], "concern")
        self.assertEqual(
            response.data["drafts"][0]["question_text"],
            "I can talk to someone I trust about coping with exam stress.",
        )

    @patch("apps.chatbot.classifier.predict")
    def test_an_unconfident_prediction_falls_back_to_the_general_bank(
        self, mock_predict
    ):
        """
        Below the classifier's confidence floor the model has said nothing, so
        the general bank is used — and the confidence is passed through so the
        caller can see how little weight the selection carried.
        """
        mock_predict.return_value = (None, 0.0)
        self.client.force_authenticate(user=self.guidance_user)
        response = self._post(question_type="likert", count=1)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["family"], "general")
        self.assertEqual(
            response.data["drafts"][0]["question_text"],
            "I can say how I am feeling about coping with exam stress.",
        )

    def test_a_draft_can_be_added_as_a_real_question(self):
        """
        The drafts are shaped to be handed straight to the question form, so one
        has to survive `AssessmentQuestion.clean()` — otherwise "AI-generated
        questions included" would end at the proposal.
        """
        assessment = Assessment.objects.create(
            title="Wellness check-in",
            assessment_type=Assessment.AssessmentType.WELLNESS,
            creator_role=Assessment.CreatorRole.GUIDANCE,
            created_by=self.guidance_user,
        )
        self.client.force_authenticate(user=self.guidance_user)
        draft = self._post(question_type="likert", count=1).data["drafts"][0]

        response = self.client.post(
            "/api/v1/assessments/assessment-questions/",
            {
                "assessment": str(assessment.id),
                "question_text": draft["question_text"],
                "question_type": "likert",
                "order": 1,
                "options": draft["options"],
                "correct_answer": draft["correct_answer"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["correct_answer"])
