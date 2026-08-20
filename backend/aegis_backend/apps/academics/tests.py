"""
Phase 2 test suite for AEGIS Academics.

Covers: model validation, serializers, API endpoints, scoped querysets,
role-based permissions, grade lifecycle, and data-scope authorization.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    FacultyProfile,
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
)
from apps.academics.models import (
    AcademicYear,
    Enrollment,
    Grade,
    GradeLevel,
    GradingPeriod,
    Schedule,
    Section,
    Subject,
    SubjectAssignment,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class AcademicsTestBase(TestCase):
    """Shared setUp for academics tests."""

    def setUp(self):
        # --- Users ---
        self.admin_user = User.objects.create_user(
            email="admin_aca@test.com", password="pass12345",
            first_name="Admin", last_name="User", role="admin",
        )
        self.faculty_user = User.objects.create_user(
            email="faculty_aca@test.com", password="pass12345",
            first_name="Fac", last_name="ulty", role="faculty",
        )
        self.faculty2_user = User.objects.create_user(
            email="faculty2_aca@test.com", password="pass12345",
            first_name="Fac2", last_name="ulty2", role="faculty",
        )
        self.student_user = User.objects.create_user(
            email="student_aca@test.com", password="pass12345",
            first_name="Stu", last_name="dent", role="student",
        )
        self.student2_user = User.objects.create_user(
            email="student2_aca@test.com", password="pass12345",
            first_name="Stu2", last_name="dent2", role="student",
        )
        self.parent_user = User.objects.create_user(
            email="parent_aca@test.com", password="pass12345",
            first_name="Par", last_name="ent", role="parent",
        )
        self.guidance_user = User.objects.create_user(
            email="guidance_aca@test.com", password="pass12345",
            first_name="Guid", last_name="ance", role="guidance",
        )

        # --- Profiles ---
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="EMP-001", department="Math",
        )
        self.faculty2_profile = FacultyProfile.objects.create(
            user=self.faculty2_user, employee_id="EMP-002", department="Science",
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user, student_id="STU-001", enrollment_date="2025-06-01",
        )
        self.student2_profile = StudentProfile.objects.create(
            user=self.student2_user, student_id="STU-002", enrollment_date="2025-06-01",
        )
        self.parent_profile = ParentProfile.objects.create(
            user=self.parent_user, relationship_to_student="mother",
        )
        ParentStudentLink.objects.create(
            parent=self.parent_profile, student=self.student_profile, is_primary=True,
        )

        # --- Academic structure ---
        self.ay = AcademicYear.objects.create(
            name="2025-2026", start_date="2025-06-01",
            end_date="2026-03-31", is_current=True,
        )
        self.g7 = GradeLevel.objects.create(name="Grade 7", level_number=7)
        self.g8 = GradeLevel.objects.create(name="Grade 8", level_number=8)

        self.section_a = Section.objects.create(
            name="Einstein", grade_level=self.g7, academic_year=self.ay,
            adviser=self.faculty_profile,
        )
        self.section_b = Section.objects.create(
            name="Newton", grade_level=self.g8, academic_year=self.ay,
        )

        self.math = Subject.objects.create(name="Mathematics", code="MATH7", grade_level=self.g7)
        self.science = Subject.objects.create(name="Science", code="SCI7", grade_level=self.g7)

        self.sa_math = SubjectAssignment.objects.create(
            subject=self.math, faculty=self.faculty_profile,
            section=self.section_a, academic_year=self.ay,
        )
        self.sa_science = SubjectAssignment.objects.create(
            subject=self.science, faculty=self.faculty2_profile,
            section=self.section_a, academic_year=self.ay,
        )

        self.schedule1 = Schedule.objects.create(
            subject_assignment=self.sa_math,
            day_of_week="mon", start_time="08:00", end_time="09:00", room="R101",
        )

        self.gp1 = GradingPeriod.objects.create(
            academic_year=self.ay, name="1st Quarter", order=1,
            start_date="2025-06-01", end_date="2025-08-31",
        )
        self.gp2 = GradingPeriod.objects.create(
            academic_year=self.ay, name="2nd Quarter", order=2,
            start_date="2025-09-01", end_date="2025-11-30",
        )

        self.enrollment1 = Enrollment.objects.create(
            student=self.student_profile, section=self.section_a,
            academic_year=self.ay, date_enrolled="2025-06-01",
        )
        self.enrollment2 = Enrollment.objects.create(
            student=self.student2_profile, section=self.section_b,
            academic_year=self.ay, date_enrolled="2025-06-01",
        )

        # Update student profiles to reflect section assignment
        self.student_profile.section = self.section_a
        self.student_profile.grade_level = self.g7
        self.student_profile.save()
        self.student2_profile.section = self.section_b
        self.student2_profile.grade_level = self.g8
        self.student2_profile.save()

        self.grade1 = Grade.objects.create(
            student=self.student_profile, subject_assignment=self.sa_math,
            grading_period=self.gp1, score=Decimal("85.50"),
            encoded_by=self.faculty_profile, status=Grade.StatusChoices.DRAFT,
        )

        self.client = APIClient()


# ===========================================================================
# Model tests
# ===========================================================================


class AcademicYearModelTest(AcademicsTestBase):
    def test_str(self):
        self.assertEqual(str(self.ay), "2025-2026")

    def test_clean_end_before_start_raises(self):
        ay = AcademicYear(
            name="Bad", start_date="2026-01-01", end_date="2025-01-01",
        )
        with self.assertRaises(ValidationError) as ctx:
            ay.clean()
        self.assertIn("end_date", ctx.exception.message_dict)


class GradeLevelModelTest(AcademicsTestBase):
    def test_str(self):
        self.assertEqual(str(self.g7), "Grade 7")

    def test_ordering(self):
        levels = list(GradeLevel.objects.values_list("level_number", flat=True))
        self.assertEqual(levels, sorted(levels))


class SectionModelTest(AcademicsTestBase):
    def test_str(self):
        self.assertIn("Einstein", str(self.section_a))

    def test_unique_together(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Section.objects.create(
                name="Einstein", grade_level=self.g7, academic_year=self.ay,
            )


class SubjectModelTest(AcademicsTestBase):
    def test_str(self):
        self.assertIn("MATH7", str(self.math))

    def test_code_unique(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Subject.objects.create(name="Math 2", code="MATH7", grade_level=self.g7)


class SubjectAssignmentModelTest(AcademicsTestBase):
    def test_str(self):
        self.assertIn("Mathematics", str(self.sa_math))

    def test_unique_together(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            SubjectAssignment.objects.create(
                subject=self.math, faculty=self.faculty_profile,
                section=self.section_a, academic_year=self.ay,
            )


class ScheduleModelTest(AcademicsTestBase):
    def test_str(self):
        self.assertIn("Monday", str(self.schedule1))

    def test_clean_end_before_start_raises(self):
        s = Schedule(
            subject_assignment=self.sa_math,
            day_of_week="tue", start_time="09:00", end_time="08:00",
        )
        with self.assertRaises(ValidationError):
            s.clean()


class GradingPeriodModelTest(AcademicsTestBase):
    def test_str(self):
        self.assertIn("1st Quarter", str(self.gp1))

    def test_clean_end_before_start_raises(self):
        gp = GradingPeriod(
            academic_year=self.ay, name="Bad", order=99,
            start_date="2026-01-01", end_date="2025-01-01",
        )
        with self.assertRaises(ValidationError):
            gp.clean()


class EnrollmentModelTest(AcademicsTestBase):
    def test_str(self):
        self.assertIn("STU-001", str(self.enrollment1))

    def test_unique_together(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Enrollment.objects.create(
                student=self.student_profile, section=self.section_a,
                academic_year=self.ay, date_enrolled="2025-06-01",
            )


class GradeModelTest(AcademicsTestBase):
    def test_str(self):
        s = str(self.grade1)
        self.assertIn("85.50", s)

    def test_score_validation(self):
        g = Grade(
            student=self.student_profile, subject_assignment=self.sa_math,
            grading_period=self.gp1, score=Decimal("150.00"),
            encoded_by=self.faculty_profile, status=Grade.StatusChoices.DRAFT,
        )
        with self.assertRaises(ValidationError):
            g.full_clean()

    def test_unique_together(self):
        with self.assertRaises(ValidationError):
            Grade.objects.create(
                student=self.student_profile, subject_assignment=self.sa_math,
                grading_period=self.gp1, score=Decimal("90.00"),
                encoded_by=self.faculty_profile, status=Grade.StatusChoices.DRAFT,
            )


# ===========================================================================
# API tests — Authentication required
# ===========================================================================


class AcademicsUnauthenticatedTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_list_academic_years_unauthenticated(self):
        response = self.client.get("/api/v1/academics/academic-years/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_grades_unauthenticated(self):
        response = self.client.get("/api/v1/academics/grades/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ===========================================================================
# API tests — Admin full CRUD
# ===========================================================================


class AdminAcademicYearCRUDTest(AcademicsTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.admin_user)}"
        )

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken

        return str(RefreshToken.for_user(user).access_token)

    def test_list_academic_years(self):
        response = self.client.get("/api/v1/academics/academic-years/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_create_academic_year(self):
        response = self.client.post(
            "/api/v1/academics/academic-years/",
            {
                "name": "2026-2027",
                "start_date": "2026-06-01",
                "end_date": "2027-03-31",
                "is_current": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(AcademicYear.objects.count(), 2)

    def test_update_academic_year(self):
        response = self.client.patch(
            f"/api/v1/academics/academic-years/{self.ay.id}/",
            {"name": "2025-2026 Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.ay.refresh_from_db()
        self.assertEqual(self.ay.name, "2025-2026 Updated")

    def test_delete_academic_year(self):
        ay2 = AcademicYear.objects.create(
            name="2024-2025", start_date="2024-06-01", end_date="2025-03-31",
        )
        response = self.client.delete(f"/api/v1/academics/academic-years/{ay2.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


# ===========================================================================
# API tests — Faculty read-only on admin-managed resources
# ===========================================================================


class FacultyReadOnlyTest(AcademicsTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)

    def test_list_academic_years(self):
        response = self.client.get("/api/v1/academics/academic-years/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_academic_year_forbidden(self):
        response = self.client.post(
            "/api/v1/academics/academic-years/",
            {"name": "Bad", "start_date": "2025-01-01", "end_date": "2025-12-31"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_subject_forbidden(self):
        response = self.client.post(
            "/api/v1/academics/subjects/",
            {"name": "Bad", "code": "BAD", "grade_level": self.g7.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ===========================================================================
# API tests — Faculty scoped queryset
# ===========================================================================


class FacultyScopedQuerysetTest(AcademicsTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)

    def test_faculty_sees_own_subject_assignments(self):
        response = self.client.get("/api/v1/academics/subject-assignments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in response.data["results"]]
        self.assertIn(str(self.sa_math.id), ids)
        self.assertNotIn(str(self.sa_science.id), ids)

    def test_faculty_sees_own_schedules(self):
        response = self.client.get("/api/v1/academics/schedules/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_faculty_sees_own_grades(self):
        response = self.client.get("/api/v1/academics/grades/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_faculty_sees_own_enrollments(self):
        response = self.client.get("/api/v1/academics/enrollments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 1)


# ===========================================================================
# API tests — Student scoped queryset
# ===========================================================================


class StudentScopedQuerysetTest(AcademicsTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.student_user)}"
        )

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)

    def test_student_sees_own_grades_only(self):
        response = self.client.get("/api/v1/academics/grades/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_student_sees_own_section_in_sections(self):
        response = self.client.get("/api/v1/academics/sections/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in response.data["results"]]
        self.assertIn(str(self.section_a.id), ids)
        self.assertNotIn(str(self.section_b.id), ids)

    def test_student_sees_own_enrollments(self):
        response = self.client.get("/api/v1/academics/enrollments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)


# ===========================================================================
# API tests — Parent scoped queryset
# ===========================================================================


class ParentScopedQuerysetTest(AcademicsTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.parent_user)}"
        )

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)

    def test_parent_sees_linked_child_grades(self):
        response = self.client.get("/api/v1/academics/grades/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_parent_sees_linked_child_enrollments(self):
        response = self.client.get("/api/v1/academics/enrollments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_parent_does_not_see_other_student(self):
        # Create grade for student2
        Grade.objects.create(
            student=self.student2_profile, subject_assignment=self.sa_science,
            grading_period=self.gp1, score=Decimal("75.00"),
            encoded_by=self.faculty2_profile, status=Grade.StatusChoices.DRAFT,
        )
        response = self.client.get("/api/v1/academics/grades/")
        self.assertEqual(response.data["count"], 1)


# ===========================================================================
# API tests — Grade encode action
# ===========================================================================


class GradeEncodeActionTest(AcademicsTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)

    def test_encode_grade_success(self):
        response = self.client.post(
            "/api/v1/academics/grades/encode/",
            {
                "student": str(self.student2_profile.id),
                "subject_assignment": str(self.sa_math.id),
                "grading_period": str(self.gp2.id),
                "score": "92.50",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Grade.objects.count(), 2)

    def test_encode_grade_wrong_faculty(self):
        """Faculty cannot encode for another faculty's subject assignment."""
        response = self.client.post(
            "/api/v1/academics/grades/encode/",
            {
                "student": str(self.student_profile.id),
                "subject_assignment": str(self.sa_science.id),
                "grading_period": str(self.gp1.id),
                "score": "80.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_encode_grade_duplicate(self):
        response = self.client.post(
            "/api/v1/academics/grades/encode/",
            {
                "student": str(self.student_profile.id),
                "subject_assignment": str(self.sa_math.id),
                "grading_period": str(self.gp1.id),
                "score": "90.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_encode_grade_invalid_score(self):
        response = self.client.post(
            "/api/v1/academics/grades/encode/",
            {
                "student": str(self.student2_profile.id),
                "subject_assignment": str(self.sa_math.id),
                "grading_period": str(self.gp2.id),
                "score": "150.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_encode_grade_student_not_found(self):
        import uuid

        response = self.client.post(
            "/api/v1/academics/grades/encode/",
            {
                "student": str(uuid.uuid4()),
                "subject_assignment": str(self.sa_math.id),
                "grading_period": str(self.gp2.id),
                "score": "80.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ===========================================================================
# API tests — Grade finalize action
# ===========================================================================


class GradeFinalizeActionTest(AcademicsTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.admin_user)}"
        )

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)

    def test_finalize_submitted_grade(self):
        self.grade1.status = Grade.StatusChoices.SUBMITTED
        self.grade1.save()
        response = self.client.post(
            f"/api/v1/academics/grades/{self.grade1.id}/finalize/",
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.grade1.refresh_from_db()
        self.assertEqual(self.grade1.status, Grade.StatusChoices.FINALIZED)

    def test_finalize_draft_grade_fails(self):
        response = self.client.post(
            f"/api/v1/academics/grades/{self.grade1.id}/finalize/",
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_faculty_cannot_finalize(self):
        self.grade1.status = Grade.StatusChoices.SUBMITTED
        self.grade1.save()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )
        response = self.client.post(
            f"/api/v1/academics/grades/{self.grade1.id}/finalize/",
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)


# ===========================================================================
# API tests — Batch import placeholder
# ===========================================================================


class GradeBatchImportTest(AcademicsTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)

    def test_batch_import_returns_501(self):
        response = self.client.post(
            "/api/v1/academics/grades/batch-import/",
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)


# ===========================================================================
# API tests — Grade query parameter filtering (A6)
# ===========================================================================


class GradeFilteringTest(AcademicsTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.admin_user)}"
        )

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)

    def test_filter_by_student(self):
        response = self.client.get(
            f"/api/v1/academics/grades/?student={self.student_profile.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_filter_by_grading_period(self):
        response = self.client.get(
            f"/api/v1/academics/grades/?grading_period={self.gp1.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_filter_by_status(self):
        response = self.client.get("/api/v1/academics/grades/?status=draft")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_filter_by_subject_assignment(self):
        response = self.client.get(
            f"/api/v1/academics/grades/?subject_assignment={self.sa_math.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)


# ===========================================================================
# API tests — Guidance can read all
# ===========================================================================


class GuidanceReadOnlyTest(AcademicsTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)

    def test_guidance_sees_all_grades(self):
        response = self.client.get("/api/v1/academics/grades/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_guidance_cannot_create_academic_year(self):
        response = self.client.post(
            "/api/v1/academics/academic-years/",
            {"name": "Bad", "start_date": "2025-01-01", "end_date": "2025-12-31"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
