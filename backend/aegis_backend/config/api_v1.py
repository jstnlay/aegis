"""
API v1 URL configuration.

All versioned endpoints are routed through here.
"""

from django.urls import path, include

urlpatterns = [
    path("auth/", include("apps.accounts.urls.auth")),
    path("accounts/", include("apps.accounts.urls.accounts")),
    path("academics/", include("apps.academics.urls.academics")),
    path("attendance/", include("apps.attendance.urls.attendance")),
    path("guidance/", include("apps.guidance.urls.guidance")),
    path("notifications/", include("apps.notifications.urls")),
]
