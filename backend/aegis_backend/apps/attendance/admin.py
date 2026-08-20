"""
Attendance admin registrations.
"""

from django.contrib import admin

from .models import AttendanceRecord


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "section",
        "date",
        "status",
        "recorded_by",
    )
    list_filter = ("status", "section__academic_year", "date")
    search_fields = ("student__user__email", "student__student_id")
    date_hierarchy = "date"
