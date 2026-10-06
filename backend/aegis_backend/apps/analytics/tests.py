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


# ---------------------------------------------------------------------------
# PH11.10: academic and attendance trends
# ---------------------------------------------------------------------------


class AnalyticsTrendTestBase(AnalyticsTestBase):
    """Shared fixtures: two grading periods and a few attendance days."""

    def setUp(self):
        super().setUp()

        # A second period whose `order` deliberately disagrees with its name, so
        # a test can tell academic ordering from alphabetical ordering: sorted
        # by name, "2nd Quarter" would come before "1st Quarter".
        self.gp_second = GradingPeriod.objects.create(
            academic_year=self.academic_year,
            name="2nd Quarter", order=2,
            start_date=date(2024, 8, 21), end_date=date(2024, 10, 20),
        )

        # A period with no grades at all, to prove gaps are reported honestly.
        self.gp_third = GradingPeriod.objects.create(
            academic_year=self.academic_year,
            name="3rd Quarter", order=3,
            start_date=date(2024, 10, 21), end_date=date(2024, 12, 20),
        )

    def add_grade(self, period, score, status="finalized"):
        """
        Add a grade in `period` for this student.

        `Grade` is unique on (student, subject_assignment, grading_period), so a
        second grade in the same period needs its own subject — which is why
        every call gets a fresh assignment rather than reusing `self.sa`.
        """
        subject = Subject.objects.create(
            name=f"Subject {Subject.objects.count()}",
            code=f"SUBJ-{Subject.objects.count():03d}",
            grade_level=self.grade_level,
        )
        assignment = SubjectAssignment.objects.create(
            subject=subject,
            section=self.section,
            academic_year=self.academic_year,
            faculty=self.faculty_profile,
        )
        return Grade.objects.create(
            student=self.student_profile,
            subject_assignment=assignment,
            grading_period=period,
            score=Decimal(score) if score is not None else None,
            status=status,
            encoded_by=self.faculty_profile,
        )

    def add_attendance(self, day, status, student=None):
        """
        Record one attendance row.

        `AttendanceRecord` is unique on (student, date), so a student has
        exactly one status per day — three statuses on one day for one student is
        a constraint violation, not a fixture. Multi-status days therefore need
        several students, which is what the school-wide tests do.
        """
        from apps.attendance.models import AttendanceRecord

        return AttendanceRecord.objects.create(
            student=student or self.student_profile,
            section=self.section,
            date=day,
            status=status,
            recorded_by=self.faculty_profile,
        )

    def make_student(self, student_id, section=None, academic_year=None):
        """
        Another student, enrolled in `section` for `academic_year`.

        Enrollment is required: SEC-013 rejects a grade whose student is not
        enrolled in the assignment's section for that year, so a bare profile
        would not satisfy `Grade.save()`.
        """
        user = User.objects.create_user(
            email=f"{student_id.lower()}@test.com",
            password="pass12345",
            first_name="Extra",
            last_name=student_id,
            role="student",
        )
        target_section = section or self.section
        target_year = academic_year or self.academic_year
        profile = StudentProfile.objects.create(
            user=user,
            student_id=student_id,
            grade_level=self.grade_level,
            section=target_section,
            enrollment_date=target_year.start_date,
        )
        Enrollment.objects.create(
            student=profile,
            section=target_section,
            academic_year=target_year,
            date_enrolled=target_year.start_date,
            is_active=True,
        )
        return profile


