"""
Seed the realistic Philippine Junior High School QA dataset.

This is the data half of the shared DEV/QA provisioning architecture. Its
sibling, ``provision_qa_accounts``, creates the five shared QA logins; this
command builds the school those logins need so every role-gated page has real,
synthetic data to exercise.

The dataset models one public JHS campus::

    School        AEGIS Integrated School
    School year   2026-2027 (the current academic year)
    Grade 7       Rizal        25 students
    Grade 8       Bonifacio    25 students   <- student.qa is here
    Grade 9       Mabini       25 students
    Grade 10      Luna         25 students
                   100 students, 100 synthetic parent accounts

The eight learning areas are the DepEd K-to-12 Junior High School core
curriculum subjects. No subject is invented.

Safety properties, all of which are covered by tests_qa_dataset.py:

* **Synthetic only.** Every account, name, code and identifier written here is
  generated from fixed name pools and ``qa-``-prefixed ``@aegis.local``
  addresses. The only pre-existing accounts touched are the five QA allowlist
  addresses owned by ``provision_qa_accounts``, and only their display name,
  phone number and role-linked profile rows.
* **Isolation.** Seeded accounts use the ``qa-`` email prefix and the
  ``AEGIS-QA-`` identifier prefix. Records are located by those keys plus each
  model's own ``unique_together``, so the command never adopts, rewrites or
  deletes a row it did not create. The ``@aegis.dev`` E2E accounts and any
  ``@aegis.test`` legacy seed data are invisible to it.
* **No secrets.** Synthetic accounts get an unusable password, so no password,
  hash or token exists for them anywhere. The four QA logins keep whatever
  password ``provision_qa_accounts`` gave them; this command never reads, sets
  or prints a password.
* **No fabricated AI output.** ``RiskScore`` is deliberately NOT seeded. It is
  a machine-generated computation log written only by the ``ai_engine``
  (``run_risk_computation``), it has no API surface at all, and inventing an
  ``explanation`` trace would be fabricated model output. ``RiskAlert`` rows are
  written with ``source="manual"`` and ``risk_score_ref=None``, which is exactly
  what ``POST /api/v1/guidance/risk-alerts/`` produces.
* **Idempotent.** Every write is a ``get_or_create``/``update_or_create`` keyed
  on a natural key, so re-running never duplicates a row and never trips a
  unique constraint. All 100 synthetic students, their profiles, enrollments,
  grades, attendance and guidance records are reused rather than recreated.
* **Additive only, with one narrow exception.** The command creates and
  updates; it never deletes data a school or a tester created. Changing a
  declared table (for example ``QA_PARENT_CHILDREN``) adds the new rows without
  removing the old ones. The single exception is the seed's own superseded
  four-quarter calendar: ``_retire_legacy_grading_periods`` re-points and then
  deletes only grading periods on this seed's academic year whose name, order
  and both dates match ``LEGACY_GRADING_PERIODS`` exactly, so a database seeded
  before the move to three terms ends up with three terms and no orphaned
  grades.
* **Dates are legal by construction.** Nothing is written with a future
  timestamp. Attendance uses the three most recently completed Mon-Fri school
  weeks; grades exist only for terms that have already opened, a closed term is
  finalized while an open one stays draft/submitted, and a term that has not
  begun gets no grades at all. A row that has gone stale since the last run is
  corrected in place.

Usage:
    python manage.py seed_qa_dataset
"""

import random
from collections import Counter
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import (
    FacultyProfile,
    GuidanceProfile,
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
)
from apps.academics.models import (
    AcademicYear,
    Enrollment,
    Grade,
    GradeLevel,
    GradingPeriod,
    Schedule,
    Section,
    Subject,
    SubjectAssignment,
)
from apps.assessments.models import (
    Assessment,
    AssessmentQuestion,
    AssessmentResult,
)
from apps.attendance.models import AttendanceRecord
from apps.guidance.models import (
    BehavioralNote,
    ConsultationRecord,
    Intervention,
    InterventionStep,
    ProgressNote,
    RiskAlert,
)

# ---------------------------------------------------------------------------
# Identity / isolation constants
# ---------------------------------------------------------------------------

#: Master seed. Every random draw is namespaced by a stable record key (see
#: ``_rand``) so the dataset is reproducible and independent of the order in
#: which the seeding phases happen to run.
RANDOM_SEED = "aegis-qa-dataset-2026"

#: Every synthetic account is a ``qa-`` prefixed local part on this domain.
QA_EMAIL_DOMAIN = "aegis.local"
QA_EMAIL_PREFIX = "qa-"

#: Prefix for every school-assigned identifier this command writes.
QA_CODE_PREFIX = "AEGIS-QA-"

#: The five shared DEV/QA logins owned by ``provision_qa_accounts``. Only these
#: four roles receive dataset records; admin.qa is left alone (see module
#: docstring and ``_report``).
QA_FACULTY_EMAIL = "faculty.qa@aegis.local"
QA_GUIDANCE_EMAIL = "guidance.qa@aegis.local"
QA_STUDENT_EMAIL = "student.qa@aegis.local"
QA_PARENT_EMAIL = "parent.qa@aegis.local"

SCHOOL_NAME = "AEGIS Integrated School"

#: Zero-based roster index of student.qa: first Grade 8 -- Bonifacio student.
QA_STUDENT_ROSTER_INDEX = 25

# ---------------------------------------------------------------------------
# Academic calendar
# ---------------------------------------------------------------------------

ACADEMIC_YEAR_NAME = "2026-2027"
ACADEMIC_YEAR_START = date(2026, 6, 8)
ACADEMIC_YEAR_END = date(2027, 4, 8)

#: (name, order, start_date, end_date) for the official three-term SY 2026-2027
#: basic education calendar. All three sit inside the academic year bounds as
#: ``GradingPeriod.clean()`` requires. ``GradingPeriod`` is name/order/date
#: generic, so terms need no schema support of their own.
GRADING_PERIODS = (
    ("Term 1", 1, date(2026, 6, 8), date(2026, 9, 15)),
    ("Term 2", 2, date(2026, 9, 16), date(2026, 12, 18)),
    ("Term 3", 3, date(2027, 1, 4), date(2027, 4, 8)),
)

#: The four-quarter calendar an earlier revision of this seed wrote for the same
#: academic year. It is retained only so that revision's rows can be recognised
#: and retired by ``_retire_legacy_grading_periods``; nothing else reads it, and
#: it must never be seeded again.
LEGACY_GRADING_PERIODS = (
    ("1st Quarter", 1, date(2026, 6, 1), date(2026, 8, 21)),
    ("2nd Quarter", 2, date(2026, 8, 24), date(2026, 10, 23)),
    ("3rd Quarter", 3, date(2026, 10, 26), date(2027, 1, 22)),
    ("4th Quarter", 4, date(2027, 1, 25), date(2027, 3, 31)),
)

#: (section name, grade level number, grade level name).
SECTION_PLAN = (
    ("Rizal", 7, "Grade 7"),
    ("Bonifacio", 8, "Grade 8"),
    ("Mabini", 9, "Grade 9"),
    ("Luna", 10, "Grade 10"),
)

STUDENTS_PER_SECTION = 25
TOTAL_STUDENTS = STUDENTS_PER_SECTION * len(SECTION_PLAN)  # 100

