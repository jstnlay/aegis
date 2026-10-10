"""Portfolio serializers."""

from rest_framework import serializers

from .models import PortfolioEntry


class PortfolioEntrySerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.user.get_full_name", read_only=True
    )

    class Meta:
        model = PortfolioEntry
        fields = [
            "id",
            "student",
            "student_name",
            "title",
            "activity_type",
            "description",
            "link_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "student", "created_at", "updated_at"]

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("Title cannot be empty.")
        return value.strip()
