from rest_framework import serializers


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