class StudentPeriodTrendServiceTest(AnalyticsTrendTestBase):
    """`student_period_trend` — real per-period averages."""

    def test_averages_are_computed_per_period(self):
        from apps.analytics import services

        # The base fixture already has 88 in 1st Quarter.
        self.add_grade(self.gp_second, Decimal("92"))

        result = services.student_period_trend(self.student_profile)

        by_name = {entry["period"]: entry for entry in result["periods"]}
        self.assertEqual(by_name["1st Quarter"]["average"], 88.0)
        self.assertEqual(by_name["2nd Quarter"]["average"], 92.0)
        self.assertTrue(result["has_data"])

    def test_averages_several_grades_within_one_period(self):
        from apps.analytics import services

        # A second subject in the same period, so the period average is a real
        # mean rather than a single row's score.
        other_subject = Subject.objects.create(
            name="Science", code="SCI-7", grade_level=self.grade_level
        )
        other_assignment = SubjectAssignment.objects.create(
            subject=other_subject, section=self.section,
            academic_year=self.academic_year, faculty=self.faculty_profile,
        )
        Grade.objects.create(
            student=self.student_profile, subject_assignment=other_assignment,
            grading_period=self.gp, score=Decimal("96"), status="finalized",
            encoded_by=self.faculty_profile,
        )

        result = services.student_period_trend(self.student_profile)
        first = next(
            entry for entry in result["periods"] if entry["period"] == "1st Quarter"
        )
        self.assertEqual(first["average"], 92.0)  # (88 + 96) / 2
        self.assertEqual(first["grade_count"], 2)

    def test_periods_are_ordered_by_grading_period_order(self):
        from apps.analytics import services

        self.add_grade(self.gp_second, Decimal("92"))

        orders = [
            entry["order"]
            for entry in services.student_period_trend(self.student_profile)["periods"]
        ]
        self.assertEqual(orders, sorted(orders))
        # Name order would be ["1st Quarter", "2nd Quarter"] too, so the
        # assertion that matters is the third, absent period below.
        self.assertEqual(
            [entry["period"] for entry in
             services.student_period_trend(self.student_profile)["periods"]],
            ["1st Quarter", "2nd Quarter"],
        )

    def test_a_period_with_no_grades_is_absent_not_zero_filled(self):
        from apps.analytics import services

        result = services.student_period_trend(self.student_profile)
        names = [entry["period"] for entry in result["periods"]]

        # 3rd Quarter exists in the database with no finalized grades. It must
        # not appear with an average of 0, which would read as a failing score.
        self.assertNotIn("3rd Quarter", names)
        self.assertFalse(
            any(entry["average"] == 0 for entry in result["periods"])
        )

    def test_draft_and_submitted_grades_are_excluded(self):
        from apps.analytics import services

        self.add_grade(self.gp_second, Decimal("40"), status="draft")
        self.add_grade(self.gp_second, Decimal("50"), status="submitted")

        result = services.student_period_trend(self.student_profile)
        names = [entry["period"] for entry in result["periods"]]

        # Neither is reportable, so the period must not appear at all.
        self.assertEqual(names, ["1st Quarter"])

    def test_a_null_score_does_not_drag_the_average_down(self):
        from apps.analytics import services

        self.add_grade(self.gp_second, None)

        result = services.student_period_trend(self.student_profile)
        second = next(
            entry for entry in result["periods"] if entry["period"] == "2nd Quarter"
        )
        self.assertEqual(second["grade_count"], 0)
        # No score was recorded, so there is no average to report.
        self.assertIsNone(second["average"])

    def test_no_grades_reports_has_data_false_with_an_empty_list(self):
        from apps.analytics import services

        Grade.objects.all().delete()

        result = services.student_period_trend(self.student_profile)
        self.assertFalse(result["has_data"])
        self.assertEqual(result["periods"], [])

    def test_it_really_is_a_series_and_not_the_metrics_figure_restated(self):
        """
        The reason this endpoint exists.

        `student_academic_metrics` reports `latest_period_average` computed from
        its own overall average, so with one period it equals the overall mean.
        A genuine trend must instead differ per period.
        """
        from apps.analytics import services

        self.add_grade(self.gp_second, Decimal("60"))

        trend = services.student_period_trend(self.student_profile)
        metrics = services.student_academic_metrics(self.student_profile)

        averages = [entry["average"] for entry in trend["periods"]]
        self.assertNotEqual(averages[0], averages[1])
        self.assertEqual(metrics["latest_period_average"], metrics["overall_average"])


