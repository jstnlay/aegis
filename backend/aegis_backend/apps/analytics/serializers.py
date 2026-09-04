"""
Phase 9 analytics serializers.

Role-safe JSON responses for analytics endpoints.
"""

from rest_framework import serializers


class AnalyticsSuccessSerializer(serializers.Serializer):
    status = serializers.CharField(default="ok")
    data = serializers.JSONField()


class AnalyticsErrorSerializer(serializers.Serializer):
    status = serializers.CharField(default="error")
    detail = serializers.CharField()
