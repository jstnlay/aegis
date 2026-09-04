"""
Phase 9 analytics app tests.

Covers: aggregation services, RBAC, admin anonymization, student privacy.
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
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
    Enrollment,
    Grade,
    GradeLevel,
    GradingPeriod,
    Section,
    Subject,
    SubjectAssignment,
)
from apps.guidance.models import RiskAlert, RiskScore

User = get_user_model()


class AnalyticsTestBase(TestCase):
    """Shared setUp for analytics tests."""

    def setUp(self):
        self.client = APIClient()

        # --- Roles ---
        self.admin_user = User.objects.create_user(
            email="admin_an@test.com", password="pass12345",
            first_name="Admin", last_name="An", role="admin",
        )
        self.faculty_user = User.objects.create_user(
            email="faculty_an@test.com", password="pass12345",
            first_name="Fac", last_name="An", role="faculty",
        )
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="FAN001"
        )
        self.guidance_user = User.objects.create_user(
            email="guidance_an@test.com", password="pass12345",
            first_name="Gui", last_name="An", role="guidance",
        )
        self.guidance_profile = GuidanceProfile.objects.create(
            user=self.guidance_user, employee_id="GAN001"
        )
        self.student_user = User.objects.create_user(
            email="student_an@test.com", password="pass12345",
            first_name="Stu", last_name="An", role="student",
        )
        self.grade_level = GradeLevel.objects.create(
            name="Grade 7", level_number=7
        )
        self.academic_year = AcademicYear.objects.create(
            name="2024-2025",
            start_date=date(2024, 6, 10),
            end_date=date(2025, 3, 25),
            is_current=True,
        )
        self.section = Section.objects.create(
            name="Einstein",
            grade_level=self.grade_level,
            academic_year=self.academic_year,
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="STUAN001",
            grade_level=self.grade_level,
            section=self.section,
            enrollment_date=date(2024, 6, 10),
        )
        Enrollment.objects.create(
            student=self.student_profile, section=self.section,
            academic_year=self.academic_year, date_enrolled=date(2024, 6, 10),
            is_active=True,
        )

        self.subject = Subject.objects.create(
            name="Mathematics", code="MATH-7", grade_level=self.grade_level
        )
        self.sa = SubjectAssignment.objects.create(
            subject=self.subject, section=self.section,
            academic_year=self.academic_year, faculty=self.faculty_profile,
        )
        self.gp = GradingPeriod.objects.create(
            academic_year=self.academic_year,
            name="1st Quarter", order=1,
            start_date=date(2024, 6, 10), end_date=date(2024, 8, 20),
        )
        Grade.objects.create(
            student=self.student_profile, subject_assignment=self.sa,
            grading_period=self.gp, score=Decimal("88"), status="finalized",
            encoded_by=self.faculty_profile,
        )

    def force_auth(self, user):
        self.client.force_authenticate(user=user)


# ---------------------------------------------------------------------------
# Analytics services tests
# ---------------------------------------------------------------------------

class AnalyticsServiceTest(AnalyticsTestBase):
    """Test aggregation service functions."""

    def test_student_academic_metrics(self):
        from apps.analytics import services
        metrics = services.student_academic_metrics(self.student_profile)
        self.assertTrue(metrics["has_data"])
        self.assertEqual(metrics["overall_average"], 88.0)

    def test_student_attendance_summary_no_data(self):
        from apps.analytics import services
        result = services.student_attendance_summary(self.student_profile)
        self.assertFalse(result["has_data"])

    def test_school_wide_aggregates(self):
        from apps.analytics import services
        result = services.school_wide_aggregates()
        self.assertIn("total_students", result)
        self.assertEqual(result["total_students"], 1)

    def test_risk_distribution_no_data(self):
        from apps.analytics import services
        result = services.risk_distribution()
        self.assertIn("distribution", result)
        self.assertEqual(result["total_with_scores"], 0)


# ---------------------------------------------------------------------------
# Analytics API RBAC tests
# ---------------------------------------------------------------------------

class AnalyticsRBACTest(AnalyticsTestBase):
    """Test role-controlled access to analytics endpoints."""

    def test_student_can_access_own_metrics(self):
        self.force_auth(self.student_user)
        url = f"/api/v1/analytics/students/{self.student_profile.id}/metrics/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "ok")

    def test_student_cannot_access_other_student_metrics(self):
        other_user = User.objects.create_user(
            email="other_an@test.com", password="pass12345",
            first_name="Oth", last_name="An", role="student",
        )
        other_profile = StudentProfile.objects.create(
            user=other_user, student_id="OTH001",
            grade_level=self.grade_level, section=self.section,
            enrollment_date=date(2024, 6, 10),
        )
        self.force_auth(self.student_user)
        url = f"/api/v1/analytics/students/{other_profile.id}/metrics/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_access_school_wide(self):
        self.force_auth(self.admin_user)
        url = "/api/v1/analytics/school-wide/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_non_admin_cannot_access_school_wide(self):
        self.force_auth(self.guidance_user)
        url = "/api/v1/analytics/school-wide/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_guidance_access_section_performance(self):
        self.force_auth(self.guidance_user)
        url = f"/api/v1/analytics/sections/{self.section.id}/performance/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_admin_risk_distribution(self):
        # Add a risk score to test distribution
        RiskScore.objects.create(
            student=self.student_profile,
            computation_status="ready",
            risk_score=85.0,
            risk_level="high",
            model_version="v1",
            computed_at=date(2024, 7, 1),
        )
        self.force_auth(self.admin_user)
        url = "/api/v1/analytics/risk-distribution/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertIn("distribution", data)
        self.assertEqual(data["distribution"]["high"], 1)
