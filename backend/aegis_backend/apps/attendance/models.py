"""
Attendance app models.

Daily attendance records per student per date.
Faculty records; students and parents view.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimestampedModel


class AttendanceRecord(TimestampedModel):
    """
    One attendance record per student per date.

    Unique constraint: (student, date) ensures no duplicate records.
    """

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        LATE = "late", "Late"
        ABSENT = "absent", "Absent"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.PROTECT,
        related_name="attendance_records",
    )
    section = models.ForeignKey(
        "academics.Section",
        on_delete=models.PROTECT,
        related_name="attendance_records",
    )
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    recorded_by = models.ForeignKey(
        "accounts.FacultyProfile",
        on_delete=models.PROTECT,
        related_name="attendance_records",
    )

    class Meta:
        unique_together = ("student", "date")
        verbose_name = "attendance record"
        verbose_name_plural = "attendance records"
        ordering = ["-date", "student__user__last_name"]
        # The attendance summary counts a student's records by status
        # (present / late / absent), and the school-wide trend groups by
        # date. The unique constraint covers (student, date) only, so the
        # status filter and the date range are both unindexed without this.
        indexes = [
            models.Index(fields=["student", "status"], name="attend_student_status_idx"),
            models.Index(fields=["date"], name="attend_date_idx"),
        ]

    def __str__(self):
        return (
            f"{self.student} — {self.get_status_display()} on {self.date}"
        )

    def clean(self):
        if self.date and self.date > timezone.localdate():
            raise ValidationError(
                {"date": "Attendance date cannot be in the future."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
