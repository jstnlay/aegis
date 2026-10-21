"""
Parent invitations: nominating a parent, approving the nomination, and
turning the invitation into an account.

The shape of the flow, and why:

1. **A student nominates** (or an administrator nominates directly). A
   nomination is a request. It creates no account and grants nothing.
2. **An administrator approves** it, which is the moment the school says
   this person is this child's parent. Approval issues the invitation token
   and mails the link.
3. **The parent accepts**, setting their own password. Accepting creates the
   parent account *and* the link to the child in one transaction, because a
   parent account without its child link grants nothing.

A parent's account shows a child's grades, attendance, guidance records and
behavioural notes. That is why the invitation is issued by the school
rather than requested from a public form: an open request would be a way to
ask for someone else's child.
"""

import hashlib
import logging
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_audit

from .models import ParentInvitation, ParentProfile, ParentStudentLink, User

logger = logging.getLogger(__name__)

#: How long an invitation link stays usable. A parent may not open the mail
#: the same afternoon.
INVITATION_LIFETIME_DAYS = 7

SCHOOL_NAME = "His Care Christian Institute"


def hash_token(raw_token: str) -> str:
    """The stored form of an invitation token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def nominate_parent(
    *,
    email: str,
    full_name: str,
    relationship: str,
    student,
    nominated_by: User | None = None,
) -> tuple[ParentInvitation | None, str]:
    """
    Record a nomination. Returns the invitation and the raw token, or
    ``(None, "")`` when one is already live for that address and child.
    """
    if User.objects.filter(email__iexact=email).exists():
        return None, ""

    live = ParentInvitation.objects.filter(
        email__iexact=email, student=student
    ).filter(
        status__in=[
            ParentInvitation.Status.PENDING,
            ParentInvitation.Status.APPROVED,
        ]
    ).first()
    if live is not None:
        return None, ""

    invitation = ParentInvitation.objects.create(
        email=email,
        full_name=full_name,
        relationship=relationship,
        student=student,
        nominated_by=nominated_by,
    )
    return invitation, ""


def approve_invitation(
    invitation: ParentInvitation, *, reviewer: User
) -> tuple[ParentInvitation, str]:
    """
    Approve a nomination and issue the invitation link.

    The token is minted here, not at nomination: the link that reaches the
    parent's inbox is the one the school approved.
    """
    if invitation.status != ParentInvitation.Status.PENDING:
        raise ValueError("This invitation has already been decided.")

    raw_token = secrets.token_urlsafe(32)
    invitation.token_hash = hash_token(raw_token)
    invitation.expires_at = timezone.now() + timezone.timedelta(
        days=INVITATION_LIFETIME_DAYS
    )
    invitation.status = ParentInvitation.Status.APPROVED
    invitation.approved_by = reviewer
    invitation.approved_at = timezone.now()
    invitation.reviewed_at = invitation.approved_at
    invitation.save(
        update_fields=[
            "token_hash",
            "expires_at",
            "status",
            "approved_by",
            "approved_at",
            "reviewed_at",
            "updated_at",
        ]
    )

    try:
        record_audit(
            action="update",
            old_instance=invitation,
            new_instance=invitation,
            user=reviewer,
        )
    except Exception:
        logger.exception("PARENT_INVITATION audit record failed (invitation still issued)")

    send_invitation_email(invitation, raw_token)
    return invitation, raw_token


def reject_invitation(
    invitation: ParentInvitation, *, reviewer: User, note: str = ""
) -> ParentInvitation:
    """Close a nomination without issuing anything."""
    invitation.status = ParentInvitation.Status.REJECTED
    invitation.reviewed_at = timezone.now()
    invitation.review_note = note
    invitation.save(
        update_fields=["status", "reviewed_at", "review_note", "updated_at"]
    )
    try:
        record_audit(
            action="update",
            old_instance=invitation,
            new_instance=invitation,
            user=reviewer,
        )
    except Exception:
        logger.exception("PARENT_INVITATION audit record failed (nomination still closed)")
    return invitation


def accept_invitation(
    *,
    raw_token: str,
    password: str,
) -> tuple[User, ParentStudentLink] | None:
    """
    Redeem an invitation: create the parent account and the child link.

    Returns the user and the link, or ``None`` when the token is unknown,
    already used or expired.
    """
    if not raw_token:
        return None

    invitation = ParentInvitation.objects.filter(
        token_hash=hash_token(raw_token)
    ).select_related("student").first()
    if invitation is None or invitation.status != ParentInvitation.Status.APPROVED:
        return None
    if invitation.expires_at and invitation.expires_at <= timezone.now():
        invitation.status = ParentInvitation.Status.EXPIRED
        invitation.save(update_fields=["status", "updated_at"])
        return None

    if User.objects.filter(email__iexact=invitation.email).exists():
        raise ValueError("An account already exists for that address.")

    with transaction.atomic():
        user = User(
            email=invitation.email,
            username="",
            first_name=invitation.full_name.split(" ")[0][:150],
            last_name=(
                " ".join(invitation.full_name.split(" ")[1:])[:150]
                if " " in invitation.full_name
                else ""
            ),
            role=User.Role.PARENT,
            is_active=True,
            must_change_password=False,
        )
        user.set_password(password)
        user.save()

        profile = ParentProfile.objects.create(
            user=user,
            relationship_to_student=invitation.relationship,
        )
        link = ParentStudentLink.objects.create(
            parent=profile, student=invitation.student
        )

        invitation.status = ParentInvitation.Status.ACCEPTED
        invitation.reviewed_at = timezone.now()
        invitation.save(update_fields=["status", "reviewed_at", "updated_at"])

    try:
        record_audit(action="create", instance=user)
        record_audit(
            action="update",
            old_instance=invitation,
            new_instance=invitation,
            user=user,
        )
    except Exception:
        logger.exception("PARENT_INVITATION audit record failed (account still created)")

    return user, link


def invitation_url(raw_token: str) -> str:
    base = settings.AEGIS_FRONTEND_URL.rstrip("/")
    return f"{base}/accept-invitation?token={raw_token}"


def send_invitation_email(invitation: ParentInvitation, raw_token: str) -> bool:
    """Mail the invitation link."""
    subject = f"{SCHOOL_NAME} — your parent account invitation"
    body = (
        f"Hello {invitation.full_name},\n\n"
        f"{invitation.student} has asked for you to have an AEGIS parent "
        "account, and the school has approved it. Open the link below to set "
        "a password and see your child's academic record.\n\n"
        f"{invitation_url(raw_token)}\n\n"
        f"The link stops working in {INVITATION_LIFETIME_DAYS} days and can "
        "only be used once.\n\n"
        f"— {SCHOOL_NAME}"
    )
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [invitation.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Parent invitation email could not be sent")
        return False
    return True
