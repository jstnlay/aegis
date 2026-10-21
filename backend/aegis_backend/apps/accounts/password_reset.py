"""
Password reset: issuing, redeeming and mailing a reset link.

Three rules shape this module.

**The raw token is never stored.** Only its SHA-256 hash is, so a database
leak cannot be turned into password resets. The raw value exists in one
place: the email.

**One live token per account.** Issuing a new one closes the previous, so an
older link cannot be redeemed after a newer request.

**A reset kills the sessions it should.** Redeeming a token revokes every
outstanding refresh token for that account. A password reset exists because
a session may be stolen; leaving that session alive would defeat the point.
"""

import hashlib
import logging
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.audit.services import record_audit

from .models import PasswordResetToken, User

logger = logging.getLogger(__name__)

#: How long a reset link stays usable.
RESET_TOKEN_LIFETIME_MINUTES = 30

#: How long a newly provisioned account's set-password link stays usable.
#: A teacher or counselor may not open the mail the same afternoon.
SET_PASSWORD_LINK_MINUTES = 24 * 60

#: The school the links are for. The frontend is a separate service, so the
#: link has to be built from a configured base URL.
SCHOOL_NAME = "His Care Christian Institute"

#: The answer every password-reset request gets, whether or not the address
#: belongs to an account. A different answer for a known address would turn
#: this endpoint into a way of discovering who has an account.
GENERIC_RESET_ANSWER = (
    "If an account exists for that address, a password reset link is on its way."
)


def hash_token(raw_token: str) -> str:
    """The stored form of a token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_reset_token(
    user: User, lifetime_minutes: int = RESET_TOKEN_LIFETIME_MINUTES
) -> tuple[str, PasswordResetToken]:
    """
    Issue a fresh reset token for ``user`` and return it with its record.

    Any previous unused token for the account is closed first, so only the
    newest link works. The lifetime is a parameter because the two callers
    need different windows: a forgotten password is fresh in the mind, a
    newly provisioned account may not be opened the same afternoon.
    """
    now = timezone.now()
    PasswordResetToken.objects.filter(
        user=user, used_at__isnull=True
    ).update(used_at=now)

    raw_token = secrets.token_urlsafe(32)
    record = PasswordResetToken.objects.create(
        user=user,
        token_hash=hash_token(raw_token),
        expires_at=now + timezone.timedelta(minutes=lifetime_minutes),
    )
    return raw_token, record


def redeem_reset_token(raw_token: str) -> PasswordResetToken | None:
    """
    Return the token record for a raw token, if it may still be used.

    A token that is unknown, already used, or expired returns ``None`` — the
    three cases are indistinguishable to the caller on purpose.
    """
    if not raw_token:
        return None

    record = PasswordResetToken.objects.filter(
        token_hash=hash_token(raw_token)
    ).first()
    if record is None or record.is_used or record.is_expired:
        return None
    return record


def close_reset_token(record: PasswordResetToken) -> None:
    """Mark a token used, and record that it was redeemed."""
    before = PasswordResetToken.objects.get(pk=record.pk)
    record.used_at = timezone.now()
    record.save(update_fields=["used_at", "updated_at"])
    try:
        record_audit(
            action="update",
            old_instance=before,
            new_instance=record,
            user=record.user,
        )
    except Exception:
        logger.exception("PASSWORD_RESET audit record failed (token still closed)")


def revoke_sessions(user: User) -> int:
    """
    Blacklist every outstanding refresh token for ``user``.

    Returns how many were revoked. The blacklist application is already in
    the project (the logout route uses it), so this is the same mechanism
    used to sign out.
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )
    except ImportError:  # pragma: no cover - the app is a hard dependency
        return 0

    revoked = 0
    for outstanding in OutstandingToken.objects.filter(user=user):
        try:
            # `OutstandingToken` has no `blacklist()` method of its own; the
            # blacklist is the row that points at it.
            BlacklistedToken.objects.get_or_create(token=outstanding)
            revoked += 1
        except Exception:
            logger.exception("Could not revoke a refresh token during password reset")
    return revoked


def reset_url(raw_token: str) -> str:
    """The link the recipient follows."""
    base = settings.AEGIS_FRONTEND_URL.rstrip("/")
    return f"{base}/reset-password?token={raw_token}"


def set_password_url(raw_token: str) -> str:
    """
    The link a newly provisioned account follows.

    It points at the same redemption the password reset uses. The two are
    the same primitive: a hashed, single-use token on the account that
    becomes a password when it is redeemed. Only the wording differs.
    """
    base = settings.AEGIS_FRONTEND_URL.rstrip("/")
    return f"{base}/set-password?token={raw_token}"


def send_set_password_email(user: User, raw_token: str) -> bool:
    """
    Mail the link that lets a newly provisioned account set its password.

    No password is ever mailed, and no administrator chooses one: the
    person sets their own when they follow the link.
    """
    subject = f"{SCHOOL_NAME} - set your AEGIS password"
    body = (
        f"Hello {user.get_full_name() or user.email},\n\n"
        "An account has been created for you at "
        f"{SCHOOL_NAME}. Open the link below to set your password and sign "
        "in. The link stops working in 24 hours and can only be used once.\n\n"
        f"{set_password_url(raw_token)}\n\n"
        "If you were not expecting this, you can ignore this message - the "
        "account cannot be used until the password is set.\n\n"
        f"- {SCHOOL_NAME}"
    )
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Set-password email could not be sent")
        return False
    return True


def send_reset_email(user: User, raw_token: str) -> bool:
    """
    Mail the reset link. Returns whether the message was handed to the mail
    backend.

    The address in the body is the account's own address, so the mail is not a
    disclosure to a third party: it only goes to the address on the account.
    """
    subject = f"{SCHOOL_NAME} — password reset"
    body = (
        f"Hello {user.get_full_name() or user.email},\n\n"
        "A password reset was requested for your AEGIS account. "
        "Open the link below to choose a new password. "
        f"The link stops working in {RESET_TOKEN_LIFETIME_MINUTES} minutes "
        "and can only be used once.\n\n"
        f"{reset_url(raw_token)}\n\n"
        "If you did not ask for this, nothing has changed on your account and "
        "you can ignore this message.\n\n"
        f"— {SCHOOL_NAME}"
    )
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Password reset email could not be sent")
        return False
    return True