#: The eight DepEd JHS core learning areas as (subject code, subject name).
#: Applied to every grade level; the code carries a level suffix because
#: ``Subject.code`` is globally unique.
LEARNING_AREAS = (
    ("FIL", "Filipino"),
    ("ENG", "English"),
    ("MATH", "Mathematics"),
    ("AP", "Araling Panlipunan"),
    ("SCI", "Science"),
    ("TLE", "Technology and Livelihood Education"),
    ("MAPEH", "MAPEH"),
    ("ESP", "Edukasyon sa Pagpapakatao"),
)

#: Grade 8 subject codes taught by faculty.qa. A homeroom teacher carrying three
#: core areas alongside 25 advisees is the normal JHS staffing shape and gives
#: the faculty grade and attendance surfaces enough rows of their own.
QA_FACULTY_SUBJECT_CODES = ("FIL", "ENG", "ESP")

#: Sections with no QA faculty take their homeroom adviser from the Edukasyon sa
#: Pagpapakatao teacher, which is the usual DepEd homeroom convention.
ADVISER_AREA_CODE = "ESP"

#: How many completed Mon-Fri school weeks of attendance to write. Anchoring to
#: whole past weeks rather than "the last N days" means a re-run inside the
#: same week is a true no-op instead of adding a new day's rows.
ATTENDANCE_WEEKS = 3

#: Attendance mix for the synthetic roster.
ATTENDANCE_PRESENT_CUTOFF = 0.82
ATTENDANCE_LATE_CUTOFF = 0.90

# ---------------------------------------------------------------------------
# Synthetic name / address pools
# ---------------------------------------------------------------------------

FIRST_NAMES = (
    "Juan", "Maria", "Jose", "Ana", "Pedro", "Luz", "Ramon", "Elena",
    "Carlos", "Rosa", "Miguel", "Sofia", "Luis", "Carmen", "Andres",
    "Patricia", "Jorge", "Leticia", "Fernando", "Gloria", "Antonio",
    "Isabel", "Manuel", "Cristina", "Ricardo", "Teresa", "Daniel",
    "Veronica", "Eduardo", "Monica", "Rafael", "Josefina", "Rodrigo",
    "Angeline", "Benigno", "Corazon", "Dalisay", "Efren", "Filomena",
)

SURNAMES = (
    "Santos", "Reyes", "Cruz", "Bautista", "Ocampo", "Villanueva",
    "Aquino", "Mendoza", "De la Cruz", "Torres", "Ramos", "Garcia",
    "Domingo", "Navarro", "Salazar", "Castillo", "Vergara", "Perez",
    "Fernandez", "Gonzales", "Lopez", "Martinez", "Rodriguez", "Diaz",
    "Alvarez", "Morales", "Rivera", "Gomez", "Santiago", "Lazaro",
    "Padilla", "Sarmiento", "Aguilar", "Cabrera",
)

#: (barangay, municipality/city, province) used to build plausible addresses.
LOCALITIES = (
    ("San Isidro", "Quezon City", "Metro Manila"),
    ("Sto. Nino", "Malabon", "Metro Manila"),
    ("Mabini", "Caloocan", "Metro Manila"),
    ("Bagong Silang", "General Santos City", "South Cotabato"),
    ("Poblacion", "Davao City", "Davao del Sur"),
    ("Mabini", "Iloilo City", "Iloilo"),
    ("Mangalag", "Bacolod City", "Negros Occidental"),
    ("Lazaro", "Cagayan de Oro", "Misamis Oriental"),
    ("Cabatuan", "Tarlac City", "Tarlac"),
    ("Poblacion", "San Fernando", "Pampanga"),
    ("Centro", "Tagum City", "Davao del Sur"),
    ("Sto. Nino", "Zamboanga City", "Zamboanga del Sur"),
)

#: Obviously synthetic PH-format mobile numbers: +63917 then six digits. No
#: real subscriber range is targeted.
PHONE_PREFIX = "+63917"

# ---------------------------------------------------------------------------
# Grade scale
# ---------------------------------------------------------------------------

#: (minimum score, letter grade, DepEd remark). Letter codes are short because
#: ``Grade.letter_grade`` is a 5-character column.
GRADE_SCALE = (
    (90, "A", "Outstanding"),
    (85, "B+", "Very Satisfactory"),
    (80, "B", "Satisfactory"),
    (75, "C+", "Fairly Satisfactory"),
    (70, "C", "Fairly Satisfactory"),
    (65, "D", "Fairly Satisfactory"),
    (0, "F", "Failed"),
)

#: Score generation envelope for the synthetic roster.
SCORE_MEAN = 83.0
SCORE_SPREAD = 7.5
SUBJECT_NOISE = 3.5
SCORE_FLOOR = 62.0
SCORE_CEILING = 99.0

#: Additional downward nudge for students who carry a risk alert, so the
#: guidance and academic data tell the same story.
AT_RISK_ABILITY_PENALTY = 9.0

#: Probability that a grade in the open term is already submitted.
OPEN_TERM_SUBMIT_RATE = 0.4

# ---------------------------------------------------------------------------
# Declared guidance dataset
# ---------------------------------------------------------------------------

#: Students drawn an active risk alert, as zero-based roster indices into the
#: 100-student list. Declared rather than sampled so the guidance pages have a
#: predictable, hand-checkable population spanning every status and level.
RISK_ALERT_STUDENTS = (
    # (roster index, risk_level, status, risk_factors)
    (2, "high", "active", ["Repeated absences", "Declining subject scores"]),
    (5, "moderate", "active", ["Missed assignments"]),
    (8, "moderate", "under_monitoring", ["Peer conflict reported"]),
    (11, "high", "escalated", ["Withdrawal from peer group", "Sleep disruption"]),
    (14, "low", "active", ["Occasional late arrival"]),
    (17, "moderate", "resolved", ["Adjustment period, now stable"]),
    (21, "high", "active", ["Low academic rating", "Guardian follow-up pending"]),
    (24, "low", "under_monitoring", ["Improved attendance after counselling"]),
    (30, "moderate", "active", ["Difficulty concentrating"]),
    (36, "high", "active", ["Repeated absences", "Failing term grade"]),
    (42, "moderate", "under_monitoring", ["Conflict with classmate"]),
    (55, "high", "active", ["Absenteeism during exams"]),
    (61, "moderate", "resolved", ["Home visit completed"]),
    (74, "moderate", "active", ["Declining EsP participation"]),
    (88, "high", "under_monitoring", ["Reported bullying, monitoring"]),
    # PH11.9: the three parent.qa children (QA_PARENT_CHILDREN). Without these
    # the parent's read-only Student Support page renders three empty tables,
    # which is indistinguishable from a broken queryset. Every status and level
    # is represented so the page's badges and the open-alert count are
    # exercised, and the factors stay plainly synthetic.
    (QA_STUDENT_ROSTER_INDEX, "low", "under_monitoring", ["Improved attendance after counselling"]),
    (QA_STUDENT_ROSTER_INDEX + 1, "moderate", "active", ["Missed assignments"]),
    (2 * STUDENTS_PER_SECTION, "high", "resolved", ["Adjustment period, now stable"]),
)

