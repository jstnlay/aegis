"""
Chatbot API: persisted role-aware chat, notice acceptance, flag workflow and
administrator controls.
"""

from __future__ import annotations

import logging
import uuid

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chatbot import agreements, gemini_client, insights, routing
from apps.chatbot.models import (
    ChatMessage,
    ChatThread,
    Flag,
    FlagAction,
    KeywordTerm,
    KnowledgeChunk,
    KnowledgeDocument,
)
from apps.chatbot.pipeline import process_message
from apps.chatbot.serializers import (
    AssessmentDraftRequestSerializer,
    CaseNoteSerializer,
    ChatMessageSerializer,
    ChatThreadDetailSerializer,
    ChatThreadSerializer,
    FacultyFlagSerializer,
    FlagSerializer,
    KeywordTermSerializer,
    KnowledgeDocumentSerializer,
    NoticeAcceptSerializer,
    ResolutionSerializer,
)
from apps.chatbot.taxonomy import ChatIntent, UrgencyLevel
from core.crypto import status as encryption_status
from core.permissions import IsAdminUser

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 2000


class ChatMessageRequestSerializer:
    @staticmethod
    def validate(data):
        errors = {}
        message = str(data.get("message", "")).strip()
        if not message:
            errors["message"] = "Message is required."
        if len(message) > MAX_MESSAGE_LENGTH:
            errors["message"] = f"Message too long (max {MAX_MESSAGE_LENGTH} chars)."
        return message, errors


class ChatView(APIView):
    """POST /chatbot/message/ - persisted, role-aware, screened."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        message, errors = ChatMessageRequestSerializer.validate(request.data)
        if errors:
            return Response({"detail": errors}, status=status.HTTP_400_BAD_REQUEST)

        if agreements.student_must_accept(request.user):
            return Response(
                {
                    "detail": "Accept the current student notice before chatting.",
                    "notice_required": True,
                    "notice": agreements.notice_payload(request.user),
                },
                status=status.HTTP_428_PRECONDITION_REQUIRED,
            )

        thread = None
        thread_id = request.data.get("thread_id")
        if thread_id:
            try:
                thread_uuid = uuid.UUID(str(thread_id))
            except (TypeError, ValueError):
                return Response(
                    {"detail": "Invalid chat id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            thread = ChatThread.objects.filter(
                id=thread_uuid,
                user=request.user,
                deleted_at__isnull=True,
            ).first()
            if thread is None:
                return Response(
                    {"detail": "Chat not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        response = process_message(
            request.user, message, use_gemini=True, thread=thread
        )
        payload = response.to_dict()
        payload["notice"] = agreements.notice_payload(request.user)
        return Response(payload, status=status.HTTP_200_OK)


class ChatThreadListView(APIView):
    """GET /chatbot/threads/ - the caller's own conversations."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = (
            ChatThread.objects.filter(
                user=request.user, deleted_at__isnull=True
            )
            .annotate(message_count=Count("messages"))
            .order_by("-updated_at")[:50]
        )
        return Response({"results": ChatThreadSerializer(rows, many=True).data})


