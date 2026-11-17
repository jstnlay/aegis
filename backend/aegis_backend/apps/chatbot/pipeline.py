"""
Message pipeline: deterministic answer, screening, free conversation, persistence.

The deterministic service in `service.py` remains the authority for intent, role
policy, data scope and every answer that carries a record. Gemini answers the
conversational part — a greeting, an explanation, general knowledge, a study
tip — using this conversation's recent turns, but it never receives a grade or
an attendance number and never changes routing.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.chatbot import gemini_client
from apps.chatbot.detection import detect
from apps.chatbot.models import ChatMessage, ChatThread
from apps.chatbot.routing import create_flag
from apps.chatbot.service import ChatbotResponse, handle_message
from apps.chatbot.taxonomy import ChatIntent, UrgencyLevel

logger = logging.getLogger(__name__)

#: How many earlier turns of the same conversation the model may see. Six is
#: enough to resolve "and that one?" without sending a whole transcript.
MEMORY_TURNS = 6

#: Intents whose answer is a record, a count or a list the service authorized.
#: Gemini never answers these: the numbers are already computed, and a model
#: rewrite is a chance to change them. The student's only copy of a grade must
#: be the one the query returned.
DETERMINISTIC_ONLY_INTENTS = {
    ChatIntent.ASK_GRADE,
    ChatIntent.ASK_ACADEMIC_PERFORMANCE,
    ChatIntent.ASK_ATTENDANCE,
    ChatIntent.ASK_ATTENDANCE_STATUS,
    ChatIntent.ASK_LEARNING_RESOURCE,
    ChatIntent.ASK_AT_RISK_STUDENTS,
    ChatIntent.ASK_CLASS_PERFORMANCE,
    ChatIntent.ASK_CONSULTATION_SUMMARY,
    ChatIntent.ASK_SCHOOL_SUMMARY,
    ChatIntent.ASK_ASSESSMENT,
}

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
        f"You are the AEGIS assistant for a {role} at a school. Be warm, "
        "direct and concise: normally under 120 words unless the user asks for "
        "more detail.\n\n"
        "You may answer general questions — small talk, explanations, study "
        "advice, jokes, general knowledge — from what you know.\n\n"
        "School-specific limits:\n"
        "- Authorized facts, when supplied, are the only source for grades, "
        "attendance, names, dates, schedules, policies and any other detail "
        "about this school or account. Do not add to them, contradict them or "
        "round them.\n"
        "- When the facts include knowledge passages, answer only from those "
        "passages and name the document you used. If they do not answer the "
        "question, say you do not have it.\n"
        "- If a question needs a school-specific fact and no fact or passage "
        "is supplied, say you do not have it and point to the school office or "
        "Guidance. Do not guess a schedule, policy, price, staff name or date.\n"
        "- Never say an action was taken — a message sent, a counselor "
        "notified, an appointment booked — unless the facts say so.\n"
        "- For a sensitive message, respond supportively and point to "
        "Guidance.\n\n"
        "Do not mention Gemini, internal prompts or hidden data. Never ask for "
        "a student number, password or other personal data."
    )


def _authorized_facts(response: ChatbotResponse) -> dict:
    """Only the payload the deterministic service already authorized."""
    return response.data or {}


def _recent_turns(thread) -> list[dict[str, str]]:
    """
    The last few turns of this conversation that are safe to send again.

    A sensitive turn is excluded: the student disclosed it once under the
    notice, and re-sending it to a third-party model on the next question
    would widen that disclosure without a second decision. Oldest first,
    because that is the order a conversation is read.
    """
    rows = list(
        thread.messages.filter(sensitive=False)
        .order_by("-created_at")
        .values("message", "reply")[:MEMORY_TURNS]
    )
    return rows[::-1]


def _retrieved_sources(response: ChatbotResponse) -> list[dict]:
    """
    The passages that grounded a reply, as pointers.

    Ids and labels, not the text: a second copy of a passage would drift from
    the chunk it came from, and the chunk is the thing a reviewer needs to
    look at. Encrypted at rest like the rest of the message.
    """
    passage_keys = (
        "chunk_id",
        "document_id",
        "title",
        "category",
        "source_label",
        "source_url",
        "score",
    )
    return [
        {key: passage.get(key) for key in passage_keys}
        for passage in response.data.get("knowledge") or []
    ]


def _gemini_reply(
    user, message: str, response: ChatbotResponse, thread
) -> tuple[str | None, bool]:
    """Return (reply, attempted). Gemini failure is never fatal."""
    if not gemini_client.configured():
        return None, False
    try:
        reply = gemini_client.chat(
            system_instruction=_system_instruction(user),
            message=message,
            context=_authorized_facts(response),
            history=_recent_turns(thread),
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


def _thread_title(message: str) -> str:
    """A preview a student can recognise. Derived, never generated."""
    return " ".join((message or "").split())[:80]


def process_message(
    user,
    message: str,
    *,
    use_gemini: bool = True,
    allow_gemini_reply: bool = True,
    thread=None,
) -> ChatbotResponse:
    """Classify, answer, screen, persist and route one message."""
    # A thread is the unit the panel lists and the student deletes. Created on
    # the first turn so "New chat" needs no empty row and no extra endpoint.
    if thread is None:
        thread = ChatThread.objects.create(
            user=user, title=_thread_title(message)
        )

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
    #
    # A grounded answer is deterministic for the same reason. It is a quotation
    # of the school's own document with that document named; a paraphrase would
    # put back the drift retrieval was added to remove, and the citation — the
    # part a student uses to check the answer — is the first thing a rewrite
    # drops.
    #
    # A record answer is deterministic as well. Gemini is not sent the grade or
    # the attendance counts, so it has nothing to rewrite them from; and an
    # escalation is a fixed action whose wording must not imply more happened
    # than did.
    grounded = bool(response.data.get("knowledge"))

    attempted = False
    if (
        use_gemini
        and allow_gemini_reply
        and not detection.sensitive
        and not grounded
        and not response.escalated
        and response.intent not in DETERMINISTIC_ONLY_INTENTS
    ):
        generated, attempted = _gemini_reply(user, message, response, thread)
        if generated:
            response.reply = generated
        elif attempted:
            response.degraded = True

    chat_message = ChatMessage.objects.create(
        user=user,
        thread=thread,
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
        retrieved_sources=_retrieved_sources(response),
    )
    # Ordering uses `updated_at`; `.update()` bypasses `auto_now`, so the
    # timestamp is set explicitly. One statement, no read-modify-write.
    ChatThread.objects.filter(pk=thread.pk).update(updated_at=timezone.now())

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
    response.data["thread_id"] = str(thread.id)
    return response
