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


class RiskModelArtifact(TimestampedModel):
    """
    The trained Decision Tree, stored in the database.

    Why this exists rather than a file on disk
    -------------------------------------------
    The model was originally written to
    `ai_engine/saved_models/decision_tree_v1.pkl` by
    `risk_scorer.save_model`. That works locally and is not durable in
    deployment: the host has no persistent disk, so the artifact is lost on
    every deploy or instance restart, and `run_risk_computation` then correctly
    refuses to score anyone. A risk pipeline that silently stops producing
    alerts after a redeploy is worse than one that is visibly stopped.

    The artifact lives beside RiskScore and RiskAlert, which are the other risk
    domain records, and it is the only one of the three that is deliberately
    overwritten rather than appended: RiskScore is a computation *history* and
    RiskAlert is *actionable state*, while the estimator is a derived, fully
    reproducible function of the labelled dataset. Keeping every past tree would
    be storage for something `train_risk_model` can rebuild from the database
    in seconds.

    `activate()` enforces at most one active artifact per version, so a stale
    tree cannot be scored by accident after a retrain.

    `payload` is a pickled estimator. That is not a reviewable format and is not
    meant to be: it is loaded only by `ai_engine.risk_scorer.load_stored_model`,
    and the model it contains carries a warning about its own labels. The
    `metadata` JSON beside it is the part worth reading.
    """

    version = models.CharField(
        max_length=32,
        default="v1",
        help_text="Model version identifier, e.g. 'v1'.",
    )
    payload = models.BinaryField(
        help_text="Pickled sklearn estimator. Loaded only by ai_engine.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Training metadata: sample count, classes, feature importances, "
            "and the labelling caveat."
        ),
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_model_artifacts",
        help_text="Academic year this model was trained against.",
    )
    n_samples = models.PositiveIntegerField(
        default=0,
        help_text="Number of labelled samples the model was fitted on.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only one artifact per version may be active.",
    )

    class Meta(TimestampedModel.Meta):
        verbose_name = "risk model artifact"
        verbose_name_plural = "risk model artifacts"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["version"],
                condition=models.Q(is_active=True),
                name="unique_active_risk_model_per_version",
            ),
        ]

    def __str__(self):
        return (
            f"{self.version} "
            f"({'active' if self.is_active else 'superseded'}, "
            f"{self.n_samples} samples)"
        )

    def activate(self, *, commit: bool = True):
        """
        Make this the artifact loaded for its version.

        Supersedes any other active artifact of the same version first, so the
        partial unique constraint holds and no stale tree can be picked up by
        `load_stored_model` after a retrain.
        """
        RiskModelArtifact.objects.filter(
            version=self.version, is_active=True
        ).exclude(pk=self.pk).update(is_active=False)
        self.is_active = True
        if commit:
            self.save(update_fields=["is_active", "updated_at"])
        return self


class RiskScore(TimestampedModel):
    """
    Machine-generated risk computation result/history.

    Each computation produces a RiskScore record. RiskScore is the
    authoritative computation log. RiskAlert is the actionable Guidance
    alert state derived from RiskScore when warranted.

    PH9 architecture: RiskScore ≠ RiskAlert.
    RiskScore = computation result/history
    RiskAlert = actionable Guidance alert
    """

    class ComputationStatus(models.TextChoices):
        READY = "ready", "Ready"
        INSUFFICIENT_DATA = "insufficient_data", "Insufficient Data"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.PROTECT,
        related_name="risk_scores",
    )
    computation_status = models.CharField(
        max_length=20,
        choices=ComputationStatus.choices,
        default=ComputationStatus.READY,
    )
    risk_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Severity/prioritization index 0-100. Null when INSUFFICIENT_DATA.",
    )
    risk_level = models.CharField(
        max_length=10,
        choices=(
            ("low", "Low"),
            ("moderate", "Moderate"),
            ("high", "High"),
        ),
        null=True,
        blank=True,
        help_text="Operational risk class. Null when INSUFFICIENT_DATA.",
    )
    model_version = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Identifier for the model/version that produced this score.",
    )
    feature_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Feature values used for this computation.",
    )
    explanation = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Student-specific explanation: decision path, contributing "
            "factors, rule traces."
        ),
    )
    computed_at = models.DateTimeField()

    class Meta(TimestampedModel.Meta):
        verbose_name = "risk score"
        verbose_name_plural = "risk scores"
        ordering = ["-computed_at", "-created_at"]
        # Every risk aggregate reads the latest computable scores
        # ("computation_status = 'ready'"), and the guidance dashboard and
        # student profile both read one student's latest score.
        indexes = [
            models.Index(
                fields=["computation_status"], name="risk_score_status_idx"
            ),
            models.Index(
                fields=["student", "computed_at"], name="risk_score_student_time_idx"
            ),
        ]

    def __str__(self):
        score_display = f"{self.risk_score}" if self.risk_score is not None else "N/A"
        return (
            f"Risk Score: {self.student} — "
            f"{score_display} ({self.get_computation_status_display()})"
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class RiskAlert(TimestampedModel):
    """
    Actionable Guidance risk alert for a student.

    Created/updated when a RiskScore computation produces a meaningful
    risk-state change. Manual alerts are also supported.

    PH9 architecture: RiskAlert is created/updated only when actionable
    state changes. Unchanged daily computation does NOT create duplicate
    alerts.

    Status transitions: acknowledge, under_monitoring, resolved, escalated.
    """

    class RiskLevel(models.TextChoices):
        LOW = "low", "Low"
        MODERATE = "moderate", "Moderate"
        HIGH = "high", "High"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        DECISION_TREE = "decision_tree", "Decision Tree"

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
        help_text="Array of risk factor observations (manual or DT-derived).",
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
    risk_score_ref = models.ForeignKey(
        RiskScore,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_alerts",
        help_text="The RiskScore that triggered this alert (null for manual).",
    )
    generated_at = models.DateTimeField()
    last_updated = models.DateTimeField(auto_now=True)

    class Meta(TimestampedModel.Meta):
        verbose_name = "risk alert"
        verbose_name_plural = "risk alerts"
        ordering = ["-generated_at", "-created_at"]
        # Open alerts are counted per student for the guidance dashboard and
        # per day for the 30-day trend, so both the status filter and the
        # creation date are read in a range query.
        indexes = [
            models.Index(fields=["status"], name="risk_alert_status_idx"),
            models.Index(
                fields=["status", "created_at"], name="risk_alert_status_time_idx"
            ),
        ]

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
