from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.audit.hooks import audit_successful_login

from .models import ConsentRecord, FacultyProfile, ParentStudentLink, User


class AegisTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Login serializer (PH8.7 onboarding signal).

    Returns the standard JWT pair from SimpleJWT unchanged, plus a single
    additive top-level boolean that tells the client whether the account
    is still on its provisioned temporary credential and therefore must
    complete an initial password change before normal access.

    PH10.7: after successful token issuance, records a LOGIN audit event
    with the authenticated user, client IP, and user-agent.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        audit_successful_login(self.user)
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


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """
    Administrator write for PATCH /api/v1/accounts/users/{id}/ (PH11).

    Deliberately narrow: exactly the two fields that constitute role-based
    access — which role the account holds (FR-036) and whether it can still
    sign in. Everything else about an account still goes through its own
    owner's ``/accounts/me/`` serializer, so this route cannot be used to
    edit someone's name, contact details, or identity.

    SEC-001 is untouched: it governs *self*-service writes, and
    ``/accounts/me/`` keeps ``role`` and ``is_active`` read-only there. This
    is a separate, administrator-gated surface.
    """

    class Meta:
        model = User
        fields = ("role", "is_active")


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Self-service serializer for GET/PATCH /api/v1/accounts/me/.

    Writable: genuine profile fields only — names, contact details and
    language preference, matching the specification's own-profile scope.

    Server-controlled (read-only): the login identity (email is the
    USERNAME_FIELD, username defaults server-side) and account state
    (role, is_active). Role/status changes are administrator operations
    performed through ``PATCH /api/v1/accounts/users/{id}/`` (PH11) or the
    Django admin site, never through self-service (SEC-001 remediation).
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


class FacultyProfileListSerializer(serializers.ModelSerializer):
    """
    Read-only faculty roster for GET /api/v1/accounts/faculty-profiles/.

    PH11.10: `SubjectAssignment.faculty` is a required foreign key, but until
    now no administrator-facing route listed `FacultyProfile`, so the academic
    structure screen could not populate the picker and every assignment create
    was rejected with a 400 on a field the form did not offer.

    Only what a picker needs is exposed: the profile id (the foreign key
    value), the display name and the employee id. No email, no phone number, no
    address — this is a teaching-assignment roster, not a personnel record, and
    NFR-010 keeps identifiable student data out of administrator views by the
    same reasoning applied here to staff.
    """

    name = serializers.SerializerMethodField()

    class Meta:
        model = FacultyProfile
        fields = ("id", "name", "employee_id")
        read_only_fields = ("id", "name", "employee_id")

    def get_name(self, obj) -> str:
        return obj.user.get_full_name()


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


class ConsentRecordSerializer(serializers.ModelSerializer):
    """
    A family consent record (NFR-010, TC-ADM-17).

    `student` is writable on create and read-only after: a consent is about
    one student, and moving it to another would rewrite history. `granted_by`
    is never in the payload - it is the request's user, so the record always
    names who actually clicked. Revocation is a separate endpoint, not a field
    edit, for the same reason: closing a consent is an event, not a correction.
    """

    student_name = serializers.CharField(
        source="student.user.full_name", read_only=True
    )
    granted_by_email = serializers.EmailField(
        source="granted_by.email", read_only=True
    )
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = ConsentRecord
        fields = (
            "id",
            "student",
            "student_name",
            "granted_by_email",
            "note",
            "is_active",
            "revoked_at",
            "created_at",
        )
        read_only_fields = (
            "id",
            "student_name",
            "granted_by_email",
            "is_active",
            "revoked_at",
            "created_at",
        )

    def validate_student(self, student):
        request = self.context["request"]
        user = request.user
        if user.role == "admin":
            return student
        # A parent may only consent for a linked child. Anything else is a 400
        # here rather than a silent empty scope, because consenting for a
        # stranger's child is a mistake the caller should hear about.
        linked = ParentStudentLink.objects.filter(
            parent__user=user, student=student
        ).exists()
        if not linked:
            raise serializers.ValidationError(
                "Consent can only be granted for your own linked child."
            )
        return student

    def validate(self, attrs):
        request = self.context["request"]
        # An administrator recording a paper form must say which form. Without
        # provenance the row is an admin permitting themselves, which is the
        # one thing this table must never be able to mean. Create-only: the
        # revoke endpoint PATCHes with an empty body, and must not trip this.
        if (
            self.instance is None
            and request.user.role == "admin"
            and not (attrs.get("note") or "").strip()
        ):
            raise serializers.ValidationError(
                {
                    "note": (
                        "Recording offline consent requires naming the signed "
                        "form on file."
                    )
                }
            )
        student = attrs.get("student") or getattr(self.instance, "student", None)
        if (
            self.instance is None
            and student is not None
            and ConsentRecord.objects.active().filter(student=student).exists()
        ):
            raise serializers.ValidationError(
                {
                    "student": (
                        "An active consent already exists for this student. "
                        "Revoke it before recording a new one."
                    )
                }
            )
        return attrs

    def create(self, validated_data):
        from django.db import transaction

        request = self.context["request"]
        # The `validate` check above is the user-facing path; this savepoint
        # keeps the database constraint as the backstop without poisoning the
        # outer transaction on the (raced) duplicate.
        try:
            with transaction.atomic():
                return ConsentRecord.objects.create(
                    granted_by=request.user, **validated_data
                )
        except IntegrityError:
            raise serializers.ValidationError(
                {
                    "student": (
                        "An active consent already exists for this student. "
                        "Revoke it before recording a new one."
                    )
                }
            )
