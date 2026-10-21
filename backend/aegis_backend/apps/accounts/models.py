import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.db.models import Q

from .managers import UserManager
from core.models import UUIDModel, TimestampedModel


class User(AbstractUser):
    """
    Custom User model for AEGIS.

    Uses email as the primary identifier.
    Role-based access control via the 'role' field.
    """

    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        PARENT = "parent", "Parent"
        FACULTY = "faculty", "Faculty"
        GUIDANCE = "guidance", "Guidance Counselor"
        ADMIN = "admin", "Administrator"

    objects = UserManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, blank=True, default="")
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices)
    profile_photo = models.ImageField(upload_to="profile_photos/", blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    language_preference = models.CharField(max_length=10, blank=True, null=True)
    privacy_policy_accepted = models.BooleanField(default=False)
    privacy_policy_accepted_at = models.DateTimeField(blank=True, null=True)
    must_change_password = models.BooleanField(
        default=False,
        help_text=(
            "True until the user completes the required initial "
            "password change (provisioned temporary credentials)."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name", "role"]

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "user"
        verbose_name_plural = "users"
        # Every role-scoped queryset in the project filters on
        # ``role`` ("student", "faculty", ...), and the account list the
        # administrator screen reads is ordered by creation date.
        indexes = [
            models.Index(fields=["role"], name="user_role_idx"),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    @property
    def full_name(self):
        return self.get_full_name()


class StudentProfile(TimestampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    student_id = models.CharField(max_length=20, unique=True, help_text="School-assigned student ID")
    grade_level = models.ForeignKey("academics.GradeLevel", on_delete=models.PROTECT, null=True, blank=True)
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, null=True, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    guardian_contact = models.CharField(max_length=255, blank=True, null=True)
    enrollment_date = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "student profile"
        verbose_name_plural = "student profiles"

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.student_id})"


class ParentProfile(TimestampedModel):
    class RelationshipType(models.TextChoices):
        MOTHER = "mother", "Mother"
        FATHER = "father", "Father"
        GUARDIAN = "guardian", "Guardian"
        OTHER = "other", "Other"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="parent_profile")
    relationship_to_student = models.CharField(max_length=20, choices=RelationshipType.choices)

    class Meta:
        verbose_name = "parent profile"
        verbose_name_plural = "parent profiles"

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.get_relationship_to_student_display()})"


class ParentStudentLink(UUIDModel):
    parent = models.ForeignKey(ParentProfile, on_delete=models.CASCADE, related_name="student_links")
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="parent_links")
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ("parent", "student")
        verbose_name = "parent-student link"
        verbose_name_plural = "parent-student links"

    def __str__(self):
        return f"{self.parent} -> {self.student}"


class FacultyProfile(TimestampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="faculty_profile")
    employee_id = models.CharField(max_length=20, unique=True, help_text="School-assigned employee ID")
    department = models.CharField(max_length=100, blank=True, null=True)
    is_adviser = models.BooleanField(default=False)
    advisory_section = models.ForeignKey(
        "academics.Section", on_delete=models.SET_NULL, null=True, blank=True, related_name="faculty_adviser"
    )

    class Meta:
        verbose_name = "faculty profile"
        verbose_name_plural = "faculty profiles"

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.employee_id})"


class GuidanceProfile(TimestampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="guidance_profile")
    employee_id = models.CharField(max_length=20, unique=True, help_text="School-assigned employee ID")
    specialization = models.CharField(max_length=100, blank=True, null=True)
    license_number = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = "guidance profile"
        verbose_name_plural = "guidance profiles"

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.employee_id})"


class AdminProfile(TimestampedModel):
    class AdminLevel(models.TextChoices):
        SUPERADMIN = "superadmin", "Super Admin"
        ADMIN = "admin", "Admin"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="admin_profile")
    admin_level = models.CharField(max_length=20, choices=AdminLevel.choices, default=AdminLevel.ADMIN)

    class Meta:
        verbose_name = "admin profile"
        verbose_name_plural = "admin profiles"

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.get_admin_level_display()})"


class ConsentRecordManager(models.Manager):
    def active(self):
        """Consents currently in force. A revoked consent stays on record."""
        return self.filter(revoked_at__isnull=True)


