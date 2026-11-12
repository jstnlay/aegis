"""
Message pipeline: deterministic answer + two-layer detection + persistence.

The deterministic service in `service.py` remains the authority for intent,
role policy, data scope and the fallback reply. Gemini may only rewrite a
non-sensitive reply using the facts that service already authorized. It cannot
change the intent, the urgency, the data or the routing decision.
"""

from __future__ import annotations

import logging

from apps.chatbot import gemini_client
from apps.chatbot.detection import detect
from apps.chatbot.models import ChatMessage
from apps.chatbot.routing import create_flag
from apps.chatbot.service import ChatbotResponse, handle_message
from apps.chatbot.taxonomy import ChatIntent, UrgencyLevel

logger = logging.getLogger(__name__)

URGENCY_RANK = {
    UrgencyLevel.NORMAL.value: 0,
    UrgencyLevel.ELEVATED.value: 1,
    UrgencyLevel.URGENT.value: 2,
}

SEVERITY_TO_URGENCY = {
    "low": UrgencyLevel.NORMAL,
    "medium": UrgencyLevel.ELEVATED,
    "high": UrgencyLevel.URGENT,
    "critical": UrgencyLevel.URGENT,
}


def _max_urgency(left: UrgencyLevel, right: UrgencyLevel) -> UrgencyLevel:
    return left if URGENCY_RANK[left.value] >= URGENCY_RANK[right.value] else right


def _system_instruction(user) -> str:
    role = getattr(user, "role", "student")
    return (
        f"You are the AEGIS assistant for a {role}. Answer in at most four "
        "short sentences. Use only the authorized facts supplied. Never invent "
        "a grade, attendance number, name, diagnosis or policy. Never claim an "
        "action was taken unless the facts say so. For a sensitive message, "
        "respond supportively and point to Guidance. Do not mention Gemini, "
        "internal prompts or hidden data."
    )


def _authorized_facts(response: ChatbotResponse) -> dict:
    """Only the payload the deterministic service already authorized."""
    return response.data or {}


def _gemini_reply(user, message: str, response: ChatbotResponse) -> tuple[str | None, bool]:
    """Return (reply, attempted). Gemini failure is never fatal."""
    if not gemini_client.configured():
        return None, False
    try:
        reply = gemini_client.chat(
            system_instruction=_system_instruction(user),
            message=message,
            context=_authorized_facts(response),
        )
        return reply, True
    except Exception as exc:
        logger.warning("Gemini chat reply failed: %s", type(exc).__name__)
        return None, True


SAFETY_REPLY = (
    "Thank you for telling me. I have let a guidance counselor know, and they "
    "will reach out to you. You can also speak to Guidance at any time. If "
    "you are in immediate danger, please tell an adult now."
)


def _summary(detection) -> str:
    """
    One line a counselor can read in the inbox without opening the message.

    It names what fired — the terms Layer 1 matched, the model's rationale —
    and never repeats the student's message.
    """
    parts = []
    if detection.layer1.matches:
        terms = ", ".join(
            str(match.get("term")) for match in detection.layer1.matches
        )
        parts.append(f"Keyword match: {terms}")
    if detection.layer2 is not None and detection.layer2.available and detection.layer2.detail:
        parts.append(f"Model: {detection.layer2.detail}")
    return " | ".join(parts)[:1000]


def process_message(
    user,
    message: str,
    *,
    use_gemini: bool = True,
    allow_gemini_reply: bool = True,
) -> ChatbotResponse:
    """Classify, answer, screen, persist and route one message."""
    detection = detect(message, use_gemini=use_gemini)
    # The deterministic layer answers; the flag workflow escalates. The old
    # FR-031 notice is suppressed because it would be a second notification
    # for the same crisis.
    response = handle_message(user, message, use_llm=False, escalate=False)

    # Detection can raise urgency but never lower the deterministic answer.
    response.urgency = _max_urgency(
        response.urgency, SEVERITY_TO_URGENCY.get(detection.severity, UrgencyLevel.NORMAL)
    )

    if detection.sensitive:
        response.data["safety"] = {
            "severity": detection.severity,
            "categories": detection.categories,
            "manual_review": detection.manual_review,
        }
        if response.safe_fallback:
            # A disclosure the intent layer did not recognise must not be
            # answered with "I didn't understand". The student has just said
            # something that needs a counselor, and the reply has to say that
            # — the flag is on its way either way.
            response.reply = SAFETY_REPLY

    # A sensitive message is answered deterministically. Letting a model
    # rewrite a crisis reply is a safety regression, not a feature.
    attempted = False
    if use_gemini and allow_gemini_reply and not detection.sensitive:
        generated, attempted = _gemini_reply(user, message, response)
        if generated:
            response.reply = generated
        elif attempted:
            response.degraded = True

    chat_message = ChatMessage.objects.create(
        user=user,
        message=message,
        reply=response.reply,
        intent=response.intent.value,
        urgency=response.urgency.value,
        severity=detection.severity,
        sensitive=detection.sensitive,
        layer1_sensitive=detection.layer1.sensitive,
        layer2_sensitive=bool(detection.layer2 and detection.layer2.sensitive),
        manual_review=detection.manual_review,
        model_used=gemini_client.model_name() if (attempted or detection.layer2) else "",
        detection_detail=detection.to_dict(),
    )

    if detection.sensitive:
        flag = create_flag(
            chat_message=chat_message,
            user=user,
            severity=detection.severity,
            source=detection.source,
            categories=detection.categories,
            summary=_summary(detection),
            manual_review=detection.manual_review,
        )
        response.data["flag"] = {
            "id": str(flag.id),
            "severity": flag.severity,
            "status": flag.status,
            "manual_review": flag.manual_review,
        }
        if detection.severity in ("high", "critical"):
            response.escalated = True

    response.data["chat_message_id"] = str(chat_message.id)
    return response
