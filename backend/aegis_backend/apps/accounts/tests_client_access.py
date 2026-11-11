"""
Focused tests for the client test-credential command.

``apps.accounts.management.commands.provision_client_access`` makes the client
school's *existing* accounts usable for an on-site test:

* every learner and adviser gets a fresh random password and can sign in;
* the forced initial-password change is cleared, because the generated
  password is already the one the tester was handed;
* every learner gets a linked parent login, so the parent module shows the
  client's own child;
* the credentials go to a file, never to stdout;
* the optional ``--finalize-grades`` publishes the imported grades.

The command must stay idempotent in shape: a second run rotates the passwords
but does not create a second parent or a second link.
"""

import csv
import io
import tempfile
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.models import ParentProfile, ParentStudentLink, StudentProfile
from apps.academics.models import (
    AcademicYear,
    Enrollment,
    Grade,
    GradingPeriod,
    Section,
    SubjectAssignment,
)

User = get_user_model()

#: Two learners are enough to prove the per-learner work; the real command
#: runs over the 97 the import creates.
LEARNERS = (
    ("Gabriel", "Andaya", "136884180155"),
    ("Kael Cassandra", "Valencia", "107753190030"),
)

ADVISER_EMAIL = "gerald.gutierrez@hccsi.aegis.local"


class ClientAccessTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("provision_client_school", stdout=io.StringIO())
        cls.section = Section.objects.get(
            name="Timothy",
            grade_level__level_number=7,
            academic_year__name="2026-2027",
        )
        cls.students = []
        for first, last, lrn in LEARNERS:
            user = User.objects.create(
                email=f"{lrn}@students.aegis.local",
                username="",
                first_name=first,
                last_name=last,
                role=User.Role.STUDENT,
                must_change_password=True,
            )
            user.set_unusable_password()
            user.save(update_fields=["password"])
            cls.students.append(
                StudentProfile.objects.create(
                    user=user,
                    student_id=lrn,
                    grade_level=cls.section.grade_level,
                    section=cls.section,
                    enrollment_date=date(2026, 6, 8),
                )
            )
            Enrollment.objects.create(
                student=cls.students[-1],
                section=cls.section,
                academic_year=cls.section.academic_year,
                date_enrolled=date(2026, 6, 8),
                is_active=True,
            )

    def run_command(self, **options):
        """Run the command into a temporary file and return its rows."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credentials.csv"
            out = io.StringIO()
            call_command(
                "provision_client_access",
                output=str(path),
                stdout=out,
                **options,
            )
            with path.open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            raw = path.read_bytes()
        return rows, out.getvalue(), raw


class ClientCredentialTest(ClientAccessTestCase):
    def test_every_learner_can_sign_in_with_the_written_password(self):
        rows, _out, _raw = self.run_command()
        by_email = {row["email"]: row for row in rows}

        for profile in self.students:
            row = by_email[profile.user.email]
            user = User.objects.get(pk=profile.user_id)
            self.assertTrue(row["password"])
            self.assertTrue(user.check_password(row["password"]))

    def test_the_forced_change_gate_is_cleared(self):
        self.run_command()

        for profile in self.students:
            profile.user.refresh_from_db()
            self.assertFalse(profile.user.must_change_password)
            self.assertTrue(profile.user.has_usable_password())

    def test_the_adviser_can_sign_in(self):
        rows, _out, _raw = self.run_command()

        row = next(row for row in rows if row["email"] == ADVISER_EMAIL)
        adviser = User.objects.get(email=ADVISER_EMAIL)
        self.assertTrue(adviser.check_password(row["password"]))

    def test_the_faculty_row_names_the_advisers_own_class(self):
        rows, _out, _raw = self.run_command()

        row = next(row for row in rows if row["email"] == ADVISER_EMAIL)
        self.assertEqual(row["role"], "faculty")
        self.assertEqual(row["section"], "Grade 7 - Timothy")

    def test_every_learner_gets_a_linked_parent(self):
        self.run_command()

        for profile in self.students:
            link = ParentStudentLink.objects.get(student=profile, is_primary=True)
            self.assertEqual(
                link.parent.user.email,
                f"parent.{profile.student_id}@parents.aegis.local",
            )
            self.assertEqual(
                link.parent.relationship_to_student,
                ParentProfile.RelationshipType.GUARDIAN,
            )

    def test_the_parent_password_is_in_the_file_and_signs_in(self):
        rows, _out, _raw = self.run_command()

        for profile in self.students:
            row = next(
                row
                for row in rows
                if row["email"] == f"parent.{profile.student_id}@parents.aegis.local"
            )
            parent = User.objects.get(email=row["email"])
            self.assertTrue(parent.check_password(row["password"]))

    def test_the_passwords_never_reach_stdout(self):
        rows, out, _raw = self.run_command()

        for row in rows:
            self.assertNotIn(row["password"], out)

    def test_running_twice_rotates_passwords_and_keeps_one_parent(self):
        first_rows, _out, _raw = self.run_command()
        first = {row["email"]: row["password"] for row in first_rows}

        second_rows, _out, _raw = self.run_command()
        second = {row["email"]: row["password"] for row in second_rows}

        self.assertEqual(set(first), set(second))
        self.assertEqual(
            ParentStudentLink.objects.count(), len(self.students)
        )
        for email, old in first.items():
            self.assertNotEqual(old, second[email])
            user = User.objects.get(email=email)
            self.assertFalse(user.check_password(old))
            self.assertTrue(user.check_password(second[email]))

    def test_it_refuses_a_school_without_learners(self):
        Enrollment.objects.all().delete()
        StudentProfile.objects.all().delete()

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CommandError) as caught:
                call_command(
                    "provision_client_access",
                    output=str(Path(tmp) / "credentials.csv"),
                    stdout=io.StringIO(),
                )
        self.assertIn("import_client_datasets", str(caught.exception))


class GradePublicationTest(ClientAccessTestCase):
    def _draft_grade(self):
        academic_year = AcademicYear.objects.get(name="2026-2027")
        period = GradingPeriod.objects.get(
            academic_year=academic_year, name="Term 1"
        )
        assignment = SubjectAssignment.objects.filter(section=self.section).first()
        return Grade.objects.create(
            student=self.students[0],
            subject_assignment=assignment,
            grading_period=period,
            score=87,
            encoded_by=assignment.faculty,
        )

    def test_grades_stay_draft_without_the_flag(self):
        grade = self._draft_grade()

        self.run_command()

        grade.refresh_from_db()
        self.assertEqual(grade.status, Grade.StatusChoices.DRAFT)

    def test_finalize_grades_publishes_the_import(self):
        grade = self._draft_grade()

        self.run_command(finalize_grades=True)

        grade.refresh_from_db()
        self.assertEqual(grade.status, Grade.StatusChoices.FINALIZED)
