from django.contrib import admin

from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "recipient",
        "notification_type",
        "title",
        "is_read",
        "created_at",
    )
    list_filter = ("notification_type", "is_read")
    search_fields = ("recipient__email", "title", "message")
    readonly_fields = ("created_at", "updated_at", "read_at")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "email_enabled", "in_app_enabled", "quiet_hours_start", "quiet_hours_end")
    search_fields = ("user__email",)
