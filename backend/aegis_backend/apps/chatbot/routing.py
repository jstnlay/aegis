"""
Flag routing, notifications, acknowledgment and escalation.

Routing rules (severity is the maximum of both detection layers):

  critical  guidance + admin + the student's faculty, faculty notice carries
            no content and no student name
  high      guidance + the student's faculty, same content-free faculty notice
  medium    guidance only
  low       stored in the inbox, no push notification

The 15-minute acknowledgment timer is data, not a daemon. `escalate_stale_flags`
is called by the admin endpoint and by the management command, so a deployment
without Celery still escalates when someone opens the dashboard.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.chatbot.models import Flag, FlagAction, FlagRecipient
from apps.cms.settings_registry import get_int_setting
from apps.notifications.events import dispatch_event
from apps.notifications.models import NotificationType

logger = logging.getLogger(__name__)


def acknowledgment_minutes(severity: str | None = None) -> int:
    """
    The window Guidance has to acknowledge a flag of this severity.

    The school-wide setting is the floor. A per-severity setting overrides it
    when it holds a positive number, so a critical flag can have a shorter
    window than a medium one without the two being two different code paths.
    """
    if severity:
        from apps.cms.settings_registry import get_setting

        key = f"chatbot.acknowledgment_timer_minutes.{severity}"
        raw = str(get_setting(key, "") or "").strip()
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return get_int_setting("chatbot.acknowledgment_timer_minutes", 15)


def severity_windows() -> dict[str, int]:
    """Every severity's window, for the administrator dashboard."""
    return {
        severity: acknowledgment_minutes(severity)
        for severity in ("critical", "high", "medium", "low")
    }


def faculty_notifications_enabled() -> bool:
    """Administrators can switch the content-free faculty notice off."""
    from apps.cms.settings_registry import get_setting

    return str(get_setting("chatbot.faculty_notifications_enabled", "true")).lower() in (
        "true",
        "1",
        "yes",
        "on",
    )


def is_guidance_or_admin(user) -> bool:
    return getattr(user, "role", None) in ("guidance", "admin")


def faculty_sections(user):
    from django.db.models import Q

    from apps.academics.models import Section

    profile = getattr(user, "faculty_profile", None)
    if profile is None:
        return Section.objects.none()
    return Section.objects.filter(
        Q(adviser=profile) | Q(subject_assignments__faculty=profile)
    ).distinct()


def resolve_recipients(flag: Flag) -> dict[str, list]:
    """Who receives this flag, by role. Faculty are content-blind by design."""
    from apps.accounts.models import User

    guidance = list(
        User.objects.filter(role=User.Role.GUIDANCE, is_active=True).order_by("email")
    )
    faculty = []
    admins = []

    if (
        flag.severity in ("high", "critical")
        and flag.student_id
        and faculty_notifications_enabled()
    ):
        faculty = list(
            User.objects.filter(
                role=User.Role.FACULTY,
                is_active=True,
                faculty_profile__advised_sections__enrollments__student=flag.student,
            ).distinct()
        )
        # Subject teachers of the student's active sections, not only advisers.
        faculty += list(
            User.objects.filter(
                role=User.Role.FACULTY,
                is_active=True,
                faculty_profile__subject_assignments__section__enrollments__student=flag.student,
            ).distinct()
        )

    if flag.severity == "critical":
        admins = list(
            User.objects.filter(role=User.Role.ADMIN, is_active=True).order_by("email")
        )

    # Deduplicate by pk while preserving order: guidance, faculty, admin.
    seen = set()
    result = {"guidance": [], "faculty": [], "admin": []}
    for role, users in (
        ("guidance", guidance),
        ("faculty", faculty),
        ("admin", admins),
    ):
        for user in users:
            if user.pk in seen:
                continue
            seen.add(user.pk)
            result[role].append(user)
    return result


