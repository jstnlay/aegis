from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Read-only admin interface for audit logs.

    Audit logs are immutable evidence records.  No add, change, or
    delete operations are permitted through the admin interface.
    """

    list_display = (
        "id",
        "user",
        "action",
        "model_name",
        "object_id",
        "timestamp",
    )
    list_filter = ("action", "model_name")
    search_fields = ("model_name",)
    ordering = ("-timestamp",)
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
