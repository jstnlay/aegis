"""
Guidance URL router.

Registers all guidance ViewSets and exposes them under /api/v1/guidance/.
The report endpoint is wired manually per spec §H.1.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from ..views import (
    BehavioralNoteViewSet,
    GuidanceStudentDirectoryView,
    ConsultationRecordViewSet,
    GuidanceReportView,
    InterventionViewSet,
    RiskAlertViewSet,
)

router = DefaultRouter()
router.register(
    "behavioral-notes", BehavioralNoteViewSet, basename="behavioral-note"
)
router.register(
    "consultations", ConsultationRecordViewSet, basename="consultation-record"
)
router.register("risk-alerts", RiskAlertViewSet, basename="risk-alert")
router.register("interventions", InterventionViewSet, basename="intervention")

app_name = "guidance"

urlpatterns = [
    path(
        "students/",
        GuidanceStudentDirectoryView.as_view(),
        name="guidance-student-directory",
    ),
    path(
        "reports/student/<uuid:student_id>/",
        GuidanceReportView.as_view(),
        name="guidance-report",
    ),
    path("", include(router.urls)),
]
