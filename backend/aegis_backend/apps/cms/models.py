"""
CMS integration models.

This app does NOT model CMS content natively — Announcements and
Resources live in the self-hosted Strapi Community instance (Phase 7
architecture decision). The only Django-side model is an idempotency /
audit log for processed Strapi webhook deliveries.
"""

from django.db import models

from core.models import TimestampedModel


class CmsWebhookEvent(TimestampedModel):
    """
    Record of a Strapi webhook delivery, used for idempotency and audit.

    event_id is a stable key per publication cycle
    (e.g. "announcement:<documentId>:<publishedAt>") so duplicate
    deliveries from Strapi are recognized and skipped.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"
        DUPLICATE = "duplicate", "Duplicate"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"

    event_id = models.CharField(max_length=255, unique=True, db_index=True)
    source = models.CharField(max_length=30, default="strapi")
    event_type = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    detail = models.JSONField(default=dict, blank=True)

    class Meta(TimestampedModel.Meta):
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.event_type or 'webhook'} [{self.status}] {self.event_id}"
