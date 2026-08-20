"""
Guidance app models.

Behavioral notes, consultation records, risk alerts,
intervention plans, intervention steps, and progress notes.

Faculty records behavioral notes. Guidance manages all other records.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimestampedModel


class BehavioralNote(TimestampedModel):
    """
    A behavioral observation recorded by a faculty member for a student.

    Immutable after creation — no update or delete.
    """

    class NoteType(models.TextChoices):
        POSITIVE = "positive", "Positive"
        WARNING = "warning", "Warning"
        INCIDENT = "incident", "Incident"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.PROTECT,
        related_name="behavioral_notes",
    )
    recorded_by = models.ForeignKey(
        "accounts.FacultyProfile",
        on_delete=models.PROTECT,
        related_name="behavioral_notes",
    )
    note_type = models.CharField(max_length=10, choices=NoteType.choices)
    note_text = models.TextField()
    date_recorded = models.DateField()

    class Meta(TimestampedModel.Meta):
        verbose_name = "behavioral note"
        verbose_name_plural = "behavioral notes"
        ordering = ["-date_recorded", "-created_at"]

    def __str__(self):
        return (
            f"{self.student} — {self.get_note_type_display()} "
            f"on {self.date_recorded}"
        )

    def clean(self):
        if self.date_recorded and self.date_recorded > timezone.localdate():
            raise ValidationError(
                {"date_recorded": "Date recorded cannot be in the future."}
            )
        if self.note_text is not None and not self.note_text.strip():
            raise ValidationError({"note_text": "Note text cannot be empty."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ConsultationRecord(TimestampedModel):
    """
    A counseling session record managed by a guidance counselor.
    """

    class SessionType(models.TextChoices):
        INDIVIDUAL_COUNSELING = "individual_counseling", "Individual Counseling"
        GROUP = "group", "Group"
        PARENT_CONFERENCE = "parent_conference", "Parent Conference"
        FOLLOW_UP = "follow_up", "Follow Up"

    class PriorityLevel(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    class Status(models.TextChoices):
        ONGOING = "ongoing", "Ongoing"
        COMPLETED = "completed", "Completed"
        FOLLOW_UP = "follow_up", "Follow Up"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.PROTECT,
        related_name="consultation_records",
    )
    counselor = models.ForeignKey(
        "accounts.GuidanceProfile",
        on_delete=models.PROTECT,
        related_name="consultation_records",
    )
    session_date = models.DateField()
    session_time = models.TimeField()
    session_type = models.CharField(
        max_length=25, choices=SessionType.choices
    )
    concern_categories = models.JSONField(
        help_text=(
            'Array of concern categories, e.g. ["academic", "behavioral"]. '
            "Valid values: academic, behavioral, emotional, family, bullying, other."
        ),
    )
    session_notes = models.TextField()
    recommendations = models.TextField(blank=True, null=True)
    next_session_date = models.DateField(blank=True, null=True)
    priority_level = models.CharField(
        max_length=10, choices=PriorityLevel.choices
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.ONGOING
    )

    class Meta(TimestampedModel.Meta):
        verbose_name = "consultation record"
        verbose_name_plural = "consultation records"
        ordering = ["-session_date", "-created_at"]

    def __str__(self):
        return (
            f"Consultation: {self.student} with {self.counselor} "
            f"on {self.session_date}"
        )

    def clean(self):
        valid_categories = {
            "academic", "behavioral", "emotional",
            "family", "bullying", "other",
        }
        if self.concern_categories is not None:
            if not isinstance(self.concern_categories, list):
                raise ValidationError(
                    {"concern_categories": "Must be a JSON array."}
                )
            for cat in self.concern_categories:
                if cat not in valid_categories:
                    raise ValidationError(
                        {
                            "concern_categories": (
                                f"Invalid category: '{cat}'. "
                                f"Valid values: {', '.join(sorted(valid_categories))}."
                            )
                        }
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class RiskAlert(TimestampedModel):
    """
    A manually-created risk alert for a student.

    In Phase 5, only manual alerts are supported.
    AI-generated alerts (source=decision_tree) are deferred to Phase 9.
    """

    class RiskLevel(models.TextChoices):
        LOW = "low", "Low"
        MODERATE = "moderate", "Moderate"
        HIGH = "high", "High"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        UNDER_MONITORING = "under_monitoring", "Under Monitoring"
        RESOLVED = "resolved", "Resolved"
        ESCALATED = "escalated", "Escalated"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.PROTECT,
        related_name="risk_alerts",
    )
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices)
    risk_factors = models.JSONField(
        default=list,
        blank=True,
        help_text="Array of manually-entered risk factor observations.",
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    assigned_counselor = models.ForeignKey(
        "accounts.GuidanceProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_alerts",
    )
    generated_at = models.DateTimeField()
    last_updated = models.DateTimeField(auto_now=True)

    class Meta(TimestampedModel.Meta):
        verbose_name = "risk alert"
        verbose_name_plural = "risk alerts"
        ordering = ["-generated_at", "-created_at"]

    def __str__(self):
        return (
            f"Risk Alert: {self.student} — "
            f"{self.get_risk_level_display()} ({self.get_status_display()})"
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Intervention(TimestampedModel):
    """
    An intervention plan for an at-risk student, managed by guidance.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.PROTECT,
        related_name="interventions",
    )
    risk_alert = models.ForeignKey(
        RiskAlert,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interventions",
    )
    assigned_counselor = models.ForeignKey(
        "accounts.GuidanceProfile",
        on_delete=models.PROTECT,
        related_name="interventions",
    )
    plan_start_date = models.DateField()
    target_review_date = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta(TimestampedModel.Meta):
        verbose_name = "intervention"
        verbose_name_plural = "interventions"
        ordering = ["-plan_start_date", "-created_at"]

    def __str__(self):
        return (
            f"Intervention: {self.student} — "
            f"{self.get_status_display()} "
            f"(started {self.plan_start_date})"
        )

    def clean(self):
        if self.target_review_date and self.plan_start_date:
            if self.target_review_date < self.plan_start_date:
                raise ValidationError(
                    {
                        "target_review_date": (
                            "Target review date cannot be before "
                            "the plan start date."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class InterventionStep(TimestampedModel):
    """
    A discrete step within an intervention plan.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        SCHEDULED = "scheduled", "Scheduled"

    intervention = models.ForeignKey(
        Intervention,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING,
    )
    order = models.PositiveIntegerField()

    class Meta(TimestampedModel.Meta):
        verbose_name = "intervention step"
        verbose_name_plural = "intervention steps"
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"Step {self.order}: {self.title} ({self.get_status_display()})"

    def clean(self):
        if self.order < 1:
            raise ValidationError({"order": "Order must be at least 1."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProgressNote(TimestampedModel):
    """
    A progress note recorded by a guidance counselor for an intervention.
    """

    intervention = models.ForeignKey(
        Intervention,
        on_delete=models.CASCADE,
        related_name="progress_notes",
    )
    note_text = models.TextField()
    recorded_by = models.ForeignKey(
        "accounts.GuidanceProfile",
        on_delete=models.PROTECT,
        related_name="progress_notes",
    )
    next_follow_up = models.DateTimeField(blank=True, null=True)

    class Meta(TimestampedModel.Meta):
        verbose_name = "progress note"
        verbose_name_plural = "progress notes"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Progress Note for {self.intervention} "
            f"by {self.recorded_by} on {self.created_at}"
        )

    def clean(self):
        if self.note_text is not None and not self.note_text.strip():
            raise ValidationError({"note_text": "Note text cannot be empty."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
