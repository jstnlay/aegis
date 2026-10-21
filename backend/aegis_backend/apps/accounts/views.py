import logging

from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView as _BaseTokenRefreshView,
)

from apps.audit.hooks import audit_account_access_change, audit_successful_logout
from apps.audit.services import record_audit
from core.permissions import IsAdminUser
from core.throttling import (
    LoginRateThrottle,
    ParentInvitationRateThrottle,
    PasswordChangeRateThrottle,
    PasswordForgotRateThrottle,
    PasswordResetRateThrottle,
    RegistrationRateThrottle,
    TokenRefreshRateThrottle,
)

from .models import (
    ConsentRecord,
    FacultyProfile,
    ParentInvitation,
    RegistrationRequest,
    User,
)
from .parent_invitation import (
    accept_invitation,
    approve_invitation,
    nominate_parent,
    reject_invitation,
)
from .registration import (
    GENERIC_REGISTRATION_ANSWER,
    approve_registration,
    reject_registration,
    submit_registration,
    verify_registration,
)
from .password_reset import (
    GENERIC_RESET_ANSWER,
    SET_PASSWORD_LINK_MINUTES,
    close_reset_token,
    issue_reset_token,
    redeem_reset_token,
    revoke_sessions,
    send_reset_email,
    send_set_password_email,
)
from .serializers import (
    AegisTokenObtainPairSerializer,
    AdminParentInvitationSerializer,
    AdminRegistrationSerializer,
    AdminUserUpdateSerializer,
    ConsentRecordSerializer,
    FacultyProfileListSerializer,
    LogoutSerializer,
    PasswordChangeSerializer,
    PasswordForgotSerializer,
    ParentInvitationAcceptSerializer,
    ParentInvitationSerializer,
    PasswordResetSerializer,
    RegistrationApprovalSerializer,
    RegistrationRejectionSerializer,
    RegistrationRequestSerializer,
    UserSerializer,
    UserCreateSerializer,
    UserProfileSerializer,
)

logger = logging.getLogger(__name__)


class LoginView(TokenObtainPairView):
    """JWT login, rate-limited per client IP (SEC-002).

    Adds the PH8.7 ``must_change_password`` onboarding flag to the
    standard token-pair response for provisioned accounts.
    """

    serializer_class = AegisTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]


class TokenRefreshView(_BaseTokenRefreshView):
    """JWT refresh, rate-limited per client IP (SEC-002)."""

    throttle_classes = [TokenRefreshRateThrottle]


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/ — refresh-token revocation (SEC-003).

    Requires an authenticated user and their own current refresh token.
    The token is blacklisted via rest_framework_simplejwt.token_blacklist,
    so it can never be used (or rotated) again. Every failure mode —
    malformed, expired, already-blacklisted, or another user's token —
    gets the same generic 400 with no token reflection.

    Note: blacklisting a refresh token does not invalidate access tokens
    already issued from it; they remain valid until their own short
    expiry (JWTAuthentication does not consult the blacklist).
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
        except TokenError:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=400,
            )
        # Ownership check: the caller may only revoke their own token.
        # Same generic response as invalid tokens — no oracle, no leak.
        owner_id = str(getattr(request.user, jwt_settings.USER_ID_FIELD))
        if str(token.payload.get(jwt_settings.USER_ID_CLAIM)) != owner_id:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=400,
            )
        token.blacklist()
        audit_successful_logout()
        return Response({"detail": "Successfully logged out."})


# Administrator authority is role-based across this project (NFR-011): every
# other administrator area - academics writes, attendance, analytics, the audit
# log - gates on ``core.permissions.IsAdminUser``, which tests ``role == "admin"``.
#
# These three views previously used ``rest_framework.permissions.IsAdminUser``,
# which gates on the ``is_staff`` flag instead. The two are not equivalent: an
# account provisioned by ``provision_qa_accounts`` (and by any ``create_user``
# call) is created with ``is_staff=False``, so ``admin.qa`` held ``role="admin"``
# and was still rejected with HTTP 403 on the user-administration endpoints it is
# the administrator of. ``is_staff`` is retained for its separate purpose - it
# gates the Django admin site (apps/accounts/admin.py) and nothing in this API.
class UserListView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]


class FacultyProfileListView(generics.ListAPIView):
    """
    GET /api/v1/accounts/faculty-profiles/ - administrator faculty roster.

    PH11.10. `SubjectAssignment.faculty` is required by the serializer and the
    academic structure screen has to be able to populate it, but no
    administrator-facing route listed faculty before this one.

    Ordered by surname then forename so the picker is stable between loads
    rather than following primary-key insertion order. Read-only and
    administrator-only, matching `UserListView`.
    """

    serializer_class = FacultyProfileListSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return (
            FacultyProfile.objects.select_related("user")
            .order_by("user__last_name", "user__first_name", "employee_id")
        )


