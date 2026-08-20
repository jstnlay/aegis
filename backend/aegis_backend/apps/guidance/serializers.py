"""
Guidance serializers.

Covers: BehavioralNote, ConsultationRecord, RiskAlert,
Intervention, InterventionStep, ProgressNote, and GuidanceReport.
"""

from rest_framework import serializers

from .models import (
    BehavioralNote,
    ConsultationRecord,
    Intervention,
    InterventionStep,
    ProgressNote,
    RiskAlert,
)


class BehavioralNoteSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.user.full_name", read_only=True
    )
    student_id_code = serializers.CharField(
        source="student.student_id", read_only=True
    )
    recorded_by_name = serializers.CharField(
        source="recorded_by.user.full_name", read_only=True
    )

    class Meta:
        model = BehavioralNote
        fields = (
            "id",
            "student",
            "student_name",
            "student_id_code",
            "recorded_by",
            "recorded_by_name",
            "note_type",
            "note_text",
            "date_recorded",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "recorded_by", "created_at", "updated_at")

    def validate_date_recorded(self, value):
        from django.utils import timezone

        if value > timezone.localdate():
            raise serializers.ValidationError(
                "Date recorded cannot be in the future."
            )
        return value

    def validate_note_text(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Note text cannot be empty.")
        return value


class ConsultationRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.user.full_name", read_only=True
    )
    counselor_name = serializers.CharField(
        source="counselor.user.full_name", read_only=True
    )

    class Meta:
        model = ConsultationRecord
        fields = (
            "id",
            "student",
            "student_name",
            "counselor",
            "counselor_name",
            "session_date",
            "session_time",
            "session_type",
            "concern_categories",
            "session_notes",
            "recommendations",
            "next_session_date",
            "priority_level",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "counselor", "created_at", "updated_at")

    def validate_concern_categories(self, value):
        valid_categories = {
            "academic", "behavioral", "emotional",
            "family", "bullying", "other",
        }
        if not isinstance(value, list):
            raise serializers.ValidationError("Must be a JSON array.")
        for cat in value:
            if cat not in valid_categories:
                raise serializers.ValidationError(
                    f"Invalid category: '{cat}'. "
                    f"Valid values: {', '.join(sorted(valid_categories))}."
                )
        return value

    def validate_session_notes(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Session notes cannot be empty.")
        return value


class RiskAlertSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.user.full_name", read_only=True
    )
    assigned_counselor_name = serializers.CharField(
        source="assigned_counselor.user.full_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = RiskAlert
        fields = (
            "id",
            "student",
            "student_name",
            "risk_level",
            "risk_factors",
            "source",
            "status",
            "assigned_counselor",
            "assigned_counselor_name",
            "generated_at",
            "last_updated",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "source",
            "generated_at",
            "last_updated",
            "created_at",
            "updated_at",
        )


class InterventionStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterventionStep
        fields = (
            "id",
            "intervention",
            "title",
            "description",
            "status",
            "order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "intervention", "created_at", "updated_at")


class ProgressNoteSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(
        source="recorded_by.user.full_name", read_only=True
    )

    class Meta:
        model = ProgressNote
        fields = (
            "id",
            "intervention",
            "note_text",
            "recorded_by",
            "recorded_by_name",
            "next_follow_up",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "intervention",
            "recorded_by",
            "created_at",
            "updated_at",
        )


class InterventionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.user.full_name", read_only=True
    )
    assigned_counselor_name = serializers.CharField(
        source="assigned_counselor.user.full_name", read_only=True
    )
    risk_alert_student = serializers.CharField(
        source="risk_alert.student.user.full_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Intervention
        fields = (
            "id",
            "student",
            "student_name",
            "risk_alert",
            "risk_alert_student",
            "assigned_counselor",
            "assigned_counselor_name",
            "plan_start_date",
            "target_review_date",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "assigned_counselor",
            "status",
            "created_at",
            "updated_at",
        )


class GuidanceReportSerializer(serializers.Serializer):
    """Read-only serializer for the guidance report endpoint."""

    student = serializers.UUIDField()
    student_name = serializers.CharField()
    student_id_code = serializers.CharField()
    behavioral_note_counts = serializers.DictField()
    consultation_summary = serializers.DictField()
    intervention_summary = serializers.DictField()
    risk_alert_history = serializers.ListField()
