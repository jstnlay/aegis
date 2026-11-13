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
import re
from typing import Any

from apps.chatbot.policies import parse_message
from apps.chatbot.retrieval import retrieve
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
        ChatIntent.ASK_AT_RISK_STUDENTS,
        ChatIntent.ASK_CLASS_PERFORMANCE,
        # A teacher authors academic assessments; the chatbot drafts the
        # items for them (FR-027).
        ChatIntent.ASK_ASSESSMENT,
    },
    "guidance": {
        ChatIntent.GREETING,
        ChatIntent.HELP,
        ChatIntent.SYSTEM_NAVIGATION,
        ChatIntent.UNKNOWN,
        ChatIntent.ASK_AT_RISK_STUDENTS,
        ChatIntent.ASK_CLASS_PERFORMANCE,
        ChatIntent.ASK_CONSULTATION_SUMMARY,
        # A counselor authors wellness/behavioral assessments; the chatbot
        # drafts the items for them (FR-027).
        ChatIntent.ASK_ASSESSMENT,
    },
    "admin": {
        ChatIntent.GREETING,
        ChatIntent.HELP,
        ChatIntent.SYSTEM_NAVIGATION,
        ChatIntent.UNKNOWN,
        ChatIntent.ASK_AT_RISK_STUDENTS,
        ChatIntent.ASK_CLASS_PERFORMANCE,
        ChatIntent.ASK_CONSULTATION_SUMMARY,
        ChatIntent.ASK_SCHOOL_SUMMARY,
    },
}

# Intents that may trigger FR-031 escalation
ESCALATION_INTENTS = {
    ChatIntent.URGENT_CONCERN,
    ChatIntent.REQUEST_COUNSELOR,
}

