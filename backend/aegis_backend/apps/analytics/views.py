"""
Phase 9 analytics views.

Role-controlled aggregation endpoints. Admin gets
aggregated/anonymized only (PH9.12).
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdminUser, IsStaffOrAdmin
from apps.analytics import services


class BaseAnalyticsView(APIView):
    """Base class - authenticated; role checks in view methods."""

    permission_classes = [IsAuthenticated]


class StaffAnalyticsView(APIView):
    """Base class - only staff/admin roles."""

    permission_classes = [IsStaffOrAdmin]


class StudentMetricsView(BaseAnalyticsView):
    """
    Aggregated academic + attendance metrics for a single student.

    Access: student (own), parent (linked child), faculty (advisory/
    subject scope), guidance (all), admin (all).
    """

    def get(self, request, student_id):
        from apps.accounts.models import StudentProfile

        try:
            student = StudentProfile.objects.select_related("user").get(pk=student_id)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user = request.user
        # Role-based access control
        if user.role == "student":
            if user.student_profile.id != student_id:
                return Response(
                    {"detail": "Access denied."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif user.role == "parent":
            from apps.accounts.models import ParentStudentLink
            if not ParentStudentLink.objects.filter(
                parent=user.parent_profile, student=student
            ).exists():
                return Response(
                    {"detail": "Access denied."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif user.role == "faculty":
            # Faculty with advisory scope or subject assignment to this student
            is_adviser = (
                user.faculty_profile.is_adviser
                and student.section_id is not None
                and user.faculty_profile.advisory_section_id == student.section_id
            )
            if not is_adviser:
                # Check subject assignment scope
                from apps.academics.models import SubjectAssignment
                has_assignment = SubjectAssignment.objects.filter(
                    faculty=user.faculty_profile,
                    section=student.section,
                ).exists()
                if not has_assignment:
                    return Response(
                        {"detail": "Access denied."},
                        status=status.HTTP_403_FORBIDDEN,
                    )

        metrics = services.student_academic_metrics(student)
        attendance = services.student_attendance_summary(student)
        metrics["attendance"] = attendance
        return Response({"status": "ok", "data": metrics})


class SectionPerformanceView(StaffAnalyticsView):
    """Aggregated performance for a section."""

    def get(self, request, section_id):
        from apps.academics.models import Section

        try:
            section = Section.objects.select_related("grade_level").get(pk=section_id)
        except Section.DoesNotExist:
            return Response(
                {"detail": "Section not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user = request.user
        if user.role == "faculty":
            # Faculty can only view their own sections
            is_adviser = (
                user.faculty_profile.is_adviser
                and user.faculty_profile.advisory_section_id == section.id
            )
            has_assignment = section.subject_assignments.filter(
                faculty=user.faculty_profile
            ).exists()
            if not is_adviser and not has_assignment:
                return Response(
                    {"detail": "Access denied."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        academic_year_id = request.query_params.get("academic_year")
        result = services.section_performance(section, academic_year_id)
        return Response({"status": "ok", "data": result})


class GradeLevelComparisonView(StaffAnalyticsView):
    """Comparing performance across grade levels (staff/admin)."""

    def get(self, request):
        result = services.grade_level_comparison()
        return Response({"status": "ok", "data": result})


class _StudentScopedAnalyticsView(BaseAnalyticsView):
    """
    Shared authorization for a per-student analytics view.

    PH11.10. Extracted from `StudentMetricsView` rather than repeated, because
    the two new student-scoped trends (academic, attendance) must resolve exactly
    the same question "may this caller read this student?" and a copy of the
    ladder in three places would be three chances to diverge.

    The ladder is the one `StudentMetricsView` already enforced:
      student -> own record
      parent  -> a linked child
      faculty -> an advisory-section or subject-assignment scope
      guidance / admin -> any student
    """

    def _authorized(self, student_id):
        """
        Resolve the student and decide whether this caller may read them.

        Returns a `(student_profile, denial_response)` pair: exactly one is
        meaningful. Returning the response rather than raising keeps the refusal
        identical to the one `StudentMetricsView` already sends, so a client
        cannot tell the two apart from the body alone.
        """
        from django.shortcuts import get_object_or_404

        from apps.accounts.models import StudentProfile

        student_obj = get_object_or_404(StudentProfile, pk=student_id)
        user = self.request.user

        allowed = True
        if user.role == "student":
            allowed = user.student_profile.id == student_obj.id
        elif user.role == "parent":
            from apps.accounts.models import ParentStudentLink

            allowed = ParentStudentLink.objects.filter(
                parent=user.parent_profile, student=student_obj
            ).exists()
        elif user.role == "faculty":
            allowed = self._faculty_has_scope(user, student_obj)

        if not allowed:
            return None, Response(
                {"detail": "Access denied."}, status=status.HTTP_403_FORBIDDEN
            )
        return student_obj, None

    @staticmethod
    def _faculty_has_scope(user, student_obj) -> bool:
        """Adviser of the student's section, or teaches that student."""
        is_adviser = (
            user.faculty_profile.is_adviser
            and student_obj.section_id is not None
            and user.faculty_profile.advisory_section_id == student_obj.section_id
        )
        if is_adviser:
            return True

        from apps.academics.models import SubjectAssignment

        return SubjectAssignment.objects.filter(
            faculty=user.faculty_profile, section=student_obj.section
        ).exists()


