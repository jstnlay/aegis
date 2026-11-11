"""
Focused tests for the client school provisioning command.

``apps.accounts.management.commands.provision_client_school`` creates the
structure the client's Electronic Class Record workbooks import into: the
four classes the school sends, the adviser of each class, and one subject
assignment per learning area per section.

The contract it has to keep:

* it creates the sections, the advisers and the assignments, and nothing else
  -- a learner record arrives through the import, never from here;
* running it twice changes nothing (a re-deploy, a second school year);
* the adviser of a section is the section's adviser in both directions
  (``Section.adviser`` and ``FacultyProfile.advisory_section``);
* without ``QA_SHARED_PASSWORD`` the staff records exist but there is no
  credential for them;
* it never writes a password to stdout.
"""

import io
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.management.commands.provision_client_school import (
    CLIENT_EMAIL_DOMAIN,
    CLIENT_SECTIONS,
)
from apps.accounts.management.commands.provision_qa_accounts import PASSWORD_ENV_VAR
from apps.academics.models import (
    AcademicYear,
    GradeLevel,
    Section,
    Subject,
    SubjectAssignment,
)
from apps.accounts.models import FacultyProfile, StudentProfile

User = get_user_model()

VALID_SHARED_PASSWORD = "QaShared-9xKq-2026"

#: One subject assignment per learning area per class.
LEARNING_AREA_COUNT = 8


def run_provision(stdout=None):
    return call_command("provision_client_school", stdout=stdout)


class ClientSchoolTestCase(TestCase):
    def setUp(self):
        patcher = mock.patch.dict(
            os.environ, {PASSWORD_ENV_VAR: VALID_SHARED_PASSWORD}, clear=False
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class ClientSchoolStructureTest(ClientSchoolTestCase):
    """The structure the workbooks import into."""

    def test_it_creates_a_section_per_class_with_its_adviser(self):
        run_provision(stdout=io.StringIO())

        academic_year = AcademicYear.objects.get(name="2026-2027")
        for name, level_number, first, last, _employee_id, email_local in CLIENT_SECTIONS:
            section = Section.objects.get(
                name=name,
                grade_level__level_number=level_number,
                academic_year=academic_year,
            )
            self.assertIsNotNone(section.adviser)
            self.assertEqual(section.adviser.user.first_name, first)
            self.assertEqual(section.adviser.user.last_name, last)
            self.assertEqual(section.adviser.user.email, f"{email_local}@{CLIENT_EMAIL_DOMAIN}")

    def test_it_creates_one_subject_assignment_per_learning_area(self):
        run_provision(stdout=io.StringIO())

        for name, level_number, _first, _last, _employee_id, _email in CLIENT_SECTIONS:
            assignments = SubjectAssignment.objects.filter(
                section__name=name,
                section__grade_level__level_number=level_number,
            )
            self.assertEqual(assignments.count(), LEARNING_AREA_COUNT)
            for assignment in assignments:
                self.assertEqual(
                    assignment.faculty_id,
                    assignment.section.adviser_id,
                    "a class is taught by its own adviser",
                )

    def test_the_adviser_profile_mirrors_the_section(self):
        run_provision(stdout=io.StringIO())

        adviser = FacultyProfile.objects.get(
            user__email=f"gerald.gutierrez@{CLIENT_EMAIL_DOMAIN}"
        )
        self.assertTrue(adviser.is_adviser)
        self.assertEqual(adviser.advisory_section.name, "Timothy")

    def test_it_writes_no_learner_record(self):
        run_provision(stdout=io.StringIO())
        self.assertEqual(StudentProfile.objects.count(), 0)

    def test_running_it_twice_changes_nothing(self):
        run_provision(stdout=io.StringIO())
        before = (
            Section.objects.count(),
            SubjectAssignment.objects.count(),
            FacultyProfile.objects.count(),
        )

        run_provision(stdout=io.StringIO())

        self.assertEqual(
            (
                Section.objects.count(),
                SubjectAssignment.objects.count(),
                FacultyProfile.objects.count(),
            ),
            before,
        )

    def test_it_keeps_the_learning_area_codes_the_reader_emits(self):
        """The reader writes FIL-7; the subject has to be that code."""
        run_provision(stdout=io.StringIO())

        self.assertTrue(
            Subject.objects.filter(code="FIL-7", grade_level__level_number=7).exists()
        )
        self.assertTrue(
            Subject.objects.filter(code="ESP-10", grade_level__level_number=10).exists()
        )

    def test_it_creates_the_grade_levels_and_the_year(self):
        run_provision(stdout=io.StringIO())

        for level_number in (7, 8, 9, 10):
            self.assertTrue(
                GradeLevel.objects.filter(level_number=level_number).exists()
            )
        self.assertTrue(AcademicYear.objects.filter(name="2026-2027").exists())


class ClientSchoolLoginTest(ClientSchoolTestCase):
    """The adviser accounts are QA logins, and only when there is a secret."""

    def test_the_adviser_can_sign_in_with_the_shared_password(self):
        run_provision(stdout=io.StringIO())

        adviser = User.objects.get(email=f"gerald.gutierrez@{CLIENT_EMAIL_DOMAIN}")
        self.assertTrue(adviser.has_usable_password())
        self.assertTrue(adviser.check_password(VALID_SHARED_PASSWORD))

    def test_without_the_shared_password_the_record_has_no_credential(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            run_provision(stdout=io.StringIO())

        adviser = User.objects.get(email=f"gerald.gutierrez@{CLIENT_EMAIL_DOMAIN}")
        self.assertFalse(adviser.has_usable_password())

    def test_nothing_sensitive_reaches_stdout(self):
        out = io.StringIO()
        run_provision(stdout=out)

        printed = out.getvalue()
        self.assertNotIn(VALID_SHARED_PASSWORD, printed)
        self.assertNotIn("pbkdf2", printed)
