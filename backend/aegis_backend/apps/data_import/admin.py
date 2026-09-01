"""
Django admin for ImportJob / ImportRecord tracking.
"""

from django.contrib import admin

from .models import ImportJob, ImportRecord


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "uploaded_by",
        "import_type",
        "file_type",
        "status",
        "total_rows",
        "processed_rows",
        "error_rows",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "import_type", "file_type")
    search_fields = ("uploaded_by__email", "uploaded_by__first_name", "uploaded_by__last_name")
    readonly_fields = (
        "id",
        "uploaded_by",
        "file",
        "file_type",
        "import_type",
        "status",
        "total_rows",
        "processed_rows",
        "error_rows",
        "error_log",
        "created_at",
        "updated_at",
        "completed_at",
    )


@admin.register(ImportRecord)
class ImportRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "row_number", "status", "mapped_to_model", "mapped_to_id")
    list_filter = ("status", "job__import_type")
    search_fields = ("job__id", "mapped_to_model")
    readonly_fields = (
        "id",
        "job",
        "row_number",
        "data",
        "status",
        "error_message",
        "mapped_to_model",
        "mapped_to_id",
        "created_at",
        "updated_at",
    )
