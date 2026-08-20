from django.conf import settings
from django.db import models

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
    quiet_hours_start = models.TimeField(blank=True, null=True)
    quiet_hours_end = models.TimeField(blank=True, null=True)

    class Meta(TimestampedModel.Meta):
        ordering = ["user"]

    def __str__(self):
        return f"Preferences for {self.user}"
