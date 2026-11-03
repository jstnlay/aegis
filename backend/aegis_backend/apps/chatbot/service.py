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
        ChatIntent.ASK_RISK_STATUS,
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

# Intents a response provider may phrase.
#
# `ASK_STUDY_STRATEGY` is the only one, and the reason is evidence rather than
# taste. Asked "Am I at risk?" the local model answered "your academic status is
# not at risk"; asked for a recommendation it wrote "your average grade is 68.6,
# which is above the required 75 to pass"; asked about a resource it invented a
# `C+` in Science that no grade book held. A prompt instruction did not stop any
# of it, and `reply_is_grounded` cannot see a reversed comparison — every number
# in that sentence was real.
#
# So the application owns every sentence that states a fact about the student's
# record: grades, status, risk, attendance, recommendations and resources are
# all answered deterministically. A provider is kept for the one question whose
# answer is open-ended advice, where a differently worded answer is a feature
# and a wrong number is still caught by `reply_is_grounded`.
#
# Greetings, help and navigation need no model; a message the classifier could
# not understand ("unknown") must return the honest rephrase prompt rather than
# a model's guess; and distress never reaches a provider because that path
# returns above this gate.
LLM_ELIGIBLE_INTENTS = {
    ChatIntent.ASK_STUDY_STRATEGY,
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
        ChatIntent.ASK_RECOMMENDATION,
        ChatIntent.ASK_RISK_STATUS,
    ):
        if user.role == "student":
            context["student_id"] = str(user.student_profile.id)
            context["scope"] = "own"
        elif user.role == "parent":
            context["scope"] = "linked_student"
            context["linked_student_count"] = _linked_student_count(user)
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
    urgent: bool = True,
) -> dict[str, Any]:
    """
    Create an application-controlled escalation event (FR-031).

    The LLM does NOT independently create irreversible actions. This is
    application-controlled and writes to the same Guidance surfaces a
    counselor already monitors:

      - one open ``RiskAlert`` per student, rather than one per message, so a
        repeated crisis message does not bury the dashboard;
      - one notification per guidance user, deduplicated by student/message.

    The message text is never copied into either record. A student's crisis
    wording is not evidence a counselor needs quoted back at them, and keeping
    it out means the alert itself cannot leak it.
    """
    from django.utils import timezone

    from apps.accounts.models import User
    from apps.guidance.models import RiskAlert
    from apps.notifications.events import dispatch_event
    from apps.notifications.models import NotificationType

    target = resolve_target_student(user)
    risk_alert = None
    # Only a genuine distress signal becomes a high-risk alert. A request for
    # a counselor appointment is routed to Guidance but is not a risk finding.
    if urgent and target is not None:
        open_statuses = (
            RiskAlert.Status.ACTIVE,
            RiskAlert.Status.UNDER_MONITORING,
            RiskAlert.Status.ESCALATED,
        )
        risk_alert = (
            RiskAlert.objects.filter(
                student=target,
                source=RiskAlert.Source.CHATBOT,
                status__in=open_statuses,
            )
            .order_by("-generated_at")
            .first()
        )
        if risk_alert is None:
            risk_alert = RiskAlert.objects.create(
                student=target,
                risk_level=RiskAlert.RiskLevel.HIGH,
                risk_factors=["chatbot_distress_signal"],
                source=RiskAlert.Source.CHATBOT,
                status=RiskAlert.Status.ACTIVE,
                generated_at=timezone.now(),
            )
        else:
            changed = False
            if risk_alert.risk_level != RiskAlert.RiskLevel.HIGH:
                risk_alert.risk_level = RiskAlert.RiskLevel.HIGH
                changed = True
            if "chatbot_distress_signal" not in (risk_alert.risk_factors or []):
                risk_alert.risk_factors = [
                    *(risk_alert.risk_factors or []),
                    "chatbot_distress_signal",
                ]
                changed = True
            if changed:
                risk_alert.save()

    recipients = list(User.objects.filter(role="guidance"))
    escalation_key = (
        f"chat_escalation:{user.id}:{intent.value}:"
        f"{_message_fingerprint(message)}"
    )

    if recipients and dispatch:
        try:
            dispatch_event(
                NotificationType.RISK_ALERT_GENERATED,
                recipients=recipients,
                sender=user,
                title=f"Chatbot concern escalation: {user.get_full_name()}",
                message=(
                    f"{user.get_full_name()} sent a message indicating severe "
                    f"distress. Review the Guidance risk alert for follow-up."
                ),
                link="/app/risk-alerts",
                deduplication_key=escalation_key,
            )
        except Exception:
            # The RiskAlert is already written, so Guidance still sees the
            # case on the dashboard. A failed in-app notification must not
            # deny the student the support reply.
            logger.exception(
                "Chatbot escalation notification dispatch failed for %s.",
                user.id,
            )

    # No message content in logs either. The alert and notification are the
    # record; this line only helps an operator correlate a failed dispatch.
    logger.warning(
        "Chatbot escalation: caller=%s intent=%s risk_alert=%s recipients=%s",
        user.id,
        intent.value,
        bool(risk_alert),
        len(recipients),
    )

    return {
        "status": (
            "escalated"
            if risk_alert is not None or recipients
            else "no_recipient"
        ),
        "risk_alert_created": risk_alert is not None,
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

    Finalized grades are authoritative. Batch imports create DRAFT rows, so
    when no finalized grade exists the same summary reports the imported rows
    as provisional rather than pretending the student has no data. The
    `data_status` field is the distinction the reply and UI render.
    """
    from apps.academics.models import Grade
    from django.db.models import Avg

    if not check_can_read_student_data(user, student_profile.user):
        return None

    grades = Grade.objects.filter(
        student=student_profile,
        score__isnull=False,
    ).select_related(
        "grading_period",
        "subject_assignment__subject",
    )

    finalized = grades.filter(status="finalized")
    pending = grades.exclude(status="finalized")
    source = finalized if finalized.exists() else pending

    avg = source.aggregate(avg=Avg("score"))["avg"]
    ordered = source.order_by(
        "-grading_period__order",
        "subject_assignment__subject__name",
    )

    subject_grades = []
    seen_subjects = set()
    for grade in ordered:
        subject = grade.subject_assignment.subject
        if subject.id in seen_subjects:
            continue
        seen_subjects.add(subject.id)
        subject_grades.append(
            {
                "subject": subject.name,
                "score": round(float(grade.score), 2),
            }
        )

    latest = ordered.first()
    if finalized.exists():
        data_status = "finalized"
    elif pending.exists():
        data_status = "pending_finalization"
    else:
        data_status = "no_data"

    return {
        "student_name": student_profile.user.get_full_name(),
        # `is not None`: a student whose grades average 0 has an average.
        # Truthiness reported it as "no grades to average".
        "average": round(float(avg), 2) if avg is not None else None,
        "grade_count": source.count(),
        "finalized_count": finalized.count(),
        "pending_count": pending.count(),
        "subject_count": len(subject_grades),
        "subject_grades": subject_grades,
        "latest_period": latest.grading_period.name if latest else None,
        "data_status": data_status,
    }


def get_student_attendance_summary(user, student_profile) -> dict[str, Any] | None:
    """Authorized attendance summary, including the most recent records."""
    from apps.attendance.models import AttendanceRecord

    if not check_can_read_student_data(user, student_profile.user):
        return None

    records = AttendanceRecord.objects.filter(student=student_profile)
    total = records.count()
    present = records.filter(status="present").count()
    late = records.filter(status="late").count()
    absent = records.filter(status="absent").count()

    recent = [
        {"date": record.date.isoformat(), "status": record.status}
        for record in records.order_by("-date")[:10]
    ]

    return {
        "student_name": student_profile.user.get_full_name(),
        "total_days": total,
        "present_days": present,
        "late_days": late,
        "absent_days": absent,
        # The frontend's original wire names. Keeping both means the panel
        # renders existing deployments and new data with one response shape.
        "total_records": total,
        "present_count": present,
        "late_count": late,
        "absent_count": absent,
        "attendance_rate": round((present + late) / total, 4) if total else None,
        "recent_records": recent,
    }


def get_student_academic_status(
    user, student_profile, *, summary: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """
    Academic status plus the latest Guidance risk state.

    The academic decision uses the configured passing grade
    (`ai_engine.config.PASSING_GRADE`), not a hard-coded number. The Guidance
    fields are read-only and omitted when the risk engine has not produced a
    score; the chatbot never computes a new risk score on this path.

    `summary` may be passed by a caller that already fetched the grade summary,
    so one chat request does not run the same grade aggregate twice.
    """
    from ai_engine.config import PASSING_GRADE, WEAK_SUBJECT_THRESHOLD

    if summary is None:
        summary = get_student_grade_summary(user, student_profile)
    if summary is None:
        return None

    average = summary["average"]
    if average is None:
        status = "insufficient_data"
    elif average >= PASSING_GRADE:
        status = "on_track"
    else:
        status = "at_risk"

    weak_subjects = [
        subject
        for subject in summary["subject_grades"]
        if subject["score"] < WEAK_SUBJECT_THRESHOLD
    ]

    from apps.guidance.models import RiskAlert, RiskScore

    latest_score = (
        RiskScore.objects.filter(student=student_profile)
        .order_by("-computed_at")
        .first()
    )
    open_alert = (
        RiskAlert.objects.filter(
            student=student_profile,
            status__in=(
                RiskAlert.Status.ACTIVE,
                RiskAlert.Status.UNDER_MONITORING,
                RiskAlert.Status.ESCALATED,
            ),
        )
        .order_by("-generated_at")
        .first()
    )

    return {
        "status": status,
        "average": average,
        "passing_grade": PASSING_GRADE,
        "weak_subject_threshold": WEAK_SUBJECT_THRESHOLD,
        "weak_subjects": weak_subjects,
        "data_status": summary["data_status"],
        "provisional": summary["data_status"] == "pending_finalization",
        "latest_period": summary["latest_period"],
        "risk_score": (
            {
                "risk_level": latest_score.risk_level,
                "risk_score": (
                    float(latest_score.risk_score)
                    if latest_score.risk_score is not None
                    else None
                ),
            }
            if latest_score is not None
            else None
        ),
        "risk_alert": (
            {
                "risk_level": open_alert.risk_level,
                "status": open_alert.status,
            }
            if open_alert is not None
            else None
        ),
    }


def get_student_recommendations(
    user, student_profile, *, limit: int = 5
) -> dict[str, Any] | None:
    """
    Authorized active recommendations for the student.

    The same service backs the recommendations endpoint. A recommender failure
    degrades to an empty list instead of failing the chat request.
    """
    if not check_can_read_student_data(user, student_profile.user):
        return None

    from apps.recommendations.services import recommend_for_student

    try:
        return recommend_for_student(student_profile, limit=limit)
    except Exception:
        logger.exception(
            "Recommendation computation failed for student %s; "
            "returning an empty recommendation set.",
            student_profile.id,
        )
        return {
            "student_id": str(student_profile.id),
            "method": "unavailable",
            "recommendations": [],
            "fallback_used": True,
            "fallback_reason": "recommendation service unavailable",
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


def _recommendation_titles(data: dict[str, Any]) -> list[str]:
    """Titles from the active recommendation payload, in rank order."""
    payload = data.get("recommendations") or {}
    recommendations = payload.get("recommendations") or []
    return [
        item["title"]
        for item in recommendations
        if isinstance(item, dict) and item.get("title")
    ]


def _academic_reply(data: dict[str, Any]) -> str:
    """Reply for grade, performance and risk-status questions."""
    summary = data.get("grade_summary") or {}
    status = data.get("academic_status") or {}
    data_status = summary.get("data_status", "no_data")
    average = summary.get("average")
    subject_count = summary.get("subject_count")
    passing_grade = status.get("passing_grade")

    if data_status == "no_data" or average is None:
        return (
            "I don't see any imported grades for you yet. Once your school "
            "uploads and finalizes your grades, I can show your average and "
            "recommended next steps."
        )

    if data_status == "pending_finalization":
        first = (
            "Your latest imported grades are still pending finalization. "
            f"The provisional average is {average:.2f}%"
        )
    else:
        first = f"Your current average is {average:.2f}%"

    if subject_count:
        first += f" across {subject_count} subject(s)"
    first += "."

    parts = [first]

    if status.get("status") == "at_risk":
        parts.append(
            f"That is below the passing grade of {passing_grade}. "
            "This is a signal to use your support options early, not a "
            "final judgement of your ability."
        )
    elif status.get("status") == "on_track":
        parts.append(
            f"That is at or above the passing grade of {passing_grade}."
        )

    weak_subjects = status.get("weak_subjects") or []
    if weak_subjects:
        # Every weak subject is listed. A shortened list reads as if the other
        # subjects are fine, which is the opposite of what the student needs.
        named = ", ".join(
            f"{subject['subject']} ({subject['score']:.2f}%)"
            for subject in weak_subjects
        )
        parts.append(f"Subjects needing support: {named}.")

    titles = _recommendation_titles(data)
    if titles:
        parts.append("Recommended next steps: " + "; ".join(titles) + ".")
    else:
        parts.append(
            "No active learning recommendations are available yet, but your "
            "teachers and Guidance can suggest next steps."
        )

    return " ".join(parts)


def _risk_reply(data: dict[str, Any]) -> str:
    """Reply for "Am I at risk?" — status plus tailored recommendations."""
    status = data.get("academic_status") or {}
    academic_status = status.get("status")

    if academic_status == "at_risk":
        lead = (
            "Based on your imported academic records, you are currently in the "
            "at-risk band for your grades."
        )
    elif academic_status == "on_track":
        lead = (
            "Based on your imported academic records, you are currently on "
            "track academically."
        )
    else:
        lead = (
            "There is not enough imported academic data yet to say whether you "
            "are at risk."
        )

    parts = [lead]

    risk_alert = status.get("risk_alert")
    if risk_alert:
        parts.append(
            f"Guidance has an open {risk_alert['risk_level']} risk alert for "
            "your record, so a counselor can follow up."
        )

    academic = _academic_reply(data)
    parts.append(academic)

    return " ".join(parts)


def _attendance_reply(data: dict[str, Any]) -> str:
    """Reply for attendance count and attendance status questions."""
    summary = data.get("attendance_summary") or {}
    total = summary.get("total_records") or 0

    if total == 0:
        return (
            "I don't see any attendance records for you yet. Once your school "
            "uploads attendance, I can show your present, late and absent days."
        )

    rate = summary.get("attendance_rate")
    rate_text = (
        f" Your attendance rate is {rate * 100:.1f}%."
        if isinstance(rate, (int, float))
        else ""
    )
    return (
        f"You have {summary['present_count']} present, {summary['late_count']} "
        f"late and {summary['absent_count']} absent day(s) across "
        f"{total} recorded day(s).{rate_text}"
    )


def _subject_help_reply(data: dict[str, Any], entities) -> str:
    """
    Reply for "help me with <subject>".

    Names the student's own score for that subject when the summary has it. The
    model used to answer this one and produced "the overall average for
    Mathematics is a C-. You are currently on track" for an at-risk student, so
    the number comes from the grade book or is not stated at all.
    """
    subject = next(
        (e.value for e in entities if e.entity_type == "subject"), None
    )
    summary = data.get("grade_summary") or {}
    scores = {
        row["subject"]: row["score"]
        for row in summary.get("subject_grades") or []
    }

    if subject and subject in scores:
        return (
            f"Your current average in {subject} is {scores[subject]:.2f}%. Ask "
            f"your teacher for a review session and practice sets, and I can "
            f"list learning resources for {subject}."
        )
    if subject:
        return (
            f"Ask your teacher for extra help with {subject}, and try the "
            "learning resources for that subject. You can also ask me for your "
            "grade in it."
        )
    return (
        "Which subject do you need help with? Tell me the subject and I can "
        "point you to your grade and its learning resources."
    )


def _study_strategy_reply(data: dict[str, Any]) -> str:
    """
    Reply for "how should I study".

    Leads with the subjects the student actually needs to work on, rather than
    a generic tip list, because the weak-subject list is already computed.
    """
    weak = (data.get("academic_status") or {}).get("weak_subjects") or []
    if weak:
        names = ", ".join(item["subject"] for item in weak)
        return (
            f"Start with the subjects that need the most work: {names}. Short, "
            "regular review of one topic at a time works better than long "
            "sessions, and your teacher can give you practice sets."
        )
    return (
        "Review a little every day rather than all at once, and practise the "
        "topics you find hardest first. Ask your teacher for practice sets for "
        "the subject you are working on."
    )


def _support_reply(data: dict[str, Any] | None = None) -> str:
    """Empathetic crisis reply with the configured official contacts."""
    from django.conf import settings

    contact = getattr(
        settings,
        "AEGIS_COUNSELING_CONTACT",
        "your school's Guidance Office",
    )
    helpline = getattr(settings, "AEGIS_CRISIS_HELPLINE", "")
    emergency = getattr(settings, "AEGIS_EMERGENCY_NUMBER", "911")

    lines = [
        "I'm really sorry you're going through this. You do not have to "
        "handle it alone, and asking for help is the right move.",
        f"Please reach out to {contact} right now.",
    ]
    if helpline:
        lines.append(f"You can also call the crisis helpline at {helpline}.")
    lines.append(f"If you are in immediate danger, call {emergency} now.")

    escalation = (data or {}).get("escalation") or {}
    if escalation.get("status") == "escalated":
        lines.append(
            "I've alerted your school's Guidance team so someone can follow "
            "up with you."
        )
    else:
        lines.append(
            "Please also tell a trusted adult, teacher or counselor directly."
        )
    return " ".join(lines)


def _deterministic_reply(user, intent: ChatIntent, entities, context, data=None) -> str:
    """Generate a deterministic reply for supported intents."""
    data = data or {}

    # A parent's data question with several linked children and no child named
    # is ambiguous. Saying so is the honest answer; picking one would report a
    # real child's grades against a question about another.
    if user.role == "parent" and intent in (
        ChatIntent.ASK_GRADE,
        ChatIntent.ASK_ACADEMIC_PERFORMANCE,
        ChatIntent.ASK_RECOMMENDATION,
        ChatIntent.ASK_RISK_STATUS,
        ChatIntent.ASK_ATTENDANCE,
        ChatIntent.ASK_ATTENDANCE_STATUS,
        ChatIntent.ASK_SUBJECT_HELP,
        ChatIntent.ASK_STUDY_STRATEGY,
    ):
        if not any(
            key in data
            for key in ("grade_summary", "attendance_summary", "recommendations")
        ):
            return (
                "I can answer that, but you have more than one linked student. "
                "Which student do you mean? Tell me their name or student number."
            )

    if intent in (
        ChatIntent.ASK_GRADE,
        ChatIntent.ASK_ACADEMIC_PERFORMANCE,
    ):
        return _academic_reply(data)
    if intent == ChatIntent.ASK_RISK_STATUS:
        return _risk_reply(data)
    if intent == ChatIntent.ASK_RECOMMENDATION:
        titles = _recommendation_titles(data)
        if titles:
            return (
                "Based on your current grades and attendance, I recommend: "
                + "; ".join(titles[:5])
                + "."
            )
        return (
            "I don't have active learning recommendations for you yet. Keep "
            "your grades and attendance up to date, or ask Guidance for "
            "support options."
        )
    if intent in (ChatIntent.ASK_ATTENDANCE, ChatIntent.ASK_ATTENDANCE_STATUS):
        return _attendance_reply(data)
    if intent == ChatIntent.ASK_SUBJECT_HELP:
        return _subject_help_reply(data, entities)
    if intent == ChatIntent.ASK_STUDY_STRATEGY:
        return _study_strategy_reply(data)
    if intent in (
        ChatIntent.ASK_ASSESSMENT,
        ChatIntent.ASSESSMENT_SCHEDULE,
        ChatIntent.ASSESSMENT_INSTRUCTIONS,
    ):
        return (
            "I can't show assessment details yet — quizzes and tests appear in "
            "your classes. Please check with your teacher, or ask Guidance if "
            "you are unsure about one."
        )
    if intent == ChatIntent.ASK_LEARNING_RESOURCE:
        resources = data.get("resources") or []
        if resources:
            titles = ", ".join(item["title"] for item in resources[:5])
            return f"I found these approved learning resources: {titles}."
        return (
            "I couldn't find an approved learning resource for that subject. "
            "Ask your teacher for a module or reviewer."
        )

    if intent == ChatIntent.GREETING:
        return f"Hello, {user.first_name}! I can help with AEGIS. What do you need?"
    if intent == ChatIntent.HELP:
        return (
            "I can help with your grades, academic status, attendance, "
            "recommendations, assessments, and learning resources. "
            "What would you like to know?"
        )
    if intent == ChatIntent.UNKNOWN:
        return (
            "I'm sorry, I didn't fully understand. Could you rephrase? "
            "I can help with grades, academic status, attendance, "
            "recommendations, assessments, or learning resources."
        )
    if intent == ChatIntent.SYSTEM_NAVIGATION:
        return (
            "In AEGIS, you can use the dashboard to view your information. "
            "For specific features, use the navigation menu."
        )
    if intent == ChatIntent.URGENT_CONCERN:
        return _support_reply(data)
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


# Internal vocabulary a provider must never hand to a student.
#
# These are database values. A model that prints `at_risk` is quoting the
# system rather than talking to the student, and a reply reading "you are
# at_risk" is a bug the student can see. The provider phrases an answer; the
# application owns what the status is called. This runs on every provider
# reply because a prompt instruction is a request, not a guarantee — the
# local model ignored it.
_INTERNAL_TOKENS = {
    "at_risk": "at risk",
    "on_track": "on track",
    "insufficient_data": "not enough information",
    "no_data": "no data",
    "pending_finalization": "pending finalization",
    "study_support": "study support",
    "under_monitoring": "under monitoring",
    "high_risk": "high risk",
    "low_risk": "low risk",
}


def sanitize_provider_reply(text: str) -> str:
    """Replace internal field values a provider may have quoted verbatim."""
    for token, plain in _INTERNAL_TOKENS.items():
        text = re.sub(
            rf'["\u201c\u2018\']?{re.escape(token)}["\u201d\u2019\']?',
            plain,
            text,
            flags=re.IGNORECASE,
        )
    return text


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _authorized_numbers(data: Any) -> set[str]:
    """Every number the provider was actually given, in the forms it may print."""
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            found.update({f"{value:g}", f"{value:.1f}", f"{value:.2f}"})
        elif isinstance(value, str):
            found.update(_NUMBER_RE.findall(value))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(data)
    return found


def reply_is_grounded(reply: str, data: Any) -> bool:
    """
    False when the prose states a number the provider was never handed.

    A model given 65.72 that writes "your Math average is 85%" has invented a
    grade. The prompt forbids it and the local model did it anyway — most
    visibly on intents that carry no data at all, where it answered
    "your average is 85%" and "you are on track" for an at-risk student. The
    check is therefore mechanical rather than advisory: every number in the
    reply must appear in the authorized data, or the deterministic reply stands.
    """
    allowed = _authorized_numbers(data)
    return all(number in allowed for number in _NUMBER_RE.findall(reply))


# Headings and punctuation the service uses for its own record sections. A
# provider that prints one is copying the payload back instead of answering.
# The local model did exactly that for the advice intent: handed the grade
# book it replied "**Grade Summary:** Average: 68.6 **Academic Status:** at
# risk **Recommendations:** Content-based study activity – Mathematics" — a
# record dump plus a recommendation title no record held. Rejecting on the
# label is cheap and its only failure mode is falling back to the
# deterministic reply, which is the answer the application would have given.
_PAYLOAD_LABELS = (
    "grade summary",
    "academic status",
    "average:",
    "status:",
    "recommendations:",
    "**",
)


def reply_echoes_payload(reply: str) -> bool:
    """True when the prose restates the payload instead of answering."""
    lower = reply.lower()
    return any(label in lower for label in _PAYLOAD_LABELS)


def provider_payload(intent: ChatIntent, data: Any) -> Any:
    """
    The subset of data a provider is handed.

    Only `ASK_STUDY_STRATEGY` reaches a provider, and its answer is advice, so
    the provider is given the weak-subject names and the two numbers it may
    legitimately refer to — not the grade book, the status section or the
    recommendation list. The local model copied those sections into its reply
    verbatim when it had them. Removing the material is the root fix; the
    label check above is the backstop. The full `data` is still what the client
    receives.
    """
    if intent is ChatIntent.ASK_STUDY_STRATEGY:
        status = data.get("academic_status") or {}
        return {
            "weak_subjects": [
                item["subject"] for item in status.get("weak_subjects") or []
            ],
            "average": status.get("average"),
            "passing_grade": status.get("passing_grade"),
        }
    return data


def handle_message(
    user,
    message: str,
    *,
    use_llm: bool | None = None,
    llm_result: dict[str, Any] | None = None,
    provider=None,
) -> ChatbotResponse:
    """
    Main chatbot service entry point.

    Architecture:
      1. Parse message deterministically (intent + urgency + entities).
      2. Check policy (role allowed for intent).
      3. Build authorized context.
      4. Handle escalation if needed.
      5. Compute data, then let an optional provider produce prose.
         Any provider failure falls back to the deterministic structured reply.

    The application remains authoritative. A provider receives only authorized,
    already-computed data — it never gets ORM or database access.
    """
    from django.conf import settings

    parse_result = parse_message(message)
    intent = parse_result.intent
    urgency = parse_result.urgency
    entities = parse_result.entities

    if use_llm is None:
        use_llm = bool(getattr(settings, "AEGIS_CHATBOT_USE_LLM", False))

    # Policy check: allowed intent for role
    if not check_intent_allowed(user.role, intent):
        return ChatbotResponse(
            reply="I'm not able to help with that specific request for your account.",
            intent=ChatIntent.UNKNOWN,
            urgency=urgency,
            safe_fallback=True,
        )

    # Escalation path (FR-031 / request_counselor).
    #
    # This runs before any provider: a distress signal is handled by the
    # application, never delegated to a model.
    if urgency == UrgencyLevel.URGENT or intent in ESCALATION_INTENTS:
        try:
            escalation = create_escalation(
                user,
                intent=intent,
                message=message,
                entities=entities,
                urgent=urgency == UrgencyLevel.URGENT,
            )
        except Exception:
            # A safety reply must never depend on the alert write succeeding.
            logger.exception("Chatbot escalation failed for caller=%s.", user.id)
            escalation = {
                "status": "error",
                "risk_alert_created": False,
                "escalation_key": "",
                "intent": intent.value,
            }
        reply = _deterministic_reply(
            user, intent, entities, {}, {"escalation": escalation}
        )
        return ChatbotResponse(
            reply=reply,
            intent=intent,
            urgency=UrgencyLevel.URGENT,
            escalated=escalation["status"] == "escalated",
            data={"escalation": escalation},
        )

    # Build authorized context (least privilege)
    context = build_context(user, intent, entities)

    # Determine data to provide. Resolving the target once means a parent with
    # several linked children is asked which child instead of being answered
    # about whichever one sorted first.
    data: dict[str, Any] = {}
    target = None
    if intent in (
        ChatIntent.ASK_GRADE,
        ChatIntent.ASK_ACADEMIC_PERFORMANCE,
        ChatIntent.ASK_RECOMMENDATION,
        ChatIntent.ASK_RISK_STATUS,
        ChatIntent.ASK_ATTENDANCE,
        ChatIntent.ASK_ATTENDANCE_STATUS,
        ChatIntent.ASK_SUBJECT_HELP,
        ChatIntent.ASK_STUDY_STRATEGY,
    ):
        target = resolve_target_student(user)

    if intent in (
        ChatIntent.ASK_GRADE,
        ChatIntent.ASK_ACADEMIC_PERFORMANCE,
        ChatIntent.ASK_RECOMMENDATION,
        ChatIntent.ASK_RISK_STATUS,
        ChatIntent.ASK_SUBJECT_HELP,
        ChatIntent.ASK_STUDY_STRATEGY,
    ) and target is not None:
        summary = get_student_grade_summary(user, target)
        if summary:
            data["grade_summary"] = summary
        status = get_student_academic_status(user, target, summary=summary)
        if status:
            data["academic_status"] = status
        recommendations = get_student_recommendations(user, target)
        if recommendations:
            data["recommendations"] = recommendations
    elif intent in (
        ChatIntent.ASK_ATTENDANCE,
        ChatIntent.ASK_ATTENDANCE_STATUS,
    ) and target is not None:
        summary = get_student_attendance_summary(user, target)
        if summary:
            data["attendance_summary"] = summary
    elif intent == ChatIntent.ASK_LEARNING_RESOURCE:
        subject = None
        for e in entities:
            if e.entity_type == "subject":
                subject = e.value
        resources = get_learning_resources(user, subject=subject)
        data["resources"] = resources

    # Provider path. A caller may inject a provider directly (tests, future
    # wiring); otherwise the configured provider is built lazily. A provider
    # exception or an empty reply degrades to the deterministic answer.
    #
    # Only LLM_ELIGIBLE_INTENTS reach a provider. Everything else takes the
    # deterministic template, so a model never sees a message the classifier
    # could not understand and no model is ever asked to answer a distress
    # signal (that path returned above).
    degraded = False
    if use_llm and intent in LLM_ELIGIBLE_INTENTS:
        reply = None
        payload = provider_payload(intent, data)
        if llm_result and llm_result.get("valid"):
            reply = llm_result.get("reply") or None
        else:
            from apps.chatbot.providers import ChatProviderRequest, get_provider

            active_provider = provider or get_provider()
            try:
                reply = active_provider.generate(
                    ChatProviderRequest(
                        user_role=user.role,
                        message=message,
                        intent=intent.value,
                        urgency=urgency.value,
                        context=context,
                        data=payload,
                    )
                )
            except Exception:
                logger.exception(
                    "Chatbot provider failed; using deterministic fallback."
                )
                reply = None

        if isinstance(reply, str) and reply.strip():
            reply = sanitize_provider_reply(reply)
            if reply_is_grounded(reply, payload) and not reply_echoes_payload(reply):
                return ChatbotResponse(
                    reply=reply,
                    intent=intent,
                    urgency=urgency,
                    data=data,
                )
            logger.warning(
                "Chatbot provider reply restated the record or named a value it "
                "was not given (intent=%s); using the deterministic reply.",
                intent.value,
            )

        degraded = True

    # Deterministic fallback / low-confidence
    reply = _deterministic_reply(user, intent, entities, context, data)
    return ChatbotResponse(
        reply=reply,
        intent=intent,
        urgency=urgency,
        degraded=degraded,
        safe_fallback=True,
        data=data,
    )
