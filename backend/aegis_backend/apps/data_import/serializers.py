"""
Serializers for data-import (Phase 8.2).

ImportJobSerializer surfaces job metadata + summary + nested per-row
results. A dedicated import-create serializer accepts multipart form data
(file + import_type) and runs the PH8.3 CSV pipeline synchronously.
"""

from rest_framework import serializers

from .models import ImportJob, ImportRecord


class ImportRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRecord
        fields = (
            "id",
            "row_number",
            "data",
            "status",
            "error_message",
            "mapped_to_model",
            "mapped_to_id",
        )
        read_only_fields = fields


class ImportJobSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.SerializerMethodField()
    file_name = serializers.CharField(source="file.name", read_only=True)
    records = ImportRecordSerializer(many=True, read_only=True)
    record_summary = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = (
            "id",
            "uploaded_by",
            "file_name",
            "file_type",
            "import_type",
            "status",
            "total_rows",
            "processed_rows",
            "error_rows",
            "error_log",
            "created_at",
            "completed_at",
            "record_summary",
            "records",
        )
        read_only_fields = fields

    def get_uploaded_by(self, obj):
        user = obj.uploaded_by
        return {
            "id": str(user.pk),
            "name": user.get_full_name() or user.email,
        }

    def get_record_summary(self, obj):
        summary = {s: 0 for s in ("success", "error", "skipped")}
        for entry in obj.records.values("status"):
            summary[entry["status"]] = summary.get(entry["status"], 0) + 1
        return summary


class ImportJobCreateSerializer(serializers.Serializer):
    """
    Accepts multipart/form-data: ``file`` + ``import_type``.

    Confirms the upload against the role-authority matrix and runs the CSV
    pipeline synchronously, populating the job's ImportRecords. No
    Grade/Attendance/Student records are written at this stage.
    """

    file = serializers.FileField()
    import_type = serializers.ChoiceField(
        choices=[(t, t) for t in ("grades", "attendance", "students", "guidance_records")]
    )

    def validate(self, attrs):
        user = self.context["request"].user
        import_type = attrs.get("import_type")
        self._validate_authority(user, import_type)

        uploaded = attrs.get("file")
        if uploaded is None:
            raise serializers.ValidationError({"file": "A file is required."})
        return attrs

    @staticmethod
    def _validate_authority(user, import_type):
        from .constants import ALL_ADMIN_IMPORT_TYPES, ALL_FACULTY_IMPORT_TYPES

        if user.role == "admin":
            if import_type not in ALL_ADMIN_IMPORT_TYPES:
                raise serializers.ValidationError(
                    {"import_type": "This import type is not supported."}
                )
            return
        if user.role == "faculty":
            if import_type not in ALL_FACULTY_IMPORT_TYPES:
                raise serializers.ValidationError(
                    {"detail": "You do not have permission to run this import type."},
                )
            return
        raise serializers.ValidationError(
            {"detail": "You do not have permission to submit imports."}
        )


class ImportJobStatusSerializer(serializers.ModelSerializer):
    """Lightweight status/tracking output for list views."""

    uploaded_by = serializers.SerializerMethodField()
    file_name = serializers.CharField(source="file.name", read_only=True)
    record_summary = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = (
            "id",
            "uploaded_by",
            "file_name",
            "import_type",
            "status",
            "total_rows",
            "processed_rows",
            "error_rows",
            "created_at",
            "completed_at",
            "record_summary",
        )
        read_only_fields = fields

    def get_uploaded_by(self, obj):
        user = obj.uploaded_by
        return {"id": str(user.pk), "name": user.get_full_name() or user.email}

    def get_record_summary(self, obj):
        counts = {}
        for row in obj.records.values("status"):
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {s: counts.get(s, 0) for s in ("success", "error", "skipped")}
