"""
Academics URL router.

Registers all academics ViewSets and exposes them under /api/v1/academics/.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from ..views import (
    AcademicYearViewSet,
    EnrollmentViewSet,
    GradeLevelViewSet,
    GradeViewSet,
    GradingPeriodViewSet,
    ScheduleViewSet,
    SectionViewSet,
    StudentProfileManageView,
    SubjectAssignmentViewSet,
    SubjectViewSet,
)

router = DefaultRouter()
router.register("academic-years", AcademicYearViewSet, basename="academic-year")
router.register("grade-levels", GradeLevelViewSet, basename="grade-level")
router.register("sections", SectionViewSet, basename="section")
router.register("subjects", SubjectViewSet, basename="subject")
router.register("subject-assignments", SubjectAssignmentViewSet, basename="subject-assignment")
router.register("schedules", ScheduleViewSet, basename="schedule")
router.register("grading-periods", GradingPeriodViewSet, basename="grading-period")
router.register("enrollments", EnrollmentViewSet, basename="enrollment")
router.register("grades", GradeViewSet, basename="grade")

app_name = "academics"

urlpatterns = [
    path("", include(router.urls)),
    # FR-007 / TC-FAC-03/04: faculty management of an advisory student's
    # profile. Kept off the router because it is retrieve/update only — no
    # create (student accounts are provisioned administratively), no delete
    # (a profile lives as long as the account).
    path(
        "student-profiles/<uuid:pk>/",
        StudentProfileManageView.as_view(),
        name="student-profile-manage",
    ),
]
