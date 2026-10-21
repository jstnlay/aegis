from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.conf import settings
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.audit.hooks import audit_successful_login

from .models import (
    ConsentRecord,
    FacultyProfile,
    ParentInvitation,
    ParentStudentLink,
    RegistrationRequest,
    User,
)


class AegisTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Login serializer (PH8.7 onboarding signal).

    Returns the standard JWT pair from SimpleJWT unchanged, plus a single
    additive top-level boolean that tells the client whether the account
    is still on its provisioned temporary credential and therefore must
    complete an initial password change before normal access.

    PH10.7: after successful token issuance, records a LOGIN audit event
    with the authenticated user, client IP, and user-agent.

    Session length (document element 3, "Remember Me")
    -------------------------------------------------
    Two session lengths, from one setting pair:

    - without ``remember_me``: an idle session. The access token and the
      refresh token both live 15 minutes, so a browser left alone is signed
      out after a quarter of an hour. The client refreshes silently on a
      401, so an active user never notices.
    - with ``remember_me``: the refresh token lives a day. The access token
      still lives 15 minutes — a long session must never mean a long-lived
      access token.

    The flag is a session-lifetime choice and nothing more. It grants no
    extra permission, and it is not stored on the account: the lifetime is
    carried by the token itself, so it cannot be changed after the fact.
    """

    remember_me = serializers.BooleanField(required=False, default=False)

    @property
    def _remember_me(self) -> bool:
        request = self.context.get("request")
        data = getattr(request, "data", None) or {}
        return bool(data.get("remember_me", False))

    def get_token(self, user):
        token = super().get_token(user)
        if not self._remember_me:
            token.set_exp(
                lifetime=settings.SIMPLE_JWT["SESSION_REFRESH_LIFETIME"]
            )
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        audit_successful_login(self.user)
        data["must_change_password"] = bool(self.user.must_change_password)
        data["remember_me"] = self._remember_me
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
    """
    Administrator account creation.

    The password is optional. Without one, the account is created with an
    unusable password and a one-time set-password link is emailed to the
    person, so no administrator ever chooses a colleague's password and no
    password travels by email. With one, the account is created as before —
    an administrator may still set a password directly.
    """

    password = serializers.CharField(
        write_only=True, min_length=8, required=False, allow_blank=True, default=""
    )

    class Meta:
        model = User
        fields = (
            "email", "username", "first_name", "last_name",
            "role", "password",
        )

    def create(self, validated_data):
        password = validated_data.pop("password", "") or ""
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            # The account cannot sign in until the person sets a password
            # from the link the administrator's request triggers.
            user.set_unusable_password()
            user.must_change_password = True
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


class PasswordForgotSerializer(serializers.Serializer):
    """
    A request for a password reset link.

    The only field is the address. The response never depends on whether the
    address belongs to an account, so this endpoint cannot be used to find out
    who has one.
    """

    email = serializers.EmailField()


class PasswordResetSerializer(serializers.Serializer):
    """
    Redemption of a password reset link.

    The token is the credential; the account is whatever the token points at,
    so a request cannot name a different account.
    """

    token = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "The two passwords do not match."}
            )
        return attrs

    def validate_new_password(self, value):
        user = self.context.get("user")
        try:
            validate_password(value, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(" ".join(exc.messages))
        return value


class RegistrationRequestSerializer(serializers.Serializer):
    """
    A student's request for an account.

    There is no role field, and no field that could become one. The role is
    granted by an administrator at approval, from the account side, never
    from here.
    """

    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    student_code = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "The two passwords do not match."}
            )
        return attrs

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(" ".join(exc.messages))
        return value


class AdminRegistrationSerializer(serializers.ModelSerializer):
    """
    A registration request, as the administrator sees it.

    The password hash is never exposed: the administrator grants an account,
    they do not read a credential.
    """

    reviewed_by_name = serializers.CharField(
        source="reviewed_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = RegistrationRequest
        fields = (
            "id",
            "full_name",
            "email",
            "student_code",
            "status",
            "created_at",
            "reviewed_at",
            "reviewed_by_name",
            "review_note",
        )
        read_only_fields = fields


class RegistrationApprovalSerializer(serializers.Serializer):
    """
    An administrator's decision to approve a request.

    The section is the administrator's to name, not the applicant's: the
    student said who they are, the school says where they sit.
    """

    section_id = serializers.UUIDField(required=False, allow_null=True)
    grade_level_id = serializers.UUIDField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class RegistrationRejectionSerializer(serializers.Serializer):
    """An administrator's decision to close a request without granting it."""

    note = serializers.CharField(required=False, allow_blank=True, default="")


class ParentInvitationSerializer(serializers.Serializer):
    """
    A nomination of a parent for a child.

    A student nominates a parent for themselves; an administrator may
    nominate one for any child by student number. There is no role field
    and no way to become a parent from this payload: the account is
    created only when the parent accepts an invitation the school issued.
    """

    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    relationship = serializers.ChoiceField(
        choices=[
            ("mother", "Mother"),
            ("father", "Father"),
            ("guardian", "Guardian"),
            ("other", "Other"),
        ],
        default="other",
    )
    student_code = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )


class ParentInvitationAcceptSerializer(serializers.Serializer):
    """Redemption of a parent invitation."""

    token = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "The two passwords do not match."}
            )
        return attrs

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(" ".join(exc.messages))
        return value


class AdminParentInvitationSerializer(serializers.ModelSerializer):
    """A parent invitation, as the administrator sees it."""

    student_name = serializers.CharField(
        source="student.user.get_full_name", read_only=True, default=None
    )
    student_code = serializers.CharField(
        source="student.student_id", read_only=True, default=None
    )
    nominated_by_name = serializers.CharField(
        source="nominated_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = ParentInvitation
        fields = (
            "id",
            "full_name",
            "email",
            "relationship",
            "status",
            "student_name",
            "student_code",
            "nominated_by_name",
            "created_at",
            "reviewed_at",
            "review_note",
        )
        read_only_fields = fields
