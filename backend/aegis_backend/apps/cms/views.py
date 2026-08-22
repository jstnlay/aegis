"""
CMS integration views.

1. StrapiAnnouncementWebhookView — machine-to-machine webhook receiver
   for Strapi entry.publish events. Authenticated via a shared secret
   header (constant-time comparison); never exposed to AEGIS end users.

2. Announcement/resource read-through proxies — authenticated AEGIS
   users consume CMS content through Django, which remains authoritative
   for role-based visibility. Privileged Strapi admin APIs are never
   exposed.
"""

import hmac
import json
import logging

from django.conf import settings
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import CmsAnnouncementSerializer, CmsResourceSerializer
from .services.strapi_client import StrapiClient, StrapiError, StrapiUnavailableError
from .services.webhook import process_announcement_webhook

logger = logging.getLogger("apps.cms")

WEBHOOK_SECRET_HEADER = "X-AEGIS-Webhook-Secret"


class StrapiAnnouncementWebhookView(APIView):
    """
    POST /webhooks/strapi/announcements/

    Receiver for the Strapi "AEGIS Django" webhook (entry.publish).
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        secret = settings.STRAPI_WEBHOOK_SECRET
        if not secret:
            logger.error("Strapi webhook received but STRAPI_WEBHOOK_SECRET is not configured")
            return Response(
                {"detail": "Webhook integration is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        provided = request.headers.get(WEBHOOK_SECRET_HEADER, "")
        if not provided or not hmac.compare_digest(provided, secret):
            logger.warning("Rejected Strapi webhook with invalid or missing secret header")
            return Response(
                {"detail": "Invalid webhook authentication."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return Response(
                {"detail": "Malformed JSON body."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(payload, dict):
            return Response(
                {"detail": "Unexpected webhook payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result_status, http_status = process_announcement_webhook(payload)
        return Response({"status": result_status}, status=http_status)


def _viewer_is_staff(user):
    return user.role in ("faculty", "guidance", "admin")


def _visible_announcements(announcement_list, user):
    """
    Filter normalized announcements by viewer role.

    - Role targeting: ["all"] or containing the viewer's role.
    - Expiry: expired announcements are hidden from students/parents;
      staff keep full operational visibility.
    """
    now = timezone.now()
    visible = []
    for item in announcement_list:
        roles = item["target_roles"]
        if "all" not in roles and user.role not in roles:
            continue
        expires_at = item.get("expires_at")
        if (
            not _viewer_is_staff(user)
            and expires_at is not None
            and expires_at <= now
        ):
            continue
        visible.append(item)
    return visible


def _visible_resources(resource_list, user):
    """Filter normalized resources by audience and active flag."""
    return [
        item
        for item in resource_list
        if item["is_active"]
        and ("all" in item["target_audience"] or user.role in item["target_audience"])
    ]


class CmsAnnouncementList(generics.ListAPIView):
    serializer_class = CmsAnnouncementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        client = StrapiClient()
        items = client.list_announcements()
        return _visible_announcements(items, self.request.user)

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except StrapiUnavailableError:
            return _cms_unavailable_response()


class CmsAnnouncementDetail(generics.RetrieveAPIView):
    serializer_class = CmsAnnouncementSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "document_id"

    def get_object(self):
        document_id = self.kwargs[self.lookup_url_kwarg]
        client = StrapiClient()
        announcement = client.get_announcement(document_id)
        visible = _visible_announcements([announcement], self.request.user)
        if not visible:
            from rest_framework.exceptions import NotFound

            raise NotFound("Announcement not found.")
        return visible[0]

    def retrieve(self, request, *args, **kwargs):
        try:
            return super().retrieve(request, *args, **kwargs)
        except StrapiUnavailableError:
            return _cms_unavailable_response()


class CmsResourceList(generics.ListAPIView):
    serializer_class = CmsResourceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        client = StrapiClient()
        items = client.list_resources()
        return _visible_resources(items, self.request.user)

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except StrapiUnavailableError:
            return _cms_unavailable_response()


class CmsResourceDetail(generics.RetrieveAPIView):
    serializer_class = CmsResourceSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "document_id"

    def get_object(self):
        document_id = self.kwargs[self.lookup_url_kwarg]
        client = StrapiClient()
        resource = client.get_resource(document_id)
        visible = _visible_resources([resource], self.request.user)
        if not visible:
            from rest_framework.exceptions import NotFound

            raise NotFound("Resource not found.")
        return visible[0]

    def retrieve(self, request, *args, **kwargs):
        try:
            return super().retrieve(request, *args, **kwargs)
        except StrapiUnavailableError:
            return _cms_unavailable_response()


def _cms_unavailable_response():
    return Response(
        {"detail": "Content service is temporarily unavailable."},
        status=status.HTTP_502_BAD_GATEWAY,
    )


__all__ = [
    "StrapiAnnouncementWebhookView",
    "CmsAnnouncementList",
    "CmsAnnouncementDetail",
    "CmsResourceList",
    "CmsResourceDetail",
    "StrapiError",
]
