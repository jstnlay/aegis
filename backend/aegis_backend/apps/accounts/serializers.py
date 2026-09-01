from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class AegisTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Login serializer (PH8.7 onboarding signal).

    Returns the standard JWT pair from SimpleJWT unchanged, plus a single
    additive top-level boolean that tells the client whether the account
    is still on its provisioned temporary credential and therefore must
    complete an initial password change before normal access.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        data["must_change_password"] = bool(self.user.must_change_password)
        return data


class UserSerializer(serializers.ModelSerializer):
    """
    Read-oriented user representation for administrative list/detail views.

    Privilege and account-state fields (role, is_active) and the login
    identity (email) are server-controlled: they can never be written
    through this serializer regardless of where it is reused (SEC-001).
    """

    class Meta:
        model = User
        fields = (
            "id", "email", "username", "first_name", "last_name",
            "role", "phone_number", "address", "is_active",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "email", "role", "is_active", "created_at", "updated_at",
        )


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Self-service serializer for GET/PATCH /api/v1/accounts/me/.

    Writable: genuine profile fields only — names, contact details and
    language preference, matching the specification's own-profile scope.

    Server-controlled (read-only): the login identity (email is the
    USERNAME_FIELD, username defaults server-side) and account state
    (role, is_active). Role/status changes are administrator operations
    performed via the Django admin site and the admin user-creation
    endpoint, never through self-service (SEC-001 remediation).
    """

    class Meta:
        model = User
        fields = (
            "id", "email", "username", "first_name", "last_name",
            "role", "phone_number", "address", "language_preference",
            "is_active", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "email", "username", "role",
            "is_active", "created_at", "updated_at",
        )


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = (
            "email", "username", "first_name", "last_name",
            "role", "password",
        )

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LogoutSerializer(serializers.Serializer):
    """
    Payload for POST /api/v1/auth/logout/ (SEC-003).

    The caller must present their own current refresh token; it is
    blacklisted server-side so it can never be used (or rotated) again.
    The token value is write-only by nature of the endpoint: responses
    never echo it back.
    """

    refresh = serializers.CharField()


class PasswordChangeSerializer(serializers.Serializer):
    """
    Authenticated self-service password change (PH8.7 onboarding).

    Requires the current password and a validated new password.  On
    success the password is stored as a Django hash and, if the account
    still carried the provisioned initial-password state, that state is
    cleared — the account becomes a normal role-based AEGIS account.

    The new password is write-only and never echoed in the response.
    """

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError(
                "The current password is incorrect."
            )
        return value

    def validate_new_password(self, value):
        user = self.context["request"].user
        try:
            validate_password(value, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(" ".join(exc.messages))
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        if user.must_change_password:
            user.must_change_password = False
        user.save()
        return user
