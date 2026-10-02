"""
Focused tests for the shared DEV/QA account provisioning command.

Covers the safety contract of
``apps.accounts.management.commands.provision_qa_accounts``:

* a missing or weak QA_SHARED_PASSWORD aborts before any write;
* the five allowlisted QA accounts are created with the right role,
  is_active=True and must_change_password=False;
* rerunning never overwrites a password a tester already chose;
* a wrong role on an existing QA account is corrected, and only the role;
* non-QA users and @aegis.dev E2E users are untouched;
* only the five exact allowlisted emails are ever read or written;
* nothing sensitive (password, hash) reaches stdout, and no profile or
  academic records are fabricated.

The shared password used here is a throwaway value that exists only in this
test process. It is not the deployed secret and is not read from any file.
"""

import io
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.management.commands.provision_qa_accounts import (
    PASSWORD_ENV_VAR,
    QA_EMAILS,
)
from apps.accounts.models import (
    AdminProfile,
    FacultyProfile,
    GuidanceProfile,
    ParentProfile,
    StudentProfile,
)

User = get_user_model()

# Passes AUTH_PASSWORD_VALIDATORS (length, common-password, numeric) and is
# not similar to any user attribute because validation runs with user=None.
VALID_SHARED_PASSWORD = "QaShared-9xKq-2026"

EXPECTED_ROLES = {
    "guidance.qa@aegis.local": "guidance",
    "admin.qa@aegis.local": "admin",
    "faculty.qa@aegis.local": "faculty",
    "student.qa@aegis.local": "student",
    "parent.qa@aegis.local": "parent",
}


def run_provision(stdout=None):
    return call_command("provision_qa_accounts", stdout=stdout)


