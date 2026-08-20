"""
Attendance serializers.
"""

from django.utils import timezone
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from .models import AttendanceRecord


class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.user.full_name", read_only=True
    )
    student_id_code = serializers.CharField(
        source="student.student_id", read_only=True
    )
    section_name = serializers.CharField(
        source="section.name", read_only=True
    )
    recorded_by_name = serializers.CharField(
        source="recorded_by.user.full_name", read_only=True
    )

    class Meta:
        model = AttendanceRecord
        fields = (
            "id",
            "student",
            "student_name",
            "student_id_code",
            "section",
            "section_name",
            "date",
            "status",
            "recorded_by",
            "recorded_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "recorded_by", "created_at", "updated_at")
        validators = []

    def validate_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError(
                "Attendance date cannot be in the future."
            )
        return value


class AttendanceSummarySerializer(serializers.Serializer):
    """Read-only serializer for the attendance summary endpoint."""

    student = serializers.UUIDField()
    student_name = serializers.CharField()
    student_id_code = serializers.CharField()
    section_name = serializers.CharField()
    present_count = serializers.IntegerField()
    late_count = serializers.IntegerField()
    absent_count = serializers.IntegerField()
    total_records = serializers.IntegerField()
