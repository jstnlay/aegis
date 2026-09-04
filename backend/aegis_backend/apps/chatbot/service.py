"""
Phase 9 chatbot — service boundary + policy checks.

The chatbot service is the application-controlled boundary between the
user and data. It implements:

  User → Chat API → RBAC/policy layer → context builder →
  NLP/local LLM → structured intent/action → AEGIS authorization →
  approved tool/function → data retrieval → response

The LLM never has direct SQL/ORM/database access. The application
remains authoritative. The LLM never decides permissions.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.chatbot.policies import parse_message
from apps.chatbot.taxonomy import ChatIntent, UrgencyLevel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Policy: what the chatbot may / may not do
# ---------------------------------------------------------------------------

# Intents the chatbot supports for each role (least privilege)
ALLOWED_INTENTS_BY_ROLE = {
    "student": {
        ChatIntent.GREETING,
        ChatIntent.HELP,
        ChatIntent.SYSTEM_NAVIGATION,
        ChatIntent.UNKNOWN,
        ChatIntent.ASK_GRADE,
        ChatIntent.ASK_ACADEMIC_PERFORMANCE,
        ChatIntent.ASK_SUBJECT_HELP,
        ChatIntent.ASK_LEARNING_RESOURCE,
        ChatIntent.ASK_STUDY_STRATEGY,
        ChatIntent.ASK_RECOMMENDATION,
        ChatIntent.ASK_ATTENDANCE,
        ChatIntent.ASK_ATTENDANCE_STATUS,
        ChatIntent.ASK_ASSESSMENT,
        ChatIntent.ASSESSMENT_SCHEDULE,
        ChatIntent.ASSESSMENT_INSTRUCTIONS,
        ChatIntent.GUIDANCE_HELP,
        ChatIntent.EXPRESS_CONCERN,
        ChatIntent.REQUEST_COUNSELOR,
        ChatIntent.URGENT_CONCERN,
    },
    "parent": {
        ChatIntent.GREETING,
        ChatIntent.HELP,
        ChatIntent.SYSTEM_NAVIGATION,
        ChatIntent.UNKNOWN,
        ChatIntent.ASK_GRADE,
        ChatIntent.ASK_ACADEMIC_PERFORMANCE,
        ChatIntent.ASK_ATTENDANCE,
        ChatIntent.ASK_ATTENDANCE_STATUS,
        ChatIntent.ASK_ASSESSMENT,
        ChatIntent.ASSESSMENT_SCHEDULE,
        ChatIntent.ASSESSMENT_INSTRUCTIONS,
        ChatIntent.EXPRESS_CONCERN,
        ChatIntent.URGENT_CONCERN,
    },
    "faculty": {
        ChatIntent.GREETING,
        ChatIntent.HELP,
        ChatIntent.SYSTEM_NAVIGATION,
        ChatIntent.UNKNOWN,
    },
    "guidance": {
        ChatIntent.GREETING,
        ChatIntent.HELP,
        ChatIntent.SYSTEM_NAVIGATION,
        ChatIntent.UNKNOWN,
    },
    "admin": {
        ChatIntent.GREETING,
        ChatIntent.HELP,
        ChatIntent.SYSTEM_NAVIGATION,
        ChatIntent.UNKNOWN,
    },
}

# Intents that may trigger FR-031 escalation
ESCALATION_INTENTS = {
    ChatIntent.URGENT_CONCERN,
    ChatIntent.REQUEST_COUNSELOR,
}


class ChatbotPolicyError(Exception):
    """Raised when a chatbot action violates a policy boundary."""


def check_intent_allowed(user_role, intent: ChatIntent) -> bool:
    """Validate that a role is allowed to perform an intent."""
    allowed = ALLOWED_INTENTS_BY_ROLE.get(user_role, set())
    return intent in allowed


def check_can_read_student_data(user, target_user) -> bool:
    """
    Least-privilege data access check.

    A chatbot caller may only access data for students they are
    authorized to view.
    """
    role = user.role

    if role == "student":
        # Students only access their own data
        return hasattr(user, "student_profile") and (
            user.student_profile.id == target_user.student_profile.id
        )
    if role == "parent":
        from apps.accounts.models import ParentStudentLink
        return ParentStudentLink.objects.filter(
            parent=user.parent_profile,
            student__user=target_user,
        ).exists()
    if role in ("guidance", "admin"):
        return True
    return False


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_context(user, intent: ChatIntent, entities: list) -> dict[str, Any]:
    """
    Build the authorized context for the chatbot response.

    Only authorized data is included. Context is minimized — no raw
    Guidance notes, no other students' data.
    """
    from apps.chatbot.taxonomy import ChatEntity

    context: dict[str, Any] = {
        "user_role": user.role,
        "intent": intent.value,
        "entities": [e.to_dict() for e in entities],
    }

    # Include only least-privilege context based on role + intent
    if intent in (
        ChatIntent.ASK_GRADE,
        ChatIntent.ASK_ACADEMIC_PERFORMANCE,
    ):
        if user.role == "student":
            context["student_id"] = str(user.student_profile.id)
            context["scope"] = "own"
        elif user.role == "parent":
            context["scope"] = "linked_student"
        elif user.role in ("guidance", "admin"):
            context["scope"] = "authorized_students"

    elif intent in (ChatIntent.ASK_ATTENDANCE, ChatIntent.ASK_ATTENDANCE_STATUS):
        if user.role == "student":
            context["student_id"] = str(user.student_profile.id)
            context["scope"] = "own"

    return context


# ---------------------------------------------------------------------------
# Escalation (FR-031)
# ---------------------------------------------------------------------------

def create_escalation(
    user,
    *,
    intent: ChatIntent,
    message: str,
    entities: list,
    dispatch: bool = True,
) -> dict[str, Any]:
    """
    Create an application-controlled escalation event (FR-031).

    The LLM does NOT independently create irreversible actions. This is
    application-controlled and dispatches through the existing
    notification infrastructure.
    """
    from apps.notifications.events import dispatch_event
    from apps.notifications.models import NotificationType

    recipient = None
    from apps.accounts.models import User
    # Route to Guidance
    recipient = (
        User.objects.filter(role="guidance")
        .order_by("email")
        .first()
    )

    escalation_key = (
        f"chat_escalation:{user.id}:{intent.value}:"
        f"{_message_fingerprint(message)}"
    )

    if recipient is not None and dispatch:
        dispatch_event(
            NotificationType.BEHAVIORAL_WARNING,
            recipients=[recipient],
            sender=user,
            title=f"Chatbot concern escalation: {user.get_full_name()}",
            message=(
                f"Student {user.get_full_name()} expressed an urgent/concern "
                f"signal via the chatbot. Intent: {intent.value}."
            ),
            link="/guidance/risk-alerts",
            deduplication_key=escalation_key,
        )

    return {
        "status": "escalated" if recipient is not None else "no_recipient",
        "escalation_key": escalation_key,
        "intent": intent.value,
    }


def _message_fingerprint(text: str) -> str:
    """Stable fingerprint for deduplication (avoid duplicate escalation)."""
    import hashlib
    digest = hashlib.sha256(text.lower().encode("utf-8")).hexdigest()[:16]
    return digest


# ---------------------------------------------------------------------------
# Controlled data access functions (approved tools)
# ---------------------------------------------------------------------------

def get_student_grade_summary(user, student_profile) -> dict[str, Any] | None:
    """
    Authorized grade summary for the student.

    Only accessible if the caller is authorized. Returns minimal,
    role-safe data.
    """
    from apps.academics.models import Grade
    from django.db.models import Avg

    if not check_can_read_student_data(user, student_profile.user):
        return None

    grades = Grade.objects.filter(
        student=student_profile,
        score__isnull=False,
        status="finalized",
    )
    avg = grades.aggregate(avg=Avg("score"))["avg"]

    return {
        "student_name": student_profile.user.get_full_name(),
        "average": round(float(avg), 2) if avg else None,
        "grade_count": grades.count(),
    }


def get_student_attendance_summary(user, student_profile) -> dict[str, Any] | None:
    """Authorized attendance summary."""
    from apps.attendance.models import AttendanceRecord

    if not check_can_read_student_data(user, student_profile.user):
        return None

    records = AttendanceRecord.objects.filter(student=student_profile)
    total = records.count()
    present = records.filter(status="present").count()
    late = records.filter(status="late").count()

    return {
        "student_name": student_profile.user.get_full_name(),
        "total_days": total,
        "present_days": present,
        "late_days": late,
        "absent_days": total - present - late,
        "attendance_rate": round((present + late) / total, 4) if total else None,
    }


def get_learning_resources(user, subject=None, limit=5) -> list[dict[str, Any]]:
    """
    Authorized learning resource lookup.

    Only APPROVED + ACTIVE items. Content is never invented.
    """
    from apps.cms.models import LearningItem

    queryset = LearningItem.objects.filter(
        lifecycle_status="approved",
        is_active=True,
    )
    if subject:
        queryset = queryset.filter(subject__name__icontains=subject)

    items = queryset[:limit]
    return [
        {
            "title": item.title,
            "item_type": item.item_type,
            "subject": item.subject.name if item.subject else None,
            "topic": item.topic,
            "source_type": item.source_type,
            "source_id": item.source_id,
        }
        for item in items
    ]


# ---------------------------------------------------------------------------
# Chatbot service entry point
# ---------------------------------------------------------------------------

class ChatbotResponse:
    """Structured chatbot response (safe fallback guaranteed)."""

    def __init__(
        self,
        reply: str,
        intent: ChatIntent,
        urgency: UrgencyLevel,
        *,
        degraded: bool = False,
        escalated: bool = False,
        safe_fallback: bool = False,
        data: dict[str, Any] | None = None,
    ):
        self.reply = reply
        self.intent = intent
        self.urgency = urgency
        self.degraded = degraded
        self.escalated = escalated
        self.safe_fallback = safe_fallback
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "intent": self.intent.value,
            "urgency": self.urgency.value,
            "degraded": self.degraded,
            "escalated": self.escalated,
            "safe_fallback": self.safe_fallback,
            "data": self.data,
        }


def _deterministic_reply(user, intent: ChatIntent, entities, context) -> str:
    """Generate a deterministic reply for supported intents."""
    from apps.chatbot.taxonomy import ChatEntity

    if intent == ChatIntent.GREETING:
        return f"Hello, {user.first_name}! I can help with AEGIS. What do you need?"
    if intent == ChatIntent.HELP:
        return (
            "I can help you with grades, academic performance, attendance, "
            "assessments, and learning resources. What would you like to know?"
        )
    if intent == ChatIntent.UNKNOWN:
        return (
            "I'm sorry, I didn't fully understand. Could you rephrase? "
            "I can help with grades, attendance, assessments, or learning resources."
        )
    if intent == ChatIntent.SYSTEM_NAVIGATION:
        return (
            "In AEGIS, you can use the dashboard to view your information. "
            "For specific features, use the navigation menu."
        )
    if intent == ChatIntent.URGENT_CONCERN:
        return (
            "I'm here to support you. Please consider speaking with a "
            "counselor or trusted adult right away. I'll connect you with "
            "Guidance."
        )
    if intent == ChatIntent.REQUEST_COUNSELOR:
        return (
            "I can help schedule an appointment with Guidance. "
            "Would you like me to do that?"
        )
    if intent == ChatIntent.EXPRESS_CONCERN:
        return (
            "Thank you for sharing. I'm here to listen and help. "
            "You may also reach out to Guidance for additional support."
        )
    if intent == ChatIntent.GUIDANCE_HELP:
        return "Guidance is available to support you. I can help you connect."
    return "I can help you with that. What would you like to know?"


def handle_message(
    user,
    message: str,
    *,
    use_llm: bool = False,
    llm_result: dict[str, Any] | None = None,
) -> ChatbotResponse:
    """
    Main chatbot service entry point.

    Architecture:
      1. Parse message deterministically (intent + urgency + entities).
      2. Check policy (role allowed for intent).
      3. Build authorized context.
      4. Handle escalation if needed.
      5. If LLM available and confident, use it; else deterministic fallback.

    The application remains authoritative. No direct DB access by LLM.
    """
    parse_result = parse_message(message)
    intent = parse_result.intent
    urgency = parse_result.urgency
    entities = parse_result.entities

    # Policy check: allowed intent for role
    if not check_intent_allowed(user.role, intent):
        return ChatbotResponse(
            reply="I'm not able to help with that specific request for your account.",
            intent=ChatIntent.UNKNOWN,
            urgency=urgency,
            safe_fallback=True,
        )

    # Escalation path (FR-031 / request_counselor)
    if urgency == UrgencyLevel.URGENT or intent in ESCALATION_INTENTS:
        escalation = create_escalation(
            user,
            intent=intent,
            message=message,
            entities=entities,
        )
        reply = _deterministic_reply(user, intent, entities, {})
        return ChatbotResponse(
            reply=reply,
            intent=intent,
            urgency=UrgencyLevel.URGENT,
            escalated=True,
            data={"escalation": escalation},
        )

    # Build authorized context (least privilege)
    context = build_context(user, intent, entities)

    # Determine data to provide
    data = {}
    if intent in (
        ChatIntent.ASK_GRADE,
        ChatIntent.ASK_ACADEMIC_PERFORMANCE,
    ):
        if hasattr(user, "student_profile"):
            summary = get_student_grade_summary(user, user.student_profile)
            if summary:
                data["grade_summary"] = summary
    elif intent in (ChatIntent.ASK_ATTENDANCE, ChatIntent.ASK_ATTENDANCE_STATUS):
        if hasattr(user, "student_profile"):
            summary = get_student_attendance_summary(user, user.student_profile)
            if summary:
                data["attendance_summary"] = summary
    elif intent == ChatIntent.ASK_LEARNING_RESOURCE:
        subject = None
        for e in entities:
            if e.entity_type == "subject":
                subject = e.value
        resources = get_learning_resources(user, subject=subject)
        data["resources"] = resources

    # LLM path (optional, structured, validated) — deterministic fallback otherwise
    if use_llm and llm_result and llm_result.get("valid"):
        reply = llm_result.get("reply", "")
        return ChatbotResponse(
            reply=reply,
            intent=intent,
            urgency=urgency,
            data=data,
        )

    # Deterministic fallback / low-confidence
    reply = _deterministic_reply(user, intent, entities, context)
    degraded = use_llm and not (llm_result and llm_result.get("valid"))
    return ChatbotResponse(
        reply=reply,
        intent=intent,
        urgency=urgency,
        degraded=degraded,
        safe_fallback=True,
        data=data,
    )
