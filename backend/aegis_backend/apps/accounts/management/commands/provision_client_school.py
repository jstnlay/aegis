"""
Provision the client school's sections, advisers and subject assignments.

The school sends its grades in the Electronic Class Record workbooks at the
repository root (``GRADE-7-LATEST-SEPTEMBER-4-2026.xlsx`` and its siblings).
Those workbooks name sections the seeded QA school does not have -- Grade 7
Timothy, Grade 8 Ephesians, Grade 9 Daniel, Grade 10 Daniel -- and a grade
import resolves its section and subject assignment against the database, so
the structure has to exist before the first upload.

This command creates that structure and nothing else: the learners, their
grades and their remarks arrive through the import pipeline, which is the
path the school will use.  It is idempotent -- running it twice changes
nothing -- and it never writes a learner record.

What it writes
--------------
* the academic year, its three grading periods, the grade levels and the eight
  learning areas per level (reused from the QA seed: the codes are what the
  ECR reader emits, e.g. ``FIL-7``);
* one faculty account per client section, with the adviser the workbook
  names;
* one section per client class, with that adviser;
* one subject assignment per learning area per section, taught by the
  section's adviser -- a JHS homeroom teacher carries the areas of their own
  class.

Usage:
    python manage.py provision_client_school

Logins
-------
The adviser accounts are QA logins.  When ``QA_SHARED_PASSWORD`` is set (the
same variable ``provision_qa_accounts`` reads) the accounts get that
password, so a tester can sign in as an adviser and see their advisees.
Without it the accounts exist but cannot be signed in to, which is the right
shape for a staff record that has no credential yet.
"""

import os

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.models import (
    AcademicYear,
    GradeLevel,
    GradingPeriod,
    Section,
    Subject,
    SubjectAssignment,
)
from apps.accounts.management.commands.provision_qa_accounts import PASSWORD_ENV_VAR
from apps.accounts.management.commands.seed_qa_dataset import (
    ACADEMIC_YEAR_END,
    ACADEMIC_YEAR_NAME,
    ACADEMIC_YEAR_START,
    GRADING_PERIODS,
    LEARNING_AREAS,
)
from apps.accounts.models import FacultyProfile

#: The client school: (section name, level number, adviser first, adviser
#: last, employee id, email local part).  The adviser names are the ones the
#: workbooks carry in their ``TERM n SUMMARY`` header.
CLIENT_SECTIONS = (
    ("Timothy", 7, "Gerald", "Gutierrez", "CLT-F001", "gerald.gutierrez"),
    ("Ephesians", 8, "Cirila", "Cuevas", "CLT-F002", "cirila.cuevas"),
    ("Daniel", 9, "Brian Jasper", "Garcia", "CLT-F003", "brian.garcia"),
    ("Daniel", 10, "Gihan Myles", "Gupong", "CLT-F004", "gihan.gupong"),
)

#: Mail domain for the adviser accounts.  Not routable: these are QA logins.
CLIENT_EMAIL_DOMAIN = "hccsi.aegis.local"

#: (level number, level name).
CLIENT_GRADE_LEVELS = ((7, "Grade 7"), (8, "Grade 8"), (9, "Grade 9"), (10, "Grade 10"))


