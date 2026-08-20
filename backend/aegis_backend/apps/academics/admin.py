"""
Academics admin registrations.
"""

from django.contrib import admin

from .models import (
    AcademicYear,
    Enrollment,
    Grade,
    GradeLevel,
    GradingPeriod,
    Schedule,
    Section,
    Subject,
    SubjectAssignment,
)


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_current")
    list_filter = ("is_current",)
    search_fields = ("name",)


@admin.register(GradeLevel)
class GradeLevelAdmin(admin.ModelAdmin):
    list_display = ("name", "level_number")
    ordering = ("level_number",)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "grade_level", "academic_year", "adviser")
    list_filter = ("grade_level", "academic_year")
    search_fields = ("name",)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "grade_level")
    list_filter = ("grade_level",)
    search_fields = ("code", "name")


@admin.register(SubjectAssignment)
class SubjectAssignmentAdmin(admin.ModelAdmin):
    list_display = ("subject", "faculty", "section", "academic_year")
    list_filter = ("academic_year", "section__grade_level")
    search_fields = ("subject__name", "faculty__user__email")


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ("subject_assignment", "day_of_week", "start_time", "end_time", "room")
    list_filter = ("day_of_week",)


@admin.register(GradingPeriod)
class GradingPeriodAdmin(admin.ModelAdmin):
    list_display = ("name", "academic_year", "order", "start_date", "end_date")
    list_filter = ("academic_year",)
    ordering = ("order",)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "section", "academic_year", "date_enrolled", "is_active")
    list_filter = ("is_active", "academic_year")
    search_fields = ("student__user__email", "student__student_id")


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "subject_assignment",
        "grading_period",
        "score",
        "letter_grade",
        "status",
    )
    list_filter = ("status", "grading_period__academic_year")
    search_fields = ("student__user__email", "student__student_id")
