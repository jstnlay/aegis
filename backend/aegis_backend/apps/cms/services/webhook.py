"""
Announcement publication webhook processing.

Flow (Phase 7 architecture decision):

  Strapi publish
    -> Strapi webhook (entry.publish, model=announcement)
    -> Django webhook endpoint (secret-verified)
    -> canonical announcement fetched from Strapi REST API
    -> validation/normalization
    -> AEGIS recipient resolution (Django users/roles)
    -> dispatch_event(ANNOUNCEMENT_PUBLISHED) via the existing
       Phase 4 notification system

Idempotency is enforced at two layers:
  1. CmsWebhookEvent.event_id — one record per publication cycle;
     duplicate deliveries short-circuit before any work.
  2. dispatch_event(deduplication_key=...) — the existing all-or-nothing
     notification dedup acts as a backstop.
"""

import logging

from django.db import transaction

from apps.cms.models import CmsWebhookEvent
from apps.notifications.events import dispatch_event
from apps.notifications.models import NotificationType

from .recipients import resolve_announcement_recipients
from .strapi_client import (
    StrapiClient,
    StrapiError,
    StrapiNotFoundError,
    StrapiUnavailableError,
    _parse_datetime,
)

logger = logging.getLogger("apps.cms")

IGNORED = "ignored"
PROCESSED = "processed"
DUPLICATE = "duplicate"
REJECTED = "rejected"
FAILED = "failed"
UNAVAILABLE = "unavailable"


def build_event_id(document_id, published_at):
    """Stable idempotency key per publication cycle."""
    published_token = published_at.isoformat() if published_at else ""
    return f"announcement:{document_id}:{published_token}"


def process_announcement_webhook(payload):
    """
    Handle one verified Strapi webhook payload.

    Returns:
        (status_string, http_status_int)
    """
    event = payload.get("event")
    model = payload.get("model")
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}

    if event != "entry.publish" or model != "announcement":
        return IGNORED, 200

    document_id = str(entry.get("documentId") or entry.get("id") or "").strip()
    if not document_id:
        logger.warning("Announcement webhook without documentId: %r", entry)
        return REJECTED, 200

    published_at = _parse_datetime(entry.get("publishedAt"))
    event_id = build_event_id(document_id, published_at)

    webhook_event, created = CmsWebhookEvent.objects.get_or_create(
        event_id=event_id,
        defaults={
            "source": "strapi",
            "event_type": f"{event}:{model}",
            "status": CmsWebhookEvent.Status.PENDING,
        },
    )
    if not created and webhook_event.status in (
        CmsWebhookEvent.Status.PROCESSED,
        CmsWebhookEvent.Status.DUPLICATE,
    ):
        return DUPLICATE, 200

    # --- Canonical data retrieval (never trust the raw payload body) ---
    client = StrapiClient()
    try:
        announcement = client.get_announcement(document_id)
    except StrapiUnavailableError as exc:
        webhook_event.status = CmsWebhookEvent.Status.FAILED
        webhook_event.detail = {"error": "strapi_unavailable", "reason": str(exc)}
        webhook_event.save(update_fields=["status", "detail", "updated_at"])
        return UNAVAILABLE, 502
    except StrapiNotFoundError as exc:
        webhook_event.status = CmsWebhookEvent.Status.REJECTED
        webhook_event.detail = {"error": "not_found_or_unpublished", "reason": str(exc)}
        webhook_event.save(update_fields=["status", "detail", "updated_at"])
        return REJECTED, 200
    except StrapiError as exc:
        webhook_event.status = CmsWebhookEvent.Status.REJECTED
        webhook_event.detail = {"error": "invalid_data", "reason": str(exc)}
        webhook_event.save(update_fields=["status", "detail", "updated_at"])
        return REJECTED, 422

    # --- Recipient resolution + dispatch through the existing system ---
    recipients = resolve_announcement_recipients(
        announcement["target_roles"], announcement["target_sections"]
    )
    recipient_count = recipients.count()

    deduplication_key = build_event_id(
        announcement["document_id"], announcement["published_at"]
    )

    try:
        with transaction.atomic():
            dispatch_event(
                NotificationType.ANNOUNCEMENT_PUBLISHED,
                recipients=recipients,
                sender=None,
                title=f"Announcement: {announcement['title']}",
                message=announcement["content"],
                link=f"/announcements/{announcement['document_id']}",
                deduplication_key=deduplication_key,
            )
            webhook_event.status = CmsWebhookEvent.Status.PROCESSED
            webhook_event.detail = {
                "recipient_count": recipient_count,
                "priority": announcement["priority"],
                "announcement_type": announcement["announcement_type"],
            }
            webhook_event.save(update_fields=["status", "detail", "updated_at"])
    except Exception:
        # Row stays pending so a Strapi retry can reprocess cleanly.
        logger.exception(
            "Failed to dispatch ANNOUNCEMENT_PUBLISHED for %s", document_id
        )
        raise

    logger.info(
        "Processed announcement %s for %d recipients",
        document_id,
        recipient_count,
    )
    return PROCESSED, 200
