"""
Student registration: asking for an account, and being granted one.

The rule this module exists to protect: **a registration never grants a
role.** A student who registers has asked for access; an administrator
decides. So the request is its own table with its own lifecycle, and the
only way from it to a real account runs through the administrator's
approval, which is the same path the school's own provisioning uses.

The steps:

1. The student submits a request (name, email, password, student number).
2. They receive a verification link and follow it. Until they do, the
   request is not worth an administrator's time.
3. An administrator approves it, naming the section the student belongs to.
   Approval creates the account *and* the student profile together, because
   in this system those are one record: a student profile belongs to a user.
4. The student receives a link to sign in.

Every answer to a public request is the same, whether or not the address is
known, so the endpoint cannot be used to discover who has an account.
"""

import hashlib
import logging
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_audit

from .models import RegistrationRequest, User

logger = logging.getLogger(__name__)

#: How long a verification link stays usable.
VERIFICATION_LIFETIME_HOURS = 24

SCHOOL_NAME = "His Care Christian Institute"

#: The answer every registration request gets.
GENERIC_REGISTRATION_ANSWER = (
    "If that address can be registered, a verification link is on its way. "
    "Check your inbox, then an administrator will review the request."
)


def hash_token(raw_token: str) -> str:
    """The stored form of a verification token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def submit_registration(
    *,
    email: str,
    full_name: str,
    password: str,
    student_code: str = "",
) -> tuple[RegistrationRequest | None, str]:
    """
    Record a registration request and mail the verification link.

    Returns the request and the raw token, or ``(None, "")`` when the
    address already has a live request or an account. The caller answers
    the same way in every case.
    """
    existing_account = User.objects.filter(email__iexact=email).exists()
    if existing_account:
        return None, ""

    live_request = RegistrationRequest.objects.filter(
        email__iexact=email
    ).filter(
        status__in=[
            RegistrationRequest.Status.PENDING,
            RegistrationRequest.Status.VERIFIED,
        ]
    ).first()
    if live_request is not None:
        return None, ""

    from django.contrib.auth.hashers import make_password

    raw_token = secrets.token_urlsafe(32)
    request = RegistrationRequest.objects.create(
        email=email,
        full_name=full_name,
        password_hash=make_password(password),
        student_code=student_code,
        verification_token_hash=hash_token(raw_token),
        verification_expires_at=timezone.now()
        + timezone.timedelta(hours=VERIFICATION_LIFETIME_HOURS),
    )
    send_verification_email(request, raw_token)
    return request, raw_token


def verify_registration(raw_token: str) -> RegistrationRequest | None:
    """
    Mark a request verified. Returns the request, or ``None`` when the token
    is unknown, already used or expired.
    """
    if not raw_token:
        return None

    request = RegistrationRequest.objects.filter(
        verification_token_hash=hash_token(raw_token)
    ).first()
    if request is None or request.status != RegistrationRequest.Status.PENDING:
        return None
    if request.verification_expires_at <= timezone.now():
        return None

    request.status = RegistrationRequest.Status.VERIFIED
    request.save(update_fields=["status", "updated_at"])
    return request


def approve_registration(
    request: RegistrationRequest,
    *,
    reviewer: User,
    section=None,
) -> User:
    """
    Approve a verified request: create the account and the student profile.

    The account is created with the password the student chose, so
    ``must_change_password`` is not needed — they already have one. The
    student profile is created in the same transaction, because a student
    profile without its user is not a student: the two are one record here.

    Raises ``ValueError`` when the request is not in a state that can be
    approved, or when the address has since been taken.
    """
    if request.status not in (
        RegistrationRequest.Status.VERIFIED,
        RegistrationRequest.Status.PENDING,
    ):
        raise ValueError("This request has already been decided.")

    if User.objects.filter(email__iexact=request.email).exists():
        raise ValueError("An account already exists for that address.")

    with transaction.atomic():
        user = User(
            email=request.email,
            username="",
            first_name=request.full_name.split(" ")[0][:150],
            last_name=(
                " ".join(request.full_name.split(" ")[1:])[:150]
                if " " in request.full_name
                else ""
            ),
            role=User.Role.STUDENT,
            is_active=True,
            # The hash the student chose at registration is carried over as
            # it is. A hash cannot be reversed into the password, but it can
            # be copied, so the student signs in with the password they
            # chose and no plaintext password is ever stored.
            password=request.password_hash,
            must_change_password=False,
        )
        user.save()

        from apps.accounts.models import StudentProfile

        StudentProfile.objects.create(
            user=user,
            student_id=request.student_code or f"PENDING-{user.pk.hex[:8].upper()}",
            grade_level=getattr(section, "grade_level", None),
            section=section,
            enrollment_date=timezone.localdate(),
            is_active=True,
        )

        request.status = RegistrationRequest.Status.APPROVED
        request.reviewed_by = reviewer
        request.reviewed_at = timezone.now()
        request.save(
            update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"]
        )

    try:
        record_audit(action="create", instance=user, user=reviewer)
        record_audit(action="update", old_instance=request, new_instance=request, user=reviewer)
    except Exception:
        logger.exception("REGISTRATION audit record failed (account still created)")

    send_approval_email(user)
    return user


def reject_registration(
    request: RegistrationRequest, *, reviewer: User, note: str = ""
) -> RegistrationRequest:
    """Close a request without granting anything."""
    request.status = RegistrationRequest.Status.REJECTED
    request.reviewed_by = reviewer
    request.reviewed_at = timezone.now()
    request.review_note = note
    request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "updated_at",
        ]
    )
    try:
        record_audit(
            action="update", old_instance=request, new_instance=request, user=reviewer
        )
    except Exception:
        logger.exception("REGISTRATION audit record failed (request still closed)")
    return request


def verification_url(raw_token: str) -> str:
    base = settings.AEGIS_FRONTEND_URL.rstrip("/")
    return f"{base}/register?token={raw_token}"


def send_verification_email(request: RegistrationRequest, raw_token: str) -> bool:
    """Mail the verification link. Returns whether it was handed off."""
    subject = f"{SCHOOL_NAME} — verify your account request"
    body = (
        f"Hello {request.full_name},\n\n"
        "We received a request for an AEGIS account. Confirm that this is "
        "your address by opening the link below. After that an administrator "
        "reviews the request and creates your account.\n\n"
        f"{verification_url(raw_token)}\n\n"
        f"The link stops working in {VERIFICATION_LIFETIME_HOURS} hours.\n\n"
        f"— {SCHOOL_NAME}"
    )
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [request.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Registration verification email could not be sent")
        return False
    return True


def send_approval_email(user: User) -> bool:
    """Tell the student the account exists."""
    subject = f"{SCHOOL_NAME} — your account is ready"
    body = (
        f"Hello {user.get_full_name() or user.email},\n\n"
        "An administrator approved your account request. Sign in with the "
        "email address you registered and the password you chose. If you "
        "cannot sign in yet, the school will activate your enrolment first.\n\n"
        f"{settings.AEGIS_FRONTEND_URL.rstrip('/')}/login\n\n"
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
        logger.exception("Registration approval email could not be sent")
        return False
    return True
