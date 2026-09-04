"""
AEGIS — PH9.1 synthetic development data seed.

Creates realistic synthetic data (~200 students, 2-3 completed terms)
for development/demo purposes.

IMPORTANT:
  This is SYNTHETIC DEVELOPMENT DATA — NOT real school data.
  Do not label this as historical school data.
  Do not use for production.

Usage:
  python manage.py shell < scripts/seed_ph9_synthetic.py
  OR
  python scripts/seed_ph9_synthetic.py
"""

import os
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

# Ensure Django is configured
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
import django

django.setup()

from django.utils import timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NUM_STUDENTS = 200          # D5: preferred ~200
NUM_TERMS = 3               # D5: 2-3 completed terms
SUBJECTS_PER_GT = 8         # Subjects per grade level

random.seed(42)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def gen_name(i):
    first_names = [
        "Juan", "Maria", "Jose", "Ana", "Pedro", "Luz", "Ramon", "Elena",
        "Carlos", "Rosa", "Miguel", "Sofia", "Luis", "Carmen", "Andres",
        "Patricia", "Jorge", "Leticia", "Fernando", "Gloria", "Antonio",
        "Isabel", "Manuel", "Cristina", "Ricardo", "Teresa", "Daniel",
        "Veronica", "Eduardo", "Monica",
    ]
    last_names = [
        "Santos", "Reyes", "Cruz", "Bautista", "Ocampo", "Villanueva",
        "Aquino", "Mendoza", "De la Cruz", "Torres", "Ramos", "Garcia",
        "Domingo", "Navarro", "Salazar", "Castillo", "Vergara", "Perez",
        "Fernandez", "Gonzales", "Lopez", "Martinez", "Rodriguez", "Diaz",
        "Alvarez", "Morales", "Rivera", "Gomez", "Santiago", "Lazaro",
    ]
    return (
        f"{random.choice(first_names)}",
        f"{random.choice(last_names)} {random.choice(last_names)}",
    )

# ---------------------------------------------------------------------------
# Main seed logic
# ---------------------------------------------------------------------------

