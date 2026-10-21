"""
AEGIS Backend URL Configuration.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.cms.views import StrapiAnnouncementWebhookView
from core.health import health, ready

urlpatterns = [
    # Probes are also mounted at the root, because that is where a
    # load balancer or an uptime monitor looks for them by default. Both the
    # slashed and the unslashed form answer, so a monitor that probes
    # "/health" does not get a redirect it may not follow.
    path("health", health, name="health-root-noslash"),
    path("ready", ready, name="ready-root-noslash"),
    path("health/", health, name="health-root"),
    path("ready/", ready, name="ready-root"),
    path("api/v1/", include("config.api_v1")),
    # Machine-to-machine webhook receiver for the Strapi CMS (Phase 7).
    # Authenticated via shared-secret header, not AEGIS JWT.
    path("webhooks/strapi/announcements/", StrapiAnnouncementWebhookView.as_view()),
]

# The Django admin site is a second, separate authority: it authenticates on
# `is_staff` and knows nothing about the five role model this API enforces.
# It stays on in development, where it is the fastest way to inspect a
# record, and it is off by default in production (see
# config/settings/production.py) so a deployment does not publish a second
# login surface it does not manage. A deployment that wants it sets
# DJANGO_ENABLE_ADMIN_SITE=true.
if getattr(settings, "ENABLE_ADMIN_SITE", True):
    urlpatterns.insert(0, path("admin/", admin.site.urls))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
