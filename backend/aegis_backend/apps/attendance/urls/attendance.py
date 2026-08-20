"""
Attendance URL router.

Registers all attendance ViewSets and exposes them under /api/v1/attendance/.
Summary is registered as a top-level endpoint per spec §H.1.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from ..views import AttendanceRecordViewSet

router = DefaultRouter()
router.register("records", AttendanceRecordViewSet, basename="attendance-record")

app_name = "attendance"

urlpatterns = [
    path("summary/", AttendanceRecordViewSet.as_view({"get": "summary"}), name="attendance-summary"),
    path("", include(router.urls)),
]
