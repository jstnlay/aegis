"""
Phase 9 chatbot — API views.

Exposes the deterministic chatbot service boundary. The application
remains authoritative — no direct DB access by LLM.

PH9.10: builds the chatbot policy + deterministic layer WITHOUT
prematurely depending on the final LLM. Complex LLM response generation
(PH9.12) is deferred until D29 model selection is approved.
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chatbot import service
from apps.chatbot.taxonomy import ChatIntent, UrgencyLevel


class ChatMessageRequestSerializer:
    """Lightweight validation for chat message requests."""

    @staticmethod
    def validate(data):
        errors = {}
        message = data.get("message", "").strip()
        if not message:
            errors["message"] = "Message is required."
        if len(message) > 2000:
            errors["message"] = "Message too long (max 2000 chars)."
        return message, errors


class ChatView(APIView):
    """Chatbot message endpoint (deterministic layer)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.chatbot.taxonomy import ChatIntent

        message, errors = ChatMessageRequestSerializer.validate(
            request.data
        )
        if errors:
            return Response(
                {"detail": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # PH9.10: deterministic only. No LLM yet.
        response = service.handle_message(
            request.user,
            message,
            use_llm=False,
        )

        return Response(response.to_dict(), status=status.HTTP_200_OK)


class IntentsView(APIView):
    """Expose the supported intent taxonomy (D25)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        intents = [
            {"id": i.value, "label": i.name}
            for i in ChatIntent
        ]
        urgencies = [
            {"id": u.value, "label": u.name}
            for u in UrgencyLevel
        ]
        return Response({
            "intents": intents,
            "urgencies": urgencies,
        })
