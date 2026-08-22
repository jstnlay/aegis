from django.contrib import admin

from .models import CmsWebhookEvent


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
