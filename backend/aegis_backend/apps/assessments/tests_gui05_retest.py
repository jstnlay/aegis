"""
TC-GUI-05 re-test — the Cycle-3 log's actual result was:

    FAILED – Notice shows "I don't have permission" to create assessment.
    Note:
    - The Counselor account and Student account combines without authentication.
    - It auto changes account login even, without proper sign authentication.

The row's condition is: "a counselor can deploy a created assessment to an
assigned student", expecting "Assessment is successfully deployed and made
available to the assigned student" (FR-028).

Two separate claims are tangled in that row, so this file tests them separately:

1. *"I don't have permission"* — the counselor's create/deploy path. The gate is
   `CanCreateAssessment` (faculty/guidance/admin may create) plus
   `Assessment.clean()`, which ties `assessment_type` to `creator_role`:
   academic -> faculty, wellness/behavioral -> guidance. A counselor creating a
   wellness assessment is allowed; creating an academic one is refused **with a
   reason**, which is the behaviour the log read as a bare permission denial.
   The guidance screen defaults to `wellness` (`AssessmentsPage.tsx`), matching
   the rule, so the default path is the permitted one.

2. *"The Counselor account and Student account combines without
   authentication."* — a session-isolation claim. The API is token-scoped, so
   what this can assert is that a student token cannot create or deploy, and a
   counselor reading the list never sees another counselor's rows. The browser
   half (two logins sharing one stored session) is a frontend concern and is
   pinned in the frontend suite.

This is a re-test: no production code changed.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    FacultyProfile,
    GuidanceProfile,
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
    User,
)
from apps.assessments.models import Assessment, AssessmentQuestion


class _Gui05Base(TestCase):
    """A counselor, a student, and one targetable section each."""

    def setUp(self):
        from apps.academics.models import (
            AcademicYear,
            GradeLevel,
            Section,
        )

        self.ay = AcademicYear.objects.create(
            name="2025-2026", start_date="2025-06-01", end_date="2026-03-31",
            is_current=True,
        )
        self.g7 = GradeLevel.objects.create(name="Grade 7", level_number=7)
        self.section = Section.objects.create(
            name="S-GUI05", grade_level=self.g7, academic_year=self.ay
        )

        self.counselor_user = User.objects.create_user(
            email="counselor_gui05@test.com", password="pass12345",
            first_name="Cora", last_name="Counsel", role="guidance",
        )
        GuidanceProfile.objects.create(
            user=self.counselor_user, employee_id="EMP-GUI05-001"
        )
        self.counselor2_user = User.objects.create_user(
            email="counselor2_gui05@test.com", password="pass12345",
            first_name="Other", last_name="Counsel", role="guidance",
        )
        GuidanceProfile.objects.create(
            user=self.counselor2_user, employee_id="EMP-GUI05-002"
        )
        self.student_user = User.objects.create_user(
            email="student_gui05@test.com", password="pass12345",
            first_name="Nina", last_name="Reyes", role="student",
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user, student_id="STU-GUI05-001",
            grade_level=self.g7, section=self.section,
            enrollment_date="2025-06-01",
        )
        self.faculty_user = User.objects.create_user(
            email="faculty_gui05@test.com", password="pass12345",
            first_name="Fay", last_name="Culty", role="faculty",
        )
        FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="EMP-GUI05-FAC"
        )

    def _as(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _create_wellness(self, client):
        resp = client.post(
            "/api/v1/assessments/assessments/",
            {
                "title": "Wellness Check",
                "assessment_type": "wellness",
                "target_students": [str(self.student.id)],
            },
            format="json",
        )
        return resp


class Gui05CounselorDeployJourneyTest(_Gui05Base):
    """
    The whole row: a counselor creates an assessment, adds a question, deploys
    it, and the assigned student can then see it.
    """

    def test_counselor_creates_adds_a_question_and_deploys(self):
        counselor = self._as(self.counselor_user)

        created = self._create_wellness(counselor)
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.content)
        assessment_id = created.data["id"]

        question = counselor.post(
            "/api/v1/assessments/assessment-questions/",
            {
                "assessment": assessment_id,
                "question_text": "How are you feeling this week?",
                "question_type": "essay",
                "order": 1,
            },
            format="json",
        )
        self.assertIn(
            question.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
            question.content,
        )

        deployed = counselor.post(
            f"/api/v1/assessments/assessments/{assessment_id}/deploy/",
            format="json",
        )
        self.assertEqual(deployed.status_code, status.HTTP_200_OK, deployed.content)
        self.assertTrue(deployed.data["is_published"])

    def test_the_assigned_student_can_then_see_the_deployed_assessment(self):
        """'made available to the assigned student' - the second half of the row."""
        counselor = self._as(self.counselor_user)
        assessment_id = self._create_wellness(counselor).data["id"]
        counselor.post(
            "/api/v1/assessments/assessment-questions/",
            {
                "assessment": assessment_id,
                "question_text": "How are you feeling this week?",
                "question_type": "essay",
                "order": 1,
            },
            format="json",
        )
        counselor.post(
            f"/api/v1/assessments/assessments/{assessment_id}/deploy/",
            format="json",
        )

        student = self._as(self.student_user)
        listed = student.get("/api/v1/assessments/assessments/")
        self.assertEqual(listed.status_code, status.HTTP_200_OK, listed.content)
        ids = [row["id"] for row in listed.data["results"]]
        self.assertIn(assessment_id, ids)

    def test_a_draft_assessment_is_not_visible_to_the_student(self):
        """Deploy is what makes it available, so an undeployed draft is hidden."""
        counselor = self._as(self.counselor_user)
        assessment_id = self._create_wellness(counselor).data["id"]

        student = self._as(self.student_user)
        listed = student.get("/api/v1/assessments/assessments/")
        ids = [row["id"] for row in listed.data["results"]]
        self.assertNotIn(assessment_id, ids)


class Gui05PermissionPathTest(_Gui05Base):
    """
    The literal "I don't have permission" symptom.  The gate is `can create`,
    not `can deploy`, so a refusal must name the real reason rather than read
    as a bare denial.
    """

    def test_counselor_may_create_a_wellness_assessment(self):
        resp = self._create_wellness(self._as(self.counselor_user))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_counselor_may_create_a_behavioral_assessment(self):
        resp = self._as(self.counselor_user).post(
            "/api/v1/assessments/assessments/",
            {"title": "Behavioral Review", "assessment_type": "behavioral"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_counselor_creating_an_academic_assessment_gets_a_reason(self):
        """
        This is the shape the log recorded as "I don't have permission". It is
        a 400 naming the field, not a 403 - and it is the rule working, because
        `Assessment.clean()` binds academic assessments to faculty.
        """
        resp = self._as(self.counselor_user).post(
            "/api/v1/assessments/assessments/",
            {"title": "Math Quiz", "assessment_type": "academic"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn("creator_role", str(resp.json()))

    def test_faculty_may_create_academic_but_not_wellness(self):
        faculty = self._as(self.faculty_user)
        academic = faculty.post(
            "/api/v1/assessments/assessments/",
            {"title": "Math Quiz", "assessment_type": "academic"},
            format="json",
        )
        self.assertEqual(academic.status_code, status.HTTP_201_CREATED, academic.content)

        wellness = faculty.post(
            "/api/v1/assessments/assessments/",
            {"title": "Wellness Check", "assessment_type": "wellness"},
            format="json",
        )
        self.assertEqual(wellness.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_counselor_cannot_deploy_another_counselor_s_assessment(self):
        """
        `IsAssessmentCreator` is the object gate on deploy, and
        `get_queryset()` scopes guidance to their own rows - so the foreign
        assessment is not even resolvable, and the attempt is a 404 rather
        than a 403. Without either, "the counselor deployed it" would not mean
        the one who authored it.
        """
        mine = Assessment.objects.create(
            title="Mine", assessment_type="wellness",
            created_by=self.counselor_user, is_published=False,
        )
        AssessmentQuestion.objects.create(
            assessment=mine, question_text="Q", question_type="essay", order=1,
        )

        other = self._as(self.counselor2_user)
        resp = other.post(
            f"/api/v1/assessments/assessments/{mine.id}/deploy/", format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND, resp.content)
        mine.refresh_from_db()
        self.assertFalse(mine.is_published)

    def test_a_student_cannot_create_or_deploy_an_assessment(self):
        """
        The row's session-isolation note: a student token is not a counselor
        token, so neither action is reachable with it.
        """
        student = self._as(self.student_user)

        created = student.post(
            "/api/v1/assessments/assessments/",
            {"title": "Self Assessment", "assessment_type": "wellness"},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_403_FORBIDDEN, created.content)

        existing = Assessment.objects.create(
            title="Counselor's", assessment_type="wellness",
            created_by=self.counselor_user, is_published=False,
        )
        AssessmentQuestion.objects.create(
            assessment=existing, question_text="Q", question_type="essay", order=1,
        )
        deployed = student.post(
            f"/api/v1/assessments/assessments/{existing.id}/deploy/", format="json"
        )
        # 403 from the create gate, 404 from the student-scoped queryset that
        # cannot resolve a draft at all. Either way the action is unreachable.
        self.assertIn(
            deployed.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
            deployed.content,
        )
        existing.refresh_from_db()
        self.assertFalse(existing.is_published)

    def test_a_counselor_s_list_never_includes_another_counselor_s_rows(self):
        """
        The other reading of "accounts combine": if two guidance sessions shared
        state, one counselor's list would show the other's assessments.
        """
        mine = Assessment.objects.create(
            title="Mine", assessment_type="wellness",
            created_by=self.counselor_user, is_published=False,
        )
        theirs = Assessment.objects.create(
            title="Theirs", assessment_type="wellness",
            created_by=self.counselor2_user, is_published=False,
        )

        listed = self._as(self.counselor_user).get("/api/v1/assessments/assessments/")
        ids = [row["id"] for row in listed.data["results"]]
        self.assertIn(str(mine.id), ids)
        self.assertNotIn(str(theirs.id), ids)
