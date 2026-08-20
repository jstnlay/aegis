from rest_framework import serializers

from .models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    """Read-only serializer for notifications."""

    sender_full_name = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "title",
            "message",
            "link",
            "is_read",
            "read_at",
            "sender",
            "sender_full_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_sender_full_name(self, obj):
        if obj.sender:
            return obj.sender.get_full_name()
        return None


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Read/write serializer for notification preferences."""

    class Meta:
        model = NotificationPreference
        fields = [
            "id",
            "email_enabled",
            "in_app_enabled",
            "quiet_hours_start",
            "quiet_hours_end",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        start = attrs.get("quiet_hours_start", getattr(self.instance, "quiet_hours_start", None))
        end = attrs.get("quiet_hours_end", getattr(self.instance, "quiet_hours_end", None))
        if start is not None and end is not None and start == end:
            raise serializers.ValidationError(
                {"quiet_hours_end": "quiet_hours_start and quiet_hours_end must differ."}
            )
        return attrs
