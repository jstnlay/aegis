from django.contrib import admin

from .models import CmsWebhookEvent, SystemSetting


@admin.register(CmsWebhookEvent)
class CmsWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "status", "source", "created_at")
    list_filter = ("status", "source", "event_type")
    search_fields = ("event_id",)
    ordering = ("-created_at",)
    readonly_fields = (
        "event_id",
        "source",
        "event_type",
        "status",
        "detail",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "updated_by", "updated_at")
    search_fields = ("key",)
    readonly_fields = ("key", "description", "updated_at", "created_at")
    ordering = ("key",)

    # `key` and `description` are read-only because the code reads the former
    # and the latter is its label - see SystemSettingSerializer.
