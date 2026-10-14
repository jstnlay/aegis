from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from .events import schedule_maintenance_window
from .models import MaintenanceWindow, Notification, NotificationPreference


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


class MaintenanceWindowForm(forms.ModelForm):
    """
    Runs the 24-hour rule during form validation (NFR-012).

    Raising from `save_model` cannot render as a form error - the admin shows
    a success redirect or a 500, never the message - so the rule lives here,
    where a refusal is displayed on the field the admin can fix.
    """

    class Meta:
        model = MaintenanceWindow
        fields = ("starts_at", "ends_at", "message")

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        window = MaintenanceWindow(
            starts_at=cleaned.get("starts_at"),
            ends_at=cleaned.get("ends_at"),
        )
        try:
            window.clean()
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                for field, errors in exc.message_dict.items():
                    self.add_error(
                        field if field in self.fields else None, errors
                    )
            else:  # pragma: no cover - clean() always raises dict-form
                self.add_error(None, exc)
        return cleaned


@admin.register(MaintenanceWindow)
class MaintenanceWindowAdmin(admin.ModelAdmin):
    """
    Schedules maintenance through the same service the API uses (NFR-012).

    The default `save()` would create the window and never issue the notice -
    exactly the state NFR-012 forbids - so this override is not a convenience.
    Routing the admin through `schedule_maintenance_window` is what keeps the
    guarantee true for whoever reaches for the simplest available tool.

    Windows are add-only here. Editing a window after its notice went out
    would move downtime without re-notifying, and `save_model` cannot tell an
    edit from a create without re-issuing the notice - which would spam every
    active user on each save. To reschedule, add a new window: the fresh
    notice is then correct rather than surprising.
    """

    form = MaintenanceWindowForm
    list_display = ("starts_at", "ends_at", "notified_at", "created_by")
    ordering = ("starts_at",)
    readonly_fields = ("notified_at", "created_at", "updated_at")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        # `change` is always False: see `has_change_permission` above. The
        # guard stays because a subclass or a future permission change must
        # not silently turn edits into duplicate windows with duplicate
        # notices.
        if change:
            raise ValidationError(
                "Maintenance windows cannot be edited. Add a new window to "
                "reschedule."
            )
        # The form already ran `clean()`, so this is a backstop, not the
        # validation. Re-raising loudly: a silent return would show the
        # admin a success page for a window that was never scheduled.
        try:
            saved = schedule_maintenance_window(
                starts_at=obj.starts_at,
                ends_at=obj.ends_at,
                message=obj.message,
                sender=request.user,
            )
        except ValidationError:
            raise
        obj.pk = saved.pk
        obj.notified_at = saved.notified_at