class ChatThreadDetailView(APIView):
    """GET or DELETE /chatbot/threads/<id>/ - one conversation."""

    permission_classes = [IsAuthenticated]

    def _thread(self, request, pk):
        return (
            ChatThread.objects.filter(
                pk=pk, user=request.user, deleted_at__isnull=True
            )
            .annotate(message_count=Count("messages"))
            .first()
        )

    def get(self, request, pk):
        thread = self._thread(request, pk)
        if thread is None:
            return Response(
                {"detail": "Chat not found."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(ChatThreadDetailSerializer(thread).data)

    def delete(self, request, pk):
        thread = self._thread(request, pk)
        if thread is None:
            return Response(
                {"detail": "Chat not found."}, status=status.HTTP_404_NOT_FOUND
            )
        # Soft delete: a hard one would cascade to `Flag`, deleting a safety
        # record a counselor may still have to act on. The student stops
        # seeing it; Guidance and the retention job still can.
        now = timezone.now()
        ChatThread.objects.filter(pk=thread.pk).update(
            deleted_at=now, updated_at=now
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatHistoryView(APIView):
    """GET or DELETE /chatbot/history/ - the caller's persisted turns."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 50) or 50)
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 200))
        visible = Q(thread__isnull=True) | Q(thread__deleted_at__isnull=True)
        rows = ChatMessage.objects.filter(user=request.user).filter(visible)[:limit]
        return Response({"results": ChatMessageSerializer(rows, many=True).data})

    def delete(self, request):
        now = timezone.now()
        deleted = ChatThread.objects.filter(
            user=request.user, deleted_at__isnull=True
        ).update(deleted_at=now, updated_at=now)
        return Response({"deleted": deleted})


class NoticeView(APIView):
    """GET/POST /chatbot/notice/ - current student notice and acceptance."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(agreements.notice_payload(request.user))

    def post(self, request):
        serializer = NoticeAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            acceptance = agreements.accept_notice(
                request.user,
                version=serializer.validated_data.get("version") or None,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc), "notice": agreements.notice_payload(request.user)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "detail": "Notice accepted.",
                "version": acceptance.notice_version,
                "accepted_at": acceptance.accepted_at,
            },
            status=status.HTTP_201_CREATED,
        )


def _visible_flags(user):
    if user.role in ("guidance", "admin"):
        return Flag.objects.all()
    return Flag.objects.filter(recipients__user=user).distinct()


class FlagListView(APIView):
    """GET /chatbot/flags/ - guidance inbox or a faculty recipient feed."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ("guidance", "admin", "faculty"):
            return Response(
                {"detail": "Access denied."}, status=status.HTTP_403_FORBIDDEN
            )

        # Lazy escalation: no scheduler is required for the timer to have teeth.
        if request.user.role in ("guidance", "admin"):
            routing.escalate_stale_flags()

        queryset = _visible_flags(request.user).select_related(
            "student__user", "chat_message"
        ).prefetch_related("actions", "recipients")

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        severity = request.query_params.get("severity")
        if severity:
            queryset = queryset.filter(severity=severity)

        if request.user.role == "faculty":
            serializer = FacultyFlagSerializer(queryset, many=True)
        else:
            serializer = FlagSerializer(
                queryset, many=True, context={"request": request}
            )
        return Response({"results": serializer.data})


class FlagDetailView(APIView):
    """GET /chatbot/flags/<id>/ - full flag for guidance/admin only."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        flag = _visible_flags(request.user).select_related(
            "student__user", "chat_message"
        ).prefetch_related("actions", "recipients").filter(pk=pk).first()
        if flag is None:
            return Response({"detail": "Flag not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role not in ("guidance", "admin"):
            return Response(
                {"detail": "Chat content is restricted to Guidance."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(
            FlagSerializer(flag, context={"request": request}).data
        )


class FlagActionView(APIView):
    """POST /chatbot/flags/<id>/<action>/ - acknowledge, note, resolve, etc."""

    permission_classes = [IsAuthenticated]
    action_name = None

    def post(self, request, pk):
        flag = _visible_flags(request.user).filter(pk=pk).first()
        if flag is None:
            return Response({"detail": "Flag not found."}, status=status.HTTP_404_NOT_FOUND)
        if not routing.may_manage_flag(request.user, flag):
            return Response(
                {"detail": "Only Guidance or an administrator can act on a flag."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            return self._handle(request, flag)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def _handle(self, request, flag):
        raise NotImplementedError


class FlagAcknowledgeView(FlagActionView):
    def _handle(self, request, flag):
        note = str(request.data.get("note", "") or "").strip()
        routing.acknowledge_flag(flag, user=request.user, note=note)
        return Response(FlagSerializer(flag, context={"request": request}).data)


class FlagNoteView(FlagActionView):
    def _handle(self, request, flag):
        serializer = CaseNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = routing.add_case_note(
            flag, user=request.user, note=serializer.validated_data["note"]
        )
        return Response(
            {
                "id": str(action.id),
                "action": action.action,
                "note": action.note,
                "created_at": action.created_at,
            },
            status=status.HTTP_201_CREATED,
        )


class FlagResolveView(FlagActionView):
    def _handle(self, request, flag):
        serializer = ResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        routing.resolve_flag(
            flag, user=request.user, note=serializer.validated_data.get("note", "")
        )
        return Response(FlagSerializer(flag, context={"request": request}).data)


class FlagFalsePositiveView(FlagActionView):
    def _handle(self, request, flag):
        serializer = ResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        routing.mark_false_positive(
            flag, user=request.user, note=serializer.validated_data.get("note", "")
        )
        return Response(FlagSerializer(flag, context={"request": request}).data)


class FlagInterventionSuggestionsView(FlagActionView):
    def _handle(self, request, flag):
        result = insights.intervention_suggestions(flag)
        FlagAction.objects.create(
            flag=flag,
            actor=request.user,
            action=FlagAction.Action.INTERVENTION_SUGGESTED,
            note="",
            is_private=True,
            metadata={"source": result["source"], "count": len(result["suggestions"])},
        )
        return Response(result)


class FlagAssessmentDraftView(FlagActionView):
    def _handle(self, request, flag):
        serializer = AssessmentDraftRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = insights.assessment_drafts(
            flag,
            topic=serializer.validated_data.get("topic") or None,
            count=serializer.validated_data.get("count", 3),
        )
        FlagAction.objects.create(
            flag=flag,
            actor=request.user,
            action=FlagAction.Action.ASSESSMENT_DRAFTED,
            note="",
            is_private=True,
            metadata={"source": result["source"], "count": len(result["drafts"])},
        )
        return Response(result)


class KeywordTermViewSet(viewsets.ModelViewSet):
    """Admin CRUD for Layer 1 terms."""

    queryset = KeywordTerm.objects.all()
    serializer_class = KeywordTermSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class KnowledgeDocumentViewSet(viewsets.ModelViewSet):
    """Admin CRUD for the documents the assistant answers from."""

    queryset = KnowledgeDocument.objects.all()
    serializer_class = KnowledgeDocumentSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AdminDashboardView(APIView):
    """GET /chatbot/admin/dashboard/ - aggregate flag and screening counts."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        routing.escalate_stale_flags()
        flags = Flag.objects.all()
        since = timezone.now() - timezone.timedelta(days=7)
        acknowledged = flags.filter(acknowledged_at__isnull=False)
        ack_minutes = None
        if acknowledged.exists():
            deltas = [
                (row.acknowledged_at - row.created_at).total_seconds() / 60
                for row in acknowledged.only("created_at", "acknowledged_at")
            ]
            ack_minutes = round(sum(deltas) / len(deltas), 1)

        false_positives = flags.filter(status=Flag.Status.FALSE_POSITIVE)

        return Response(
            {
                "flags": {
                    "total": flags.count(),
                    "open": flags.filter(
                        status__in=[Flag.Status.OPEN, Flag.Status.UNDER_REVIEW]
                    ).count(),
                    "unacknowledged": flags.filter(acknowledged_at__isnull=True).exclude(
                        status__in=[Flag.Status.RESOLVED, Flag.Status.FALSE_POSITIVE]
                    ).count(),
                    "manual_review": flags.filter(manual_review=True).count(),
                    "escalated": flags.filter(escalated_at__isnull=False).count(),
                    "by_severity": list(
                        flags.values("severity").annotate(count=Count("id")).order_by("severity")
                    ),
                    "by_status": list(
                        flags.values("status").annotate(count=Count("id")).order_by("status")
                    ),
                },
                "messages": {
                    "last_7_days": ChatMessage.objects.filter(created_at__gte=since).count(),
                    "sensitive_last_7_days": ChatMessage.objects.filter(
                        created_at__gte=since, sensitive=True
                    ).count(),
                },
                "keywords": {
                    "active": KeywordTerm.objects.filter(is_active=True).count(),
                    "total": KeywordTerm.objects.count(),
                },
                # The retrieval corpus. `documents` with no chunks are
                # unretrievable, so the chunk count is the number that matters:
                # a document that has not been indexed answers nothing.
                "knowledge": {
                    "documents": KnowledgeDocument.objects.count(),
                    "active": KnowledgeDocument.objects.filter(is_active=True).count(),
                    "chunks": KnowledgeChunk.objects.count(),
                    "unindexed": KnowledgeDocument.objects.filter(
                        chunks__isnull=True
                    ).count(),
                },
                "acknowledgment": {
                    "timer_minutes": routing.acknowledgment_minutes(),
                    "per_severity": routing.severity_windows(),
                    "average_minutes": ack_minutes,
                },
                "model": gemini_client.status(),
                # Whether student free text is encrypted at rest. The
                # administrator has to be able to see this, because a
                # deployment without a key stores disclosures in plain text.
                "encryption": encryption_status(),
                # The feedback loop. A flag marked as a false positive is the
                # only evidence the school has that a term cries wolf, so the
                # newest ones are listed here with the note the counselor left.
                # The message itself is not repeated here: the admin console is
                # an oversight surface, not a second copy of the inbox.
                "false_positives": {
                    "total": false_positives.count(),
                    "recent": [
                        {
                            "id": str(row.id),
                            "severity": row.severity,
                            "categories": row.categories,
                            "note": row.resolution_note,
                            "created_at": row.created_at,
                        }
                        for row in false_positives.order_by("-created_at")[:10]
                    ],
                },
            }
        )


class AdminModelStatusView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        return Response(
            {
                **gemini_client.status(),
                "encryption": encryption_status(),
                "layer1": "database keywords + deterministic policy patterns",
                "layer2": "Gemini classification with Layer 1 fallback",
                "privacy": (
                    "Only message text is sent for classification. Names, "
                    "student numbers and records are never included."
                ),
            }
        )


class AdminEscalateView(APIView):
    """POST /chatbot/admin/escalate/ - run the acknowledgment timer now."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        rows = routing.escalate_stale_flags()
        return Response({"escalated": len(rows), "ids": [str(row.id) for row in rows]})


class IntentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "intents": [{"id": item.value, "label": item.name} for item in ChatIntent],
                "urgencies": [
                    {"id": item.value, "label": item.name} for item in UrgencyLevel
                ],
            }
        )
