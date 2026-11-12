"""
Tests for the human-review gate on AI-generated assessments.

The gate is the point: an assistant-written assessment must not reach a
student before a teacher has read it. These tests assert it at three levels —
the model, the deploy endpoint and the review endpoint — because a gate that
exists in only one of them is a gate another code path can walk around.
"""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from rest_framework import status

from apps.assessments.models import Assessment, AssessmentQuestion
from apps.assessments.tests import AssessmentsTestBase


class ReviewGateTest(AssessmentsTestBase, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.faculty_user)

    def _draft(self, *, ai_generated=True, review_status="pending"):
        return Assessment.objects.create(
            title="Algebra review quiz",
            assessment_type=Assessment.AssessmentType.ACADEMIC,
            creator_role=Assessment.CreatorRole.FACULTY,
            created_by=self.faculty_user,
            ai_generated=ai_generated,
            review_status=review_status,
        )

    # --- model ------------------------------------------------------------

    def test_model_refuses_to_publish_an_unapproved_ai_draft(self):
        assessment = self._draft()
        with self.assertRaises(ValidationError):
            assessment.is_published = True
            assessment.full_clean()

    def test_model_allows_an_approved_ai_draft(self):
        assessment = self._draft(review_status=Assessment.ReviewStatus.APPROVED)
        assessment.is_published = True
        assessment.full_clean()  # must not raise

    def test_manual_assessment_does_not_need_the_gate(self):
        assessment = self._draft(ai_generated=False, review_status="not_required")
        assessment.is_published = True
        assessment.full_clean()  # must not raise

    # --- generate ---------------------------------------------------------

    def test_generate_draft_creates_a_pending_draft(self):
        response = self.client.post(
            "/api/v1/assessments/assessments/generate-draft/",
            {"title": "Fractions", "topic": "fractions", "question_type": "essay", "count": 2},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["ai_generated"])
        self.assertEqual(response.data["review_status"], "pending")
        self.assertFalse(response.data["is_published"])

    def test_generate_draft_is_faculty_only(self):
        self.client.force_authenticate(user=self.guidance_user)
        response = self.client.post(
            "/api/v1/assessments/assessments/generate-draft/",
            {"title": "Wellbeing", "topic": "wellbeing", "question_type": "essay", "count": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_generate_draft_refuses_a_section_the_teacher_does_not_teach(self):
        response = self.client.post(
            "/api/v1/assessments/assessments/generate-draft/",
            {
                "title": "Fractions",
                "topic": "fractions",
                "question_type": "essay",
                "count": 1,
                "target_sections": [str(self.section2.id)],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- deploy -----------------------------------------------------------

    def test_deploy_is_refused_until_the_draft_is_approved(self):
        assessment = self._draft()
        AssessmentQuestion.objects.create(
            assessment=assessment,
            question_text="What is 1/2 + 1/2?",
            question_type="essay",
            order=1,
        )
        response = self.client.post(
            f"/api/v1/assessments/assessments/{assessment.id}/deploy/", {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reviewed and approved", response.data["detail"].lower())

    def test_deploy_succeeds_after_approval(self):
        assessment = self._draft()
        AssessmentQuestion.objects.create(
            assessment=assessment,
            question_text="What is 1/2 + 1/2?",
            question_type="essay",
            order=1,
        )
        review = self.client.post(
            f"/api/v1/assessments/assessments/{assessment.id}/review/",
            {"decision": "approved", "note": "Read every question."},
            format="json",
        )
        self.assertEqual(review.status_code, status.HTTP_200_OK)
        self.assertEqual(review.data["review_status"], "approved")

        deploy = self.client.post(
            f"/api/v1/assessments/assessments/{assessment.id}/deploy/", {}, format="json"
        )
        self.assertEqual(deploy.status_code, status.HTTP_200_OK)
        self.assertTrue(deploy.data["is_published"])

    def test_changes_requested_blocks_publishing(self):
        assessment = self._draft()
        AssessmentQuestion.objects.create(
            assessment=assessment,
            question_text="What is 1/2 + 1/2?",
            question_type="essay",
            order=1,
        )
        review = self.client.post(
            f"/api/v1/assessments/assessments/{assessment.id}/review/",
            {"decision": "changes_requested", "note": "Question 2 is wrong."},
            format="json",
        )
        self.assertEqual(review.status_code, status.HTTP_200_OK)
        self.assertEqual(review.data["review_status"], "changes_requested")

        deploy = self.client.post(
            f"/api/v1/assessments/assessments/{assessment.id}/deploy/", {}, format="json"
        )
        self.assertEqual(deploy.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_rejects_an_unknown_decision(self):
        assessment = self._draft()
        response = self.client.post(
            f"/api/v1/assessments/assessments/{assessment.id}/review/",
            {"decision": "whatever"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- completion tracking ---------------------------------------------

    def test_completion_endpoint_reports_the_target_students(self):
        assessment = Assessment.objects.create(
            title="Algebra",
            assessment_type=Assessment.AssessmentType.ACADEMIC,
            creator_role=Assessment.CreatorRole.FACULTY,
            created_by=self.faculty_user,
            is_published=True,
        )
        assessment.target_sections.add(self.section)

        response = self.client.get(
            f"/api/v1/assessments/assessments/{assessment.id}/completion/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["targeted"], 1)
        self.assertEqual(response.data["completed"], 0)
        self.assertEqual(response.data["not_started"], 1)
        self.assertEqual(len(response.data["non_completers"]), 1)


class GeminiDraftFailureTest(AssessmentsTestBase, TestCase):
    """A model failure must not lose the teacher's work."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.faculty_user)

    @override_settings(GEMINI_API_KEY="test-key")
    def test_generation_falls_back_to_the_deterministic_generator(self):
        with patch(
            "apps.assessments.generation.gemini_client.generate_json",
            side_effect=RuntimeError("model down"),
        ):
            response = self.client.post(
                "/api/v1/assessments/assessments/generate-draft/",
                {"title": "Fractions", "topic": "fractions", "question_type": "essay", "count": 2},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["generation_source"], "fallback")
        self.assertTrue(response.data["ai_generated"])
        self.assertEqual(response.data["review_status"], "pending")

    @override_settings(GEMINI_API_KEY="test-key")
    def test_gemini_receives_only_the_topic(self):
        """The prompt must not carry a student record."""
        from apps.assessments import generation

        with patch.object(
            generation.gemini_client,
            "generate_json",
            return_value={"questions": [{"question_text": "What is 1/2?"}]},
        ) as mocked:
            self.client.post(
                "/api/v1/assessments/assessments/generate-draft/",
                {"title": "Fractions", "topic": "fractions", "question_type": "essay", "count": 1},
                format="json",
            )
        self.assertTrue(mocked.called)
        prompt = mocked.call_args.kwargs["prompt"]
        self.assertNotIn(self.student_profile.student_id, prompt)
        self.assertNotIn(self.student_user.get_full_name(), prompt)
        self.assertIn("fractions", prompt)
