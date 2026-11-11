"""
Give the client school's existing accounts usable credentials for a test.

The import pipeline creates the client's learner accounts, and
``provision_client_school`` creates the adviser accounts.  Neither leaves a
credential a tester can use: the students importer generates a random password
and discards the plaintext, and the adviser accounts only get a password when
``QA_SHARED_PASSWORD`` is set.  The accounts also exist already, so creating
them again through *Admin -> Users -> New account* would fail on the duplicate
email -- and that form creates no ``StudentProfile``, no ``Enrollment`` and no
section, so a "student" made there has nothing to sign in to.

This command prepares the accounts that already exist for an on-site test:

* every learner in the four client sections gets a fresh random password and
  keeps their profile, section and enrollment;
* each of their advisers gets one too;
* one parent account per learner is created and linked to that learner, so the
  parent module shows the client's own data;
* with ``--finalize-grades``, the imported grades are published, so the risk
  and recommendation surfaces read them (the risk engine ignores drafts).

Every password is generated with ``secrets`` and validated by the project's
configured password validators.  Nothing is printed: the credentials are
written to a CSV file that the operator hands out and deletes.  Running the
command again rotates every password and keeps one parent per learner.

This is a test-prep command, not a provisioning step: it clears the forced
initial-password change and makes the accounts sign-in ready.  Do not run it
against a production cohort.

Usage:
    python manage.py provision_client_access
    python manage.py provision_client_access --finalize-grades
    python manage.py provision_client_access --output C:\\temp\\client.csv
"""

import csv
import secrets
from pathlib import Path

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.management.commands.provision_client_school import (
    CLIENT_SECTIONS,
)
from apps.accounts.management.commands.seed_qa_dataset import ACADEMIC_YEAR_NAME
from apps.accounts.models import (
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
)
from apps.academics.models import Grade, Section

#: Not routable, and never shared with the staff or learner domains.
PARENT_EMAIL_DOMAIN = "parents.aegis.local"

#: How many times to retry a generated password the validators reject.
PASSWORD_ATTEMPTS = 5

#: The file the operator hands out.  Never commit it; the command writes
#: plaintext passwords by design.
DEFAULT_OUTPUT = "client-credentials.csv"

CSV_HEADERS = ("role", "name", "email", "password", "section", "student_id")


class Command(BaseCommand):
    help = (
        "Set usable test credentials on the client school's existing learner "
        "and adviser accounts, and create a linked parent login per learner."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=DEFAULT_OUTPUT,
            help=(
                "Where to write the credentials CSV. Defaults to "
                f"{DEFAULT_OUTPUT} in the current directory."
            ),
        )
        parser.add_argument(
            "--finalize-grades",
            action="store_true",
            help=(
                "Publish the imported client grades (draft -> finalized) so "
                "the risk and recommendation surfaces read them. Bypasses the "
                "normal admin finalize action; use it for a test deployment."
            ),
        )

    def handle(self, *args, **options):
        User = get_user_model()
        sections = self._client_sections()
        students = list(
            StudentProfile.objects.filter(section__in=sections)
            .select_related("user", "section", "grade_level")
            .order_by(
                "section__grade_level__level_number",
                "user__last_name",
                "user__first_name",
            )
        )
        if not students:
            raise CommandError(
                "The client sections hold no learners. Run "
                "`python manage.py import_client_datasets` first."
            )

        rows = []
        with transaction.atomic():
            for section in sections:
                adviser = section.adviser
                if adviser is None:
                    raise CommandError(
                        f"Section {section} has no adviser. Run "
                        "`python manage.py provision_client_school` first."
                    )
                password = self._assign(adviser.user)
                rows.append(
                    self._row(
                        "faculty",
                        adviser.user,
                        password,
                        section,
                        student_id="",
                    )
                )

            for student in students:
                password = self._assign(student.user)
                rows.append(
                    self._row(
                        "student",
                        student.user,
                        password,
                        student.section,
                        student_id=student.student_id,
                    )
                )

            for student in students:
                parent_user, password = self._ensure_parent(User, student)
                rows.append(
                    self._row(
                        "parent",
                        parent_user,
                        password,
                        student.section,
                        student_id=student.student_id,
                    )
                )

            finalized = 0
            if options["finalize_grades"]:
                finalized = (
                    Grade.objects.filter(subject_assignment__section__in=sections)
                    .exclude(status=Grade.StatusChoices.FINALIZED)
                    .update(status=Grade.StatusChoices.FINALIZED)
                )

        path = self._write(options["output"], rows)
        faculty = sum(1 for row in rows if row["role"] == "faculty")
        self.stdout.write(
            f"Wrote {len(rows)} credentials "
            f"({len(students)} students, {len(students)} parents, {faculty} faculty) "
            f"to {path}."
        )
        self.stdout.write(
            "The file contains plaintext passwords: hand it out, then delete it."
        )
        if options["finalize_grades"]:
            self.stdout.write(f"Finalized {finalized} client grade row(s).")

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def _client_sections(self):
        """
        The four client classes, or a refusal.

        A missing section means the school structure was never provisioned;
        continuing would prepare three classes and silently skip the fourth.
        """
        sections = []
        missing = []
        for name, level_number, *_rest in CLIENT_SECTIONS:
            section = (
                Section.objects.filter(
                    name=name,
                    grade_level__level_number=level_number,
                    academic_year__name=ACADEMIC_YEAR_NAME,
                )
                .select_related("adviser__user", "grade_level")
                .first()
            )
            if section is None:
                missing.append(f"Grade {level_number} - {name}")
            else:
                sections.append(section)
        if missing:
            raise CommandError(
                "Missing client section(s): "
                + ", ".join(missing)
                + ". Run `python manage.py provision_client_school` first."
            )
        return sections

    def _assign(self, user):
        """Set a fresh random password and clear the forced-change gate."""
        password = self._new_password(user)
        user.set_password(password)
        user.must_change_password = False
        user.is_active = True
        user.save(
            update_fields=[
                "password",
                "must_change_password",
                "is_active",
                "updated_at",
            ]
        )
        return password

    def _ensure_parent(self, User, student):
        """One parent login per learner, linked to that learner."""
        email = f"parent.{student.student_id}@{PARENT_EMAIL_DOMAIN}"
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create(
                email=email,
                username="",
                first_name=f"Parent of {student.user.first_name}".strip(),
                last_name=student.user.last_name,
                role=User.Role.PARENT,
                is_active=True,
            )
        elif user.role != User.Role.PARENT:
            raise CommandError(
                f"{email} already exists with role '{user.role}'; expected "
                "a parent account. Refusing to change an existing role."
            )

        password = self._assign(user)
        profile, _created = ParentProfile.objects.get_or_create(
            user=user,
            defaults={
                "relationship_to_student": ParentProfile.RelationshipType.GUARDIAN
            },
        )
        ParentStudentLink.objects.update_or_create(
            parent=profile,
            student=student,
            defaults={"is_primary": True},
        )
        return user, password

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    def _new_password(self, user):
        for _attempt in range(PASSWORD_ATTEMPTS):
            candidate = secrets.token_urlsafe(12)
            try:
                password_validation.validate_password(candidate, user=user)
            except ValidationError:
                continue
            return candidate
        raise CommandError(
            "A password the project's validators accept could not be generated."
        )

    def _row(self, role, user, password, section, student_id):
        return {
            "role": role,
            "name": user.get_full_name().strip() or user.email,
            "email": user.email,
            "password": password,
            "section": f"{section.grade_level.name} - {section.name}",
            "student_id": student_id,
        }

    def _write(self, output, rows):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(rows)
        return path.resolve()
