"""
Recommendation endpoint tests.

Covers the two things that were previously impossible to get wrong because
neither endpoint existed:

  1. The authorization ladder — who may read a student's recommendations.
  2. The interaction write path — without it, collaborative filtering can never
     populate, so `recommend()` always falls back to content-based.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.academics.models import (
    AcademicYear,
    Enrollment,
    GradeLevel,
    GradingPeriod,
    Section,
)
from apps.cms.models import LearningItem, StudentInteraction

User = get_user_model()


class RecommendationsTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.academic_year = AcademicYear.objects.create(
            name="2024-2025",
            start_date=date(2024, 6, 10),
            end_date=date(2025, 3, 25),
            is_current=True,
        )
        self.grade_level = GradeLevel.objects.create(
            name="Grade 10", level_number=10
        )
        self.section = Section.objects.create(
            name="Newton", grade_level=self.grade_level, academic_year=self.academic_year
        )
        # A completed period, so compute_student_features has real input.
        GradingPeriod.objects.create(
            academic_year=self.academic_year,
            name="1st Quarter",
            order=1,
            start_date=date(2024, 6, 10),
            end_date=date(2024, 8, 20),
        )

        self.student_user = User.objects.create_user(
            email="rec_student@test.com",
            password="pass12345",
            first_name="Rec",
            last_name="Student",
            role="student",
        )
        self.student = self._make_student(self.student_user, "REC001")

        self.other_user = User.objects.create_user(
            email="rec_other@test.com",
            password="pass12345",
            first_name="Other",
            last_name="Student",
            role="student",
        )
        self.other_student = self._make_student(self.other_user, "REC002")

        self.parent_user = User.objects.create_user(
            email="rec_parent@test.com",
            password="pass12345",
            first_name="Rec",
            last_name="Parent",
            role="parent",
        )
        from apps.accounts.models import ParentProfile, ParentStudentLink

        self.parent_profile = ParentProfile.objects.create(
            user=self.parent_user,
            relationship_to_student=ParentProfile.RelationshipType.MOTHER,
        )
        ParentStudentLink.objects.create(
            parent=self.parent_profile, student=self.student
        )

        self.unrelated_parent_user = User.objects.create_user(
            email="rec_stranger@test.com",
            password="pass12345",
            first_name="Un",
            last_name="Parent",
            role="parent",
        )
        self.unrelated_parent = ParentProfile.objects.create(
            user=self.unrelated_parent_user,
            relationship_to_student=ParentProfile.RelationshipType.MOTHER,
        )

        self.guidance_user = User.objects.create_user(
            email="rec_guidance@test.com",
            password="pass12345",
            first_name="Rec",
            last_name="Guidance",
            role="guidance",
        )

        self.admin_user = User.objects.create_user(
            email="rec_admin@test.com",
            password="pass12345",
            first_name="Rec",
            last_name="Admin",
            role="admin",
        )

    def _make_student(self, user, student_id):
        from apps.accounts.models import StudentProfile

        sp = StudentProfile.objects.create(
            user=user,
            student_id=student_id,
            grade_level=self.grade_level,
            section=self.section,
            enrollment_date=date(2024, 6, 10),
        )
        Enrollment.objects.create(
            student=sp,
            section=self.section,
            academic_year=self.academic_year,
            date_enrolled=date(2024, 6, 10),
            is_active=True,
        )
        return sp

    def _make_item(self, title, *, approved=True, active=True):
        return LearningItem.objects.create(
            item_type=LearningItem.ItemType.LEARNING_RESOURCE,
            title=title,
            lifecycle_status=(
                LearningItem.LifecycleStatus.APPROVED
                if approved
                else LearningItem.LifecycleStatus.DRAFT
            ),
            is_active=active,
            grade_level=self.grade_level,
        )

    def _auth(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


class StudentRecommendationsAuthorizationTest(RecommendationsTestBase):
    """
    The ladder matches `_StudentScopedAnalyticsView`, so a caller cannot read a
    student's metrics but be denied their recommendations, or the reverse.
    """

    def test_student_reads_own_recommendations(self):
        self._make_item("Algebra practice")
        self._auth(self.student_user)

        response = self.client.get(f"/api/v1/recommendations/students/{self.student.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")
        self.assertIn("method", response.data["data"])

    def test_student_cannot_read_another_student(self):
        self._auth(self.student_user)

        response = self.client.get(
            f"/api/v1/recommendations/students/{self.other_student.id}/"
        )

        self.assertEqual(response.status_code, 403)

    def test_parent_reads_linked_child(self):
        self._make_item("Algebra practice")
        self._auth(self.parent_user)

        response = self.client.get(f"/api/v1/recommendations/students/{self.student.id}/")

        self.assertEqual(response.status_code, 200)

    def test_parent_cannot_read_unlinked_child(self):
        self._auth(self.unrelated_parent_user)

        response = self.client.get(f"/api/v1/recommendations/students/{self.student.id}/")

        self.assertEqual(response.status_code, 403)

    def test_guidance_and_admin_are_denied(self):
        """
        Recommendations go to the student and family. The staff-facing risk
        surface is RiskAlert, with its own acknowledge/escalate lifecycle;
        this endpoint would be a second read-only view of the same signal.
        """
        for user in (self.guidance_user, self.admin_user):
            with self.subTest(role=user.role):
                self._auth(user)
                response = self.client.get(
                    f"/api/v1/recommendations/students/{self.student.id}/"
                )
                self.assertEqual(response.status_code, 403)

    def test_faculty_is_denied(self):
        faculty_user = User.objects.create_user(
            email="rec_faculty@test.com",
            password="pass12345",
            first_name="Rec",
            last_name="Faculty",
            role="faculty",
        )
        self._auth(faculty_user)

        response = self.client.get(f"/api/v1/recommendations/students/{self.student.id}/")

        self.assertEqual(response.status_code, 403)

    def test_anonymous_is_rejected(self):
        response = self.client.get(f"/api/v1/recommendations/students/{self.student.id}/")

        self.assertEqual(response.status_code, 401)

    def test_unknown_student_is_404(self):
        self._auth(self.student_user)

        response = self.client.get(
            "/api/v1/recommendations/students/00000000-0000-0000-0000-000000000000/"
        )

        self.assertEqual(response.status_code, 404)


class RecommendationEligibilityTest(RecommendationsTestBase):
    """Only APPROVED + ACTIVE items may enter the candidate pool."""

    def test_only_approved_and_active_items_are_recommended(self):
        self._make_item("Approved and active")
        self._make_item("Draft item", approved=False)
        self._make_item("Approved but inactive", active=False)

        self._auth(self.student_user)
        response = self.client.get(f"/api/v1/recommendations/students/{self.student.id}/")

        self.assertEqual(response.status_code, 200)
        titles = [r["title"] for r in response.data["data"]["recommendations"]]
        self.assertEqual(titles, ["Approved and active"])

    def test_no_eligible_items_returns_empty_not_an_error(self):
        """
        An empty pool is a real state, not a failure. It must not be padded with
        invented recommendations.
        """
        self._auth(self.student_user)

        response = self.client.get(f"/api/v1/recommendations/students/{self.student.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["recommendations"], [])

    def test_method_is_reported(self):
        """
        CF and content-based are materially different claims. A caller showing
        these to a student needs to know which produced the list.
        """
        self._make_item("Algebra practice")
        self._auth(self.student_user)

        response = self.client.get(f"/api/v1/recommendations/students/{self.student.id}/")

        self.assertIn(response.data["data"]["method"], ("cf", "content_based"))


class StudentInteractionWriteTest(RecommendationsTestBase):
    """
    The only write path into the CF signal.

    Without it `recommend()` always falls back to content-based, because
    `check_eligibility` requires 5 interactions across 3 distinct items from at
    least 3 students.
    """

    def test_student_records_an_interaction(self):
        item = self._make_item("Algebra practice")
        self._auth(self.student_user)

        response = self.client.post(
            "/api/v1/recommendations/interactions/",
            {"learning_item": str(item.id), "interaction_type": "completed"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            StudentInteraction.objects.filter(
                student=self.student, learning_item=item
            ).exists()
        )

    def test_all_four_interaction_types_are_accepted(self):
        item = self._make_item("Algebra practice")
        self._auth(self.student_user)

        for interaction_type in ("viewed", "started", "saved", "completed"):
            with self.subTest(interaction_type=interaction_type):
                response = self.client.post(
                    "/api/v1/recommendations/interactions/",
                    {
                        "learning_item": str(item.id),
                        "interaction_type": interaction_type,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 201)

    def test_staff_cannot_write_interactions_for_a_student(self):
        """
        A preference signal attributed to someone who did not express it
        corrupts the interaction matrix.
        """
        item = self._make_item("Algebra practice")

        for user in (self.guidance_user, self.admin_user):
            with self.subTest(role=user.role):
                self._auth(user)
                response = self.client.post(
                    "/api/v1/recommendations/interactions/",
                    {"learning_item": str(item.id), "interaction_type": "viewed"},
                    format="json",
                )
                self.assertEqual(response.status_code, 403)

    def test_parent_cannot_write_interactions(self):
        item = self._make_item("Algebra practice")
        self._auth(self.parent_user)

        response = self.client.post(
            "/api/v1/recommendations/interactions/",
            {"learning_item": str(item.id), "interaction_type": "viewed"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_unapproved_item_is_refused(self):
        """
        Recording an interaction with an unapproved item would put it in the CF
        matrix while the recommender will never surface it, so the similarity
        signal would derive from something the system will not show.
        """
        item = self._make_item("Draft item", approved=False)
        self._auth(self.student_user)

        response = self.client.post(
            "/api/v1/recommendations/interactions/",
            {"learning_item": str(item.id), "interaction_type": "viewed"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(StudentInteraction.objects.exists())

    def test_inactive_item_is_refused(self):
        item = self._make_item("Inactive item", active=False)
        self._auth(self.student_user)

        response = self.client.post(
            "/api/v1/recommendations/interactions/",
            {"learning_item": str(item.id), "interaction_type": "viewed"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_missing_learning_item_is_400(self):
        self._auth(self.student_user)

        response = self.client.post(
            "/api/v1/recommendations/interactions/",
            {"interaction_type": "viewed"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_interaction_type_is_400(self):
        item = self._make_item("Algebra practice")
        self._auth(self.student_user)

        response = self.client.post(
            "/api/v1/recommendations/interactions/",
            {"learning_item": str(item.id), "interaction_type": "graded_it"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_unknown_learning_item_is_404(self):
        self._auth(self.student_user)

        response = self.client.post(
            "/api/v1/recommendations/interactions/",
            {
                "learning_item": "00000000-0000-0000-0000-000000000000",
                "interaction_type": "viewed",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_anonymous_cannot_write(self):
        item = self._make_item("Algebra practice")

        response = self.client.post(
            "/api/v1/recommendations/interactions/",
            {"learning_item": str(item.id), "interaction_type": "viewed"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)


class CollaborativeFilteringBecomesReachableTest(RecommendationsTestBase):
    """
    With enough real interaction data, `recommend()` must report method="cf"
    instead of falling back to content-based.

    This is the D19 threshold check working through the endpoint: 5
    interactions across 3 distinct items per student, and 3 students per item.
    """

    def _seed_cf_cohort(self):
        items = [self._make_item(f"Item {i}") for i in range(4)]

        # Three peers who have engaged with every item, including the fourth.
        peers = [self.other_student]
        for index in range(2):
            peer_user = User.objects.create_user(
                email=f"rec_peer{index}@test.com",
                password="pass12345",
                first_name=f"Peer{index}",
                last_name="Student",
                role="student",
            )
            peers.append(self._make_student(peer_user, f"REC10{index}"))

        for peer in peers:
            for item in items:
                for interaction_type in ("viewed", "started"):
                    StudentInteraction.objects.create(
                        student=peer,
                        learning_item=item,
                        interaction_type=interaction_type,
                        interaction_at=timezone.now() - timedelta(days=1),
                    )

        # The student under test has engaged with the first three only, so the
        # fourth is an unseen candidate with peer support behind it.
        for item in items[:3]:
            for interaction_type in ("viewed", "started"):
                StudentInteraction.objects.create(
                    student=self.student,
                    learning_item=item,
                    interaction_type=interaction_type,
                    interaction_at=timezone.now() - timedelta(days=1),
                )

        return items[3]

    def test_cf_is_used_once_the_thresholds_are_met(self):
        candidate = self._seed_cf_cohort()
        self._auth(self.student_user)

        response = self.client.get(f"/api/v1/recommendations/students/{self.student.id}/")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["method"], "cf")
        self.assertFalse(data["fallback_used"])
        self.assertIn(
            str(candidate.id),
            [r["learning_item_id"] for r in data["recommendations"]],
        )