#: (roster index, session_type, priority, status, concern_categories,
#:  days_ago, next_session_in_days).
#: Exactly one consultation per (student, session_type) keeps the natural key
#: stable across runs even though the dates move with "today".
CONSULTATIONS = (
    (2, "individual_counseling", "high", "follow_up", ["academic", "emotional"], 21, 7),
    (5, "individual_counseling", "medium", "ongoing", ["academic"], 14, 10),
    (8, "parent_conference", "medium", "completed", ["behavioral", "family"], 35, None),
    (11, "individual_counseling", "high", "follow_up", ["emotional", "family"], 9, 4),
    (14, "follow_up", "low", "completed", ["behavioral"], 28, None),
    (21, "group", "medium", "completed", ["academic"], 18, None),
    (24, "individual_counseling", "medium", "ongoing", ["academic"], 11, 12),
    (36, "individual_counseling", "high", "follow_up", ["academic", "behavioral"], 6, 3),
    (42, "parent_conference", "low", "completed", ["family"], 41, None),
    (61, "follow_up", "medium", "completed", ["behavioral"], 25, None),
    # PH11.9: the three parent.qa children, one session each, spanning three
    # different session types and statuses so the parent's counselling table
    # has a row per state it can render.
    (QA_STUDENT_ROSTER_INDEX, "individual_counseling", "low", "completed", ["academic"], 16, None),
    (QA_STUDENT_ROSTER_INDEX + 1, "parent_conference", "medium", "follow_up", ["family", "behavioral"], 7, 9),
    (2 * STUDENTS_PER_SECTION, "follow_up", "high", "completed", ["emotional"], 33, None),
)

#: (roster index, status, days_since_start, review_in_days, steps) where steps
#: is a tuple of (title, description, status).
INTERVENTIONS = (
    (
        2,
        "active",
        20,
        25,
        (
            ("Parent conference", "Meet guardian to review the attendance plan.", "completed"),
            ("Weekly check-in", "Fifteen-minute grade and attendance check-in.", "in_progress"),
            ("Peer-buddy pairing", "Pair with a classmate for classroom support.", "scheduled"),
        ),
    ),
    (
        11,
        "active",
        9,
        40,
        (
            ("Counselling series", "Four-session individual counselling series.", "in_progress"),
            ("Guardian referral", "Refer to the guardian for home support.", "pending"),
            ("Re-assessment", "Re-administer the well-being check after four weeks.", "scheduled"),
        ),
    ),
    (
        36,
        "completed",
        55,
        None,
        (
            ("Attendance contract", "Signed attendance agreement with the guardian.", "completed"),
            ("Tutorial session", "Weekly subject tutoring.", "completed"),
            ("Case closure review", "Reviewed and closed with the guardian present.", "completed"),
        ),
    ),
)

#: (roster index, note_type, days_ago).
BEHAVIORAL_NOTES = (
    (2, "warning", 19),
    (2, "positive", 12),
    (5, "positive", 13),
    (8, "incident", 30),
    (11, "incident", 8),
    (14, "positive", 26),
    (21, "warning", 17),
    (24, "positive", 10),
    (30, "warning", 15),
    (42, "incident", 32),
    (61, "positive", 24),
    # PH11.9: the three parent.qa children. Behavioral notes are immutable once
    # written, so the parent's page reads them as a history.
    (QA_STUDENT_ROSTER_INDEX, "positive", 6),
    (QA_STUDENT_ROSTER_INDEX + 1, "warning", 11),
    (2 * STUDENTS_PER_SECTION, "incident", 20),
)

#: The guidance-owned wellness assessment. Wellness/behavioral assessments must
#: carry ``creator_role="guidance"`` and a guidance ``created_by``, which is the
#: shape ``POST /api/v1/assessments/assessments/`` accepts.
WELLNESS_ASSESSMENT_TITLE = "Bonifacio Section Well-Being Check"
WELLNESS_ASSESSMENT_DESCRIPTION = (
    "A short well-being pulse administered by the Guidance Office to Grade 8 "
    "Bonifacio. Responses inform counselling and support; they are not graded."
)

#: (question_text, question_type, options, correct_answer, points). The declared
#: points are reused verbatim when building results, so a seeded score can never
#: exceed the seeded total.
WELLNESS_QUESTIONS = (
    (
        "I am able to concentrate during class.",
        AssessmentQuestion.QuestionType.LIKERT,
        ["Strongly Disagree", "Disagree", "Neutral", "Agree", "Strongly Agree"],
        None,
        0,
    ),
    (
        "I have someone at school I can talk to when I am upset.",
        AssessmentQuestion.QuestionType.LIKERT,
        ["Strongly Disagree", "Disagree", "Neutral", "Agree", "Strongly Agree"],
        None,
        0,
    ),
    (
        "Classmates treat me with respect.",
        AssessmentQuestion.QuestionType.MULTIPLE_CHOICE,
        ["Almost always", "Often", "Sometimes", "Rarely", "Never"],
        "Almost always",
        2,
    ),
    (
        "I get enough rest and sleep on school nights.",
        AssessmentQuestion.QuestionType.TRUE_FALSE,
        None,
        "True",
        2,
    ),
    (
        "Homework assignments are manageable for me.",
        AssessmentQuestion.QuestionType.MULTIPLE_CHOICE,
        ["Yes", "Somewhat", "No"],
        "Yes",
        2,
    ),
    (
        "I feel safe travelling to and from school.",
        AssessmentQuestion.QuestionType.MULTIPLE_CHOICE,
        ["Yes", "Sometimes", "No"],
        "Yes",
        2,
    ),
    (
        "I know who to contact at Guidance when I need help.",
        AssessmentQuestion.QuestionType.TRUE_FALSE,
        None,
        "True",
        2,
    ),
)

#: Roster indices with a completed wellness assessment result, including
#: student.qa so the student-facing dashboard has a result to show.
#: PH11.9 adds the second parent.qa child who sits in the assessment's target
#: section. The third child is in Grade 9 Mabini and is deliberately left out:
#: the assessment targets Grade 8 Bonifacio only, and a result from an
#: untargeted student would contradict the targeting contract
#: ``AssessmentResultViewSet.perform_create`` enforces on submission.
WELLNESS_RESULT_STUDENTS = (
    1, 8, 11, 14, 21, QA_STUDENT_ROSTER_INDEX, QA_STUDENT_ROSTER_INDEX + 1,
    30, 36, 42, 61, 74,
)

#: Chance that an auto-gradable item is answered correctly.
WELLNESS_CORRECT_RATE = 0.8

#: Days from now until the wellness assessment deadline. Assessment.clean()
#: rejects a deadline that is not in the future, so this is refreshed on every
#: run rather than pinned to a fixed date.
WELLNESS_DEADLINE_DAYS = 21
WELLNESS_TIME_LIMIT_MINUTES = 20

#: parent.qa's children, as roster indices. Includes student.qa so the QA
#: parent login exercises the frontend's child-selection behaviour, and spans
#: two sections (Grade 8 Bonifacio and Grade 9 Mabini) so the parent's
#: section-scoped querysets are exercised across sections too.
QA_PARENT_CHILDREN = (
    QA_STUDENT_ROSTER_INDEX,
    QA_STUDENT_ROSTER_INDEX + 1,
    2 * STUDENTS_PER_SECTION,
)

#: Synthetic parents (one-based) that also take a second child, so multi-child
#: scoping is testable without using a QA login.
SHARED_SECOND_CHILD_PARENTS = (6, 16, 26, 36, 46)


