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
    path("assessments/", include("apps.assessments.urls")),
    # CMS read-through proxy (Phase 7): content lives in Strapi,
    # access rules stay in Django.
    path("cms/", include("apps.cms.urls")),
    # Data import (Phase 8): /data-import/jobs/ exposed by the app router.
    path("data-import/", include("apps.data_import.urls")),
    # Analytics (Phase 9): /analytics/ role-controlled aggregation API.
    path("analytics/", include("apps.analytics.urls")),
    # Chatbot (Phase 9): /chatbot/ deterministic service boundary.
    path("chatbot/", include("apps.chatbot.urls")),
]