# Intents a passage from a school document may answer: the questions about the
# school itself — its rules, its schedule, its procedures — that no table in
# this database holds. A grade or an attendance question is deliberately NOT
# here. Those are answered from a scoped query, and a document someone typed
# must never be able to stand in for a child's record.
KNOWLEDGE_INTENTS = {
    ChatIntent.UNKNOWN,
    ChatIntent.SYSTEM_NAVIGATION,
    ChatIntent.ASK_SUBJECT_HELP,
    ChatIntent.ASK_STUDY_STRATEGY,
    ChatIntent.ASK_RECOMMENDATION,
    ChatIntent.ASSESSMENT_SCHEDULE,
    ChatIntent.ASSESSMENT_INSTRUCTIONS,
    ChatIntent.GUIDANCE_HELP,
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
        elif user.role == "parent":
            # A parent has no student_profile of their own; the data functions
            # resolve which linked child from the ParentStudentLink rows. With
            # more than one child the caller must disambiguate, so the count is
            # recorded here for the reply to use.
            context["scope"] = "linked_student"
            context["linked_student_count"] = _linked_student_count(user)

    return context


def _linked_student_count(user) -> int:
    """How many students this parent is linked to."""
    if user.role != "parent":
        return 0
    from apps.accounts.models import ParentStudentLink

    return ParentStudentLink.objects.filter(
        parent=user.parent_profile
    ).count()


def resolve_target_student(user):
    """
    Resolve which student a data question is about.

    Returns a `StudentProfile`, or `None` when it cannot be determined.

    Never guesses. A parent with more than one linked child returns `None` here,
    so the reply asks which child rather than answering about whichever one
    sorted first — reporting a real child's grades against a question about a
    sibling is worse than asking a follow-up.

    Name-based disambiguation is deliberately absent. `parse_message` extracts
    only `subject` and `topic` entities (`policies._extract_entities`); there is
    no `person` entity type in `ChatEntity`, so there is nothing to match a
    child's name against. Adding one is an NLP change to the parser, not a
    lookup change, and would arrive with the classifier work rather than be
    assumed here.
    """
    if user.role == "student":
        return getattr(user, "student_profile", None)

    if user.role != "parent":
        return None

    from apps.accounts.models import ParentStudentLink

    linked = ParentStudentLink.objects.filter(parent=user.parent_profile).select_related(
        "student__user"
    )

    if linked.count() != 1:
        return None

    return linked.first().student


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
        # `is not None`: a student whose finalized grades average 0 has an
        # average. Truthiness reported it as "no grades to average".
        "average": round(float(avg), 2) if avg is not None else None,
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


def get_learning_resources(user, subject=None, limit=5, query=None) -> list[dict[str, Any]]:
    """
    Authorized learning resource lookup.

    Only APPROVED + ACTIVE items. Content is never invented.

    `query` is the student's own question. When the question names no subject
    the caller recognised, the item is kept only if one of its own words
    appears in the question. Without that filter the lookup was "every
    approved item", so asking for underwater basket weaving returned the
    algebra module — a real answer to a question nobody asked, which is what
    "not accurate" meant in practice. A question that matches nothing now
    returns nothing, and the reply says so.
    """
    from apps.cms.models import LearningItem

    queryset = LearningItem.objects.filter(
        lifecycle_status="approved",
        is_active=True,
    )
    if subject:
        queryset = queryset.filter(subject__name__icontains=subject)
    elif query:
        queryset = _filter_items_by_query(queryset, query)

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


def _filter_items_by_query(queryset, query: str):
    """Keep only items whose own words appear in the question."""
    from django.db.models import Q

    terms = {
        word
        for word in re.findall(r"[a-z0-9]+", (query or "").lower())
        if len(word) >= 4
    }
    if not terms:
        return queryset.none()
    condition = Q()
    for term in terms:
        condition |= (
            Q(title__icontains=term)
            | Q(topic__icontains=term)
            | Q(subject__name__icontains=term)
        )
    return queryset.filter(condition)


def _faculty_sections(user):
    """Sections this faculty member advises or teaches, as a queryset."""
    from django.db.models import Q

    from apps.academics.models import Section

    profile = getattr(user, "faculty_profile", None)
    if profile is None:
        return Section.objects.none()
    return Section.objects.filter(
        Q(adviser=profile) | Q(subject_assignments__faculty=profile)
    ).distinct()


def get_at_risk_students(user, limit=5) -> dict[str, Any] | None:
    """
    Open moderate/high risk alerts the caller may see.

    Guidance and admin see the school; faculty see only students enrolled in
    the sections they advise or teach. A student or parent gets ``None`` — this
    is a staff summary, not another student's record.
    """
    from apps.guidance.models import RiskAlert

    if user.role not in ("faculty", "guidance", "admin"):
        return None

    open_statuses = (
        RiskAlert.Status.ACTIVE,
        RiskAlert.Status.UNDER_MONITORING,
        RiskAlert.Status.ESCALATED,
    )
    alerts = RiskAlert.objects.filter(
        status__in=open_statuses,
        risk_level__in=(RiskAlert.RiskLevel.MODERATE, RiskAlert.RiskLevel.HIGH),
    ).select_related("student__user")

    if user.role == "faculty":
        alerts = alerts.filter(
            student__enrollments__section__in=_faculty_sections(user)
        )

    total = alerts.values("student_id").distinct().count()

    # One row per student, highest severity first. A student can have more than
    # one open alert; listing them repeatedly would overstate the caseload.
    students = []
    seen = set()
    for level in (RiskAlert.RiskLevel.HIGH, RiskAlert.RiskLevel.MODERATE):
        for alert in alerts.filter(risk_level=level).order_by("-generated_at"):
            if alert.student_id in seen:
                continue
            seen.add(alert.student_id)
            students.append(
                {
                    "name": alert.student.user.get_full_name(),
                    "risk_level": level,
                }
            )
            if len(students) >= limit:
                return {"total": total, "students": students}

    return {"total": total, "students": students}


def get_class_performance(user) -> dict[str, Any] | None:
    """
    Finalized grade average for the caller's class or for all sections.

    Faculty are scoped to their own sections. Guidance and admin read the
    school aggregate. Students and parents get ``None``.
    """
    from django.db.models import Avg

    from apps.academics.models import Grade

    if user.role not in ("faculty", "guidance", "admin"):
        return None

    grades = Grade.objects.filter(score__isnull=False, status="finalized")
    if user.role == "faculty":
        grades = grades.filter(
            student__enrollments__section__in=_faculty_sections(user)
        )

    average = grades.aggregate(avg=Avg("score"))["avg"]
    return {
        "average": round(float(average), 2) if average is not None else None,
        "grade_count": grades.count(),
        "student_count": grades.values("student_id").distinct().count(),
    }


def get_consultation_summary(user) -> dict[str, Any] | None:
    """
    Consultation counts the caller may see.

    Guidance counts their own sessions; admin counts the school. Other roles
    get ``None``.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.guidance.models import ConsultationRecord

    if user.role == "admin":
        records = ConsultationRecord.objects.all()
    elif user.role == "guidance":
        profile = getattr(user, "guidance_profile", None)
        if profile is None:
            return None
        records = ConsultationRecord.objects.filter(counselor=profile)
    else:
        return None

    since = timezone.localdate() - timedelta(days=30)
    return {
        "total": records.count(),
        "last_30_days": records.filter(session_date__gte=since).count(),
        "ongoing": records.filter(
            status=ConsultationRecord.Status.ONGOING
        ).count(),
        "follow_up": records.filter(
            status=ConsultationRecord.Status.FOLLOW_UP
        ).count(),
    }


def get_school_summary(user) -> dict[str, Any] | None:
    """Active account and section counts. Admin only."""
    from apps.accounts.models import User
    from apps.academics.models import Section

    if user.role != "admin":
        return None

    active = User.objects.filter(is_active=True)
    return {
        "students": active.filter(role=User.Role.STUDENT).count(),
        "faculty": active.filter(role=User.Role.FACULTY).count(),
        "guidance": active.filter(role=User.Role.GUIDANCE).count(),
        "sections": Section.objects.count(),
    }


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


def _assessment_topic(message: str, entities) -> str | None:
    """
    The topic an assessment request is about.

    A keyword topic entity wins when the message names one of the known
    topics; otherwise the phrase after "about/on/for" is used, trimmed of the
    words that name the artifact ("quiz", "test", "assessment").
    """
    for entity in entities:
        if entity.entity_type == "topic":
            return entity.value

    match = re.search(
        r"\b(?:about|on|regarding|for)\s+(?:a|an|the)?\s*([a-z][a-z\s\-]{2,40})",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    topic = re.split(
        r"\b(?:quiz|test|assessment|question|questions|item|items)\b",
        match.group(1),
        flags=re.IGNORECASE,
    )[0].strip()
    return topic if len(topic) >= 3 else None


def _draft_assessment_items(user, topic: str) -> list[dict]:
    """Draft assessment items for `topic` in the caller's item bank."""
    from apps.chatbot.question_generator import (
        QuestionGenerationError,
        generate_question_drafts,
    )

    family = "academic" if user.role == "faculty" else "concern"
    try:
        result = generate_question_drafts(
            topic=topic,
            question_type="essay",
            count=3,
            family=family,
        )
    except QuestionGenerationError:
        return []
    return result["drafts"]


def _record_subject(user, summary: dict) -> str:
    """
    "You have" for the student, the student's name for everyone else.

    A parent reads their child's record, so "You have" would be wrong; a
    student reading their own name back is accurate but unfriendly.
    """
    if user.role == "student":
        return "You have"
    return f"{summary.get('student_name') or 'That student'} has"


def _deterministic_reply(user, intent: ChatIntent, entities, context, data=None) -> str:
    """Generate a deterministic reply for supported intents."""
    from apps.chatbot.taxonomy import ChatEntity

    data = data or {}

    # A parent's data question with several linked children and no child named
    # is ambiguous. Saying so is the honest answer; picking one would report a
    # real child's grades against a question about another.
    if user.role == "parent" and intent in (
        ChatIntent.ASK_GRADE,
        ChatIntent.ASK_ACADEMIC_PERFORMANCE,
        ChatIntent.ASK_ATTENDANCE,
        ChatIntent.ASK_ATTENDANCE_STATUS,
    ):
        if not any(k in data for k in ("grade_summary", "attendance_summary")):
            return (
                "I can answer that, but you have more than one linked student. "
                "Which student do you mean? Tell me their name or student number."
            )

    # -- Grounded answer from a school document ------------------------------
    #
    # Checked before the canned branches, because a real passage about the
    # school beats a stock sentence about the assistant. It is only reached
    # when `handle_message` retrieved something, and retrieval is not run for
    # a record question, so this can never answer "what is my grade".
    #
    # The source is named in full. That is what makes the answer checkable by
    # the student reading it, and it is what separates an answer grounded in
    # this school from a sentence that merely sounds like one.
    passages = data.get("knowledge") or []
    if passages:
        answer = " ".join(passages[0]["excerpt"].split())
        label = passages[0]["source_label"] or passages[0]["title"]
        reply = f"From “{label}”: {answer}"
        if len(passages) > 1:
            second = passages[1]
            second_label = second["source_label"] or second["title"]
            reply += (
                f"\n\nAlso from “{second_label}”: "
                f"{' '.join(second['excerpt'].split())}"
            )
        return f"{reply}\n\nIf that does not cover it, ask the school office."

    if intent == ChatIntent.GREETING:
        return f"Hello, {user.first_name}! I can help with AEGIS. What do you need?"
    if intent == ChatIntent.HELP:
        if user.role == "faculty":
            return (
                "I can help with your class roster, class performance, and the "
                "at-risk students in your sections. What would you like to know?"
            )
        if user.role == "guidance":
            return (
                "I can help with at-risk students, class performance, and your "
                "consultation summary. What would you like to know?"
            )
        if user.role == "admin":
            return (
                "I can help with the school summary, at-risk students, class "
                "performance, and consultation totals. What would you like to know?"
            )
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
    if intent == ChatIntent.ASK_AT_RISK_STUDENTS:
        summary = data.get("at_risk_students")
        if not summary or summary["total"] == 0:
            return (
                "There are no open moderate or high risk alerts in the students "
                "you can see."
            )
        listed = ", ".join(
            f"{row['name']} ({row['risk_level']})"
            for row in summary["students"]
        )
        remainder = summary["total"] - len(summary["students"])
        tail = (
            f" {remainder} more not listed." if remainder > 0 else ""
        )
        return (
            f"{summary['total']} student(s) have an open moderate or high risk "
            f"alert: {listed}.{tail} Open Guidance > Risk alerts to review them."
        )
    if intent == ChatIntent.ASK_CLASS_PERFORMANCE:
        performance = data.get("class_performance")
        if not performance or performance["grade_count"] == 0:
            return (
                "No finalized grades are recorded yet, so there is no average "
                "to report."
            )
        scope = "your class" if user.role == "faculty" else "all sections"
        return (
            f"Across {scope}, {performance['student_count']} student(s) have "
            f"{performance['grade_count']} finalized grade(s) averaging "
            f"{performance['average']}."
        )
    if intent == ChatIntent.ASK_CONSULTATION_SUMMARY:
        summary = data.get("consultation_summary")
        if not summary:
            return "I cannot read consultation records for this account."
        scope = "The school has" if user.role == "admin" else "You have"
        return (
            f"{scope} {summary['total']} consultation record(s): "
            f"{summary['last_30_days']} in the last 30 days, "
            f"{summary['ongoing']} ongoing, and {summary['follow_up']} "
            "marked follow-up."
        )
    if intent == ChatIntent.ASK_SCHOOL_SUMMARY:
        summary = data.get("school_summary")
        if not summary:
            return "I cannot read the school summary for this account."
        return (
            f"The school has {summary['students']} active student(s), "
            f"{summary['faculty']} faculty, {summary['guidance']} guidance "
            f"counselor(s), and {summary['sections']} section(s)."
        )
    if intent == ChatIntent.ASK_ASSESSMENT and user.role in ("faculty", "guidance"):
        drafts = data.get("assessment_drafts") or []
        if not drafts:
            return (
                "I can draft assessment items for you. Tell me the topic, for "
                "example “draft a quiz about study habits”."
            )
        topic = data.get("assessment_topic", "")
        listed = "\n".join(
            f"{index}. {draft['question_text']}"
            for index, draft in enumerate(drafts, start=1)
        )
        where = (
            "Faculty > Assessments"
            if user.role == "faculty"
            else "Guidance > Assessments"
        )
        return (
            f"Here are {len(drafts)} draft item(s) for “{topic}”:\n{listed}\n"
            f"Open {where} and use “Generate draft” to fill them in — nothing "
            "is saved until you add the question."
        )
    # -- Authorized record answers ------------------------------------------
    #
    # These read the facts `handle_message` had already fetched. Until this
    # block existed, none of these intents had a branch, so a student asking
    # about their own grade fell through to the generic tail and was told
    # nothing — even though the number was in `data` the whole time. The data
    # was never the missing part; the sentence was.
    if intent in (ChatIntent.ASK_GRADE, ChatIntent.ASK_ACADEMIC_PERFORMANCE):
        summary = data.get("grade_summary")
        if not summary:
            return (
                "I don't have finalized grades for that student, so there is no "
                "average I can report. I only read grades a teacher has finalized; "
                "ask your teacher if a grade is missing."
            )
        if not summary["grade_count"] or summary["average"] is None:
            return (
                f"{_record_subject(user, summary)} no finalized grades yet, so "
                "there is no average to report. One appears here once a teacher "
                "finalizes the first grade."
            )
        return (
            f"{_record_subject(user, summary)} {summary['grade_count']} finalized "
            f"grade(s), averaging {summary['average']:.2f}. Open Grades to see each "
            "subject."
        )
    if intent in (ChatIntent.ASK_ATTENDANCE, ChatIntent.ASK_ATTENDANCE_STATUS):
        summary = data.get("attendance_summary")
        if not summary:
            return (
                "I don't have attendance records for that student. If you expected "
                "some, ask the school office whether attendance has been encoded."
            )
        if not summary["total_days"]:
            return (
                f"{_record_subject(user, summary)} no recorded attendance days yet."
            )
        # A late arrival is a day the student was in school; counting it as an
        # absence would report a child who attended as a child who did not.
        attended = summary["present_days"] + summary["late_days"]
        rate = (
            f" ({summary['attendance_rate'] * 100:.1f}%)"
            if summary["attendance_rate"] is not None
            else ""
        )
        return (
            f"{_record_subject(user, summary)} attended {attended} of "
            f"{summary['total_days']} recorded days{rate}: "
            f"{summary['present_days']} present, {summary['late_days']} late, "
            f"{summary['absent_days']} absent."
        )
    if intent == ChatIntent.ASK_LEARNING_RESOURCE:
        resources = data.get("resources") or []
        if not resources:
            return (
                "I don't have an approved learning resource for that yet. Try "
                "naming a subject, or ask your teacher what to use."
            )
        listed = "; ".join(
            row["title"] + (f" ({row['subject']})" if row.get("subject") else "")
            for row in resources
        )
        return (
            f"These are the approved learning resources I can see: {listed}. "
            "Your teacher may have more in class."
        )
    # The honest tail. Naming what this assistant cannot answer is the whole
    # point: a confident non-answer is what made the old tail read as wrong.
    return (
        "I can look up your grades, attendance and approved learning resources. "
        "I don't have an answer for this one — for school rules, schedules or "
        "anything else, ask the school office or Guidance."
    )


def handle_message(
    user,
    message: str,
    *,
    use_llm: bool = False,
    llm_result: dict[str, Any] | None = None,
    escalate: bool = True,
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

    `escalate` controls whether the FR-031 escalation *notification* is
    dispatched. The pipeline passes False because the flag workflow is now the
    escalation path: it reaches every Guidance counselor, the administrators
    and the student's faculty, with the severity and a timer attached. Leaving
    the old notice on as well meant one crisis produced two notifications for
    the same counselor, which is how a channel gets ignored. The intent, the
    urgency and the reply are unchanged either way.
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
            dispatch=escalate,
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
        # Resolves to the caller's own profile for a student, or to a linked
        # child for a parent. It returns None rather than guessing when a
        # parent has several children and named none, so the reply can ask
        # which child rather than answer about the wrong one.
        target = resolve_target_student(user)
        if target is not None:
            summary = get_student_grade_summary(user, target)
            if summary:
                data["grade_summary"] = summary
    elif intent in (ChatIntent.ASK_ATTENDANCE, ChatIntent.ASK_ATTENDANCE_STATUS):
        target = resolve_target_student(user)
        if target is not None:
            summary = get_student_attendance_summary(user, target)
            if summary:
                data["attendance_summary"] = summary
    elif intent == ChatIntent.ASK_LEARNING_RESOURCE:
        subject = None
        for e in entities:
            if e.entity_type == "subject":
                subject = e.value
        resources = get_learning_resources(user, subject=subject, query=message)
        data["resources"] = resources
    elif intent == ChatIntent.ASK_AT_RISK_STUDENTS:
        summary = get_at_risk_students(user)
        if summary is not None:
            data["at_risk_students"] = summary
    elif intent == ChatIntent.ASK_CLASS_PERFORMANCE:
        performance = get_class_performance(user)
        if performance is not None:
            data["class_performance"] = performance
    elif intent == ChatIntent.ASK_CONSULTATION_SUMMARY:
        summary = get_consultation_summary(user)
        if summary is not None:
            data["consultation_summary"] = summary
    elif intent == ChatIntent.ASK_SCHOOL_SUMMARY:
        summary = get_school_summary(user)
        if summary is not None:
            data["school_summary"] = summary
    elif intent == ChatIntent.ASK_ASSESSMENT and user.role in (
        "faculty",
        "guidance",
    ):
        # A teacher or counselor asking for an assessment gets drafted items
        # for the topic they named. Nothing is written: the drafts are
        # proposals, and only the assessments module saves a question.
        topic = _assessment_topic(message, entities)
        drafts = _draft_assessment_items(user, topic) if topic else []
        if drafts:
            data["assessment_drafts"] = drafts
            data["assessment_topic"] = topic

    # Knowledge retrieval (RAG).
    #
    # This is where the assistant stops guessing about the school and starts
    # quoting it. The passages come back with their document attached, so the
    # reply can name where the answer came from and the student can go read it.
    #
    # Retrieval is not run for a record question. A passage is school prose
    # that anyone with database access could have written; a grade is the
    # student's own record behind an authorization check. Letting the first
    # stand in for the second would trade a permission boundary for a search
    # hit, which is exactly the kind of accuracy the client complained about.
    if intent in KNOWLEDGE_INTENTS:
        passages = retrieve(message, limit=3)
        if passages:
            data["knowledge"] = passages

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
    reply = _deterministic_reply(user, intent, entities, context, data)
    degraded = use_llm and not (llm_result and llm_result.get("valid"))
    return ChatbotResponse(
        reply=reply,
        intent=intent,
        urgency=urgency,
        degraded=degraded,
        safe_fallback=True,
        data=data,
    )
