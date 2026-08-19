"""
Academics app models - stub models for Phase 1.

These are minimal stubs needed by the accounts app FK references.
Full implementation deferred to Phase 2.
"""

from django.db import models

from core.models import UUIDModel, TimestampedModel


class AcademicYear(TimestampedModel):
    name = models.CharField(max_length=20, help_text='e.g., "2025-2026"')
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        verbose_name = "academic year"
        verbose_name_plural = "academic years"

    def __str__(self):
        return self.name


class GradeLevel(UUIDModel):
    name = models.CharField(max_length=50, help_text='e.g., "Grade 7"')
    level_number = models.PositiveIntegerField()

    class Meta:
        ordering = ["level_number"]
        verbose_name = "grade level"
        verbose_name_plural = "grade levels"

    def __str__(self):
        return self.name


class Section(UUIDModel):
    name = models.CharField(max_length=100, help_text='e.g., "Einstein"')
    grade_level = models.ForeignKey(GradeLevel, on_delete=models.CASCADE, related_name="sections")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="sections")
    adviser = models.ForeignKey(
        "accounts.FacultyProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advised_sections",
    )

    class Meta:
        unique_together = ("name", "grade_level", "academic_year")
        verbose_name = "section"
        verbose_name_plural = "sections"

    def __str__(self):
        return f"{self.name} ({self.grade_level})"