def _notify(flag: Flag, recipients, *, role: str) -> int:
    if not recipients:
        return 0

    if role == "faculty":
        title = "Student support flag in your class"
        message = (
            "A student in one of your classes has a support flag. Open the "
            "faculty flag feed to see severity and status. The conversation "
            "content and the student's identity are withheld from this notice."
        )
        link = "/app/faculty/flags"
    elif role == "admin":
        title = "Critical student support flag"
        message = (
            f"A critical chatbot support flag was created for student "
            f"{flag.student.user.get_full_name() if flag.student else flag.user_id}. "
            "Open the flag inbox to review it."
        )
        link = "/app/admin/chatbot"
    else:
        title = "Chat support flag"
        who = flag.student.user.get_full_name() if flag.student else "a user"
        message = (
            f"A {flag.severity} support flag was created for {who}. "
            "The message is available in the flag inbox. Review and "
            "acknowledge it within the timer."
        )
        link = "/app/guidance/flags"

    for user in recipients:
        row, created = FlagRecipient.objects.get_or_create(
            flag=flag,
            user=user,
            defaults={"role_snapshot": role},
        )
        if not created and row.notified_at is not None:
            continue
        dispatch_event(
            NotificationType.BEHAVIORAL_WARNING,
            recipients=[user],
            sender=flag.user,
            title=title,
            message=message,
            link=link,
            deduplication_key=f"chat_flag:{flag.id}:{user.id}",
        )
        if row.notified_at is None:
            row.notified_at = timezone.now()
            row.save(update_fields=["notified_at", "updated_at"])
    return len(recipients)


def route_flag(flag: Flag, *, dispatch: bool = True) -> dict:
    """Create recipient rows and dispatch notifications once."""
    recipients = resolve_recipients(flag)
    sent = 0
    if dispatch:
        for role in ("guidance", "faculty", "admin"):
            sent += _notify(flag, recipients[role], role=role)
    else:
        for role, users in recipients.items():
            for user in users:
                FlagRecipient.objects.get_or_create(
                    flag=flag,
                    user=user,
                    defaults={"role_snapshot": role},
                )
    FlagAction.objects.create(
        flag=flag,
        action=FlagAction.Action.NOTIFIED,
        note="",
        is_private=True,
        metadata={"recipients": sent},
    )
    return {
        "guidance": len(recipients["guidance"]),
        "faculty": len(recipients["faculty"]),
        "admin": len(recipients["admin"]),
        "notified": sent,
    }


def create_flag(
    *,
    chat_message,
    user,
    severity: str,
    source: str,
    categories: list[str],
    summary: str,
    manual_review: bool,
) -> Flag:
    """Create the flag and its timer, then route it."""
    student = getattr(user, "student_profile", None)
    with transaction.atomic():
        flag = Flag.objects.create(
            student=student,
            user=user,
            chat_message=chat_message,
            severity=severity,
            source=source,
            categories=categories,
            summary=summary[:1000],
            manual_review=manual_review,
            escalation_due_at=timezone.now()
            + timezone.timedelta(minutes=acknowledgment_minutes(severity)),
        )
        FlagAction.objects.create(
            flag=flag,
            actor=user,
            action=FlagAction.Action.CREATED,
            note="",
            is_private=True,
            metadata={
                "source": source,
                "severity": severity,
                "manual_review": manual_review,
            },
        )
        route_flag(flag)
    return flag


def may_view_flag(user, flag: Flag) -> bool:
    if is_guidance_or_admin(user):
        return True
    return FlagRecipient.objects.filter(flag=flag, user=user).exists()


def may_manage_flag(user, flag: Flag) -> bool:
    """Guidance and admin act on a flag. Faculty recipients only read."""
    return is_guidance_or_admin(user)


