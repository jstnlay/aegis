"""
Data-import URL routes.

Registers the jobs router (GET/POST /api/v1/data-import/jobs/,
GET /api/v1/data-import/jobs/{id}/) via a DefaultRouter, and the
PH8.8 controlled-export endpoints under /api/v1/data-import/exports/.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceExportView,
    GradesExportView,
    ImportJobViewSet,
    StudentsExportView,
)

router = DefaultRouter()
router.register("jobs", ImportJobViewSet, basename="import-job")

app_name = "data-import"

urlpatterns = [
    *router.urls,
    path(
        "exports/grades/",
        GradesExportView.as_view(),
        name="export-grades",
    ),
    path(
        "exports/attendance/",
        AttendanceExportView.as_view(),
        name="export-attendance",
    ),
    path(
        "exports/students/",
        StudentsExportView.as_view(),
        name="export-students",
    ),
]
