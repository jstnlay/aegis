"""
AEGIS Backend URL Configuration.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.cms.views import StrapiAnnouncementWebhookView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("config.api_v1")),
    # Machine-to-machine webhook receiver for the Strapi CMS (Phase 7).
    # Authenticated via shared-secret header, not AEGIS JWT.
    path("webhooks/strapi/announcements/", StrapiAnnouncementWebhookView.as_view()),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