class StudentAcademicTrendView(_StudentScopedAnalyticsView):
    """
    GET /api/v1/analytics/students/{id}/academic-trend/

    PH11.10. Real per-grading-period averages for one student.

    `StudentMetricsView` cannot serve a trend: its `latest_period_average` is
    derived from the same overall average, so it reports one figure twice rather
    than two periods. This returns genuine per-period averages, ordered by
    `GradingPeriod.order`.
    """

    def get(self, request, student_id):
        student, denial = self._authorized(student_id)
        if denial is not None:
            return denial
        return Response(
            {"status": "ok", "data": services.student_period_trend(student)}
        )


class StudentAttendanceTrendView(_StudentScopedAnalyticsView):
    """
    GET /api/v1/analytics/students/{id}/attendance-trend/

    PH11.10. Per-day present / late / absent counts for one student, ascending
    by date. Optional `date_from` / `date_to` bound the range; omitted, the full
    history is returned.
    """

    def get(self, request, student_id):
        student, denial = self._authorized(student_id)
        if denial is not None:
            return denial

        from_date, to_date = _optional_date_range(request)

        return Response(
            {
                "status": "ok",
                "data": services.student_attendance_trend(
                    student, from_date=from_date, to_date=to_date
                ),
            }
        )


def _optional_date_range(request):
    """Read `date_from` / `date_to`, ignoring a value that is not a date.

    A malformed bound is dropped rather than 400ing: the range is a convenience
    filter on a read-only aggregate, and refusing the whole request over it would
    be a worse failure than returning a slightly wider range.
    """
    from datetime import date as date_cls

    def parse(name):
        raw = request.query_params.get(name)
        if not raw:
            return None
        try:
            return date_cls.fromisoformat(raw)
        except ValueError:
            return None

    return parse("date_from"), parse("date_to")


class SchoolWideAcademicTrendView(StaffAnalyticsView):
    """
    GET /api/v1/analytics/academic-trend/

    PH11.10. Per-grading-period averages across the school, for the school-wide
    academic-performance visual reports. Optional `academic_year` narrows it.
    Aggregate only: no student is identified.
    """

    def get(self, request):
        academic_year_id = request.query_params.get("academic_year")
        return Response(
            {
                "status": "ok",
                "data": services.school_wide_period_trend(academic_year_id),
            }
        )


class SchoolWideAttendanceTrendView(APIView):
    """
    GET /api/v1/analytics/attendance-trend/

    PH11.10. Per-day present / late / absent counts across the school.

    Administrator-only, matching `/analytics/school-wide/` and
    `/analytics/risk-distribution/`. Aggregate counts only, so NFR-010's
    anonymisation requirement is met by the shape of the data rather than by a
    display-layer decision.
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        from_date, to_date = _optional_date_range(request)
        return Response(
            {
                "status": "ok",
                "data": services.school_wide_attendance_trend(
                    from_date=from_date, to_date=to_date
                ),
            }
        )


class SubjectTrendsView(StaffAnalyticsView):
    """Subject performance trends."""

    def get(self, request):
        academic_year_id = request.query_params.get("academic_year")
        result = services.subject_trends(academic_year_id)
        return Response({"status": "ok", "data": result})


class SchoolWideAggregatesView(APIView):
    """School-wide aggregates (admin only, anonymized)."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        result = services.school_wide_aggregates()
        return Response({"status": "ok", "data": result})


class RiskDistributionView(APIView):
    """Risk distribution across students (admin, anonymized)."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        result = services.risk_distribution()
        return Response({"status": "ok", "data": result})


class LowPerformanceView(APIView):
    """Lowest performing students (admin, anonymized)."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        threshold = request.query_params.get("threshold", 75)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            threshold = 75.0
        result = services.low_performance_students(threshold=threshold)
        return Response({"status": "ok", "data": result})