def acknowledge_flag(flag: Flag, *, user, note: str = "") -> Flag:
    if not may_manage_flag(user, flag):
        raise PermissionError("Only guidance or admin can acknowledge a flag.")
    if flag.acknowledged_at is not None:
        return flag

    now = timezone.now()
    flag.acknowledged_at = now
    flag.acknowledged_by = user
    if flag.status == Flag.Status.OPEN:
        flag.status = Flag.Status.ACKNOWLEDGED
    flag.save(
        update_fields=[
            "acknowledged_at",
            "acknowledged_by",
            "status",
            "updated_at",
        ]
    )
    FlagRecipient.objects.filter(flag=flag, user=user, acknowledged_at__isnull=True).update(
        acknowledged_at=now
    )
    FlagAction.objects.create(
        flag=flag,
        actor=user,
        action=FlagAction.Action.ACKNOWLEDGED,
        note=note,
        is_private=True,
    )
    return flag


def add_case_note(flag: Flag, *, user, note: str) -> FlagAction:
    if not may_manage_flag(user, flag):
        raise PermissionError("Only guidance or admin can add a case note.")
    if not note.strip():
        raise ValueError("A case note cannot be empty.")
    return FlagAction.objects.create(
        flag=flag,
        actor=user,
        action=FlagAction.Action.NOTE,
        note=note.strip(),
        is_private=True,
    )


def resolve_flag(flag: Flag, *, user, note: str = "") -> Flag:
    if not may_manage_flag(user, flag):
        raise PermissionError("Only guidance or admin can resolve a flag.")
    flag.status = Flag.Status.RESOLVED
    flag.resolved_at = timezone.now()
    flag.resolution_note = note.strip()
    flag.save(update_fields=["status", "resolved_at", "resolution_note", "updated_at"])
    FlagAction.objects.create(
        flag=flag,
        actor=user,
        action=FlagAction.Action.RESOLVED,
        note=note.strip(),
        is_private=True,
    )
    return flag


def mark_false_positive(flag: Flag, *, user, note: str = "") -> Flag:
    if not may_manage_flag(user, flag):
        raise PermissionError("Only guidance or admin can mark a false positive.")
    flag.status = Flag.Status.FALSE_POSITIVE
    flag.resolved_at = timezone.now()
    flag.resolution_note = note.strip()
    flag.save(update_fields=["status", "resolved_at", "resolution_note", "updated_at"])
    FlagAction.objects.create(
        flag=flag,
        actor=user,
        action=FlagAction.Action.FALSE_POSITIVE,
        note=note.strip(),
        is_private=True,
    )
    return flag


def escalate_stale_flags(*, now=None) -> list[Flag]:
    """
    Escalate open, unacknowledged flags past their timer.

    Returns the flags escalated in this call. Idempotent: `escalated_at`
    prevents a second admin notice for the same flag.
    """
    from apps.accounts.models import User

    now = now or timezone.now()
    stale = Flag.objects.filter(
        acknowledged_at__isnull=True,
        escalated_at__isnull=True,
        escalation_due_at__lte=now,
    ).exclude(status__in=[Flag.Status.RESOLVED, Flag.Status.FALSE_POSITIVE])

    admins = list(
        User.objects.filter(role=User.Role.ADMIN, is_active=True).order_by("email")
    )
    escalated = []
    for flag in stale:
        flag.escalated_at = now
        if flag.status == Flag.Status.OPEN:
            flag.status = Flag.Status.UNDER_REVIEW
        flag.save(update_fields=["escalated_at", "status", "updated_at"])
        FlagAction.objects.create(
            flag=flag,
            action=FlagAction.Action.ESCALATED,
            note="Acknowledgment timer expired.",
            is_private=True,
            metadata={"due_at": flag.escalation_due_at.isoformat() if flag.escalation_due_at else None},
        )
        dispatch_event(
            NotificationType.BEHAVIORAL_WARNING,
            recipients=admins,
            title="Support flag not acknowledged",
            message=(
                f"A {flag.severity} support flag for "
                f"{flag.student.user.get_full_name() if flag.student else flag.user_id} "
                "passed its acknowledgment timer. Guidance has not acknowledged it."
            ),
            link="/app/admin/chatbot",
            deduplication_key=f"chat_flag_escalated:{flag.id}",
        )
        escalated.append(flag)
    return escalated
