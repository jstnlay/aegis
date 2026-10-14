"""
CMS integration models.

This app does NOT model CMS content natively — Announcements and
Resources live in the self-hosted Strapi Community instance (Phase 7
architecture decision). The only Django-side model is an idempotency /
audit log for processed Strapi webhook deliveries.

Phase 9 adds LearningItem — a lightweight Django-side metadata /
eligibility / recommendation layer that maps to Strapi resources
without duplicating the content body. Strapi Resource remains the
content/source of truth.
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


class LearningItem(TimestampedModel):
    """
    Lightweight Django-side metadata / eligibility / recommendation layer
    for learning content.

    Strapi Resource remains the underlying content/source of truth.
    LearningItem provides AI/recommendation metadata, approval/eligibility,
    and a mapping to the source content — without duplicating the
    resource body.

    Only APPROVED + ACTIVE items enter the recommendation candidate pool.
    A human-controlled approval boundary MUST exist before an item becomes
    recommendation-eligible.
    """

    class ItemType(models.TextChoices):
        STUDY_ACTIVITY = "study_activity", "Study Activity"
        LEARNING_RESOURCE = "learning_resource", "Learning Resource"
        LEARNING_STRATEGY = "learning_strategy", "Learning Strategy"

    class LifecycleStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Review"
        APPROVED = "approved", "Approved"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    class SourceType(models.TextChoices):
        STRAPI_RESOURCE = "strapi_resource", "Strapi Resource"
        INTERNAL = "internal", "Internal"

    # Source mapping
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.STRAPI_RESOURCE,
    )
    source_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Strapi Resource document_id or internal identifier.",
    )

    # Item metadata
    item_type = models.CharField(
        max_length=20,
        choices=ItemType.choices,
    )
    title = models.CharField(
        max_length=255,
        help_text="Display title (may mirror Strapi title).",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Brief description for recommendation display.",
    )

    # Academic classification
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_items",
    )
    topic = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Specific topic within the subject.",
    )
    grade_level = models.ForeignKey(
        "academics.GradeLevel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_items",
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Array of skill/topic tags for content-based matching.",
    )
    difficulty = models.PositiveIntegerField(
        default=1,
        help_text="Difficulty level 1-5.",
    )

    # Lifecycle / approval
    lifecycle_status = models.CharField(
        max_length=15,
        choices=LifecycleStatus.choices,
        default=LifecycleStatus.DRAFT,
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Only active + approved items enter candidate pool.",
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_learning_items",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Provenance
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_learning_items",
    )

    class Meta(TimestampedModel.Meta):
        verbose_name = "learning item"
        verbose_name_plural = "learning items"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_item_type_display()}] {self.title}"

    @property
    def is_recommendation_eligible(self):
        """Only APPROVED + ACTIVE items enter the recommendation pool."""
        return (
            self.lifecycle_status == self.LifecycleStatus.APPROVED
            and self.is_active
        )


class StudentInteraction(TimestampedModel):
    """
    Observable student interaction with a learning item.

    PH9 D17: CF interactions are observable student interactions with
    learning items (viewed, started, completed, saved/accepted).

    IMPORTANT: Grades are NOT CF preference signals.
    Attendance is NOT CF preference signals.
    Behavior is NOT CF preference signals.
    Counseling is NOT CF preference signals.
    """

    class InteractionType(models.TextChoices):
        VIEWED = "viewed", "Viewed"
        STARTED = "started", "Started"
        COMPLETED = "completed", "Completed"
        SAVED = "saved", "Saved/Accepted"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.PROTECT,
        related_name="learning_interactions",
    )
    learning_item = models.ForeignKey(
        LearningItem,
        on_delete=models.PROTECT,
        related_name="student_interactions",
    )
    interaction_type = models.CharField(
        max_length=10,
        choices=InteractionType.choices,
    )
    interaction_at = models.DateTimeField()

    class Meta(TimestampedModel.Meta):
        verbose_name = "student interaction"
        verbose_name_plural = "student interactions"
        ordering = ["-interaction_at"]
        indexes = [
            models.Index(fields=["student", "learning_item"]),
            models.Index(fields=["interaction_type"]),
        ]

    def __str__(self):
        return (
            f"{self.student} — {self.get_interaction_type_display()} "
            f"→ {self.learning_item}"
        )


class SystemSetting(TimestampedModel):
    """
    A system-wide setting an administrator can change at runtime (FR-034, TC-ADM-11).

    `key` is the stable identifier code reads (`attendance.absence_threshold`),
    not a user-facing label - the label is `description`, written once when the
    setting is seeded and never editable, so a mislabelled control stays
    mislabelled only if the code that names it is wrong.

    `value` is stored as text. Coercion to int/bool/float happens at the read
    site through `apps.cms.settings_registry`, which is the only thing that
    knows a setting's type - the table does not.
    """

    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.TextField(blank=True)
    description = models.TextField(null=True, blank=True)
    # SET_NULL, not CASCADE: removing an administrator must not wipe the
    # configuration they once saved.
    updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "system setting"
        verbose_name_plural = "system settings"
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} = {self.value}"