class UserDetailView(generics.RetrieveUpdateAPIView):
    """
    GET/PATCH /api/v1/accounts/users/{id}/ — administrator only.

    PH11 (TC-ADM-10, FR-036, NFR-011): role-based access is assignable
    from the API instead of only through the Django admin site, which is
    what the Cycle-2 log recorded as "Not implemented".

    The one guard the write needs is self-lockout: an administrator cannot
    change their own role or deactivate their own account. Locking yourself
    out through this API has no self-service recovery, so the change is
    refused rather than accepted and regretted. There is deliberately no
    "last administrator" guard — an authenticated administrator is always
    an active one, so acting on any *other* account can never leave AEGIS
    without an administrator.

    Every change writes one audit event carrying the acting administrator,
    the target account and a ``role``/``is_active`` diff. Nothing else about
    an account is writable here: only GET and PATCH are routed (PUT would
    otherwise reach the read-oriented ``UserSerializer``), and profile fields
    stay with the account's own ``/accounts/me/`` serializer (SEC-001).
    """

    queryset = User.objects.all()
    permission_classes = [IsAdminUser]
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return AdminUserUpdateSerializer
        return UserSerializer

    def patch(self, request, *args, **kwargs):
        target = self.get_object()

        if target.pk == request.user.pk:
            return Response(
                {"detail": "You cannot change your own role or account status."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        write_serializer = self.get_serializer(
            target, data=request.data, partial=True
        )
        write_serializer.is_valid(raise_exception=True)

        before = User.objects.get(pk=target.pk)
        updated = write_serializer.save()

        if (updated.role, updated.is_active) != (before.role, before.is_active):
            audit_account_access_change(before, updated)

        return Response(UserSerializer(updated).data)


class UserCreateView(generics.CreateAPIView):
    """
    POST /api/v1/accounts/users/create/ - create an account.

    Without a password, the account is created with an unusable password and
    a one-time set-password link is emailed to the person, so no
    administrator chooses a colleague's password and no password travels by
    email. With a password, the account is created as before.
    """

    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [IsAdminUser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        if not (request.data or {}).get("password"):
            raw_token, _record = issue_reset_token(
                user, lifetime_minutes=SET_PASSWORD_LINK_MINUTES
            )
            send_set_password_email(user, raw_token)
            try:
                record_audit(action="create", instance=user, user=request.user)
            except Exception:
                logger.exception("ACCOUNT_CREATED audit record failed")

        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class CurrentUserView(generics.RetrieveUpdateAPIView):
    """
    GET/PATCH /api/v1/accounts/me/ — own profile only.

    Uses UserProfileSerializer so self-service writes are limited to
    legitimate profile fields; role/is_active/email/username remain
    server-controlled (SEC-001).
    """

    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class PasswordChangeView(APIView):
    """
    POST /api/v1/accounts/password/change/ — self-service password change.

    Verifies the current password, validates the new password against the
    standard Django validators, and clears the PH8.7 initial-password
    state when present.  This is the ONLY route a provisioned account
    may use while ``must_change_password`` is set (enforced by the
    authentication gate in core/authentication.py).

    Throttled per account (SEC-002): the endpoint checks the *current*
    password, so whoever holds a stolen access token could otherwise
    guess it as fast as the network allows.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [PasswordChangeRateThrottle]

    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password changed."})


class ConsentListView(generics.ListCreateAPIView):
    """
    Family consent records (NFR-010, TC-ADM-17).

    Admins list everything - oversight is the reason the table exists. Parents
    list only their own linked children's rows; every other role has no
    business here. Creation is the grant: a linked parent granting for their
    own child, or an administrator recording a signed paper form (which must
    name the form - see the serializer).
    """

    serializer_class = ConsentRecordSerializer
    pagination_class = None

    def get_permissions(self):
        # Both actions share the same gate; the queryset below does the
        # scoping. `getattr` because this runs before `IsAuthenticated`, and
        # an anonymous user has no `role` to read.
        if getattr(self.request.user, "role", None) not in ("admin", "parent"):
            self.permission_denied(self.request)
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = ConsentRecord.objects.select_related(
            "student__user", "granted_by"
        ).order_by("-created_at")
        if self.request.user.role == "admin":
            return qs
        return qs.filter(
            student__parent_links__parent__user=self.request.user
        )

    def perform_create(self, serializer):
        serializer.save()


class ConsentRevokeView(generics.UpdateAPIView):
    """
    Withdraw a consent (NFR-010, TC-ADM-17).

    PATCH with an empty body. Revocation closes the row - it never deletes -
    so the history keeps answering "who permitted what, when". Only an
    administrator or a linked parent of the student may revoke; revoking an
    already-revoked row is a 400, not a silent no-op, because the caller asked
    for something that is already true and should know it.
    """

    serializer_class = ConsentRecordSerializer
    http_method_names = ["patch", "head", "options"]
    queryset = ConsentRecord.objects.all()

    def get_permissions(self):
        if getattr(self.request.user, "role", None) not in ("admin", "parent"):
            self.permission_denied(self.request)
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == "admin":
            return qs
        return qs.filter(
            student__parent_links__parent__user=self.request.user
        )

    def perform_update(self, serializer):
        record = serializer.instance
        if record.revoked_at is not None:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "This consent was already revoked "
                f"at {record.revoked_at.isoformat()}."
            )
        serializer.save(
            revoked_at=timezone.now(), revoked_by=self.request.user
        )


class PasswordForgotView(APIView):
    """
    POST /api/v1/accounts/password/forgot/ — request a reset link.

    The answer is the same whether or not the address belongs to an account,
    so this endpoint cannot be used to find out who has one. The throttle
    bounds how much mail a stranger can make the school send.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordForgotRateThrottle]

    def post(self, request):
        serializer = PasswordForgotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        user = (
            User.objects.filter(email__iexact=email, is_active=True).first()
        )
        if user is not None:
            raw_token, record = issue_reset_token(user)
            try:
                record_audit(action="create", instance=record, user=user)
            except Exception:
                logger.exception("PASSWORD_RESET_REQUEST audit record failed")
            send_reset_email(user, raw_token)

        return Response({"detail": GENERIC_RESET_ANSWER}, status=status.HTTP_202_ACCEPTED)


class PasswordResetView(APIView):
    """
    POST /api/v1/accounts/password/reset/ — redeem a reset link.

    The token is the credential: the account is whatever the token points at,
    so a request cannot name a different one. On success the password is set,
    the onboarding flag is cleared, and every outstanding refresh token for
    that account is revoked — a reset exists because a session may be
    stolen, and leaving that session alive would defeat the point.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record = redeem_reset_token(serializer.validated_data["token"])
        if record is None:
            return Response(
                {"detail": "This reset link is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = record.user
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])

        close_reset_token(record)
        revoke_sessions(user)

        return Response({"detail": "Password reset. You can sign in now."})


class RegistrationSubmitView(APIView):
    """
    POST /api/v1/accounts/registrations/ - ask for a student account.

    The answer is the same whether the address is new, already registered
    or unknown, so the endpoint cannot be used to find out who has an
    account. A request is not an account: it carries no role and no
    permissions, and only an administrator turns it into one.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegistrationRateThrottle]

    def post(self, request):
        serializer = RegistrationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        request_row, _raw_token = submit_registration(
            email=data["email"],
            full_name=data["full_name"],
            password=data["password"],
            student_code=data.get("student_code", ""),
        )
        if request_row is not None:
            try:
                record_audit(action="create", instance=request_row)
            except Exception:
                logger.exception("REGISTRATION audit record failed")

        return Response(
            {"detail": GENERIC_REGISTRATION_ANSWER},
            status=status.HTTP_202_ACCEPTED,
        )


class RegistrationVerifyView(APIView):
    """
    GET /api/v1/accounts/registrations/verify/?token=...

    Confirms that the applicant owns the address. After this the request
    waits for an administrator.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegistrationRateThrottle]

    def get(self, request):
        raw_token = request.query_params.get("token", "")
        registration = verify_registration(raw_token)
        if registration is None:
            return Response(
                {"detail": "This verification link is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"status": registration.status})


class AdminRegistrationListView(generics.ListAPIView):
    """
    GET /api/v1/admin/registrations/ - the review queue.

    Administrator only, like every other administrator surface: the queue
    holds names and addresses, and NFR-010 keeps identifiable student data
    out of the wrong hands.
    """

    serializer_class = AdminRegistrationSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = RegistrationRequest.objects.select_related("reviewed_by").all()
        status_filter = self.request.query_params.get("status")
        if status_filter == "pending":
            qs = qs.filter(
                status__in=[
                    RegistrationRequest.Status.PENDING,
                    RegistrationRequest.Status.VERIFIED,
                ]
            )
        return qs


class AdminRegistrationApproveView(APIView):
    """
    POST /api/v1/admin/registrations/{id}/approve/

    The only path from a request to an account. It creates the user and
    the student profile in one transaction, because in this system a
    student profile belongs to a user: they are one record.
    """

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        serializer = RegistrationApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        registration = RegistrationRequest.objects.filter(pk=pk).first()
        if registration is None:
            return Response(
                {"detail": "No registration request matches the given id."},
                status=status.HTTP_404_NOT_FOUND,
            )

        section = None
        if data.get("section_id"):
            from apps.academics.models import Section

            section = Section.objects.filter(pk=data["section_id"]).first()
            if section is None:
                return Response(
                    {"detail": "No section matches the given id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            approve_registration(
                registration, reviewer=request.user, section=section
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "detail": "Registration approved. The account can sign in now.",
                "email": registration.email,
            }
        )


class AdminRegistrationRejectView(APIView):
    """POST /api/v1/admin/registrations/{id}/reject/ - close a request."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        serializer = RegistrationRejectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        registration = RegistrationRequest.objects.filter(pk=pk).first()
        if registration is None:
            return Response(
                {"detail": "No registration request matches the given id."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if registration.status == RegistrationRequest.Status.APPROVED:
            return Response(
                {"detail": "This request was already approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reject_registration(
            registration,
            reviewer=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response({"detail": "Registration rejected."})


class ParentInvitationCreateView(APIView):
    """
    POST /api/v1/accounts/parent-invitations/ - nominate a parent.

    A student nominates a parent for themselves; an administrator may
    nominate one for any child by student number. Either way this is a
    request: an administrator still approves it, and only the parent, on
    accepting the invitation, gets an account.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ParentInvitationRateThrottle]

    def post(self, request):
        serializer = ParentInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        student = None
        if request.user.role == "student":
            student = getattr(request.user, "student_profile", None)
        if student is None and data.get("student_code"):
            from apps.accounts.models import StudentProfile

            student = StudentProfile.objects.filter(
                student_id=data["student_code"]
            ).first()

        if student is None:
            return Response(
                {
                    "detail": "A student number is required to nominate a parent."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        invitation, _token = nominate_parent(
            email=data["email"],
            full_name=data["full_name"],
            relationship=data["relationship"],
            student=student,
            nominated_by=request.user,
        )
        if invitation is not None:
            try:
                record_audit(action="create", instance=invitation, user=request.user)
            except Exception:
                logger.exception("PARENT_INVITATION audit record failed")

        return Response(
            {
                "detail": "The nomination was received. The school will review it.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ParentInvitationAcceptView(APIView):
    """
    POST /api/v1/accounts/parent-invitations/accept/ - redeem an invitation.

    The token is the credential: the account and the child are whatever the
    invitation names, so a request cannot choose either.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ParentInvitationRateThrottle]

    def post(self, request):
        serializer = ParentInvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            created = accept_invitation(
                raw_token=data["token"], password=data["password"]
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if created is None:
            return Response(
                {"detail": "This invitation link is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, _link = created
        return Response(
            {"detail": "Your account is ready. You can sign in now.", "email": user.email}
        )


class AdminParentInvitationListView(generics.ListAPIView):
    """GET /api/v1/accounts/admin/parent-invitations/ - the nomination queue."""

    serializer_class = AdminParentInvitationSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = ParentInvitation.objects.select_related(
            "student__user", "nominated_by"
        ).all()
        if self.request.query_params.get("status") == "pending":
            qs = qs.filter(
                status__in=[
                    ParentInvitation.Status.PENDING,
                    ParentInvitation.Status.APPROVED,
                ]
            )
        return qs


class AdminParentInvitationApproveView(APIView):
    """POST /api/v1/accounts/admin/parent-invitations/{id}/approve/."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        invitation = ParentInvitation.objects.filter(pk=pk).first()
        if invitation is None:
            return Response(
                {"detail": "No parent invitation matches the given id."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            approve_invitation(invitation, reviewer=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Invitation issued."})


class AdminParentInvitationRejectView(APIView):
    """POST /api/v1/accounts/admin/parent-invitations/{id}/reject/."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        invitation = ParentInvitation.objects.filter(pk=pk).first()
        if invitation is None:
            return Response(
                {"detail": "No parent invitation matches the given id."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if invitation.status == ParentInvitation.Status.ACCEPTED:
            return Response(
                {"detail": "This invitation was already accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        note = (request.data or {}).get("note", "")
        reject_invitation(invitation, reviewer=request.user, note=note)
        return Response({"detail": "Nomination rejected."})
