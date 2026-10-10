"""
Student portfolio entries.

One row per showcased work. The student owns their rows; staff, linked
parents and administrators read them. No file column: without persistent
disk an uploaded file would not survive a redeploy, so the entry carries
an optional link URL to work hosted elsewhere instead of pretending to
store bytes it cannot keep.
"""

from django.db import models

from core.models import TimestampedModel


class PortfolioEntry(TimestampedModel):
    class ActivityType(models.TextChoices):
        PAPERWORK = "paperwork", "Paperwork"
        TERM_EXAM = "term_exam", "Term exam"
        RECITATION = "recitation", "Recitation"
        QUIZ = "quiz", "Quiz"
        PROJECT = "project", "Project"
        PERFORMANCE_TASK = "performance_task", "Performance task"
        OTHER = "other", "Other"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.CASCADE,
        related_name="portfolio_entries",
    )
    title = models.CharField(max_length=200)
    activity_type = models.CharField(
        max_length=20, choices=ActivityType.choices, default=ActivityType.OTHER
    )
    description = models.TextField(blank=True, default="")
    link_url = models.URLField(max_length=500, blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "portfolio entry"
        verbose_name_plural = "portfolio entries"

    def __str__(self):
        return f"{self.student} — {self.title}"