class Command(BaseCommand):
    help = (
        "Seed the realistic Philippine JHS QA dataset (AEGIS Integrated School, "
        "SY 2026-2027): 100 students, 100 parent accounts, 4 sections, 32 "
        "subject assignments, finalized grades, attendance, and the guidance "
        "records the Guidance pages need. Idempotent."
    )

    def __init__(self, *args, **options):
        super().__init__(*args, **options)
        self._created = Counter()
        self._reused = Counter()
        self._today = timezone.localdate()

    # -- small helpers ---------------------------------------------------

    @staticmethod
    def _rand(*parts):
        """
        A private RNG namespaced by a stable record key.

        The namespace comes from the record's own identity rather than from call
        order, so adding or reordering a seeding phase can never shift another
        record's numbers.
        """
        return random.Random("|".join((RANDOM_SEED, *(str(part) for part in parts))))

    @staticmethod
    def _first_name(index, salt=1):
        return FIRST_NAMES[(index * 7 + salt) % len(FIRST_NAMES)]

    @staticmethod
    def _surname(index, salt=3):
        """Two surnames where they differ, which is the usual PH convention."""
        first = SURNAMES[(index * 11 + salt) % len(SURNAMES)]
        second = SURNAMES[(index * 17 + salt) % len(SURNAMES)]
        if first == second:
            second = SURNAMES[(index * 17 + salt + 1) % len(SURNAMES)]
        return f"{first} {second}"

    @staticmethod
    def _phone(index):
        return f"{PHONE_PREFIX}{index + 1:06d}"

    def _address(self, index):
        barangay, city, province = LOCALITIES[index % len(LOCALITIES)]
        return f"{100 + (index % 900)} Rizal St., Barangay {barangay}, {city}, {province}"

    def _school_days(self, weeks):
        """
        The Mon-Fri days of the ``weeks`` most recently completed school weeks.

        Every day returned is strictly before today, which is what
        ``AttendanceRecord.clean()`` requires, and the window only advances once
        a whole week has passed.
        """
        this_monday = self._today - timedelta(days=self._today.weekday())
        first_monday = this_monday - timedelta(weeks=weeks)
        days = []
        for week in range(weeks):
            monday = first_monday + timedelta(weeks=week)
            days.extend(monday + timedelta(days=offset) for offset in range(5))
        return days

    @staticmethod
    def _letter_and_remark(score):
        for minimum, letter, remark in GRADE_SCALE:
            if score >= minimum:
                return letter, remark
        return "F", "Failed"

    @staticmethod
    def _decimal(value):
        return Decimal(str(round(float(value), 2)))

    def _tally(self, label, created):
        (self._created if created else self._reused)[label] += 1

    def _get_or_create(self, model, label, lookup, defaults):
        obj, created = model.objects.get_or_create(**lookup, defaults=defaults)
        self._tally(label, created)
        return obj

    def _update_or_create(self, model, label, lookup, defaults):
        obj, created = model.objects.update_or_create(**lookup, defaults=defaults)
        self._tally(label, created)
        return obj

    def _apply_existing(self, obj, label, fields):
        """
        Write ``fields`` onto an existing row, saving only what changed.

        Used for the guidance models whose natural key is a column value that
        drifts with "today" (a consultation's ``session_date``, an
        intervention's ``plan_start_date``). Looking the row up by its stable
        identity and then refreshing its date keeps repeated runs idempotent
        without inventing a second row.
        """
        changed = [name for name, value in fields.items() if getattr(obj, name) != value]
        if not changed:
            self._tally(label, False)
            return obj
        for name, value in fields.items():
            setattr(obj, name, value)
        obj.save()
        self._tally(label, False)
        return obj

    # -- QA login resolution ---------------------------------------------

    def _qa_users(self, User):
        """
        Resolve the QA logins this dataset attaches records to.

        ``provision_qa_accounts`` owns creating these accounts. This command
        refuses to run without them rather than inventing logins and a password
        it does not own.
        """
        expected = (
            ("faculty", QA_FACULTY_EMAIL),
            ("guidance", QA_GUIDANCE_EMAIL),
            ("student", QA_STUDENT_EMAIL),
            ("parent", QA_PARENT_EMAIL),
        )
        users = {}
        for role, email in expected:
            user = User.objects.filter(email=email).first()
            if user is None:
                raise CommandError(
                    f"QA login {email} does not exist. Run "
                    "`python manage.py provision_qa_accounts` first; this "
                    "command never creates logins or passwords."
                )
            if user.role != role:
                raise CommandError(
                    f"QA login {email} has role '{user.role}', expected "
                    f"'{role}'. Re-run `provision_qa_accounts`."
                )
            users[role] = user
        return users

    def _name_qa_login(self, user, index, salt):
        """
        Give a QA login a realistic synthetic display name.

        ``provision_qa_accounts`` writes a placeholder ("QA Student"); the
        dataset needs a plausible identity for the UI to read naturally. Only
        names and a phone number change -- role, email, is_active and
        must_change_password are left exactly as provisioning set them.
        """
        first = self._first_name(index, salt)
        last = self._surname(index, salt + 2)
        updates = []
        if user.first_name != first:
            user.first_name = first
            updates.append("first_name")
        if user.last_name != last:
            user.last_name = last
            updates.append("last_name")
        phone = self._phone(index)
        if user.phone_number != phone:
            user.phone_number = phone
            updates.append("phone_number")
        if updates:
            user.save(update_fields=[*updates, "updated_at"])

    # -- phases -----------------------------------------------------------

    def handle(self, *args, **options):
        User = get_user_model()
        self.stdout.write(
            f"Seeding the {SCHOOL_NAME} QA dataset ({ACADEMIC_YEAR_NAME}). "
            f"Today is {self._today}."
        )

        with transaction.atomic():
            qa_users = self._qa_users(User)
            academic_year = self._seed_academic_year()
            grade_levels = self._seed_grade_levels()
            subjects = self._seed_subjects(grade_levels)
            grading_periods = self._seed_grading_periods(academic_year)
            # Must run after the current terms exist (it re-points onto them)
            # and before any grade is written (so grades land on terms).
            self._retire_legacy_grading_periods(academic_year, grading_periods)
            staff = self._seed_faculty(User, grade_levels)
            sections = self._seed_sections(academic_year, grade_levels, staff)
            assignments = self._seed_subject_assignments(academic_year, sections, subjects, staff)
            self._seed_schedules(assignments)
            students = self._seed_students(User, grade_levels, sections)
            self._seed_enrollments(academic_year, students)
            profiles = self._seed_profiles(qa_users, staff, students)
            self._seed_grades(students, assignments, grading_periods)
            self._seed_attendance(students, staff)
            self._seed_guidance(students, profiles, staff)
            self._seed_assessments(qa_users, profiles, students, sections, grading_periods)

        self._report()

    def _seed_academic_year(self):
        academic_year = AcademicYear.objects.filter(name=ACADEMIC_YEAR_NAME).first()
        created = academic_year is None
        if created:
            academic_year = AcademicYear(name=ACADEMIC_YEAR_NAME)
        academic_year.start_date = ACADEMIC_YEAR_START
        academic_year.end_date = ACADEMIC_YEAR_END
        academic_year.is_current = True
        academic_year.save()
        self._tally("AcademicYear", created)

        # AcademicYearSerializer allows exactly one current year. Demote any
        # other rather than leaving two "current" years, which would make
        # _faculty_section_ids() and attendance writes non-deterministic.
        for other in AcademicYear.objects.exclude(pk=academic_year.pk).filter(is_current=True):
            other.is_current = False
            other.save(update_fields=["is_current", "updated_at"])
            self.stdout.write(
                f"  NOTE  pre-existing academic year {other.name!r} was demoted "
                f"from is_current so {ACADEMIC_YEAR_NAME!r} is the only current year."
            )
        return academic_year

    def _seed_grade_levels(self):
        grade_levels = {}
        for _, level_number, level_name in SECTION_PLAN:
            grade_level, created = GradeLevel.objects.get_or_create(
                level_number=level_number, defaults={"name": level_name}
            )
            if not created and grade_level.name != level_name:
                grade_level.name = level_name
                grade_level.save(update_fields=["name"])
            self._tally("GradeLevel", created)
            grade_levels[level_number] = grade_level
        return grade_levels

    def _seed_subjects(self, grade_levels):
        subjects = {}
        for level_number, grade_level in grade_levels.items():
            for code, name in LEARNING_AREAS:
                subjects[(level_number, code)] = self._get_or_create(
                    Subject,
                    "Subject",
                    {"code": f"{code}-{level_number}"},
                    {"name": name, "grade_level": grade_level},
                )
        return subjects

    def _seed_grading_periods(self, academic_year):
        """
        Create the three terms.

        Keyed on (academic_year, name), deliberately not on ``order``: the
        superseded calendar also used orders 1-4, so an order-based lookup would
        silently adopt the legacy "1st Quarter" row as Term 1 and leave its name
        and dates stale. ``name`` is the seed's stable identity for a term.
        """
        periods = []
        for name, order, start, end in GRADING_PERIODS:
            period, created = GradingPeriod.objects.get_or_create(
                academic_year=academic_year,
                name=name,
                defaults={"order": order, "start_date": start, "end_date": end},
            )
            self._tally("GradingPeriod", created)
            stale = (
                period.order != order
                or period.start_date != start
                or period.end_date != end
            )
            if stale:
                period.order = order
                period.start_date = start
                period.end_date = end
                period.save(
                    update_fields=["order", "start_date", "end_date"]
                )
            periods.append(period)
        return periods

    @staticmethod
    def _superseding_term(legacy_start, legacy_end):
        """
        The current term that supersedes a legacy period.

        Matched on the legacy period's mid-point, so a quarter that straddles a
        new term boundary resolves to the term holding the bulk of it. Returns
        None when no current term contains the mid-point.
        """
        midpoint = legacy_start + (legacy_end - legacy_start) / 2
        for name, _order, start, end in GRADING_PERIODS:
            if start <= midpoint <= end:
                return name
        return None

    def _retire_legacy_grading_periods(self, academic_year, periods):
        """
        Retire grading periods written by the superseded four-quarter calendar.

        A database seeded before the move to three terms holds "1st Quarter" ..
        "4th Quarter" on this seed's academic year, with up to 1600 Grade rows
        pointing at them (``Grade.grading_period`` is ``PROTECT``) and possibly
        an Assessment pointing at one (``Assessment.quarter`` is ``SET_NULL``).
        Leaving them would give the school seven periods with duplicate orders
        and duplicate names in every period dropdown, so they are collapsed onto
        the terms that supersede them and then deleted.

        Safety properties:

        * Scope is an exact four-way match on (academic_year, name, order,
          start_date, end_date) against ``LEGACY_GRADING_PERIODS``. A period a
          school or tester created, or a legacy row whose dates were edited, is
          detected, reported and left untouched.
        * Grades are re-pointed, never dropped, except where the schema allows
          only one grade per (student, subject_assignment, period) and a term
          therefore has to absorb two legacy quarters. Newest legacy quarter
          wins, so each term keeps the most recent grades available for it.
        * ``period.delete()`` still goes through ``PROTECT``: if any row the
          seed does not own were to reference one of these periods, the delete
          raises and the surrounding ``transaction.atomic()`` rolls the whole
          run back rather than leaving a partial migration.
        """
        terms_by_name = {period.name: period for period in periods}
        legacy = []
        for name, order, start, end in LEGACY_GRADING_PERIODS:
            period = GradingPeriod.objects.filter(
                academic_year=academic_year,
                name=name,
                order=order,
                start_date=start,
                end_date=end,
            ).first()
            if period is not None:
                legacy.append(period)

        # Newest first, so the most recent legacy quarter claims the term.
        retired = []
        for period in sorted(legacy, key=lambda row: row.order, reverse=True):
            target = terms_by_name.get(
                self._superseding_term(period.start_date, period.end_date)
            )
            if target is None:
                self.stdout.write(
                    f"  NOTE  legacy grading period {period.name!r} does not "
                    f"fall inside any current term and was left in place."
                )
                continue

            Assessment.objects.filter(quarter=period).update(quarter=target)

            moved = 0
            superseded = 0
            for grade in list(Grade.objects.filter(grading_period=period)):
                twin = (
                    Grade.objects.filter(
                        student=grade.student,
                        subject_assignment=grade.subject_assignment,
                        grading_period=target,
                    )
                    .exclude(pk=grade.pk)
                    .first()
                )
                if twin is None:
                    grade.grading_period = target
                    grade.save(update_fields=["grading_period", "updated_at"])
                    moved += 1
                else:
                    superseded += 1
                    grade.delete()

            period.delete()
            retired.append(period.pk)
            self._tally("Legacy GradingPeriod retired", True)
            self.stdout.write(
                f"  NOTE  retired superseded grading period {period.name!r} "
                f"-> {target.name!r} (grades moved={moved} "
                f"superseded={superseded})."
            )

        # Any other period on this academic year is neither a current term nor a
        # row the seed retired, so it belongs to someone else. Report it and
        # leave it alone.
        current_names = [name for name, *_ in GRADING_PERIODS]
        for period in GradingPeriod.objects.filter(
            academic_year=academic_year
        ).exclude(name__in=current_names):
            if period.pk in retired:
                continue
            self.stdout.write(
                f"  NOTE  pre-existing grading period {period.name!r} "
                f"(order={period.order}) on {academic_year.name} is not this "
                f"seed's superseded calendar and was left untouched."
            )

    def _seed_faculty(self, User, grade_levels):
        """
        Create the teaching staff and resolve every (level, area) teacher slot.

        One teacher per (learning area, grade level) keeps SubjectAssignment
        ownership realistic. Grade 8's Filipino, English and ESP assignments
        belong to faculty.qa, who also advises Grade 8 -- Bonifacio.

        Returns a dict with the QA faculty profile, the synthetic roster keyed
        by email, the adviser per grade level, and the teacher per
        (level, area) slot.
        """
        qa_user = User.objects.get(email=QA_FACULTY_EMAIL)
        self._name_qa_login(qa_user, index=0, salt=11)
        qa_profile = self._get_or_create(
            FacultyProfile,
            "FacultyProfile",
            {"user": qa_user},
            {
                "employee_id": f"{QA_CODE_PREFIX}F001",
                "department": "Junior High School",
            },
        )

        roster = {}
        teacher_for = {}
        adviser_of = {}
        next_employee = 2
        for _, level_number, _ in SECTION_PLAN:
            for code, _ in LEARNING_AREAS:
                if level_number == 8 and code in QA_FACULTY_SUBJECT_CODES:
                    teacher_for[(level_number, code)] = qa_profile
                    continue
                email = f"{QA_EMAIL_PREFIX}faculty-{next_employee:03d}@{QA_EMAIL_DOMAIN}"
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "first_name": self._first_name(next_employee, 2),
                        "last_name": self._surname(next_employee, 4),
                        "role": User.Role.FACULTY,
                        "phone_number": self._phone(400 + next_employee),
                        "address": self._address(next_employee),
                    },
                )
                self._tally("User (synthetic faculty)", created)
                if created:
                    # Synthetic staff are never logins. An unusable password
                    # means no credential for them exists anywhere.
                    user.set_unusable_password()
                    user.save(update_fields=["password"])
                profile = self._get_or_create(
                    FacultyProfile,
                    "FacultyProfile",
                    {"user": user},
                    {
                        "employee_id": f"{QA_CODE_PREFIX}F{next_employee:03d}",
                        "department": "Junior High School",
                    },
                )
                roster[email] = profile
                teacher_for[(level_number, code)] = profile
                if code == ADVISER_AREA_CODE:
                    adviser_of[level_number] = profile
                next_employee += 1

        # faculty.qa advises Grade 8 -- Bonifacio.
        adviser_of[8] = qa_profile
        return {
            "qa": qa_profile,
            "roster": roster,
            "adviser_of": adviser_of,
            "teacher_for": teacher_for,
        }

    def _seed_sections(self, academic_year, grade_levels, staff):
        sections = {}
        for name, level_number, _ in SECTION_PLAN:
            section = self._get_or_create(
                Section,
                "Section",
                {
                    "name": name,
                    "grade_level": grade_levels[level_number],
                    "academic_year": academic_year,
                },
                {"adviser": staff["adviser_of"][level_number]},
            )
            if section.adviser_id != staff["adviser_of"][level_number].id:
                section.adviser = staff["adviser_of"][level_number]
                section.save(update_fields=["adviser"])
            sections[level_number] = section

        # Mirror each adviser onto FacultyProfile so both directions of the
        # model (Section.adviser and FacultyProfile.advisory_section) agree.
        for level_number, profile in staff["adviser_of"].items():
            if profile.is_adviser and profile.advisory_section_id == sections[level_number].id:
                continue
            profile.is_adviser = True
            profile.advisory_section = sections[level_number]
            profile.save(update_fields=["is_adviser", "advisory_section", "updated_at"])
        return sections

    def _seed_subject_assignments(self, academic_year, sections, subjects, staff):
        assignments = {}
        for _, level_number, _ in SECTION_PLAN:
            for code, _ in LEARNING_AREAS:
                assignment = self._get_or_create(
                    SubjectAssignment,
                    "SubjectAssignment",
                    {
                        "subject": subjects[(level_number, code)],
                        "section": sections[level_number],
                        "academic_year": academic_year,
                    },
                    {"faculty": staff["teacher_for"][(level_number, code)]},
                )
                assignments.setdefault(level_number, {})[code] = assignment
        return assignments

    def _seed_schedules(self, assignments):
        """
        One weekly class period per (section, learning area).

        The Cycle 1 QA log recorded TC-STU-04 as "missing feature: class
        schedule page is not available in the system navigation". The page now
        exists, and this gives it rows to display: the dataset never wrote a
        ``Schedule`` at all, so a student verifying that the timetable "matches
        the student's actual enrollment" against an empty table would be
        verifying nothing.

        The slot table is deliberately collision-free within a section — the
        day comes from ``index % 5`` and the slot from ``index // 5``, so the
        eight learning areas land on eight distinct (day, start) pairs — and
        identical across sections, the way a shared period structure works.
        ``Schedule.clean()`` requires ``end_time > start_time``, which both
        slots satisfy.
        """
        days = ("mon", "tue", "wed", "thu", "fri")
        slots = ((time(7, 30), time(8, 30)), (time(9, 0), time(10, 0)))
        for level_number, areas in assignments.items():
            for index, (code, _name) in enumerate(LEARNING_AREAS):
                start, end = slots[index // len(days)]
                self._get_or_create(
                    Schedule,
                    "Schedule",
                    {
                        "subject_assignment": areas[code],
                        "day_of_week": days[index % len(days)],
                        "start_time": start,
                    },
                    {
                        "end_time": end,
                        "room": f"R{level_number}0{(index // len(days)) + 1}",
                    },
                )
        return assignments

    def _student_email(self, roster_index):
        if roster_index == QA_STUDENT_ROSTER_INDEX:
            return QA_STUDENT_EMAIL
        return f"{QA_EMAIL_PREFIX}student-{roster_index + 1:03d}@{QA_EMAIL_DOMAIN}"

    def _seed_students(self, User, grade_levels, sections):
        students = []
        for roster_index in range(TOTAL_STUDENTS):
            section_slot = roster_index // STUDENTS_PER_SECTION
            _, level_number, _ = SECTION_PLAN[section_slot]
            section = sections[level_number]
            grade_level = grade_levels[level_number]
            email = self._student_email(roster_index)

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": self._first_name(roster_index),
                    "last_name": self._surname(roster_index),
                    "role": User.Role.STUDENT,
                    "phone_number": None,
                    "address": self._address(roster_index),
                },
            )
            self._tally("User (synthetic student)", created)
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])

            # JHS cohort ages: roughly 12-13 in Grade 7 rising to 15-16 in
            # Grade 10.
            birth_year = 2012 + section_slot
            date_of_birth = date(
                birth_year, 1 + (roster_index * 5) % 12, 1 + (roster_index * 7) % 28
            )
            student, student_created = StudentProfile.objects.get_or_create(
                user=user,
                defaults={
                    "student_id": f"{QA_CODE_PREFIX}S{roster_index + 1:04d}",
                    "grade_level": grade_level,
                    "section": section,
                    "date_of_birth": date_of_birth,
                    "enrollment_date": ACADEMIC_YEAR_START,
                    "is_active": True,
                },
            )
            self._tally("StudentProfile", student_created)
            if (
                student.grade_level_id != grade_level.id
                or student.section_id != section.id
                or not student.is_active
            ):
                student.grade_level = grade_level
                student.section = section
                student.is_active = True
                student.save(
                    update_fields=["grade_level", "section", "is_active", "updated_at"]
                )
            students.append(student)
        return students

    def _seed_enrollments(self, academic_year, students):
        for student in students:
            self._get_or_create(
                Enrollment,
                "Enrollment",
                {
                    "student": student,
                    "section": student.section,
                    "academic_year": academic_year,
                },
                {"date_enrolled": ACADEMIC_YEAR_START, "is_active": True},
            )

    def _seed_profiles(self, qa_users, staff, students):
        """Build the guidance, parent and parent-child link records."""
        User = get_user_model()
        profiles = {"faculty": staff["qa"]}

        guidance_user = qa_users["guidance"]
        self._name_qa_login(guidance_user, index=3, salt=13)
        profiles["guidance"] = self._get_or_create(
            GuidanceProfile,
            "GuidanceProfile",
            {"user": guidance_user},
            {
                "employee_id": f"{QA_CODE_PREFIX}G001",
                "specialization": "Junior High School Guidance",
            },
        )

        # student.qa must be one of the seeded students, in Grade 8 --
        # Bonifacio. Assert rather than trust: if the roster changes under us,
        # stop instead of silently seeding a mislabelled student.
        student_profile = students[QA_STUDENT_ROSTER_INDEX]
        if student_profile.user.email != QA_STUDENT_EMAIL:
            raise CommandError(
                f"Roster index {QA_STUDENT_ROSTER_INDEX} is "
                f"{student_profile.user.email}, expected {QA_STUDENT_EMAIL}."
            )
        if student_profile.grade_level.level_number != 8:
            raise CommandError(
                f"{QA_STUDENT_EMAIL} is in "
                f"{student_profile.grade_level.name}, expected Grade 8."
            )
        # student.qa already exists (provision_qa_accounts created it with a
        # placeholder name), so _seed_students' get_or_create never applied the
        # roster identity. Re-apply the exact name _seed_students derives for
        # this index, using salt=1 to match it.
        self._name_qa_login(student_profile.user, QA_STUDENT_ROSTER_INDEX, salt=1)
        profiles["student"] = student_profile

        parent_user = qa_users["parent"]
        self._name_qa_login(parent_user, index=6, salt=17)
        profiles["parent"] = self._get_or_create(
            ParentProfile,
            "ParentProfile",
            {"user": parent_user},
            {"relationship_to_student": ParentProfile.RelationshipType.MOTHER},
        )

        relationships = (
            ParentProfile.RelationshipType.MOTHER,
            ParentProfile.RelationshipType.FATHER,
            ParentProfile.RelationshipType.GUARDIAN,
        )
        for offset in range(TOTAL_STUDENTS):
            email = f"{QA_EMAIL_PREFIX}parent-{offset + 1:03d}@{QA_EMAIL_DOMAIN}"
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": self._first_name(offset, 3),
                    "last_name": self._surname(offset, 5),
                    "role": User.Role.PARENT,
                    "phone_number": self._phone(600 + offset),
                    "address": self._address(offset),
                },
            )
            self._tally("User (synthetic parent)", created)
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            profile = self._get_or_create(
                ParentProfile,
                "ParentProfile",
                {"user": user},
                {"relationship_to_student": relationships[offset % len(relationships)]},
            )
            self._get_or_create(
                ParentStudentLink,
                "ParentStudentLink",
                {"parent": profile, "student": students[offset]},
                {"is_primary": True},
            )

        # A few synthetic parents take a second child, so multi-child scoping is
        # testable without spending a QA login on it.
        for parent_number in SHARED_SECOND_CHILD_PARENTS:
            email = f"{QA_EMAIL_PREFIX}parent-{parent_number:03d}@{QA_EMAIL_DOMAIN}"
            profile = ParentProfile.objects.get(user__email=email)
            self._get_or_create(
                ParentStudentLink,
                "ParentStudentLink",
                {"parent": profile, "student": students[parent_number]},
                {"is_primary": False},
            )

        for position, child_index in enumerate(QA_PARENT_CHILDREN):
            self._get_or_create(
                ParentStudentLink,
                "ParentStudentLink",
                {"parent": profiles["parent"], "student": students[child_index]},
                {"is_primary": position == 0},
            )
        return profiles

    def _seed_grades(self, students, assignments, grading_periods):
        """
        Write grades for the terms that have actually opened.

        ``Grade`` has no future-date validation, but a finalized score for a
        term that has not happened would be impossible data, so each period's
        state is derived from its own dates against today:

        * ``start_date > today`` -> no rows at all
        * ``end_date < today``   -> finalized, which is what every student and
          parent dashboard plus the guidance grade table require
        * otherwise              -> the term is open, so rows stay
          draft/submitted and appear as pending work on the faculty dashboard
        """
        at_risk = {index for index, *_ in RISK_ALERT_STUDENTS}

        for roster_index, student in enumerate(students):
            level_number = student.grade_level.level_number
            rng = self._rand("grade", student.student_id)
            # One stable ability per student, nudged down for students carrying
            # a risk alert so the guidance and academic data agree.
            ability = rng.gauss(SCORE_MEAN, SCORE_SPREAD)
            if roster_index in at_risk:
                ability -= AT_RISK_ABILITY_PENALTY

            for code, _ in LEARNING_AREAS:
                assignment = assignments[level_number][code]
                for period in grading_periods:
                    if period.start_date > self._today:
                        continue
                    closed = period.end_date < self._today
                    score = min(
                        SCORE_CEILING,
                        max(SCORE_FLOOR, ability + rng.gauss(0.0, SUBJECT_NOISE)),
                    )
                    letter, remark = self._letter_and_remark(score)
                    if closed:
                        status = Grade.StatusChoices.FINALIZED
                    elif rng.random() < OPEN_TERM_SUBMIT_RATE:
                        status = Grade.StatusChoices.SUBMITTED
                    else:
                        status = Grade.StatusChoices.DRAFT

                    grade, created = Grade.objects.get_or_create(
                        student=student,
                        subject_assignment=assignment,
                        grading_period=period,
                        defaults={
                            "score": self._decimal(score),
                            "letter_grade": letter,
                            "remarks": remark,
                            "encoded_by": assignment.faculty,
                            "status": status,
                        },
                    )
                    self._tally("Grade", created)
                    if not created and grade.status != status:
                        # The term closed since the last run: advance this
                        # row in place rather than writing a second one.
                        grade.status = status
                        grade.save(update_fields=["status", "updated_at"])

    def _seed_attendance(self, students, staff):
        """Three most recently completed school weeks, recorded by the adviser."""
        school_days = self._school_days(ATTENDANCE_WEEKS)
        for student in students:
            section = student.section
            recorder = staff["adviser_of"][section.grade_level.level_number]
            rng = self._rand("attendance", student.student_id)
            for day in school_days:
                roll = rng.random()
                if roll < ATTENDANCE_PRESENT_CUTOFF:
                    status = AttendanceRecord.Status.PRESENT
                elif roll < ATTENDANCE_LATE_CUTOFF:
                    status = AttendanceRecord.Status.LATE
                else:
                    status = AttendanceRecord.Status.ABSENT
                self._get_or_create(
                    AttendanceRecord,
                    "AttendanceRecord",
                    {"student": student, "date": day},
                    {"section": section, "status": status, "recorded_by": recorder},
                )

    def _seed_guidance(self, students, profiles, staff):
        counselor = profiles["guidance"]
        now = timezone.now()

        # -- RiskAlert: source="manual", risk_score_ref=None -----------------
        # Byte-for-byte what POST /api/v1/guidance/risk-alerts/ writes. No
        # RiskScore is invented behind these rows.
        for roster_index, level, status, factors in RISK_ALERT_STUDENTS:
            student = students[roster_index]
            generated_at = now - timedelta(days=30 - roster_index % 12)
            fields = {
                "risk_level": level,
                "risk_factors": list(factors),
                "status": status,
                "assigned_counselor": counselor,
                "generated_at": generated_at,
                "risk_score_ref": None,
            }
            alert = RiskAlert.objects.filter(
                student=student, source=RiskAlert.Source.MANUAL
            ).order_by("created_at").first()
            if alert is not None:
                self._apply_existing(alert, "RiskAlert", fields)
                continue
            RiskAlert.objects.create(
                student=student, source=RiskAlert.Source.MANUAL, **fields
            )
            self._tally("RiskAlert", True)

        # -- ConsultationRecord: natural key is (student, session_type) -------
        for roster_index, session_type, priority, status, categories, days_ago, next_in in CONSULTATIONS:
            student = students[roster_index]
            defaults = {
                "counselor": counselor,
                "session_date": self._today - timedelta(days=days_ago),
                "session_time": time(9, 0),
                "concern_categories": list(categories),
                "session_notes": (
                    f"Synthetic QA consultation for the {ACADEMIC_YEAR_NAME} "
                    f"Guidance Office. Covered: {', '.join(categories)}."
                ),
                "recommendations": (
                    "Synthetic QA recommendation: continue the scheduled "
                    "follow-up and coordinate with the class adviser."
                ),
                "next_session_date": (
                    self._today + timedelta(days=next_in) if next_in else None
                ),
                "priority_level": priority,
                "status": status,
            }
            record = ConsultationRecord.objects.filter(
                student=student, session_type=session_type
            ).first()
            if record is None:
                ConsultationRecord.objects.create(
                    student=student, session_type=session_type, **defaults
                )
                self._tally("ConsultationRecord", True)
            else:
                self._apply_existing(record, "ConsultationRecord", defaults)

        # -- Intervention + steps + progress note -----------------------------
        for roster_index, status, days_since_start, review_in, steps in INTERVENTIONS:
            student = students[roster_index]
            plan_start = self._today - timedelta(days=days_since_start)
            alert = RiskAlert.objects.filter(
                student=student, source=RiskAlert.Source.MANUAL
            ).first()
            defaults = {
                "assigned_counselor": counselor,
                "risk_alert": alert,
                "plan_start_date": plan_start,
                "target_review_date": (
                    self._today + timedelta(days=review_in) if review_in else None
                ),
                "status": status,
            }
            intervention = Intervention.objects.filter(student=student).first()
            if intervention is None:
                intervention = Intervention.objects.create(student=student, **defaults)
                self._tally("Intervention", True)
            else:
                intervention = self._apply_existing(
                    intervention, "Intervention", defaults
                )

            for order, (title, description, step_status) in enumerate(steps, start=1):
                self._update_or_create(
                    InterventionStep,
                    "InterventionStep",
                    {"intervention": intervention, "order": order},
                    {"title": title, "description": description, "status": step_status},
                )

            # One progress note per intervention, keyed on the intervention:
            # ProgressNote has no natural key of its own and is a private
            # guidance record, so the seed owns every row on these plans.
            note_defaults = {
                "recorded_by": counselor,
                "note_text": (
                    "Synthetic QA progress note: step progress reviewed for the "
                    f"plan started on {plan_start.isoformat()}."
                ),
                "next_follow_up": now + timedelta(days=14),
            }
            note = ProgressNote.objects.filter(intervention=intervention).first()
            if note is None:
                ProgressNote.objects.create(intervention=intervention, **note_defaults)
                self._tally("ProgressNote", True)
            else:
                self._apply_existing(note, "ProgressNote", note_defaults)

        # -- BehavioralNote: natural key is (student, note_type, recorder) ----
        for roster_index, note_type, days_ago in BEHAVIORAL_NOTES:
            student = students[roster_index]
            recorder = staff["adviser_of"][student.grade_level.level_number]
            defaults = {
                "note_text": (
                    f"Synthetic QA behavioral note ({note_type}) recorded by the "
                    f"class adviser for {ACADEMIC_YEAR_NAME}."
                ),
                "date_recorded": self._today - timedelta(days=days_ago),
            }
            note = BehavioralNote.objects.filter(
                student=student, note_type=note_type, recorded_by=recorder
            ).first()
            if note is None:
                BehavioralNote.objects.create(
                    student=student,
                    recorded_by=recorder,
                    note_type=note_type,
                    **defaults,
                )
                self._tally("BehavioralNote", True)
            else:
                self._apply_existing(note, "BehavioralNote", defaults)

    def _seed_assessments(self, qa_users, profiles, students, sections, grading_periods):
        guidance_user = qa_users["guidance"]
        bonifacio = sections[8]

        assessment, created = Assessment.objects.get_or_create(
            title=WELLNESS_ASSESSMENT_TITLE,
            assessment_type=Assessment.AssessmentType.WELLNESS,
            created_by=guidance_user,
            defaults={
                "description": WELLNESS_ASSESSMENT_DESCRIPTION,
                "creator_role": Assessment.CreatorRole.GUIDANCE,
                "quarter": grading_periods[1],
                "is_published": True,
                "time_limit_minutes": WELLNESS_TIME_LIMIT_MINUTES,
                "deadline": timezone.now() + timedelta(days=WELLNESS_DEADLINE_DAYS),
            },
        )
        self._tally("Assessment", created)
        # Assessment.clean() rejects a deadline that is not in the future, so
        # push it out on every run rather than letting it go stale.
        if assessment.deadline <= timezone.now() + timedelta(days=1):
            assessment.deadline = timezone.now() + timedelta(days=WELLNESS_DEADLINE_DAYS)
            assessment.is_published = True
            assessment.save(update_fields=["deadline", "is_published", "updated_at"])

        if bonifacio not in assessment.target_sections.all():
            assessment.target_sections.add(bonifacio)
            self._tally("Assessment.target_sections link", True)
        else:
            self._tally("Assessment.target_sections link", False)

        questions = []
        for order, (text, qtype, options, correct, _points) in enumerate(
            WELLNESS_QUESTIONS, start=1
        ):
            question, created = AssessmentQuestion.objects.update_or_create(
                assessment=assessment,
                order=order,
                defaults={
                    "question_text": text,
                    "question_type": qtype,
                    "options": list(options) if options else None,
                    "correct_answer": correct,
                },
            )
            self._tally("AssessmentQuestion", created)
            questions.append((question, correct, _points))

        # Points come from the declared question table, so a seeded score can
        # never exceed the seeded total.
        auto_gradable = [row for row in questions if row[1] is not None]
        total_possible = float(sum(row[2] for row in auto_gradable))

        for roster_index in WELLNESS_RESULT_STUDENTS:
            student = students[roster_index]
            rng = self._rand("wellness", student.student_id)
            answers = {}
            earned = 0.0
            for question, correct, points in auto_gradable:
                if rng.random() < WELLNESS_CORRECT_RATE:
                    answers[str(question.id)] = correct
                    earned += points
                else:
                    answers[str(question.id)] = self._wrong_answer(question)
            percentage = (earned / total_possible * 100) if total_possible else 0.0
            self._update_or_create(
                AssessmentResult,
                "AssessmentResult",
                {"assessment": assessment, "student": student},
                {
                    "answers": answers,
                    "score": self._decimal(earned),
                    "total_possible": self._decimal(total_possible),
                    "percentage": self._decimal(percentage),
                    "status": AssessmentResult.Status.COMPLETED,
                },
            )

    @staticmethod
    def _wrong_answer(question):
        """A plausible wrong answer for an auto-gradable question."""
        if question.question_type == AssessmentQuestion.QuestionType.TRUE_FALSE:
            return "False" if question.correct_answer == "True" else "True"
        for option in question.options or []:
            if option != question.correct_answer:
                return option
        return "False"

    # -- reporting ---------------------------------------------------------

    def _report(self):
        labels = sorted(
            set(self._created) | set(self._reused),
            key=lambda name: (-(self._created[name] + self._reused[name]), name),
        )
        self.stdout.write("")
        self.stdout.write("QA dataset records written per model:")
        created_total = 0
        reused_total = 0
        for label in labels:
            created = self._created[label]
            reused = self._reused[label]
            created_total += created
            reused_total += reused
            self.stdout.write(f"  {label:32} created={created:<6} reused={reused}")
        self.stdout.write(f"  {'TOTAL':32} created={created_total:<6} reused={reused_total}")
        self.stdout.write("")
        self.stdout.write(
            "QA logins: faculty.qa advises Grade 8 Bonifacio and teaches its "
            "FIL/ENG/ESP; guidance.qa owns every consultation, intervention, "
            "risk alert and the wellness assessment; student.qa is "
            f"{QA_CODE_PREFIX}S0026 in Grade 8 Bonifacio; parent.qa has "
            f"{len(QA_PARENT_CHILDREN)} linked children. admin.qa is untouched "
            "-- AdminProfile is not required by any serializer, permission or "
            "view in this codebase."
        )
        self.stdout.write(
            "RiskScore was intentionally not seeded: it is written only by the "
            "ai_engine, exposes no API, and fabricating an explanation trace "
            "would be invented AI output. RiskAlert rows use source='manual' "
            "with risk_score_ref=None, exactly as the guidance API creates them."
        )