def run():
    from apps.academics.models import (
        AcademicYear, GradeLevel, Section, Subject,
        SubjectAssignment, GradingPeriod, Enrollment, Grade,
    )
    from apps.accounts.models import (
        User, StudentProfile, FacultyProfile, ParentProfile,
        ParentStudentLink, GuidanceProfile,
    )
    from apps.attendance.models import AttendanceRecord
    from apps.guidance.models import BehavioralNote, ConsultationRecord

    # --- Academic structure ---
    term_year = 2024
    academic_years = []
    for t in range(NUM_TERMS):
        start_year = term_year + t
        yr = AcademicYear.objects.create(
            name=f"{start_year}-{start_year+1}",
            start_date=date(start_year, 6, 10),
            end_date=date(start_year+1, 3, 25),
            is_current=(t == NUM_TERMS - 1),
        )
        academic_years.append(yr)

    grade_levels = []
    for level_num, level_name in [(7, "Grade 7"), (8, "Grade 8"), (9, "Grade 9"), (10, "Grade 10")]:
        gl, _ = GradeLevel.objects.get_or_create(
            level_number=level_num,
            defaults={"name": level_name},
        )
        grade_levels.append(gl)

    # Faculty for grade encoding and advisership
    faculty_users = []
    for i in range(12):
        fname, lname = gen_name(i + 100)
        email = f"faculty{i+1}@aegis.test"
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": fname,
                "last_name": lname,
                "role": "faculty",
                "username": f"faculty{i+1}",
            },
        )
        if not hasattr(user, "faculty_profile"):
            faculty_profile = FacultyProfile.objects.create(
                user=user,
                employee_id=f"FAC{i+1:04d}",
            )
        else:
            faculty_profile = user.faculty_profile
        faculty_users.append(faculty_profile)

    # Guidance
    gname, glname = gen_name(200)
    guser, _ = User.objects.get_or_create(
        email="guidance1@aegis.test",
        defaults={
            "first_name": gname,
            "last_name": glname,
            "role": "guidance",
            "username": "guidance1",
        },
    )
    if not hasattr(guser, "guidance_profile"):
        guidance_profile = GuidanceProfile.objects.create(
            user=guser,
            employee_id="GUID001",
            specialization="Counseling",
        )
    else:
        guidance_profile = guser.guidance_profile

    # Subjects per grade level
    subject_names = [
        ("ENG", "English"),
        ("MATH", "Mathematics"),
        ("SCI", "Science"),
        ("FIL", "Filipino"),
        ("AP", "Araling Panlipunan"),
        ("MAPEH", "MAPEH"),
        ("TLE", "TLE"),
        ("ESP", "Edukasyon sa Pagpapakatao"),
    ]
    subject_defs = []
    for gl in grade_levels:
        for code, name in subject_names:
            subj, _ = Subject.objects.get_or_create(
                code=f"{code}-{gl.level_number}",
                defaults={"name": name, "grade_level": gl},
            )
            subject_defs.append(subj)

    # Sections per grade level per term
    section_names = ["Einstein", "Newton", "Galileo", "Curie"]
    sections_by_year = {}
    for yr in academic_years:
        sections = []
        for gl in grade_levels:
            for sn in section_names[:2]:  # 2 sections per grade level
                sec, _ = Section.objects.get_or_create(
                    name=f"{sn}",
                    grade_level=gl,
                    academic_year=yr,
                    defaults={"adviser": random.choice(faculty_users)},
                )
                sections.append(sec)
        sections_by_year[yr.id] = sections

    # Grading periods per year
    grading_periods = {}
    for yr in academic_years:
        periods = []
        for idx, (pname, pstart, pend) in enumerate([
            ("1st Quarter", date(yr.start_date.year, 6, 10), date(yr.start_date.year, 8, 20)),
            ("2nd Quarter", date(yr.start_date.year, 9, 1), date(yr.start_date.year, 10, 30)),
            ("3rd Quarter", date(yr.start_date.year, 11, 10), date(yr.start_date.year, 12, 20)),
            ("4th Quarter", date(yr.end_date.year, 1, 6), date(yr.end_date.year, 3, 20)),
        ]):
            gp = GradingPeriod.objects.create(
                academic_year=yr,
                name=pname,
                order=idx + 1,
                start_date=pstart,
                end_date=pend,
            )
            periods.append(gp)
        grading_periods[yr.id] = periods

    # Subject assignments per section per year (reuse subject_defs by grade level)
    current_gp_count = 0

    # --- Students ---
    for i in range(NUM_STUDENTS):
        fname, lname = gen_name(i)
        email = f"student{i+1}@aegis.test"
        # Create user
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": fname,
                "last_name": lname,
                "role": "student",
                "username": f"student{i+1}",
            },
        )

        # Grade level progression: students progress through years
        gl_index = i % 4  # spread across grade levels
        student_gl = grade_levels[gl_index]

        # Create student profile
        student_profile, created = StudentProfile.objects.get_or_create(
            user=user,
            defaults={
                "student_id": f"STU{i+1:04d}",
                "grade_level": student_gl,
                "enrollment_date": academic_years[0].start_date,
            },
        )
        if not created and student_profile.grade_level is None:
            student_profile.grade_level = student_gl
            student_profile.save()

        # Enroll in each term
        base_enrollment_date = academic_years[0].start_date
        for term_idx, yr in enumerate(academic_years):
            # The grade level for this student in this term
            gl_for_term = grade_levels[min(gl_index + term_idx, 3)]

            # Find a section for this term matching this grade level
            section_pool = [
                s for s in sections_by_year[yr.id]
                if s.grade_level == gl_for_term
            ]
            if not section_pool:
                continue
            section = random.choice(section_pool)

            enrollment, _ = Enrollment.objects.get_or_create(
                student=student_profile,
                section=section,
                academic_year=yr,
                defaults={
                    "date_enrolled": base_enrollment_date + timedelta(days=5 * term_idx),
                    "is_active": True,
                },
            )

            # Update student's current grade level/section
            if term_idx == NUM_TERMS - 1:
                student_profile.grade_level = gl_for_term
                student_profile.section = section
                student_profile.save()

        # --- Grades for each term ---
        # Academic aptitude determines grade level quality
        aptitude = random.gauss(80, 10)  # base aptitude ~80
        aptitude = max(50, min(98, aptitude))

        # Per-subject strengths
        subject_strengths = {}
        for subj in subject_defs:
            if subj.grade_level == student_gl:
                subject_strengths[subj.code] = random.gauss(0, 5)

        for term_idx, yr in enumerate(academic_years):
            gl_for_term = grade_levels[min(gl_index + term_idx, 3)]
            period_list = grading_periods[yr.id]
            # Determine which periods are "completed" for this term
            # For simplicity, mark all 4 periods as completed except possibly
            # the last term's last period (incomplete)
            completed_periods = period_list
            if term_idx == NUM_TERMS - 1:
                # Leave last period incomplete for the current term
                completed_periods = period_list[:-1]

            # Get section for this student's term
            enroll = Enrollment.objects.filter(
                student=student_profile,
                academic_year=yr,
            ).first()
            if not enroll:
                continue
            section = enroll.section

            # Subject assignments for this section
            section_subjects = [
                s for s in subject_defs
                if s.grade_level == gl_for_term
            ]

            for subj in section_subjects:
                sa, _ = SubjectAssignment.objects.get_or_create(
                    subject=subj,
                    section=section,
                    academic_year=yr,
                    defaults={"faculty": random.choice(faculty_users)},
                )

                for gp in completed_periods:
                    # Grade varies around aptitude + subject strength + term drift
                    drift = -random.uniform(0, 3) * (NUM_TERMS - term_idx - 1)
                    grade_val = aptitude + subject_strengths.get(subj.code, 0) + drift
                    grade_val = max(50, min(100, grade_val))
                    grade_val = round(grade_val, 2)

                    Grade.objects.get_or_create(
                        student=student_profile,
                        subject_assignment=sa,
                        grading_period=gp,
                        defaults={
                            "score": Decimal(str(grade_val)),
                            "status": "finalized",
                            "encoded_by": sa.faculty,
                        },
                    )

            # --- Attendance for each term ---
            section_att = AttendanceRecord.objects.filter(
                student=student_profile,
                section=section,
                date__gte=yr.start_date,
            )
            if not section_att.exists():
                # ~85% attendance rate
                days_in_term = 100
                for d in range(days_in_term):
                    date_val = yr.start_date + timedelta(days=d)
                    if date_val.weekday() >= 5:  # skip weekends
                        continue
                    if date_val > date.today():
                        break
                    roll = random.random()
                    if roll < 0.85:
                        status = "present"
                    elif roll < 0.90:
                        status = "late"
                    else:
                        status = "absent"
                    AttendanceRecord.objects.create(
                        student=student_profile,
                        section=section,
                        date=date_val,
                        status=status,
                        recorded_by=random.choice(faculty_users),
                    )

        # --- Guidance aggregates (some students) ---
        # ~30% of students have consultations
        if random.random() < 0.30:
            num_consults = random.randint(1, 3)
            for c in range(num_consults):
                ConsultationRecord.objects.create(
                    student=student_profile,
                    counselor=guidance_profile,
                    session_date=academic_years[-1].start_date + timedelta(days=random.randint(1, 300)),
                    session_time=random.choice([
                        timezone.now().time().replace(hour=h, minute=0)
                        for h in range(8, 16)
                    ]),
                    session_type="individual_counseling",
                    concern_categories=random.choice([
                        ["academic"], ["behavioral"], ["emotional"],
                        ["academic", "emotional"],
                    ]),
                    session_notes="Synthetic consultation record.",
                    priority_level=random.choice(["low", "medium", "high"]),
                    status="completed",
                )

        # ~20% have behavioral notes
        if random.random() < 0.20:
            num_notes = random.randint(1, 2)
            for n in range(num_notes):
                BehavioralNote.objects.create(
                    student=student_profile,
                    recorded_by=random.choice(faculty_users),
                    note_type=random.choice(["positive", "warning", "incident"]),
                    note_text="Synthetic behavioral observation.",
                    date_recorded=academic_years[-1].start_date + timedelta(days=random.randint(1, 300)),
                )

    print(f"Seeded {NUM_STUDENTS} students across {NUM_TERMS} terms.")
    print(f"Academic years: {[str(y) for y in academic_years]}")


if __name__ == "__main__":
    run()
