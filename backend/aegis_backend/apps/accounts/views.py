from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView as _BaseTokenRefreshView,
)

from apps.audit.hooks import audit_successful_logout
from core.throttling import LoginRateThrottle, TokenRefreshRateThrottle

from .models import User
from .serializers import (
    AegisTokenObtainPairSerializer,
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


class UserListView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]


class UserDetailView(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]


class UserCreateView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.IsAdminUser]


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
