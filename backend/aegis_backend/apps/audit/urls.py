"""
Audit URL router (PH10.10).

Exposes the read-only administrator audit API under /api/v1/audit/:

    GET /api/v1/audit/logs/        list AuditLog records (paginated)
    GET /api/v1/audit/logs/{id}/   retrieve one AuditLog record

The ViewSet restricts methods to GET / HEAD / OPTIONS, so this router
maps no write routes.  No unversioned audit endpoint is exposed.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.audit.views import AuditLogViewSet

app_name = "audit"

router = DefaultRouter()
router.register("logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("", include(router.urls)),
]