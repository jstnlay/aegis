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
from core.permissions import IsAdminUser
from core.throttling import LoginRateThrottle, TokenRefreshRateThrottle

from .models import ConsentRecord, FacultyProfile, User
from .serializers import (
    AegisTokenObtainPairSerializer,
    AdminUserUpdateSerializer,
    ConsentRecordSerializer,
    FacultyProfileListSerializer,
    LogoutSerializer,
    PasswordChangeSerializer,
    UserSerializer,
    UserCreateSerializer,
    UserProfileSerializer,
)


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
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [IsAdminUser]


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
    """

    permission_classes = [permissions.IsAuthenticated]

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
