from rest_framework import serializers

from .models import User


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
    blacklisted server-side so it can never be exchanged for new tokens.
    The token value is write-only by nature of the endpoint: responses
    never echo it back.
    """

    refresh = serializers.CharField()
