"""
ImportJob / ImportRecord persistence layer (Phase 8.2).

ImportJob tracks a single uploaded structured file and its processing
lifecycle. ImportRecord stores the outcome of each parsed row so later
importers (PH8.5+) can consume validated rows without re-reading the file.

At this stage (PH8.2/8.3) no Grade/Attendance/Student records are written;
this layer is infrastructure + parsing only.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from core.models import TimestampedModel

from .constants import (
    FileType,
    ImportType,
    JobStatus,
    RecordStatus,
)

#: Storage prefix for uploaded import files. Never derived from client input.
IMPORT_FILE_STORAGE_PREFIX = "imports/"

#: Job statuses that are terminal (no further transitions allowed).
_TERMINAL_JOB_STATUSES = frozenset(
    {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PARTIAL}
)

#: Allowed job status transitions: {from: frozenset(to)}.
_JOB_TRANSITIONS = {
    JobStatus.PENDING: {JobStatus.PROCESSING, JobStatus.FAILED},
    JobStatus.PROCESSING: {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PARTIAL},
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.PARTIAL: frozenset(),
}


class ImportJob(TimestampedModel):
    """An uploaded structured import file and its processing lifecycle."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="import_jobs",
        help_text="User who submitted the import.",
    )
    file = models.FileField(
        upload_to=IMPORT_FILE_STORAGE_PREFIX,
        help_text="Uploaded import file (CSV for v1).",
    )
    file_type = models.CharField(max_length=10, choices=FileType.CHOICES)
    import_type = models.CharField(max_length=50, choices=ImportType.CHOICES)
    status = models.CharField(
        max_length=20,
        choices=JobStatus.CHOICES,
        default=JobStatus.PENDING,
        help_text="Current lifecycle status of the import job.",
    )
    total_rows = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Total number of rows parsed from the file.",
    )
    processed_rows = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of rows successfully processed.",
    )
    error_rows = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of rows that errored during validation.",
    )
    error_log = models.JSONField(
        default=list,
        blank=True,
        help_text="Job-level error log (list of safe error messages).",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimestampedModel.Meta):
        verbose_name = "import job"
        verbose_name_plural = "import jobs"

    def __str__(self):
        return f"{self.import_type} job ({self.status})"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pre_status = self.status

    def save(self, *args, **kwargs):
        if self.status != self._pre_status:
            self._validate_transition(self._pre_status, self.status)
        if self.status in _TERMINAL_JOB_STATUSES and self.completed_at is None:
            from django.utils import timezone

            self.completed_at = timezone.now()
        super().save(*args, **kwargs)
        self._pre_status = self.status

    def clean(self):
        super().clean()
        if self.pk is not None:
            try:
                current = ImportJob.objects.get(pk=self.pk)
            except ImportJob.DoesNotExist:
                return
            self._validate_transition(current.status, self.status)

    @staticmethod
    def _validate_transition(from_status, to_status):
        if from_status == to_status:
            return
        if to_status not in _JOB_TRANSITIONS.get(from_status, frozenset()):
            raise ValidationError(
                {
                    "status": (
                        f"Invalid ImportJob status transition: "
                        f"{from_status!r} -> {to_status!r}"
                    )
                }
            )


class ImportRecord(TimestampedModel):
    """Outcome of a single parsed row within an import job."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    job = models.ForeignKey(
        ImportJob,
        on_delete=models.CASCADE,
        related_name="records",
        help_text="Import job this row belongs to.",
    )
    row_number = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="1-based row number in the source file (data rows only).",
    )
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Parsed row data (already CSV-injection-sanitized).",
    )
    status = models.CharField(
        max_length=20,
        choices=RecordStatus.CHOICES,
        default=RecordStatus.ERROR,
    )
    error_message = models.TextField(blank=True, default="")
    mapped_to_model = models.CharField(max_length=100, blank=True, default="")
    mapped_to_id = models.UUIDField(null=True, blank=True, editable=False)

    class Meta(TimestampedModel.Meta):
        verbose_name = "import record"
        verbose_name_plural = "import records"
        constraints = [
            models.UniqueConstraint(
                fields=("job", "row_number"),
                name="uniq_import_job_row",
            )
        ]

    def __str__(self):
        return f"row {self.row_number} ({self.status})"
