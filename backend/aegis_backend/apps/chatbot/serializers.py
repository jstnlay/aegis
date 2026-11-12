"""Chatbot API serializers."""

from rest_framework import serializers

from apps.chatbot.models import (
    ChatMessage,
    Flag,
    FlagAction,
    FlagRecipient,
    KeywordTerm,
)


class ChatMessageSerializer(serializers.ModelSerializer):
    flag_id = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = (
            "id",
            "message",
            "reply",
            "intent",
            "urgency",
            "severity",
            "sensitive",
            "manual_review",
            "created_at",
            "flag_id",
        )

    def get_flag_id(self, obj):
        flag = getattr(obj, "flag", None)
        return str(flag.id) if flag else None


class FlagActionSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.get_full_name", read_only=True)

    class Meta:
        model = FlagAction
        fields = (
            "id",
            "action",
            "note",
            "is_private",
            "actor_name",
            "metadata",
            "created_at",
        )


class FlagSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.user.get_full_name", read_only=True, default=None
    )
    student_number = serializers.CharField(
        source="student.student_id", read_only=True, default=None
    )
    message = serializers.CharField(source="chat_message.message", read_only=True)
    reply = serializers.CharField(source="chat_message.reply", read_only=True)
    actions = serializers.SerializerMethodField()
    recipients = serializers.SerializerMethodField()

    class Meta:
        model = Flag
        fields = (
            "id",
            "student",
            "student_name",
            "student_number",
            "severity",
            "status",
            "source",
            "categories",
            "summary",
            "manual_review",
            "message",
            "reply",
            "escalation_due_at",
            "escalated_at",
            "acknowledged_at",
            "acknowledged_by",
            "resolved_at",
            "resolution_note",
            "created_at",
            "actions",
            "recipients",
        )
        read_only_fields = fields

    def get_actions(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        rows = obj.actions.all()
        if getattr(user, "role", None) not in ("guidance", "admin"):
            rows = rows.filter(is_private=False)
        return FlagActionSerializer(rows, many=True).data

    def get_recipients(self, obj):
        return [
            {
                "user": str(row.user_id),
                "role": row.role_snapshot,
                "notified_at": row.notified_at,
                "acknowledged_at": row.acknowledged_at,
            }
            for row in obj.recipients.all()
        ]


class FacultyFlagSerializer(serializers.ModelSerializer):
    """
    Content-blind faculty view.

    Deliberately has no student, message, reply, summary or category fields.
    A faculty notice says a student in their class needs support; the
    conversation belongs to Guidance.
    """

    class Meta:
        model = Flag
        fields = (
            "id",
            "severity",
            "status",
            "created_at",
            "acknowledged_at",
            "escalated_at",
        )
        read_only_fields = fields


class KeywordTermSerializer(serializers.ModelSerializer):
    class Meta:
        model = KeywordTerm
        fields = (
            "id",
            "term",
            "match_type",
            "severity",
            "category",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class CaseNoteSerializer(serializers.Serializer):
    note = serializers.CharField(allow_blank=False, max_length=5000)


class ResolutionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=5000)


class AssessmentDraftRequestSerializer(serializers.Serializer):
    topic = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")
    count = serializers.IntegerField(required=False, min_value=1, max_value=10, default=3)


class NoticeAcceptSerializer(serializers.Serializer):
    version = serializers.CharField(required=False, allow_blank=True, max_length=40)
