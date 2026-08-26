"""Seed demo AEGIS users for Phase 7 live E2E verification (idempotent)."""

import os
import sys
from datetime import date

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aegis_backend"),
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from apps.accounts.models import (  # noqa: E402
    FacultyProfile,
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
)
from apps.academics.models import AcademicYear, GradeLevel, Section, Enrollment  # noqa: E402

User = get_user_model()

# ---------------------------------------------------------------------------
# SEC-012: password is never stored in tracked source code.
# ---------------------------------------------------------------------------
PASSWORD = os.environ.get("PHASE7_E2E_PASSWORD")
if not PASSWORD or not PASSWORD.strip():
    print(
        "ERROR: PHASE7_E2E_PASSWORD environment variable is not set or empty.\n"
        "Set it before running this script."
    )
    sys.exit(1)

USERS = [
    ("e2e.admin@aegis.dev", "admin"),
    ("e2e.faculty@aegis.dev", "faculty"),
    ("e2e.guidance@aegis.dev", "guidance"),
    ("e2e.student@aegis.dev", "student"),
    ("e2e.student2@aegis.dev", "student"),
    ("e2e.parent@aegis.dev", "parent"),
]

created = []
for email, role in USERS:
    user, was_created = User.objects.get_or_create(
        email=email,
        defaults={
            "first_name": role.title(),
            "last_name": "E2E",
            "role": role,
        },
    )
    if was_created:
        user.set_password(PASSWORD)
        user.save()
    created.append((email, role, was_created))

admin = User.objects.get(email="e2e.admin@aegis.dev")
faculty = User.objects.get(email="e2e.faculty@aegis.dev")
student = User.objects.get(email="e2e.student@aegis.dev")
student2 = User.objects.get(email="e2e.student2@aegis.dev")
parent = User.objects.get(email="e2e.parent@aegis.dev")

faculty_profile, _ = FacultyProfile.objects.get_or_create(
    user=faculty, defaults={"employee_id": "EMP-E2E-001", "department": "Science"}
)

year, _ = AcademicYear.objects.get_or_create(
    name="2026-2027",
    defaults={"start_date": date(2026, 6, 1), "end_date": date(2027, 3, 31), "is_current": True},
)
level, _ = GradeLevel.objects.get_or_create(name="Grade 8", defaults={"level_number": 8})
section, _ = Section.objects.get_or_create(
    name="Curie",
    defaults={"grade_level": level, "academic_year": year, "adviser": faculty_profile},
)

sp1, _ = StudentProfile.objects.get_or_create(
    user=student,
    defaults={
        "student_id": "STU-E2E-001",
        "section": section,
        "grade_level": level,
        "enrollment_date": date(2026, 6, 1),
    },
)
sp2, _ = StudentProfile.objects.get_or_create(
    user=student2,
    defaults={
        "student_id": "STU-E2E-002",
        "grade_level": level,
        "enrollment_date": date(2026, 6, 1),
    },
)
pp, _ = ParentProfile.objects.get_or_create(user=parent, defaults={"relationship_to_student": "father"})
ParentStudentLink.objects.get_or_create(parent=pp, student=sp1, defaults={"is_primary": True})
Enrollment.objects.get_or_create(
    student=sp1, section=section, academic_year=year,
    defaults={"is_active": True, "date_enrolled": date(2026, 6, 1)},
)

for email, role, was_created in created:
    print(f"{'CREATED' if was_created else 'EXISTS  '} {role:9} {email}")
print("SEEDED")