class ConsentRecord(TimestampedModel):
    """
    A family's permission for administrators to view a student's identifiable
    records (NFR-010, TC-ADM-17).

    NFR-010 reads *"Admins shall view student data in aggregated/anonymized
    form unless consent is given."* This is the "unless": one row saying the
    family of `student` permits identifiable viewing by administrators. Its
    absence is the default, and the default is anonymous - the grades endpoint
    withholds `student_name`/`student_id` for every student with no active row
    here.

    Two ways to grant, and the difference is provenance, not power:

    * a linked parent grants in-app (`granted_by` is that parent, `note` is
      empty), or
    * an administrator records a signed paper form received offline
      (`granted_by` is the administrator, `note` names the form on file).

    Revocation never deletes. `revoked_at`/`revoked_by` close the row so the
    history answers "who permitted what, when" after the fact - which is the
    only reason a consent table is worth having over a boolean on the profile.

    `created_at` is the grant time; no separate `granted_at` column, because
    two timestamps that can never differ are one timestamp with an alias.
    """

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="consent_records"
    )
    # PROTECT, not CASCADE: deleting a user must not silently erase the history
    # of what they permitted.
    granted_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="granted_consents"
    )
    note = models.TextField(
        blank=True,
        help_text="Provenance, e.g. the signed form on file. Required when an administrator records offline consent.",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revoked_consents",
    )

    objects = ConsentRecordManager()

    class Meta:
        verbose_name = "consent record"
        verbose_name_plural = "consent records"
        constraints = [
            # Exactly one live consent per student. History rows (revoked) may
            # accumulate freely.
            models.UniqueConstraint(
                fields=["student"],
                condition=Q(revoked_at__isnull=True),
                name="one_active_consent_per_student",
            ),
        ]

    def __str__(self):
        state = "active" if self.revoked_at is None else "revoked"
        return f"Consent for {self.student} ({state})"

    @property
    def is_active(self):
        return self.revoked_at is None


class PasswordResetToken(TimestampedModel):
    """
    A single-use password-reset token.

    The token itself is never stored. What is stored is its SHA-256 hash, so a
    database leak does not hand out password resets: the raw value exists only
    in the email that was sent.

    One live token per account. Issuing a new one closes the previous, so an
    older link in an old inbox cannot be used after a newer request. Using a
    token closes it too.

    The row is kept after it is used rather than deleted, so the audit trail
    can answer "a reset was requested for this account, and here is when it
    was redeemed" without the audit table having to hold credentials.
    """

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "password reset token"
        verbose_name_plural = "password reset tokens"
        indexes = [
            models.Index(fields=["user", "expires_at"], name="pwd_reset_user_time_idx"),
        ]

    def __str__(self):
        # Deliberately says nothing about the account or the token.
        return "Password reset token"

    @property
    def is_used(self):
        return self.used_at is not None

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()


class RegistrationRequest(TimestampedModel):
    """
    A student's request for an account.

    A request is not an account. It has no role, no permissions and no
    session: a student who registers has asked for access, and an
    administrator grants it. That separation is what keeps the role model
    intact — there is no code path from this table to a role.

    The password is hashed on submission, so a request never holds a
    plaintext password, and it is carried into the account only when an
    administrator approves.

    The email must be verified before an administrator spends time on it, so
    the request proves the applicant owns the address.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending verification"
        VERIFIED = "verified", "Verified, awaiting approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    email = models.EmailField()
    full_name = models.CharField(max_length=150)
    password_hash = models.CharField(max_length=128)
    student_code = models.CharField(
        max_length=20,
        blank=True,
        help_text="The student number from the school's records, if the applicant knows it.",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    verification_token_hash = models.CharField(max_length=64, unique=True)
    verification_expires_at = models.DateTimeField()
    reviewed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_registrations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        verbose_name = "registration request"
        verbose_name_plural = "registration requests"
        ordering = ["-created_at"]
        constraints = [
            # One live request per address. Approved and rejected requests stay
            # on record; they just stop blocking a new one.
            models.UniqueConstraint(
                fields=["email"],
                condition=Q(status__in=["pending", "verified"]),
                name="one_live_registration_per_email",
            ),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.status})"

    @property
    def is_verified(self):
        return self.status in (self.Status.VERIFIED, self.Status.APPROVED)


class ParentInvitation(TimestampedModel):
    """
    A parent's invitation to have an account.

    A parent's account reveals a child's grades, attendance, guidance records
    and behavioural notes, so it is not something a stranger may ask for
    and have. The invitation is the school-side fact: a student may
    nominate a parent, but an administrator approves the nomination and
    issues the invitation, and only then does the parent get a link.

    The token is issued at approval, not at nomination, so the link that
    reaches the parent's inbox is the one the school approved.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved, invitation sent"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    email = models.EmailField()
    full_name = models.CharField(max_length=150)
    relationship = models.CharField(
        max_length=20,
        choices=ParentProfile.RelationshipType.choices,
        default=ParentProfile.RelationshipType.OTHER,
    )
    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.CASCADE,
        related_name="parent_invitations",
    )
    nominated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="nominated_parent_invitations",
        help_text="The student who nominated this parent, when a student did.",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    token_hash = models.CharField(max_length=64, null=True, blank=True, unique=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_parent_invitations",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        verbose_name = "parent invitation"
        verbose_name_plural = "parent invitations"
        ordering = ["-created_at"]
        constraints = [
            # One live invitation per address for the same child. An accepted
            # or rejected invitation stays on record and stops blocking.
            models.UniqueConstraint(
                fields=["email", "student"],
                condition=Q(status__in=["pending", "approved"]),
                name="one_live_parent_invitation_per_child",
            ),
        ]

    def __str__(self):
        return f"{self.full_name} for {self.student} ({self.status})"