class StudentAttendanceTrendServiceTest(AnalyticsTrendTestBase):
    """`student_attendance_trend` — real per-day counts."""

    def test_counts_each_students_status_per_day(self):
        from apps.analytics import services

        # One record per student per day, so the counts reflect this student's
        # own record on each date rather than three statuses on one date.
        self.add_attendance(date(2024, 7, 1), "present")
        self.add_attendance(date(2024, 7, 2), "late")
        self.add_attendance(date(2024, 7, 3), "absent")

        result = services.student_attendance_trend(self.student_profile)
        by_day = {entry["date"]: entry for entry in result["days"]}

        self.assertEqual(by_day["2024-07-01"]["present"], 1)
        self.assertEqual(by_day["2024-07-01"]["total"], 1)
        self.assertEqual(by_day["2024-07-02"]["late"], 1)
        self.assertEqual(by_day["2024-07-03"]["absent"], 1)

    def test_days_are_ascending_by_date(self):
        from apps.analytics import services

        self.add_attendance(date(2024, 7, 10), "present")
        self.add_attendance(date(2024, 7, 1), "present")
        self.add_attendance(date(2024, 7, 5), "present")

        days = [
            entry["date"]
            for entry in services.student_attendance_trend(self.student_profile)["days"]
        ]
        self.assertEqual(days, sorted(days))
        self.assertEqual(days, ["2024-07-01", "2024-07-05", "2024-07-10"])

    def test_an_unrecorded_day_is_absent_not_zero_absent(self):
        from apps.analytics import services

        self.add_attendance(date(2024, 7, 1), "present")
        # 2024-07-02 has no record at all.
        self.add_attendance(date(2024, 7, 3), "present")

        days = [
            entry["date"]
            for entry in services.student_attendance_trend(self.student_profile)["days"]
        ]
        # Filling the gap would assert an absence that was never recorded.
        self.assertEqual(days, ["2024-07-01", "2024-07-03"])

    def test_a_date_range_bounds_the_result(self):
        from apps.analytics import services

        self.add_attendance(date(2024, 7, 1), "present")
        self.add_attendance(date(2024, 7, 10), "present")
        self.add_attendance(date(2024, 8, 1), "present")

        result = services.student_attendance_trend(
            self.student_profile,
            from_date=date(2024, 7, 5),
            to_date=date(2024, 7, 31),
        )
        self.assertEqual(
            [entry["date"] for entry in result["days"]], ["2024-07-10"]
        )

    def test_no_records_reports_has_data_false_with_an_empty_list(self):
        from apps.analytics import services

        result = services.student_attendance_trend(self.student_profile)
        self.assertFalse(result["has_data"])
        self.assertEqual(result["days"], [])


class SchoolWideTrendServiceTest(AnalyticsTrendTestBase):
    """School-wide counterparts, aggregate only."""

    def test_academic_trend_aggregates_across_students(self):
        from apps.analytics import services

        other_profile = self.make_student("TREND002")
        # The base fixture's grade already covers this student in 1st Quarter,
        # so a *different* student is needed to make the mean a real one.
        Grade.objects.create(
            student=other_profile, subject_assignment=self.sa,
            grading_period=self.gp, score=Decimal("78"), status="finalized",
            encoded_by=self.faculty_profile,
        )

        result = services.school_wide_period_trend()
        first = next(
            entry for entry in result["periods"] if entry["period"] == "1st Quarter"
        )

        self.assertEqual(first["average"], 83.0)  # (88 + 78) / 2
        self.assertEqual(first["grade_count"], 2)

    def test_academic_trend_never_identifies_a_student(self):
        from apps.analytics import services

        payload = repr(services.school_wide_period_trend())
        self.assertNotIn(self.student_profile.student_id, payload)
        self.assertNotIn(str(self.student_profile.id), payload)

    def test_academic_trend_can_be_narrowed_to_one_academic_year(self):
        from apps.analytics import services

        other_year = AcademicYear.objects.create(
            name="2023-2024", start_date=date(2023, 6, 1),
            end_date=date(2024, 3, 1), is_current=False,
        )
        old_period = GradingPeriod.objects.create(
            academic_year=other_year, name="1st Quarter", order=1,
            start_date=date(2023, 6, 1), end_date=date(2023, 8, 1),
        )
        old_section = Section.objects.create(
            name="Legacy", grade_level=self.grade_level, academic_year=other_year,
        )
        old_assignment = SubjectAssignment.objects.create(
            subject=self.subject, section=old_section,
            academic_year=other_year, faculty=self.faculty_profile,
        )
        legacy_student = self.make_student(
            "LEGACY01", section=old_section, academic_year=other_year
        )
        Grade.objects.create(
            student=legacy_student, subject_assignment=old_assignment,
            grading_period=old_period, score=Decimal("50"), status="finalized",
            encoded_by=self.faculty_profile,
        )
        # The base fixture also has an 88 in the current year's 1st Quarter, so
        # an unscoped query would return both periods.

        scoped = services.school_wide_period_trend(str(other_year.id))
        self.assertEqual(
            [entry["period"] for entry in scoped["periods"]], ["1st Quarter"]
        )
        self.assertEqual(scoped["periods"][0]["average"], 50.0)

    def test_attendance_trend_counts_across_students(self):
        from apps.analytics import services

        # One status per student per date, so a day with all three statuses
        # needs three students.
        second = self.make_student("TREND003")
        third = self.make_student("TREND004")
        self.add_attendance(date(2024, 7, 1), "present")
        self.add_attendance(date(2024, 7, 1), "absent", student=second)
        self.add_attendance(date(2024, 7, 1), "late", student=third)

        result = services.school_wide_attendance_trend()
        day = next(entry for entry in result["days"] if entry["date"] == "2024-07-01")

        self.assertEqual(day["present"], 1)
        self.assertEqual(day["absent"], 1)
        self.assertEqual(day["late"], 1)
        self.assertEqual(day["total"], 3)

    def test_attendance_trend_never_identifies_a_student(self):
        from apps.analytics import services

        self.add_attendance(date(2024, 7, 1), "present")
        payload = repr(services.school_wide_attendance_trend())
        self.assertNotIn(self.student_profile.student_id, payload)


