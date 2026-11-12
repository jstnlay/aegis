"""
Chatbot persistence, flag workflow and notice acceptance.

The existing deterministic chatbot was stateless. These tables make a message
reviewable after it is sent, route a sensitive message to the people who must
act on it, and record every action taken on the resulting flag.

`ChatMessage` stores the turn; `Flag` stores the safety decision. They are
separate because a message exists whether or not it is sensitive, and a flag
may be reopened, acknowledged or marked a false positive without rewriting the
student's transcript.
"""

from django.conf import settings
from django.db import models

from core.fields import EncryptedJSONField, EncryptedTextField
from core.models import TimestampedModel


SEVERITY_CHOICES = (
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("critical", "Critical"),
)

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class KeywordTerm(TimestampedModel):
    """Layer 1 screening term, editable by an administrator."""

    class MatchType(models.TextChoices):
        KEYWORD = "keyword", "Keyword (whole word)"
        PHRASE = "phrase", "Phrase (contains)"
        REGEX = "regex", "Regular expression"

    term = models.CharField(max_length=200)
    match_type = models.CharField(
        max_length=10, choices=MatchType.choices, default=MatchType.KEYWORD
    )
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    category = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_keyword_terms",
    )

    class Meta(TimestampedModel.Meta):
        ordering = ["category", "term"]
        indexes = [
            models.Index(fields=["is_active", "severity"]),
        ]

    def __str__(self):
        return f"{self.term} ({self.severity})"


class ChatMessage(TimestampedModel):
    """
    One persisted chatbot turn.

    `message` is the student's text. `reply` is what the assistant returned.
    The two sensitivity columns are kept separately from `sensitive` so a
    reviewer can see which layer fired; `manual_review` is set when Layer 2
    could not run, never as a substitute for a decision.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages",
    )
    # Encrypted at rest: this is the student's own words. The column holds
    # ciphertext, so a database dump does not carry a disclosure in plain text.
    message = EncryptedTextField()
    reply = EncryptedTextField(blank=True, default="")
    intent = models.CharField(max_length=50, blank=True, default="")
    urgency = models.CharField(max_length=20, blank=True, default="normal")
    severity = models.CharField(
        max_length=10, choices=SEVERITY_CHOICES, default="low"
    )
    sensitive = models.BooleanField(default=False)
    layer1_sensitive = models.BooleanField(default=False)
    layer2_sensitive = models.BooleanField(default=False)
    manual_review = models.BooleanField(default=False)
    model_used = models.CharField(max_length=100, blank=True, default="")
    # What the two layers decided, including the model's own rationale. The
    # rationale can paraphrase what the student said, so the column holds
    # ciphertext: the type stays JSON, the content does not stay readable.
    detection_detail = EncryptedJSONField(default=dict, blank=True)

    class Meta(TimestampedModel.Meta):
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["sensitive", "severity"]),
        ]

    def __str__(self):
        return f"Chat message from {self.user_id} ({self.severity})"


class Flag(TimestampedModel):
    """An actionable sensitive-message flag."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        UNDER_REVIEW = "under_review", "Under Review"
        RESOLVED = "resolved", "Resolved"
        FALSE_POSITIVE = "false_positive", "False Positive"

    class Source(models.TextChoices):
        KEYWORD = "keyword", "Layer 1 keyword"
        GEMINI = "gemini", "Layer 2 Gemini"
        COMBINED = "combined", "Both layers"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_flags",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_flags",
    )
    chat_message = models.OneToOneField(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name="flag",
    )
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    source = models.CharField(max_length=10, choices=Source.choices)
    categories = models.JSONField(default=list, blank=True)
    # The counselor's first line about a flag. Encrypted like the message it
    # describes: a summary of a disclosure is still a disclosure.
    summary = EncryptedTextField(blank=True, default="")
    manual_review = models.BooleanField(default=False)
    escalation_due_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_chat_flags",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True, default="")

    class Meta(TimestampedModel.Meta):
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "severity"]),
            models.Index(fields=["escalation_due_at"]),
        ]

    def __str__(self):
        return f"Flag {self.severity} ({self.status}) for {self.student_id}"


class FlagRecipient(TimestampedModel):
    """One staff member the flag was routed to, and when they acknowledged."""

    flag = models.ForeignKey(
        Flag, on_delete=models.CASCADE, related_name="recipients"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="flag_recipient_rows",
    )
    role_snapshot = models.CharField(max_length=20)
    notified_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimestampedModel.Meta):
        unique_together = ("flag", "user")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user_id} on flag {self.flag_id}"


class FlagAction(TimestampedModel):
    """Append-only action history for a flag."""

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        NOTIFIED = "notified", "Notified"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        NOTE = "note", "Case note"
        ESCALATED = "escalated", "Escalated"
        RESOLVED = "resolved", "Resolved"
        FALSE_POSITIVE = "false_positive", "False positive"
        INTERVENTION_SUGGESTED = "intervention_suggested", "Intervention suggested"
        ASSESSMENT_DRAFTED = "assessment_drafted", "Assessment drafted"

    flag = models.ForeignKey(
        Flag, on_delete=models.CASCADE, related_name="actions"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flag_actions",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    # A private case note about a student. The most sensitive thing the
    # application stores, so it is encrypted at rest like the message.
    note = EncryptedTextField(blank=True, default="")
    is_private = models.BooleanField(
        default=True,
        help_text="Private case notes are visible to guidance and admin only.",
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(TimestampedModel.Meta):
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["flag", "action"]),
        ]

    def __str__(self):
        return f"{self.action} on flag {self.flag_id}"


class AgreementAcceptance(TimestampedModel):
    """A user's acceptance of a named notice version."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agreement_acceptances",
    )
    notice_version = models.CharField(max_length=40)
    accepted_at = models.DateTimeField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta(TimestampedModel.Meta):
        unique_together = ("user", "notice_version")
        ordering = ["-accepted_at"]
        verbose_name = "agreement acceptance"
        verbose_name_plural = "agreement acceptances"

    def __str__(self):
        return f"{self.user_id} accepted {self.notice_version}"