class Command(BaseCommand):
    help = (
        "Create or verify the client school's sections, adviser accounts and "
        "subject assignments for the Electronic Class Record imports."
    )

    def handle(self, *args, **options):
        User = get_user_model()
        password = self._read_password()

        with transaction.atomic():
            academic_year = self._ensure_academic_year()
            self._ensure_grading_periods(academic_year)
            grade_levels = self._ensure_grade_levels()
            subjects = self._ensure_subjects(grade_levels)

            created_sections = 0
            created_assignments = 0
            created_faculty = 0

            for name, level_number, first, last, employee_id, email_local in CLIENT_SECTIONS:
                grade_level = grade_levels[level_number]
                profile, faculty_created = self._ensure_faculty(
                    User, first, last, employee_id, email_local, password
                )
                created_faculty += int(faculty_created)

                section, section_created = self._ensure_section(
                    academic_year, grade_level, name, profile
                )
                created_sections += int(section_created)

                for code, _subject_name in LEARNING_AREAS:
                    assignment, assignment_created = self._ensure_assignment(
                        academic_year, subjects[(level_number, code)], section, profile
                    )
                    created_assignments += int(assignment_created)

        self.stdout.write(
            f"TOTAL sections_created={created_sections} "
            f"subject_assignments_created={created_assignments} "
            f"faculty_created={created_faculty}"
        )
        self.stdout.write(
            "Next: run `manage.py import_client_datasets`, or upload each ECR "
            "workbook as an import of type 'Students' and then as 'Grades'."
        )

    # ------------------------------------------------------------------
    # Structure
    # ------------------------------------------------------------------

    def _ensure_academic_year(self):
        year, created = AcademicYear.objects.get_or_create(
            name=ACADEMIC_YEAR_NAME,
            defaults={
                "start_date": ACADEMIC_YEAR_START,
                "end_date": ACADEMIC_YEAR_END,
                "is_current": True,
            },
        )
        self.stdout.write(
            f"{'CREATED' if created else 'EXISTS '} academic_year={year.name}"
        )
        return year

    def _ensure_grading_periods(self, academic_year):
        for name, order, start, end in GRADING_PERIODS:
            period, created = GradingPeriod.objects.get_or_create(
                academic_year=academic_year,
                name=name,
                defaults={"order": order, "start_date": start, "end_date": end},
            )
            self.stdout.write(
                f"{'CREATED' if created else 'EXISTS '} grading_period={period.name}"
            )

    def _ensure_grade_levels(self):
        grade_levels = {}
        for level_number, level_name in CLIENT_GRADE_LEVELS:
            level, created = GradeLevel.objects.get_or_create(
                level_number=level_number, defaults={"name": level_name}
            )
            if not created and level.name != level_name:
                level.name = level_name
                level.save(update_fields=["name"])
            self.stdout.write(
                f"{'CREATED' if created else 'EXISTS '} grade_level={level.name}"
            )
            grade_levels[level_number] = level
        return grade_levels

    def _ensure_subjects(self, grade_levels):
        subjects = {}
        for level_number, grade_level in grade_levels.items():
            for code, subject_name in LEARNING_AREAS:
                subject, created = Subject.objects.get_or_create(
                    code=f"{code}-{level_number}",
                    defaults={"name": subject_name, "grade_level": grade_level},
                )
                self.stdout.write(
                    f"{'CREATED' if created else 'EXISTS '} subject={subject.code}"
                )
                subjects[(level_number, code)] = subject
        return subjects

    def _ensure_section(self, academic_year, grade_level, name, adviser):
        section, created = Section.objects.get_or_create(
            name=name,
            grade_level=grade_level,
            academic_year=academic_year,
            defaults={"adviser": adviser},
        )
        if section.adviser_id != adviser.id:
            section.adviser = adviser
            section.save(update_fields=["adviser"])
        # Mirror the adviser onto the profile so both directions of the model
        # (Section.adviser and FacultyProfile.advisory_section) agree.
        if not adviser.is_adviser or adviser.advisory_section_id != section.id:
            adviser.is_adviser = True
            adviser.advisory_section = section
            adviser.save(update_fields=["is_adviser", "advisory_section", "updated_at"])
        self.stdout.write(
            f"{'CREATED' if created else 'EXISTS '} section={section.grade_level.name}"
            f" - {section.name} adviser={adviser.user.get_full_name()}"
        )
        return section, created

    def _ensure_assignment(self, academic_year, subject, section, faculty):
        assignment, created = SubjectAssignment.objects.get_or_create(
            subject=subject,
            section=section,
            academic_year=academic_year,
            defaults={"faculty": faculty},
        )
        if assignment.faculty_id != faculty.id:
            assignment.faculty = faculty
            assignment.save(update_fields=["faculty"])
        if created:
            self.stdout.write(
                f"CREATED  subject_assignment={subject.code} -> {section.name}"
            )
        return assignment, created

    # ------------------------------------------------------------------
    # Staff
    # ------------------------------------------------------------------

    def _ensure_faculty(self, User, first, last, employee_id, email_local, password):
        email = f"{email_local}@{CLIENT_EMAIL_DOMAIN}"
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first,
                "last_name": last,
                "role": User.Role.FACULTY,
                "is_active": True,
            },
        )
        if created and password:
            user.set_password(password)
            user.save(update_fields=["password"])
        elif created:
            # No shared QA password configured: the staff record exists, but
            # there is no credential for it anywhere.
            user.set_unusable_password()
            user.save(update_fields=["password"])

        profile, profile_created = FacultyProfile.objects.get_or_create(
            user=user,
            defaults={"employee_id": employee_id, "department": "Junior High School"},
        )
        self.stdout.write(
            f"{'CREATED' if created else 'EXISTS '} faculty={email} "
            f"employee_id={profile.employee_id}"
        )
        return profile, created

    # ------------------------------------------------------------------
    # Password
    # ------------------------------------------------------------------

    def _read_password(self):
        password = os.environ.get(PASSWORD_ENV_VAR)
        if password is None or not password.strip():
            self.stdout.write(
                f"NOTE  {PASSWORD_ENV_VAR} is not set: the adviser accounts are "
                "created without a usable password."
            )
            return ""
        try:
            password_validation.validate_password(password)
        except ValidationError as exc:
            raise CommandError(
                f"{PASSWORD_ENV_VAR} was rejected by the project's configured "
                "password validators:\n  - " + "\n  - ".join(exc.messages)
            ) from None
        return password
