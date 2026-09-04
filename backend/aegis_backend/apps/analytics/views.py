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
