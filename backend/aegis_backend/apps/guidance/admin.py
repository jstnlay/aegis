"""
Guidance admin registrations.
"""

from django.contrib import admin

from .models import (
    BehavioralNote,
    ConsultationRecord,
    Intervention,
    InterventionStep,
    ProgressNote,
    RiskAlert,
)


@admin.register(BehavioralNote)
class BehavioralNoteAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "recorded_by",
        "note_type",
        "date_recorded",
    )
    list_filter = ("note_type", "date_recorded")
    search_fields = ("student__user__email", "student__student_id")
    date_hierarchy = "date_recorded"
    readonly_fields = ("created_at", "updated_at")


@admin.register(ConsultationRecord)
class ConsultationRecordAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "counselor",
        "session_date",
        "session_type",
        "priority_level",
        "status",
    )
    list_filter = ("session_type", "priority_level", "status")
    search_fields = ("student__user__email", "student__student_id")
    date_hierarchy = "session_date"
    readonly_fields = ("created_at", "updated_at")


@admin.register(RiskAlert)
class RiskAlertAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "risk_level",
        "source",
        "status",
        "assigned_counselor",
        "generated_at",
    )
    list_filter = ("risk_level", "source", "status")
    search_fields = ("student__user__email", "student__student_id")
    readonly_fields = ("generated_at", "last_updated", "created_at", "updated_at")


@admin.register(Intervention)
class InterventionAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "assigned_counselor",
        "risk_alert",
        "plan_start_date",
        "status",
    )
    list_filter = ("status",)
    search_fields = ("student__user__email", "student__student_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(InterventionStep)
class InterventionStepAdmin(admin.ModelAdmin):
    list_display = (
        "intervention",
        "title",
        "status",
        "order",
    )
    list_filter = ("status",)
    ordering = ("intervention", "order")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProgressNote)
class ProgressNoteAdmin(admin.ModelAdmin):
    list_display = (
        "intervention",
        "recorded_by",
        "created_at",
    )
    search_fields = ("intervention__student__user__email",)
    readonly_fields = ("created_at", "updated_at")
