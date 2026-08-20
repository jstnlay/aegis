"""
Academics app models.

Academic structure: years, grade levels, sections, subjects,
schedules, grading periods, enrollments, and grades.
"""

from django.core.exceptions import ValidationError
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

    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({"end_date": "End date must be after start date."})


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


class Subject(UUIDModel):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True)
    grade_level = models.ForeignKey(GradeLevel, on_delete=models.PROTECT, related_name="subjects")

    class Meta:
        verbose_name = "subject"
        verbose_name_plural = "subjects"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class SubjectAssignment(UUIDModel):
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="assignments")
    faculty = models.ForeignKey(
        "accounts.FacultyProfile", on_delete=models.PROTECT, related_name="subject_assignments"
    )
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="subject_assignments")
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="subject_assignments"
    )

    class Meta:
        unique_together = ("subject", "section", "academic_year")
        verbose_name = "subject assignment"
        verbose_name_plural = "subject assignments"

    def __str__(self):
        return f"{self.subject} — {self.section}"


class Schedule(UUIDModel):
    class DayChoices(models.TextChoices):
        MON = "mon", "Monday"
        TUE = "tue", "Tuesday"
        WED = "wed", "Wednesday"
        THU = "thu", "Thursday"
        FRI = "fri", "Friday"

    subject_assignment = models.ForeignKey(
        SubjectAssignment, on_delete=models.CASCADE, related_name="schedules"
    )
    day_of_week = models.CharField(max_length=3, choices=DayChoices.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = "schedule"
        verbose_name_plural = "schedules"
        ordering = ["day_of_week", "start_time"]

    def __str__(self):
        return f"{self.subject_assignment} — {self.get_day_of_week_display()} {self.start_time}"

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "End time must be after start time."})


class GradingPeriod(UUIDModel):
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="grading_periods"
    )
    name = models.CharField(max_length=50, help_text='e.g., "1st Quarter"')
    order = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["order"]
        verbose_name = "grading period"
        verbose_name_plural = "grading periods"

    def __str__(self):
        return f"{self.name} ({self.academic_year})"

    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({"end_date": "End date must be after start date."})
        if (
            self.academic_year
            and self.start_date
            and self.end_date
            and self.academic_year
        ):
            if self.start_date < self.academic_year.start_date:
                raise ValidationError(
                    {"start_date": "Start date cannot be before the academic year start date."}
                )
            if self.end_date > self.academic_year.end_date:
                raise ValidationError(
                    {"end_date": "End date cannot be after the academic year end date."}
                )


class Enrollment(TimestampedModel):
    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.PROTECT, related_name="enrollments"
    )
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="enrollments")
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="enrollments"
    )
    date_enrolled = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("student", "section", "academic_year")
        verbose_name = "enrollment"
        verbose_name_plural = "enrollments"

    def __str__(self):
        return f"{self.student} — {self.section} ({self.academic_year})"


class Grade(TimestampedModel):
    class StatusChoices(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        FINALIZED = "finalized", "Finalized"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.PROTECT, related_name="grades"
    )
    subject_assignment = models.ForeignKey(
        SubjectAssignment, on_delete=models.PROTECT, related_name="grades"
    )
    grading_period = models.ForeignKey(
        GradingPeriod, on_delete=models.PROTECT, related_name="grades"
    )
    score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Score from 0 to 100",
    )
    letter_grade = models.CharField(max_length=5, blank=True, null=True)
    remarks = models.CharField(max_length=255, blank=True, null=True)
    encoded_by = models.ForeignKey(
        "accounts.FacultyProfile", on_delete=models.PROTECT, related_name="encoded_grades"
    )
    status = models.CharField(
        max_length=10, choices=StatusChoices.choices, default=StatusChoices.DRAFT
    )

    class Meta:
        unique_together = ("student", "subject_assignment", "grading_period")
        verbose_name = "grade"
        verbose_name_plural = "grades"

    def __str__(self):
        score_display = f"{self.score}" if self.score is not None else "N/A"
        return f"{self.student} — {self.subject_assignment} ({self.grading_period}): {score_display}"

    def clean(self):
        if self.score is not None and (self.score < 0 or self.score > 100):
            raise ValidationError({"score": "Score must be between 0 and 100."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
