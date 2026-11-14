from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimestampedModel


class NotificationType(models.TextChoices):
    GRADE_POSTED = "GRADE_POSTED", "Grade Posted"
    ATTENDANCE_THRESHOLD = "ATTENDANCE_THRESHOLD", "Attendance Threshold Exceeded"
    BEHAVIORAL_WARNING = "BEHAVIORAL_WARNING", "Behavioral Warning"
    BEHAVIORAL_INCIDENT = "BEHAVIORAL_INCIDENT", "Behavioral Incident"
    ASSESSMENT_DEPLOYED = "ASSESSMENT_DEPLOYED", "Assessment Deployed"
    ASSESSMENT_COMPLETED = "ASSESSMENT_COMPLETED", "Assessment Completed"
    RISK_ALERT_GENERATED = "RISK_ALERT_GENERATED", "Risk Alert Generated"
    INTERVENTION_UPDATE = "INTERVENTION_UPDATE", "Intervention Update"
    ANNOUNCEMENT_PUBLISHED = "ANNOUNCEMENT_PUBLISHED", "Announcement Published"
    CONSULTATION_SCHEDULED = "CONSULTATION_SCHEDULED", "Consultation Scheduled"
    MAINTENANCE_NOTICE = "MAINTENANCE_NOTICE", "Scheduled Maintenance"


class Notification(TimestampedModel):
    """
    An in-app notification delivered to a specific user.

    Created exclusively via dispatch_event() — no REST API for creation.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_notifications",
    )
    notification_type = models.CharField(max_length=30, choices=NotificationType.choices)
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)
    deduplication_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Optional key to prevent duplicate notifications (e.g., student+year for threshold events).",
    )

    class Meta(TimestampedModel.Meta):
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["notification_type"]),
        ]

    def __str__(self):
        return f"[{self.get_notification_type_display()}] → {self.recipient}"


class NotificationPreference(TimestampedModel):
    """
    Per-user notification delivery preferences.

    Created lazily via get_or_create when dispatch_event() first
    targets a user, or when the user accesses the preferences endpoint.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    email_enabled = models.BooleanField(default=True)
    in_app_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=True)
    quiet_hours_start = models.TimeField(blank=True, null=True)
    quiet_hours_end = models.TimeField(blank=True, null=True)

    class Meta(TimestampedModel.Meta):
        ordering = ["user"]

    def __str__(self):
        return f"Preferences for {self.user}"


class PushSubscription(TimestampedModel):
    """
    One browser's Web Push endpoint for one user.

    `endpoint` is unique: the push service issues one URL per browser
    subscription, and a shared device that signs in as another user must move
    the row to that user rather than leave the previous account receiving the
    new user's notifications. The API upserts on this field for that reason.

    The two key fields are the browser's public key material. Without them the
    payload cannot be encrypted for that endpoint, so they are required.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)

    class Meta(TimestampedModel.Meta):
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user"])]

    def __str__(self):
        return f"Push subscription for {self.user}"


class MaintenanceWindow(TimestampedModel):
    """
    A scheduled maintenance window (NFR-012, TC-SYS-08).

    NFR-012 reads *"Users shall be notified at least 24 hours in advance of
    scheduled maintenance."* This repo has no task scheduler - no Celery, no
    cron, no beat - so that guarantee cannot be a job that fires later and
    cannot be tested against a clock that has not advanced yet.

    It is enforced structurally instead, and `clean()` is where:

    * a window may not start sooner than `MIN_NOTICE` from now, and
    * the notification is dispatched when the row is created.

    Those two facts together are the requirement: if a window exists, its
    notice has already gone out more than 24 hours ahead of it. There is no
    state in which a window is scheduled and nobody has been told.

    `notified_at` records the send. It is not a promise of delivery -
    `dispatch_event` honours each recipient's `in_app_enabled` preference - so
    it answers "was the notice issued", which is the part NFR-012 makes a
    claim about.
    """

    #: NFR-012's own number, kept as a constant so the rule has one name.
    MIN_NOTICE = timedelta(hours=24)

    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    message = models.TextField(
        blank=True,
        help_text="Shown in the notice. Empty means the window is announced by time alone.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_windows_created",
    )
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimestampedModel.Meta):
        ordering = ["starts_at"]

    def __str__(self):
        return f"Maintenance {self.starts_at:%Y-%m-%d %H:%M}"

    def clean(self):
        """Enforce NFR-012's 24-hour rule (see the class docstring)."""
        super().clean()

        now = timezone.now()

        if self.starts_at is None:
            raise ValidationError({"starts_at": "A start time is required."})
        if self.ends_at is None:
            raise ValidationError({"ends_at": "An end time is required."})
        if self.ends_at <= self.starts_at:
            raise ValidationError(
                {"ends_at": "A window must end after it starts."}
            )

        lead = self.starts_at - now
        if lead < self.MIN_NOTICE:
            raise ValidationError(
                {
                    "starts_at": (
                        "NFR-012 requires users to be notified at least 24 "
                        "hours in advance, so a window cannot start sooner "
                        "than that. Schedule it at least 24 hours from now."
                    )
                }
            )
