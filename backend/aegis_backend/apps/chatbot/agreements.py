"""Student notice and agreement acceptance."""

from __future__ import annotations

from django.utils import timezone

from apps.chatbot.models import AgreementAcceptance
from apps.cms.settings_registry import get_setting


def notice_version() -> str:
    return str(get_setting("chatbot.notice_version", "2026-11-01"))


def notice_text() -> str:
    return str(
        get_setting(
            "chatbot.notice_text",
            (
                "AEGIS stores chatbot messages so a guidance counselor can "
                "review a safety concern. Messages are screened by an "
                "automated keyword layer and may be classified by Gemini, a "
                "third-party AI service. Only the message text is sent for "
                "classification; your name, student number and school records "
                "are not. You can ask a counselor what was stored about you."
            ),
        )
    )


def notice_payload(user) -> dict:
    version = notice_version()
    accepted = AgreementAcceptance.objects.filter(
        user=user, notice_version=version
    ).first()
    return {
        "version": version,
        "text": notice_text(),
        "accepted": accepted is not None,
        "accepted_at": accepted.accepted_at if accepted else None,
    }


def accept_notice(user, *, version: str | None = None, ip_address=None):
    """Accept the current version. A stale version is refused, not recorded."""
    current = notice_version()
    if version and version != current:
        raise ValueError(
            "The notice changed. Reload it and accept the current version."
        )
    acceptance, _created = AgreementAcceptance.objects.get_or_create(
        user=user,
        notice_version=current,
        defaults={"accepted_at": timezone.now(), "ip_address": ip_address},
    )
    return acceptance


def student_must_accept(user) -> bool:
    if getattr(user, "role", None) != "student":
        return False
    return not AgreementAcceptance.objects.filter(
        user=user, notice_version=notice_version()
    ).exists()
