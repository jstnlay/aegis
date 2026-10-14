from rest_framework import serializers

from .models import SystemSetting


class CmsAnnouncementSerializer(serializers.Serializer):
    """Normalized announcement as exposed to authenticated AEGIS users."""

    document_id = serializers.CharField()
    title = serializers.CharField()
    content = serializers.CharField()
    announcement_type = serializers.ChoiceField(
        choices=["news", "event", "alert", "academic"]
    )
    priority = serializers.ChoiceField(choices=["normal", "high", "urgent"])
    target_roles = serializers.ListField(child=serializers.CharField())
    target_sections = serializers.ListField(child=serializers.CharField())
    published_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField(allow_null=True)


class CmsResourceSerializer(serializers.Serializer):
    """Normalized resource as exposed to authenticated AEGIS users."""

    document_id = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField(allow_null=True, required=False)
    resource_type = serializers.ChoiceField(choices=["document", "link", "video", "other"])
    file_or_url = serializers.CharField(allow_null=True, required=False)
    target_audience = serializers.ListField(child=serializers.CharField())
    is_active = serializers.BooleanField()


class SystemSettingSerializer(serializers.ModelSerializer):
    """
    A runtime-editable system-wide setting (FR-034, TC-ADM-11).

    Every field is read-only except `value`. `key` is what the code reads and
    what the URL addresses, so letting it be written would let an administrator
    rename a setting out from under its callers. `description` is written once
    when the setting is registered, for the same reason - it is the control's
    label, and the code owns the label. `updated_by` is absent from the field
    list rather than read-only, so a payload cannot even name it; the view
    supplies it from the request.

    `value` is validated against the registered type rather than accepted as
    free text, so "abc" for an integer setting is rejected here instead of
    silently reverting to a default the administrator cannot see.
    """

    class Meta:
        model = SystemSetting
        fields = (
            "key",
            "value",
            "description",
            "value_type",
            "default",
            "updated_at",
            "updated_by_email",
        )
        # `key`, `description` and `updated_at` are model fields, so DRF's
        # `read_only_fields` covers them.
        read_only_fields = ("key", "description", "updated_at")

    # Declared explicitly: `value` is the one thing an administrator is here to
    # change, and the rest are derived rather than stored.
    value = serializers.CharField()
    value_type = serializers.SerializerMethodField()
    default = serializers.SerializerMethodField()
    updated_by_email = serializers.SerializerMethodField()

    def get_value_type(self, instance) -> str:
        from .settings_registry import value_type_for

        return value_type_for(instance.key)

    def get_default(self, instance):
        from .settings_registry import default_for

        try:
            return default_for(instance.key)
        except KeyError:
            return None

    def get_updated_by_email(self, instance) -> str | None:
        return instance.updated_by.email if instance.updated_by else None

    def validate_value(self, value: str) -> str:
        """Reject a value that cannot be read as the setting's registered type."""
        from .settings_registry import SettingTypeError, coerce, value_type_for

        key = self.instance.key if self.instance else None
        if key is None:
            return value
        try:
            parsed = coerce(key, value)
        except SettingTypeError as exc:
            raise serializers.ValidationError(
                f"Must be a valid {exc.expected} value."
            )
        # A negative threshold is never a policy: `absence_count >= threshold`
        # with a negative threshold alerts on every absence including the
        # first, which is not a threshold at all. Zero stays legal - "notify
        # on every absence" is a coherent choice an admin may actually want.
        if value_type_for(key) == "int" and parsed < 0:
            raise serializers.ValidationError(
                "Must be zero or a positive whole number."
            )
        return value
