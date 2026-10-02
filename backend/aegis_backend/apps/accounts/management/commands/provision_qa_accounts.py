"""
Provision the five shared DEV/QA login accounts on the hosted backend.

The Render service is the shared DEV/QA environment, so QA needs a stable set
of one account per role that survives every redeploy. This command is
idempotent and runs automatically during the Render build, after
``manage.py migrate`` and before gunicorn starts.

Safety properties, all of which are covered by tests_qa_provisioning.py:

* The allowlist is the literal QA_EMAILS tuple below. Lookups are exact
  equality matches on ``email`` -- no wildcards, no prefixes, no case folding.
  A user whose email is not in the tuple can never be read or written.
* Only the five allowlisted accounts are ever written. Non-QA users and the
  ``@aegis.dev`` E2E accounts are not read, counted, or modified.
* The shared password comes from the QA_SHARED_PASSWORD environment variable
  and is never hardcoded, logged, or echoed. The password hash is never
  printed either.
* The password is validated with the project's configured
  AUTH_PASSWORD_VALIDATORS before any account is created, so a rejected
  secret leaves the database untouched.
* An existing QA account keeps whatever password a tester has already set:
  rerunning after a role fix or any other redeploy never resets it. Only a
  wrong ``role`` is corrected, and only for the allowlisted address.
* No profile, enrollment, grade, attendance, consultation, or risk records
  are created. This task provisions logins only.

Usage:
    python manage.py provision_qa_accounts
"""

import os

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

#: Name of the environment variable holding the shared QA password.
#: The value is supplied by the Render service environment; it is never
#: stored in source, .env.example, fixtures, tests, or documentation.
PASSWORD_ENV_VAR = "QA_SHARED_PASSWORD"

#: The complete DEV/QA account allowlist: (email, role) in reporting order.
#: This tuple is the only set of emails this command may touch.
QA_EMAILS = (
    ("guidance.qa@aegis.local", "guidance"),
    ("admin.qa@aegis.local", "admin"),
    ("faculty.qa@aegis.local", "faculty"),
    ("student.qa@aegis.local", "student"),
    ("parent.qa@aegis.local", "parent"),
)


class Command(BaseCommand):
    help = (
        "Create or verify the five shared DEV/QA accounts "
        "(guidance/admin/faculty/student/parent .qa@aegis.local) using the "
        f"password in {PASSWORD_ENV_VAR}."
    )

    def handle(self, *args, **options):
        User = get_user_model()

        password = self._read_password()
        self._validate_password(password)

        role_labels = {choice.value: choice.label for choice in User.Role}

        created = 0
        unchanged = 0
        role_fixed = 0

        with transaction.atomic():
            for email, role in QA_EMAILS:
                user = User.objects.filter(email=email).first()

                if user is None:
                    User.objects.create_user(
                        email=email,
                        password=password,
                        first_name="QA",
                        last_name=role_labels[role],
                        role=role,
                        is_active=True,
                        must_change_password=False,
                    )
                    created += 1
                    self.stdout.write(f"CREATED       role={role:9} {email}")
                    continue

                # An existing QA account may carry a tester-chosen password and
                # a locally changed is_active / must_change_password. Both are
                # reported, never rewritten. Only the role is corrected, and
                # only because the allowlist defines the role each QA address
                # must have for role-gated QA to be meaningful.
                if user.role != role:
                    user.role = role
                    user.save(update_fields=["role"])
                    role_fixed += 1
                    self.stdout.write(f"UPDATED_ROLE  role={role:9} {email}")
                else:
                    unchanged += 1
                    self.stdout.write(
                        f"EXISTS        role={user.role:9} {email} "
                        f"is_active={user.is_active} "
                        f"must_change_password={user.must_change_password}"
                    )

        self.stdout.write(
            f"TOTAL created={created} exists={unchanged} updated_role={role_fixed}"
        )

    def _read_password(self):
        password = os.environ.get(PASSWORD_ENV_VAR)
        if password is None or not password.strip():
            raise CommandError(
                f"{PASSWORD_ENV_VAR} is not set or is empty. The shared QA "
                f"password is never stored in the repository; supply it as an "
                f"environment variable before running this command."
            )
        return password

    def _validate_password(self, password):
        """Reject a weak shared secret before anything is written."""
        try:
            password_validation.validate_password(password)
        except ValidationError as exc:
            raise CommandError(
                f"{PASSWORD_ENV_VAR} was rejected by the project's configured "
                "password validators:\n  - " + "\n  - ".join(exc.messages)
            ) from None