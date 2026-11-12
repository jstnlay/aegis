"""
AEGIS — synthetic chatbot safety data for development and demos.

Creates synthetic students, chatbot turns, flags in every state and the
keyword terms that screen them, so the Guidance inbox, the faculty feed and
the administrator console can be exercised without anyone typing a crisis
message to see what happens.

IMPORTANT:
  This is SYNTHETIC DEVELOPMENT DATA — NOT real school data, and not a record
  of any real student. The messages below are written to be obviously
  synthetic and are marked as such.

Usage:
  python scripts/seed_chatbot_synthetic.py

(Run it from `backend/`, or from anywhere — the script puts the Django
project directory on the path itself. Piping it into `manage.py shell` does
not work: the interactive console reads it line by line and loses the
indentation.)
"""

import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Running this file directly puts `backend/scripts` on the path, not the
# directory that holds the `config` package, so add it before Django starts.
BASE_DIR = Path(__file__).resolve().parent.parent / "aegis_backend"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
import django

django.setup()

from django.utils import timezone

# Every synthetic message carries this marker so a second run can find and
# skip what it already created instead of duplicating it.
MARKER = "[SYNTHETIC]"

NUM_STUDENTS = 12
NUM_BENIGN_TURNS = 24
NUM_FLAGS = 8

random.seed(7)

FIRST_NAMES = [
    "Ana", "Ben", "Carlo", "Dee", "Eli", "Faye", "Gio", "Hana",
    "Ira", "Kiko", "Lia", "Milo",
]
LAST_NAMES = [
    "Alvarez", "Bautista", "Cruz", "Domingo", "Espino", "Flores",
    "Gomez", "Hernandez", "Ilagan", "Jacinto",
]

BENIGN_MESSAGES = [
    "What is my grade in Math?",
    "What is my attendance?",
    "Can you give me a resource for Science?",
    "How do I study better?",
    "When is the next quiz?",
    "What can you help me with?",
    "Give me a study plan for the unit test",
    "Who is my class adviser?",
]

SENSITIVE_MESSAGES = [
    (
        "I want to hurt myself and I do not know what to do",
        "critical",
        ["self_harm"],
    ),
    (
        "Someone keeps threatening me after school",
        "high",
        ["violence"],
    ),
    (
        "I am being bullied every day and nobody believes me",
        "medium",
        ["bullying"],
    ),
    (
        "I am so stressed about failing that I cannot sleep",
        "medium",
        ["distress"],
    ),
    (
        "My family keeps arguing and I want to run away from home",
        "medium",
        ["family"],
    ),
]

RESOLUTIONS = [
    ("resolved", "Called the adviser and set a check-in for Friday."),
    ("acknowledged", "Seen. Will follow up this week."),
    ("under_review", ""),
    ("open", ""),
]


def ensure_students(count):
    """Create synthetic students if the school does not have enough."""
    from apps.accounts.models import StudentProfile, User
    from apps.academics.models import AcademicYear, GradeLevel, Section

    year = (
        AcademicYear.objects.filter(is_current=True)
        .order_by("-start_date")
        .first()
    )
    if year is None:
        year = AcademicYear.objects.create(
            name="2025-2026",
            start_date=date(2025, 6, 1),
            end_date=date(2026, 3, 31),
            is_current=True,
        )
    grade_level = GradeLevel.objects.first()
    if grade_level is None:
        grade_level = GradeLevel.objects.create(name="Grade 7", level_number=7)
    section = Section.objects.filter(academic_year=year).first()
    if section is None:
        section = Section.objects.create(
            name="Synthetic Section",
            grade_level=grade_level,
            academic_year=year,
        )

    students = []
    for index in range(count):
        email = f"chatseed{index + 1:02d}@aegis.local"
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(
                email=email,
                password="SyntheticSeed!2026",
                first_name=FIRST_NAMES[index % len(FIRST_NAMES)],
                last_name=LAST_NAMES[index % len(LAST_NAMES)],
                role="student",
            )
        profile = StudentProfile.objects.filter(user=user).first()
        if profile is None:
            profile = StudentProfile.objects.create(
                user=user,
                student_id=f"CHATSEED{index + 1:03d}",
                grade_level=grade_level,
                section=section,
                enrollment_date=date(2025, 6, 1),
            )
        students.append(profile)
    return students


def seed_keyword_terms():
    from apps.chatbot.defaults import seed_keyword_terms

    created = seed_keyword_terms()
    print(f"  keyword terms created: {created}")


def seed_turns(students):
    from apps.chatbot.models import ChatMessage

    created = 0
    for index in range(NUM_BENIGN_TURNS):
        student = students[index % len(students)]
        text = f"{MARKER} {BENIGN_MESSAGES[index % len(BENIGN_MESSAGES)]}"
        if ChatMessage.objects.filter(message=text).exists():
            continue
        ChatMessage.objects.create(
            user=student.user,
            message=text,
            reply="Here is what I found for you.",
            intent="ask_grade",
            urgency="normal",
            severity="low",
        )
        created += 1
    print(f"  benign turns created: {created}")


def seed_flags(students):
    from apps.chatbot.models import ChatMessage, Flag, FlagAction
    from apps.chatbot.routing import route_flag

    created = 0
    for index in range(NUM_FLAGS):
        text, severity, categories = SENSITIVE_MESSAGES[index % len(SENSITIVE_MESSAGES)]
        message_text = f"{MARKER} {text}"
        if ChatMessage.objects.filter(message=message_text).exists():
            continue
        student = students[index % len(students)]
        chat_message = ChatMessage.objects.create(
            user=student.user,
            message=message_text,
            reply="I hear you, and you should talk to a counselor. Guidance has been notified.",
            intent="express_concern",
            urgency="urgent" if severity in ("high", "critical") else "elevated",
            severity=severity,
            sensitive=True,
            layer1_sensitive=True,
        )
        status, note = RESOLUTIONS[index % len(RESOLUTIONS)]
        flag = Flag.objects.create(
            student=student,
            user=student.user,
            chat_message=chat_message,
            severity=severity,
            source="keyword",
            categories=categories,
            summary="Synthetic seed record.",
            escalation_due_at=timezone.now() + timedelta(minutes=15),
        )
        FlagAction.objects.create(
            flag=flag,
            actor=student.user,
            action=FlagAction.Action.CREATED,
            metadata={"source": "seed", "severity": severity},
        )
        route_flag(flag, dispatch=False)
        if status != "open":
            flag.status = status
            if status in ("acknowledged", "resolved"):
                flag.acknowledged_at = timezone.now()
                flag.resolved_at = timezone.now() if status == "resolved" else None
                flag.resolution_note = note
            flag.save()
        created += 1
    print(f"  flags created: {created}")


def run():
    print("Seeding synthetic chatbot safety data...")
    students = ensure_students(NUM_STUDENTS)
    print(f"  students available: {len(students)}")
    seed_keyword_terms()
    seed_turns(students)
    seed_flags(students)
    print("Done.")


if __name__ == "__main__":
    run()