class QaAccountsTestCase(TestCase):
    """Base class that supplies the shared password to the command."""

    def setUp(self):
        patcher = mock.patch.dict(
            os.environ, {PASSWORD_ENV_VAR: VALID_SHARED_PASSWORD}, clear=False
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class MissingPasswordTest(QaAccountsTestCase):
    """1. A missing QA_SHARED_PASSWORD fails safely, writing nothing."""

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_absent_password_raises_and_creates_nothing(self):
        out = io.StringIO()
        with self.assertRaises(CommandError) as ctx:
            run_provision(stdout=out)

        self.assertIn(PASSWORD_ENV_VAR, str(ctx.exception))
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(out.getvalue(), "")

    def test_empty_password_raises_and_creates_nothing(self):
        with mock.patch.dict(os.environ, {PASSWORD_ENV_VAR: "   "}):
            with self.assertRaises(CommandError) as ctx:
                run_provision(stdout=io.StringIO())

        self.assertIn(PASSWORD_ENV_VAR, str(ctx.exception))
        self.assertEqual(User.objects.count(), 0)

    def test_weak_password_raises_and_creates_nothing(self):
        with mock.patch.dict(os.environ, {PASSWORD_ENV_VAR: "1234"}):
            with self.assertRaises(CommandError) as ctx:
                run_provision(stdout=io.StringIO())

        self.assertIn(PASSWORD_ENV_VAR, str(ctx.exception))
        self.assertEqual(User.objects.count(), 0)


class QaAccountCreationTest(QaAccountsTestCase):
    """2-5. The five exact QA accounts are created correctly."""

    def test_five_accounts_are_created(self):
        run_provision(stdout=io.StringIO())

        self.assertEqual(
            sorted(User.objects.values_list("email", flat=True)),
            sorted(EXPECTED_ROLES),
        )

    def test_allowlist_is_exactly_the_five_qa_emails(self):
        self.assertEqual(len(QA_EMAILS), 5)
        self.assertEqual(
            sorted(email for email, _role in QA_EMAILS), sorted(EXPECTED_ROLES)
        )
        self.assertEqual(dict(QA_EMAILS), EXPECTED_ROLES)
        for email, _role in QA_EMAILS:
            with self.subTest(email=email):
                self.assertEqual(email, email.lower())
                self.assertTrue(email.endswith(".qa@aegis.local"))

    def test_roles_are_assigned(self):
        run_provision(stdout=io.StringIO())

        for email, role in EXPECTED_ROLES.items():
            with self.subTest(email=email):
                self.assertEqual(User.objects.get(email=email).role, role)

    def test_must_change_password_is_false(self):
        run_provision(stdout=io.StringIO())

        for email in EXPECTED_ROLES:
            with self.subTest(email=email):
                user = User.objects.get(email=email)
                self.assertIs(user.must_change_password, False)

    def test_is_active_is_true_and_names_are_qa_labelled(self):
        run_provision(stdout=io.StringIO())

        for email, role in EXPECTED_ROLES.items():
            with self.subTest(email=email):
                user = User.objects.get(email=email)
                self.assertIs(user.is_active, True)
                self.assertEqual(user.first_name, "QA")
                self.assertTrue(user.last_name)
                self.assertEqual(
                    user.last_name, User.Role(role).label, "role-specific label"
                )

    def test_created_accounts_authenticate_with_the_shared_password(self):
        run_provision(stdout=io.StringIO())

        for email in EXPECTED_ROLES:
            with self.subTest(email=email):
                user = User.objects.get(email=email)
                self.assertTrue(user.check_password(VALID_SHARED_PASSWORD))
                # Hashed, not stored verbatim, but never printed.
                self.assertNotEqual(user.password, VALID_SHARED_PASSWORD)

    def test_no_profile_or_academic_records_are_created(self):
        run_provision(stdout=io.StringIO())

        self.assertEqual(StudentProfile.objects.count(), 0)
        self.assertEqual(FacultyProfile.objects.count(), 0)
        self.assertEqual(GuidanceProfile.objects.count(), 0)
        self.assertEqual(ParentProfile.objects.count(), 0)
        self.assertEqual(AdminProfile.objects.count(), 0)


class QaAccountIdempotencyTest(QaAccountsTestCase):
    """6-7. Reruns preserve existing passwords and fix only the role."""

    def test_existing_password_is_not_overwritten_on_rerun(self):
        chosen = "Tester-Chosen-4hdP!2026"
        User.objects.create_user(
            email="student.qa@aegis.local",
            password=chosen,
            first_name="QA",
            last_name="Student",
            role="student",
        )

        run_provision(stdout=io.StringIO())

        user = User.objects.get(email="student.qa@aegis.local")
        self.assertTrue(user.check_password(chosen))
        self.assertFalse(user.check_password(VALID_SHARED_PASSWORD))

    def test_rerun_over_fully_provisioned_state_changes_nothing(self):
        run_provision(stdout=io.StringIO())
        before = dict(User.objects.values_list("email", "password"))

        out = io.StringIO()
        run_provision(stdout=out)

        after = dict(User.objects.values_list("email", "password"))
        self.assertEqual(before, after)
        self.assertEqual(out.getvalue().count("CREATED"), 0)
        self.assertEqual(out.getvalue().count("UPDATED_ROLE"), 0)
        self.assertEqual(out.getvalue().count("EXISTS"), 5)

    def test_existing_wrong_role_is_corrected_without_touching_password(self):
        chosen = "Tester-Chosen-4hdP!2026"
        User.objects.create_user(
            email="faculty.qa@aegis.local",
            password=chosen,
            first_name="QA",
            last_name="Someone",
            role="student",
            must_change_password=True,
        )

        out = io.StringIO()
        run_provision(stdout=out)

        user = User.objects.get(email="faculty.qa@aegis.local")
        self.assertEqual(user.role, "faculty")
        self.assertTrue(user.check_password(chosen))
        # Report-only fields are left exactly as the tester left them.
        self.assertIs(user.must_change_password, True)
        self.assertEqual(user.first_name, "QA")
        self.assertEqual(user.last_name, "Someone")
        self.assertIn("UPDATED_ROLE", out.getvalue())

    def test_existing_inactive_account_is_reported_not_reactivated(self):
        User.objects.create_user(
            email="parent.qa@aegis.local",
            password=VALID_SHARED_PASSWORD,
            first_name="QA",
            last_name="Parent",
            role="parent",
            is_active=False,
        )

        out = io.StringIO()
        run_provision(stdout=out)

        user = User.objects.get(email="parent.qa@aegis.local")
        self.assertIs(user.is_active, False)
        self.assertIn("is_active=False", out.getvalue())


class NonQaUserSafetyTest(QaAccountsTestCase):
    """8-10. Only the five exact allowlisted emails are touched."""

    def _snapshot(self, user):
        return (user.email, user.role, user.is_active, user.password)

    def test_non_qa_users_remain_unchanged(self):
        staff = User.objects.create_superuser(
            email="admin@aegis.local",
            password="Staff-Chosen-7kLm!2026",
            first_name="Real",
            last_name="Admin",
            role="admin",
        )
        teacher = User.objects.create_user(
            email="j.delacruz@aegis.edu",
            password="Teacher-Chosen-2pQx!2026",
            first_name="Juan",
            last_name="Dela Cruz",
            role="faculty",
        )
        before = [self._snapshot(staff), self._snapshot(teacher)]

        run_provision(stdout=io.StringIO())

        staff.refresh_from_db()
        teacher.refresh_from_db()
        self.assertEqual([self._snapshot(staff), self._snapshot(teacher)], before)
        self.assertTrue(staff.check_password("Staff-Chosen-7kLm!2026"))
        self.assertTrue(teacher.check_password("Teacher-Chosen-2pQx!2026"))

    def test_e2e_users_remain_unchanged(self):
        e2e_users = [
            User.objects.create_user(
                email=email,
                password="E2e-Chosen-5zRt!2026",
                first_name="E2E",
                last_name="User",
                role=role,
            )
            for email, role in [
                ("e2e.admin@aegis.dev", "admin"),
                ("e2e.faculty@aegis.dev", "faculty"),
                ("e2e.guidance@aegis.dev", "guidance"),
                ("e2e.student@aegis.dev", "student"),
                ("e2e.parent@aegis.dev", "parent"),
            ]
        ]
        before = [self._snapshot(user) for user in e2e_users]

        run_provision(stdout=io.StringIO())

        after = []
        for user in e2e_users:
            user.refresh_from_db()
            after.append(self._snapshot(user))
            self.assertTrue(user.check_password("E2e-Chosen-5zRt!2026"))
        self.assertEqual(after, before)

    def test_near_miss_emails_are_not_matched_or_modified(self):
        """Exact-equality lookup: no wildcard, prefix, or suffix matching."""
        near_misses = [
            "student.qa@aegis.local.evil.test",
            "student.qa@aegis.dev",
            "studentqa@aegis.local",
            "student.qa@evil.local",
            "xstudent.qa@aegis.local",
            "QA.student@aegis.local",
        ]
        for index, email in enumerate(near_misses):
            User.objects.create_user(
                email=email,
                password="Nearmiss-Chosen-3vBn!2026",
                first_name="Near",
                last_name="Miss",
                role="student",
            )
        before = dict(User.objects.values_list("email", "password"))

        run_provision(stdout=io.StringIO())

        # Exactly the five QA accounts were added; every near-miss address kept
        # its stored password byte for byte.
        outside_qa = User.objects.exclude(email__in=EXPECTED_ROLES)
        self.assertEqual(dict(outside_qa.values_list("email", "password")), before)
        self.assertEqual(User.objects.count(), len(near_misses) + 5)
        for user in User.objects.filter(email__in=near_misses):
            with self.subTest(email=user.email):
                self.assertTrue(user.check_password("Nearmiss-Chosen-3vBn!2026"))


class QaOutputTest(QaAccountsTestCase):
    """Reporting is concise and never discloses the secret or its hash."""

    def test_reports_created_and_final_counts(self):
        out = io.StringIO()
        run_provision(stdout=out)
        text = out.getvalue()

        self.assertEqual(text.count("CREATED"), 5)
        self.assertIn("TOTAL created=5 exists=0 updated_role=0", text)
        for email in EXPECTED_ROLES:
            self.assertIn(email, text)

    def test_password_and_hash_are_never_printed(self):
        out = io.StringIO()
        run_provision(stdout=out)
        text = out.getvalue()

        self.assertNotIn(VALID_SHARED_PASSWORD, text)

        for email in EXPECTED_ROLES:
            with self.subTest(email=email):
                stored = User.objects.get(email=email).password
                self.assertNotIn(stored, text)
                for marker in ("pbkdf2_", "argon2", "bcrypt", "scrypt"):
                    self.assertNotIn(marker, text.lower())