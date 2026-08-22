"""
Assessments admin registrations.
"""

from django.contrib import admin

from .models import Assessment, AssessmentQuestion, AssessmentResult


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "assessment_type",
        "creator_role",
        "created_by",
        "is_published",
        "published_at",
        "deadline",
    )
    list_filter = ("assessment_type", "creator_role", "is_published")
    search_fields = ("title", "created_by__email")
    readonly_fields = ("published_at", "created_at", "updated_at")


@admin.register(AssessmentQuestion)
class AssessmentQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "assessment",
        "order",
        "question_type",
        "question_text",
    )
    list_filter = ("question_type",)
    ordering = ("assessment", "order")
    search_fields = ("question_text", "assessment__title")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "assessment",
        "score",
        "total_possible",
        "percentage",
        "status",
        "completed_at",
    )
    list_filter = ("status",)
    search_fields = (
        "student__user__email",
        "student__student_id",
        "assessment__title",
    )
    readonly_fields = (
        "score",
        "total_possible",
        "percentage",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    )
