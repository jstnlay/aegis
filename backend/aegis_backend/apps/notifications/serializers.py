from rest_framework import serializers

from .models import MaintenanceWindow, Notification, NotificationPreference


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


class MaintenanceWindowSerializer(serializers.ModelSerializer):
    """
    A scheduled maintenance window (NFR-012, TC-SYS-08).

    `lead_hours` is derived rather than stored. NFR-012 is a claim about
    elapsed time, and the number the requirement is measured in belongs on the
    response rather than reconstructed by whoever reads it.
    """

    lead_hours = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceWindow
        fields = [
            "id",
            "starts_at",
            "ends_at",
            "message",
            "lead_hours",
            "notified_at",
            "created_at",
        ]
        read_only_fields = ["id", "lead_hours", "notified_at", "created_at"]

    def get_lead_hours(self, obj):
        from django.utils import timezone as tz

        if obj.notified_at:
            issued = obj.notified_at
        else:
            issued = tz.now()
        return int((obj.starts_at - issued).total_seconds() // 3600)