class StudentTrendEndpointAuthTest(AnalyticsTrendTestBase):
    """
    Authorization for the two new student-scoped trends.

    The ladder must match `StudentMetricsView` exactly, or a caller could read a
    student through the trend route that the metrics route refuses.
    """

    STUDENT_URL = "/api/v1/analytics/students/{student_id}/academic-trend/"
    ATTENDANCE_URL = "/api/v1/analytics/students/{student_id}/attendance-trend/"

    def setUp(self):
        super().setUp()
        self.other_user = User.objects.create_user(
            email="trend_rival@test.com", password="pass12345",
            first_name="Riv", last_name="Al", role="student",
        )
        self.other_profile = StudentProfile.objects.create(
            user=self.other_user, student_id="RIVAL001",
            grade_level=self.grade_level, section=self.section,
            enrollment_date=date(2024, 6, 10),
        )

    def _both_urls(self, student):
        student_id = getattr(student, "id", student)
        return [
            self.STUDENT_URL.format(student_id=student_id),
            self.ATTENDANCE_URL.format(student_id=student_id),
        ]

    def test_a_student_may_read_their_own_trends(self):
        self.force_auth(self.student_user)
        for url in self._both_urls(self.student_profile):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                self.assertEqual(resp.data["status"], "ok")

    def test_a_student_may_not_read_another_students_trends(self):
        self.force_auth(self.student_user)
        for url in self._both_urls(self.other_profile):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_parent_may_read_a_linked_child_and_nobody_else(self):
        parent_user = User.objects.create_user(
            email="trend_parent@test.com", password="pass12345",
            first_name="Par", last_name="Ent", role="parent",
        )
        parent_profile = ParentProfile.objects.create(
            user=parent_user, relationship_to_student="mother",
        )
        ParentStudentLink.objects.create(
            parent=parent_profile, student=self.student_profile,
        )

        self.force_auth(parent_user)
        for url in self._both_urls(self.student_profile):
            with self.subTest(linked=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, status.HTTP_200_OK)

        for url in self._both_urls(self.other_profile):
            with self.subTest(unlinked=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_teacher_without_scope_is_refused(self):
        self.force_auth(self.faculty_user)
        # The base fixture's faculty teaches this section's assignment, so the
        # refusal case is a student in a section they have no relationship to.
        elsewhere = Section.objects.create(
            name="Elsewhere", grade_level=self.grade_level,
            academic_year=self.academic_year,
        )
        stranger_user = User.objects.create_user(
            email="trend_stranger@test.com", password="pass12345",
            first_name="Str", last_name="Anger", role="student",
        )
        stranger = StudentProfile.objects.create(
            user=stranger_user, student_id="STRANGE1",
            grade_level=self.grade_level, section=elsewhere,
            enrollment_date=date(2024, 6, 10),
        )

        for url in self._both_urls(stranger):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_teacher_with_subject_scope_is_allowed(self):
        self.force_auth(self.faculty_user)
        for url in self._both_urls(self.student_profile):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_guidance_and_admin_may_read_any_student(self):
        for user in (self.guidance_user, self.admin_user):
            self.force_auth(user)
            for url in self._both_urls(self.other_profile):
                with self.subTest(user=user.role, url=url):
                    resp = self.client.get(url)
                    self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_an_anonymous_caller_is_refused(self):
        for url in self._both_urls(self.student_profile):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(
                    resp.status_code, status.HTTP_401_UNAUTHORIZED
                )

    def test_an_unknown_student_is_a_404_not_an_empty_series(self):
        self.force_auth(self.admin_user)
        missing = "00000000-0000-0000-0000-000000000000"
        for url in self._both_urls(missing):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class SchoolWideTrendEndpointAuthTest(AnalyticsTrendTestBase):
    """The school-wide aggregates carry the existing role boundaries."""

    ACADEMIC_URL = "/api/v1/analytics/academic-trend/"
    ATTENDANCE_URL = "/api/v1/analytics/attendance-trend/"

    def test_staff_and_admin_may_read_the_academic_trend(self):
        for user in (self.faculty_user, self.guidance_user, self.admin_user):
            self.force_auth(user)
            with self.subTest(user=user.role):
                resp = self.client.get(self.ACADEMIC_URL)
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                self.assertEqual(resp.data["status"], "ok")

    def test_a_student_may_not_read_the_academic_trend(self):
        self.force_auth(self.student_user)
        resp = self.client.get(self.ACADEMIC_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_parent_may_not_read_the_academic_trend(self):
        parent_user = User.objects.create_user(
            email="trend_parent2@test.com", password="pass12345",
            first_name="Par", last_name="Two", role="parent",
        )
        self.force_auth(parent_user)
        resp = self.client.get(self.ACADEMIC_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_only_an_admin_may_read_the_school_wide_attendance_trend(self):
        self.force_auth(self.admin_user)
        resp = self.client.get(self.ATTENDANCE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "ok")

        for user in (self.faculty_user, self.guidance_user, self.student_user):
            self.force_auth(user)
            with self.subTest(user=user.role):
                resp = self.client.get(self.ATTENDANCE_URL)
                self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_an_anonymous_caller_is_refused(self):
        for url in (self.ACADEMIC_URL, self.ATTENDANCE_URL):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(
                    resp.status_code, status.HTTP_401_UNAUTHORIZED
                )


class TrendEndpointResponseTest(AnalyticsTrendTestBase):
    """The wire shape the frontend consumes."""

    ACADEMIC_URL = "/api/v1/analytics/students/{student_id}/academic-trend/"
    ATTENDANCE_URL = "/api/v1/analytics/students/{student_id}/attendance-trend/"

    def test_academic_trend_reports_ordered_periods_with_counts(self):
        self.add_grade(self.gp_second, Decimal("92"))
        self.force_auth(self.student_user)
        resp = self.client.get(
            self.ACADEMIC_URL.format(student_id=self.student_profile.id)
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        periods = resp.data["data"]["periods"]
        self.assertEqual(
            [entry["period"] for entry in periods],
            ["1st Quarter", "2nd Quarter"],
        )
        for entry in periods:
            self.assertIn("average", entry)
            self.assertIn("grade_count", entry)
            self.assertIn("order", entry)
            self.assertIn("period_id", entry)

    def test_attendance_trend_reports_iso_dates(self):
        self.add_attendance(date(2024, 7, 1), "present")
        self.force_auth(self.student_user)
        resp = self.client.get(
            self.ATTENDANCE_URL.format(student_id=self.student_profile.id)
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        day = resp.data["data"]["days"][0]
        self.assertEqual(day["date"], "2024-07-01")
        # ISO 8601, so the client can parse it rather than guess a locale format.
        self.assertEqual(day["date"], date.fromisoformat(day["date"]).isoformat())

    def test_a_malformed_date_bound_is_ignored_rather_than_rejected(self):
        self.add_attendance(date(2024, 7, 1), "present")
        self.force_auth(self.admin_user)
        resp = self.client.get("/api/v1/analytics/attendance-trend/?date_from=nonsense")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]["days"]), 1)
