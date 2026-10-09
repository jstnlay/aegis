"""
Tests for the ``seed_qa_dataset`` management command.

Covers the two properties that matter for a shared DEV/QA database:

* **Idempotency** -- running the command repeatedly must reuse every record
  rather than duplicating it, so a redeploy cannot inflate the dataset.
* **Role relationships** -- each QA login must end up holding exactly the
  records its pages read, because the backend scopes every queryset by those
  links. A guidance login with no GuidanceProfile sees an empty Consultations
  page, a parent with no ParentStudentLink sees no children, a student with no
  active enrollment has an inert dashboard.

Also pinned: the isolation boundary (nothing outside the ``qa-`` allowlist is
touched), the absence of any fabricated ``RiskScore``, the absence of future
attendance or behavioral dates, and that no synthetic account is a usable login.

The dataset is seeded once per class via ``setUpTestData``, whose class-level
transaction is rolled back afterwards, so the suite stays fast despite seeding
several thousand rows.
"""

import io
import os
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Count, F
from django.test import TestCase
from django.utils import timezone

from apps.accounts.management.commands import seed_qa_dataset as seed_module
from apps.accounts.management.commands.seed_qa_dataset import (
    ACADEMIC_YEAR_NAME,
    ATTENDANCE_WEEKS,
    QA_EMAIL_PREFIX,
    QA_PARENT_CHILDREN,
    QA_STUDENT_EMAIL,
    STUDENTS_PER_SECTION,
    TOTAL_STUDENTS,
    Command as SeedCommand,
)
from apps.accounts.models import (
    AdminProfile,
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
    RiskScore,
)

User = get_user_model()

#: A throwaway value that satisfies AUTH_PASSWORD_VALIDATORS. This is a test
#: fixture, not a credential for any environment.
TEST_QA_PASSWORD = "QaDataset-Fixture-9xKq"

#: A second throwaway value used to prove the seed never touches an unrelated
#: account's credential.
OUTSIDER_PASSWORD = "Outsider-Fixture-4481"

SEEDED_MODELS = (
    AcademicYear,
    GradeLevel,
    Section,
    Subject,
    SubjectAssignment,
    Schedule,
    GradingPeriod,
    Enrollment,
    Grade,
    StudentProfile,
    ParentProfile,
    ParentStudentLink,
    FacultyProfile,
    GuidanceProfile,
    AttendanceRecord,
    BehavioralNote,
    ConsultationRecord,
    Intervention,
    InterventionStep,
    ProgressNote,
    RiskAlert,
    Assessment,
    AssessmentQuestion,
    AssessmentResult,
)


def provision_qa_logins():
    """Run the sibling command so the seed has QA logins to attach records to."""
    with mock.patch.dict(os.environ, {"QA_SHARED_PASSWORD": TEST_QA_PASSWORD}):
        call_command("provision_qa_accounts", stdout=mock.MagicMock())


def run_seed(stdout=None):
    return call_command("seed_qa_dataset", stdout=stdout or mock.MagicMock())


def snapshot():
    """Total row count per seeded model."""
    return {model.__name__: model.objects.count() for model in SEEDED_MODELS}


class SeedDatasetTestCase(TestCase):
    """Seed once for the whole class; the class transaction rolls it back."""

    @classmethod
    def setUpTestData(cls):
        provision_qa_logins()
        cls.today = timezone.localdate()
        run_seed()

    # -- academic structure ------------------------------------------------

    def test_single_current_academic_year_named_for_the_school_year(self):
        current = AcademicYear.objects.filter(is_current=True)
        self.assertEqual(current.count(), 1)
        self.assertEqual(current.get().name, ACADEMIC_YEAR_NAME)

    def test_academic_year_uses_the_official_opening_and_closing_dates(self):
        year = AcademicYear.objects.get(is_current=True)
        self.assertEqual(year.start_date, date(2026, 6, 8))
        self.assertEqual(year.end_date, date(2027, 4, 8))

    def test_grading_periods_are_exactly_the_official_three_terms(self):
        """Pinned to the official three-term SY 2026-2027 basic education
        calendar, in the exact order, names and dates it prescribes."""
        year = AcademicYear.objects.get(is_current=True)
        periods = list(
            GradingPeriod.objects.filter(academic_year=year).order_by("order")
        )
        self.assertEqual(
            [
                (period.name, period.order, period.start_date, period.end_date)
                for period in periods
            ],
            [
                ("Term 1", 1, date(2026, 6, 8), date(2026, 9, 15)),
                ("Term 2", 2, date(2026, 9, 16), date(2026, 12, 18)),
                ("Term 3", 3, date(2027, 1, 4), date(2027, 4, 8)),
            ],
        )

    def test_no_term_4_and_no_quarter_rows_exist(self):
        """The superseded four-quarter calendar must not survive anywhere: the
        model is generic, so a leftover row would show up in every period
        dropdown with a duplicate order."""
        names = set(GradingPeriod.objects.values_list("name", flat=True))
        self.assertNotIn("Term 4", names)
        for legacy in ("1st Quarter", "2nd Quarter", "3rd Quarter", "4th Quarter"):
            self.assertNotIn(
                legacy,
                names,
                f"{legacy} is still present; the superseded calendar was not retired",
            )
        self.assertEqual(
            GradingPeriod.objects.filter(order__gt=3).count(),
            0,
            "a grading period with order > 3 exists",
        )

    def test_every_term_falls_inside_the_academic_year(self):
        year = AcademicYear.objects.get(is_current=True)
        for period in GradingPeriod.objects.all():
            self.assertGreaterEqual(period.start_date, year.start_date)
            self.assertLessEqual(period.end_date, year.end_date)
            self.assertLess(period.start_date, period.end_date)

    def test_enrollment_and_student_profile_use_the_opening_date(self):
        year = AcademicYear.objects.get(is_current=True)
        for student in StudentProfile.objects.all():
            self.assertEqual(student.enrollment_date, date(2026, 6, 8))
        for enrollment in Enrollment.objects.filter(academic_year=year):
            self.assertEqual(enrollment.date_enrolled, date(2026, 6, 8))

    def test_four_grade_levels_with_one_named_section_each(self):
        self.assertEqual(GradeLevel.objects.count(), len(seed_module.SECTION_PLAN))
        expected = {
            "Grade 7": "Rizal",
            "Grade 8": "Bonifacio",
            "Grade 9": "Mabini",
            "Grade 10": "Luna",
        }
        for grade_name, section_name in expected.items():
            grade_level = GradeLevel.objects.get(name=grade_name)
            self.assertEqual(
                Section.objects.get(grade_level=grade_level).name, section_name
            )

    def test_eight_deped_learning_areas_per_grade_level(self):
        """The subject list is the real DepEd JHS core curriculum, not invented."""
        areas = seed_module.LEARNING_AREAS
        self.assertEqual(len(areas), 8)
        for grade_level in GradeLevel.objects.all():
            codes = set(
                Subject.objects.filter(grade_level=grade_level).values_list(
                    "code", flat=True
                )
            )
            expected = {f"{code}-{grade_level.level_number}" for code, _ in areas}
            self.assertEqual(codes, expected)

    def test_subject_assignments_cover_every_section_and_learning_area(self):
        self.assertEqual(
            SubjectAssignment.objects.count(),
            len(seed_module.SECTION_PLAN) * len(seed_module.LEARNING_AREAS),
        )
        for section in Section.objects.all():
            self.assertEqual(
                SubjectAssignment.objects.filter(section=section).count(),
                len(seed_module.LEARNING_AREAS),
            )

    def test_every_section_has_a_weekly_period_for_each_learning_area(self):
        """
        TC-STU-04 (class schedule) reads `ScheduleViewSet`, and the dataset
        never wrote a ``Schedule`` at all before this seed phase — a student
        verifying that the timetable "matches the student's actual
        enrollment" against an empty table would be verifying nothing.
        """
        self.assertEqual(
            Schedule.objects.count(),
            len(seed_module.SECTION_PLAN) * len(seed_module.LEARNING_AREAS),
        )
        for section in Section.objects.all():
            rows = Schedule.objects.filter(subject_assignment__section=section)
            self.assertEqual(rows.count(), len(seed_module.LEARNING_AREAS))
            # Two of the section's own periods must never share a slot.
            collisions = (
                rows.values("day_of_week", "start_time")
                .annotate(n=Count("id"))
                .filter(n__gt=1)
            )
            self.assertEqual(list(collisions), [])
            for row in rows:
                self.assertLess(row.start_time, row.end_time)
                self.assertIn(
                    row.day_of_week, ("mon", "tue", "wed", "thu", "fri")
                )

    def test_student_qa_section_has_periods_across_several_weekdays(self):
        profile = StudentProfile.objects.get(user__email=QA_STUDENT_EMAIL)
        rows = Schedule.objects.filter(
            subject_assignment__section=profile.section
        )
        self.assertEqual(rows.count(), len(seed_module.LEARNING_AREAS))
        self.assertGreaterEqual(
            rows.values("day_of_week").distinct().count(), 3
        )

    def test_exactly_three_grading_periods_named_term_1_to_3(self):
        year = AcademicYear.objects.get(is_current=True)
        periods = GradingPeriod.objects.filter(academic_year=year).order_by("order")
        self.assertEqual(periods.count(), 3)
        self.assertEqual([period.order for period in periods], [1, 2, 3])
        for period in periods:
            self.assertGreaterEqual(period.start_date, year.start_date)
            self.assertLessEqual(period.end_date, year.end_date)
            self.assertLess(period.start_date, period.end_date)

    # -- roster shape ------------------------------------------------------

    def test_hundred_students_split_evenly_across_four_sections(self):
        synthetic = StudentProfile.objects.filter(
            user__email__startswith=f"{QA_EMAIL_PREFIX}student-"
        )
        # student.qa carries the non-prefixed QA login, so it sits outside this
        # count and is asserted separately.
        self.assertEqual(synthetic.count(), TOTAL_STUDENTS - 1)
        self.assertEqual(StudentProfile.objects.count(), TOTAL_STUDENTS)
        for grade_level in GradeLevel.objects.all():
            self.assertEqual(
                StudentProfile.objects.filter(grade_level=grade_level).count(),
                STUDENTS_PER_SECTION,
            )

    def test_every_student_has_one_active_current_year_enrollment(self):
        year = AcademicYear.objects.get(is_current=True)
        for student in StudentProfile.objects.all():
            enrollment = Enrollment.objects.get(
                student=student, section=student.section, academic_year=year
            )
            self.assertTrue(enrollment.is_active)

    def test_one_hundred_synthetic_parent_accounts_each_with_a_link(self):
        synthetic = User.objects.filter(
            email__startswith=f"{QA_EMAIL_PREFIX}parent-", role=User.Role.PARENT
        )
        self.assertEqual(synthetic.count(), TOTAL_STUDENTS)
        self.assertEqual(
            ParentProfile.objects.filter(user__in=synthetic).count(), TOTAL_STUDENTS
        )
        # Every seeded student is reachable from at least one parent, which is
        # what the parent child-selection behaviour needs.
        for student in StudentProfile.objects.all():
            self.assertTrue(
                ParentStudentLink.objects.filter(student=student).exists(),
                f"{student} has no parent link",
            )

    def test_all_seeded_identifiers_carry_the_qa_prefix(self):
        self.assertTrue(
            all(
                value.startswith(seed_module.QA_CODE_PREFIX)
                for value in StudentProfile.objects.values_list("student_id", flat=True)
            )
        )
        self.assertTrue(
            all(
                value.startswith(seed_module.QA_CODE_PREFIX)
                for value in FacultyProfile.objects.values_list("employee_id", flat=True)
            )
        )
        self.assertTrue(
            all(
                value.startswith(seed_module.QA_CODE_PREFIX)
                for value in GuidanceProfile.objects.values_list("employee_id", flat=True)
            )
        )

    # -- QA role relationships ---------------------------------------------

    def test_faculty_qa_advises_bonifacio_and_teaches_three_subjects(self):
        """faculty.qa's dashboard and academics pages read adviser and
        SubjectAssignment links, both of which must be present."""
        profile = FacultyProfile.objects.get(user__email=seed_module.QA_FACULTY_EMAIL)
        self.assertTrue(profile.is_adviser)

        bonifacio = Section.objects.get(name="Bonifacio")
        self.assertEqual(bonifacio.grade_level.name, "Grade 8")
        self.assertEqual(profile.advisory_section, bonifacio)
        self.assertEqual(bonifacio.adviser, profile)

        assignments = SubjectAssignment.objects.filter(faculty=profile)
        self.assertEqual(assignments.count(), len(seed_module.QA_FACULTY_SUBJECT_CODES))
        self.assertEqual(
            sorted(assignment.subject.code for assignment in assignments),
            sorted(f"{code}-8" for code in seed_module.QA_FACULTY_SUBJECT_CODES),
        )
        # The encode picker additionally needs active enrollments in its sections.
        self.assertTrue(
            Enrollment.objects.filter(
                section__in=assignments.values_list("section_id", flat=True),
                is_active=True,
            ).exists()
        )

    def test_every_section_has_an_adviser_mirrored_onto_the_profile(self):
        for section in Section.objects.all():
            self.assertIsNotNone(section.adviser, f"{section} has no adviser")
            self.assertTrue(section.adviser.is_adviser)
            self.assertEqual(section.adviser.advisory_section, section)

    def test_guidance_qa_has_a_guidance_profile(self):
        profile = GuidanceProfile.objects.get(user__email=seed_module.QA_GUIDANCE_EMAIL)
        self.assertTrue(profile.employee_id)

    def test_guidance_qa_owns_every_consultation_and_intervention(self):
        """Both querysets filter on counselor/assigned_counselor=self, so a record
        owned by anyone else is invisible to the QA guidance login."""
        profile = GuidanceProfile.objects.get(user__email=seed_module.QA_GUIDANCE_EMAIL)
        self.assertTrue(ConsultationRecord.objects.exists())
        self.assertTrue(Intervention.objects.exists())
        self.assertFalse(
            ConsultationRecord.objects.exclude(counselor=profile).exists(),
            "a consultation is not owned by guidance.qa",
        )
        self.assertFalse(
            Intervention.objects.exclude(assigned_counselor=profile).exists(),
            "an intervention is not owned by guidance.qa",
        )

    def test_student_qa_is_a_seeded_student_in_grade_8_bonifacio(self):
        profile = StudentProfile.objects.get(user__email=QA_STUDENT_EMAIL)
        self.assertTrue(profile.is_active)
        self.assertEqual(profile.grade_level.name, "Grade 8")
        self.assertEqual(profile.section.name, "Bonifacio")
        self.assertTrue(
            Enrollment.objects.filter(student=profile, is_active=True).exists(),
            "without an active enrollment the student dashboard is inert, because "
            "the frontend resolves its own StudentProfile UUID from "
            "/academics/enrollments/",
        )

    def test_student_qa_has_finalized_grades_the_dashboards_require(self):
        """Every student, parent and guidance grade table hard-filters
        status=finalized, so a draft-only roster renders as empty."""
        profile = StudentProfile.objects.get(user__email=QA_STUDENT_EMAIL)
        finalized = Grade.objects.filter(
            student=profile, status=Grade.StatusChoices.FINALIZED
        )
        self.assertGreaterEqual(
            finalized.count(), len(seed_module.LEARNING_AREAS)
        )
        for grade in finalized:
            self.assertIsNotNone(grade.score)
            self.assertTrue(grade.letter_grade)
            self.assertLessEqual(len(grade.letter_grade), 5)

    def test_student_qa_has_attendance_so_the_attendance_rate_calculates(self):
        profile = StudentProfile.objects.get(user__email=QA_STUDENT_EMAIL)
        self.assertTrue(AttendanceRecord.objects.filter(student=profile).exists())

    def test_parent_qa_is_linked_to_student_qa_plus_other_children(self):
        parent = ParentProfile.objects.get(user__email=seed_module.QA_PARENT_EMAIL)
        links = ParentStudentLink.objects.filter(parent=parent)
        children = set(links.values_list("student_id", flat=True))
        self.assertGreaterEqual(
            len(children), 2, "multi-child selection is untestable with one child"
        )
        self.assertIn(
            StudentProfile.objects.get(user__email=QA_STUDENT_EMAIL).id, children
        )
        self.assertEqual(len(QA_PARENT_CHILDREN), len(children))
        # Exactly one primary link, matching the model default the UI assumes.
        self.assertEqual(links.filter(is_primary=True).count(), 1)

    def test_parent_qa_children_span_more_than_one_section(self):
        """Parent scoping reads Enrollment, AttendanceRecord and Section through
        the link, so children in more than one section exercise those joins."""
        parent = ParentProfile.objects.get(user__email=seed_module.QA_PARENT_EMAIL)
        sections = set(
            StudentProfile.objects.filter(
                id__in=ParentStudentLink.objects.filter(parent=parent).values_list(
                    "student_id", flat=True
                )
            ).values_list("section_id", flat=True)
        )
        self.assertGreaterEqual(len(sections), 2)

    # ------------------------------------------------------------------
    # PH11.9: every parent.qa child must have guidance records.
    #
    # The parent's Student Support page is read-only and is fed entirely by the
    # guidance endpoints. Without records for these three students the page
    # renders three empty tables, which is indistinguishable from a queryset
    # that is silently broken. Each child therefore carries at least one risk
    # alert, one consultation and one behavioural note.
    # ------------------------------------------------------------------

    def test_every_parent_qa_child_has_guidance_records(self):
        parent = ParentProfile.objects.get(user__email=seed_module.QA_PARENT_EMAIL)
        child_ids = set(
            ParentStudentLink.objects.filter(parent=parent).values_list(
                "student_id", flat=True
            )
        )
        self.assertTrue(child_ids)

        for label, model in (
            ("RiskAlert", RiskAlert),
            ("ConsultationRecord", ConsultationRecord),
            ("BehavioralNote", BehavioralNote),
        ):
            covered = set(
                model.objects.filter(student_id__in=child_ids).values_list(
                    "student_id", flat=True
                )
            )
            self.assertEqual(
                covered,
                child_ids,
                msg=(
                    f"{label}: the parent's {label} view would be missing rows "
                    f"for {sorted(str(i) for i in child_ids - covered)}"
                ),
            )

    def test_parent_qa_children_span_every_guidance_status(self):
        """
        The parent's tables render a badge per status, so the dataset must
        contain each one. A page that only ever shows "active" cannot show that
        a resolved alert still appears as history.
        """
        parent = ParentProfile.objects.get(user__email=seed_module.QA_PARENT_EMAIL)
        child_ids = list(
            ParentStudentLink.objects.filter(parent=parent).values_list(
                "student_id", flat=True
            )
        )

        self.assertEqual(
            set(
                RiskAlert.objects.filter(student_id__in=child_ids).values_list(
                    "status", flat=True
                )
            ),
            {"active", "under_monitoring", "resolved"},
        )
        self.assertEqual(
            set(
                RiskAlert.objects.filter(student_id__in=child_ids).values_list(
                    "risk_level", flat=True
                )
            ),
            {"low", "moderate", "high"},
        )
        self.assertEqual(
            set(
                ConsultationRecord.objects.filter(
                    student_id__in=child_ids
                ).values_list("status", flat=True)
            ),
            {"completed", "follow_up"},
        )
        # The parent has no intervention surface: InterventionViewSet is
        # guidance-only, so a seeded plan here would be invisible to the parent
        # and would suggest they should have one.
        self.assertFalse(
            Intervention.objects.filter(student_id__in=child_ids).exists()
        )

    def test_parent_qa_guidance_records_stay_manual_with_no_risk_score(self):
        """
        Adding parent-facing guidance rows must not invent model output.

        RiskScore is an ai_engine computation log with no API surface, so the
        dataset holds manual alerts with a null score reference and zero
        RiskScores — the same rule the original guidance rows follow.
        """
        parent = ParentProfile.objects.get(user__email=seed_module.QA_PARENT_EMAIL)
        child_ids = list(
            ParentStudentLink.objects.filter(parent=parent).values_list(
                "student_id", flat=True
            )
        )

        self.assertTrue(
            RiskAlert.objects.filter(student_id__in=child_ids).exists()
        )
        self.assertFalse(
            RiskAlert.objects.filter(
                student_id__in=child_ids, risk_score_ref__isnull=False
            ).exists()
        )
        for alert in RiskAlert.objects.filter(student_id__in=child_ids):
            self.assertEqual(alert.source, RiskAlert.Source.MANUAL)
        self.assertFalse(RiskScore.objects.exists())

    def test_admin_qa_needs_no_admin_profile(self):
        """AdminProfile is referenced only by models.py and the Django admin --
        no serializer, permission or view reads it -- so the seed must not invent
        one."""
        user = User.objects.get(email="admin.qa@aegis.local")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertFalse(AdminProfile.objects.filter(user=user).exists())

    # -- academic data quality ---------------------------------------------

    def test_grade_distribution_is_realistic_and_in_range(self):
        scores = [
            float(score)
            for score in Grade.objects.filter(score__isnull=False).values_list(
                "score", flat=True
            )
        ]
        self.assertGreater(len(scores), 1000)
        self.assertTrue(all(0 <= score <= 100 for score in scores))
        mean = sum(scores) / len(scores)
        self.assertGreater(mean, 70.0)
        self.assertLess(mean, 95.0)
        # A real roster is not uniform: the low-performance surfaces need at
        # least one failing grade to be non-empty.
        self.assertTrue(
            Grade.objects.filter(score__lt=70).exists(),
            "no failing grade seeded",
        )
        # Every DepEd descriptor band should be represented.
        letters = set(Grade.objects.values_list("letter_grade", flat=True))
        self.assertGreaterEqual(len(letters), 5)

    def test_every_grade_satisfies_the_sec_013_integrity_rules(self):
        """Grade.clean() requires the grading period to share the subject
        assignment's academic year, and an active enrollment in that section.
        Asserting it in bulk keeps this test cheap over ~1600 grades."""
        mismatched = Grade.objects.exclude(
            grading_period__academic_year_id=F("subject_assignment__academic_year_id")
        )
        self.assertFalse(
            mismatched.exists(),
            "a grade's grading period belongs to a different academic year",
        )
        grade_triples = set(
            Grade.objects.values_list(
                "student_id",
                "subject_assignment__section_id",
                "subject_assignment__academic_year_id",
            )
        )
        enrollment_triples = set(
            Enrollment.objects.filter(is_active=True).values_list(
                "student_id", "section_id", "academic_year_id"
            )
        )
        self.assertTrue(grade_triples)
        self.assertTrue(
            grade_triples.issubset(enrollment_triples),
            "at least one grade belongs to a student with no active enrollment in "
            "that section",
        )

    def test_grades_exist_only_for_periods_that_have_opened(self):
        future = Grade.objects.filter(grading_period__start_date__gt=self.today)
        self.assertFalse(
            future.exists(),
            "a grade was seeded for a grading period that has not started",
        )

    def test_closed_terms_are_finalized_and_no_open_term_is(self):
        closed = GradingPeriod.objects.filter(end_date__lt=self.today)
        self.assertTrue(closed.exists(), "no closed term, so no finalized grades")
        self.assertFalse(
            Grade.objects.filter(
                grading_period__in=closed, status__in=["draft", "submitted"]
            ).exists(),
            "a closed term still holds pending grades",
        )
        open_term = GradingPeriod.objects.filter(
            start_date__lte=self.today, end_date__gte=self.today
        ).first()
        if open_term is not None:
            self.assertFalse(
                Grade.objects.filter(
                    grading_period=open_term, status=Grade.StatusChoices.FINALIZED
                ).exists(),
                "an open term has finalized grades",
            )

    def test_open_term_supplies_pending_work_for_the_faculty_login(self):
        """The faculty dashboard counts draft and submitted grades separately.
        Both exist whenever a term is open, which is the whole school year."""
        open_term = GradingPeriod.objects.filter(
            start_date__lte=self.today, end_date__gte=self.today
        ).first()
        if open_term is None:
            self.skipTest(
                "no term is open today, so a real school would have no pending "
                "grade encoding to show"
            )
        profile = FacultyProfile.objects.get(user__email=seed_module.QA_FACULTY_EMAIL)
        for status in (Grade.StatusChoices.DRAFT, Grade.StatusChoices.SUBMITTED):
            self.assertTrue(
                Grade.objects.filter(
                    subject_assignment__faculty=profile,
                    grading_period=open_term,
                    status=status,
                ).exists(),
                f"no {status} grades for the faculty QA login",
            )

    def test_every_grade_has_an_encoder_faculty_profile(self):
        self.assertFalse(
            Grade.objects.filter(encoded_by__isnull=True).exists()
        )
        self.assertFalse(
            Grade.objects.filter(score__isnull=True).exists(),
            "a grade with no score renders as a blank cell",
        )

    # -- attendance quality ------------------------------------------------

    def test_attendance_covers_every_student_over_completed_school_weeks(self):
        self.assertEqual(
            AttendanceRecord.objects.values("student_id").distinct().count(),
            TOTAL_STUDENTS,
        )
        per_student = AttendanceRecord.objects.values("student_id").annotate(
            days=Count("id")
        )
        self.assertEqual(len(per_student), TOTAL_STUDENTS)
        for row in per_student:
            self.assertEqual(row["days"], ATTENDANCE_WEEKS * 5)

    def test_attendance_includes_present_late_and_absent(self):
        statuses = set(AttendanceRecord.objects.values_list("status", flat=True))
        self.assertEqual(
            statuses,
            {"present", "late", "absent"},
            "all three states must be present for attendance QA",
        )

    def test_attendance_is_recorded_by_a_real_faculty_profile(self):
        self.assertFalse(
            AttendanceRecord.objects.filter(recorded_by__isnull=True).exists()
        )
        self.assertEqual(
            AttendanceRecord.objects.values("recorded_by").distinct().count(),
            len(seed_module.SECTION_PLAN),
        )

    def test_no_attendance_or_behavioral_date_is_in_the_future(self):
        self.assertFalse(AttendanceRecord.objects.filter(date__gt=self.today).exists())
        self.assertFalse(
            BehavioralNote.objects.filter(date_recorded__gt=self.today).exists()
        )
        self.assertFalse(
            ConsultationRecord.objects.filter(session_date__gt=self.today).exists()
        )

    def test_attendance_dates_are_weekdays_from_completed_weeks(self):
        latest = AttendanceRecord.objects.order_by("-date").first()
        self.assertLess(latest.date.weekday(), 5)
        # Nothing on or after today: AttendanceRecord.clean() forbids it.
        self.assertLess(latest.date, self.today)

    # -- guidance coverage -------------------------------------------------

    def test_active_moderate_and_high_risk_alerts_exist(self):
        active_levels = set(
            RiskAlert.objects.filter(status=RiskAlert.Status.ACTIVE).values_list(
                "risk_level", flat=True
            )
        )
        self.assertIn("moderate", active_levels)
        self.assertIn("high", active_levels)
        # The dashboard "Active Cases" card counts these three open statuses.
        self.assertGreater(
            RiskAlert.objects.filter(
                status__in=["active", "under_monitoring", "escalated"]
            ).count(),
            5,
        )
        # Every status the Risk Alerts page renders a chip for is represented.
        self.assertEqual(
            set(RiskAlert.objects.values_list("status", flat=True)),
            {"active", "under_monitoring", "escalated", "resolved"},
        )
        self.assertEqual(
            set(RiskAlert.objects.values_list("risk_level", flat=True)),
            {"low", "moderate", "high"},
        )

    def test_risk_alerts_are_manual_with_no_invented_risk_score(self):
        """RiskScore is an ai_engine computation log with no API surface.
        Seeding one would mean fabricating model output, so the dataset must hold
        manual alerts with a null score reference and zero RiskScores."""
        self.assertFalse(RiskScore.objects.exists())
        self.assertEqual(
            set(RiskAlert.objects.values_list("source", flat=True)), {"manual"}
        )
        self.assertFalse(
            RiskAlert.objects.exclude(risk_score_ref__isnull=True).exists(),
            "a seeded alert references a RiskScore, implying a fabricated "
            "computation",
        )
        for alert in RiskAlert.objects.all():
            self.assertTrue(alert.risk_factors)
            self.assertIsNotNone(alert.assigned_counselor)
            self.assertIsNotNone(alert.generated_at)

    def test_consultations_cover_every_session_type_priority_and_status(self):
        self.assertEqual(
            set(ConsultationRecord.objects.values_list("session_type", flat=True)),
            {"individual_counseling", "parent_conference", "follow_up", "group"},
        )
        self.assertEqual(
            set(ConsultationRecord.objects.values_list("priority_level", flat=True)),
            {"high", "medium", "low"},
        )
        self.assertEqual(
            set(ConsultationRecord.objects.values_list("status", flat=True)),
            {"ongoing", "completed", "follow_up"},
        )
        for consultation in ConsultationRecord.objects.all():
            self.assertTrue(consultation.concern_categories)
            self.assertTrue(consultation.session_notes.strip())

    def test_interventions_have_multiple_steps_and_a_progress_note(self):
        self.assertGreaterEqual(Intervention.objects.count(), 2)
        self.assertEqual(
            set(Intervention.objects.values_list("status", flat=True)),
            {"active", "completed"},
        )
        for intervention in Intervention.objects.all():
            steps = InterventionStep.objects.filter(intervention=intervention)
            self.assertGreaterEqual(
                steps.count(),
                3,
                f"{intervention} has too few steps for the plan dialog",
            )
            for step in steps:
                self.assertGreaterEqual(step.order, 1)
            self.assertTrue(
                ProgressNote.objects.filter(intervention=intervention).exists(),
                f"{intervention} has no progress note",
            )
            self.assertIsNotNone(intervention.plan_start_date)
            if intervention.target_review_date:
                self.assertGreaterEqual(
                    intervention.target_review_date, intervention.plan_start_date
                )

    def test_active_interventions_link_to_the_students_risk_alert(self):
        for intervention in Intervention.objects.exclude(status="completed"):
            self.assertIsNotNone(
                intervention.risk_alert,
                "an active intervention must link its risk alert, which is what "
                "the Interventions page reads",
            )

    def test_behavioral_notes_cover_every_note_type(self):
        self.assertEqual(
            set(BehavioralNote.objects.values_list("note_type", flat=True)),
            {"positive", "warning", "incident"},
        )
        for note in BehavioralNote.objects.all():
            self.assertTrue(note.note_text.strip())
            self.assertIsNotNone(note.recorded_by)

    def test_guidance_assessment_has_questions_and_completed_results(self):
        assessment = Assessment.objects.get()
        self.assertEqual(assessment.assessment_type, "wellness")
        self.assertEqual(assessment.creator_role, "guidance")
        self.assertEqual(assessment.created_by.email, seed_module.QA_GUIDANCE_EMAIL)
        self.assertTrue(assessment.is_published)
        self.assertEqual(
            assessment.questions.count(), len(seed_module.WELLNESS_QUESTIONS)
        )
        # Assessment.clean() rejects a deadline that is not in the future, and
        # students cannot see the assessment before then.
        self.assertGreater(assessment.deadline, timezone.now())

        for question in assessment.questions.all():
            if question.question_type in ("multiple_choice", "likert"):
                self.assertGreaterEqual(len(question.options), 2)
            if question.correct_answer:
                self.assertTrue(question.correct_answer.strip())

        results = AssessmentResult.objects.filter(assessment=assessment)
        self.assertTrue(results.exists())
        for result in results:
            self.assertEqual(result.status, AssessmentResult.Status.COMPLETED)
            self.assertIsNotNone(result.completed_at)
            self.assertLessEqual(result.score, result.total_possible)
            self.assertGreaterEqual(result.percentage, 0)
            self.assertLessEqual(result.percentage, 100)
            self.assertIsInstance(result.answers, dict)

    def test_assessment_results_cover_student_qa(self):
        profile = StudentProfile.objects.get(user__email=QA_STUDENT_EMAIL)
        self.assertTrue(AssessmentResult.objects.filter(student=profile).exists())

    def test_wellness_assessment_is_targeted_at_the_bonifacio_section(self):
        assessment = Assessment.objects.get()
        self.assertEqual(
            [section.name for section in assessment.target_sections.all()],
            ["Bonifacio"],
        )

    def test_every_guidance_record_belongs_to_a_seeded_student(self):
        """Guidance pages join back to enrollments for the student code, so an
        orphan record would render as a blank row."""
        seeded_ids = set(StudentProfile.objects.values_list("id", flat=True))
        self.assertTrue(
            set(RiskAlert.objects.values_list("student_id", flat=True)).issubset(seeded_ids)
        )
        self.assertTrue(
            set(ConsultationRecord.objects.values_list("student_id", flat=True)).issubset(seeded_ids)
        )
        self.assertTrue(
            set(Intervention.objects.values_list("student_id", flat=True)).issubset(seeded_ids)
        )

    # -- safety ------------------------------------------------------------

    def test_synthetic_accounts_are_not_usable_logins(self):
        """No password, hash or token may exist for a seeded account."""
        synthetic = User.objects.filter(email__startswith=QA_EMAIL_PREFIX)
        self.assertGreater(synthetic.count(), 200)
        for user in synthetic:
            self.assertFalse(
                user.has_usable_password(), f"{user.email} has a usable password"
            )

    def test_qa_login_credentials_are_left_entirely_to_provisioning(self):
        for email, role in (
            (seed_module.QA_FACULTY_EMAIL, User.Role.FACULTY),
            (seed_module.QA_GUIDANCE_EMAIL, User.Role.GUIDANCE),
            (seed_module.QA_STUDENT_EMAIL, User.Role.STUDENT),
            (seed_module.QA_PARENT_EMAIL, User.Role.PARENT),
        ):
            user = User.objects.get(email=email)
            self.assertTrue(user.has_usable_password())
            self.assertEqual(user.role, role)
            self.assertTrue(user.is_active)
            self.assertFalse(
                user.must_change_password,
                "must_change_password would 401 every API call for this login",
            )

    def test_synthetic_names_replaced_the_provisioning_placeholders(self):
        for email in (
            seed_module.QA_FACULTY_EMAIL,
            seed_module.QA_GUIDANCE_EMAIL,
            seed_module.QA_STUDENT_EMAIL,
            seed_module.QA_PARENT_EMAIL,
        ):
            user = User.objects.get(email=email)
            self.assertNotEqual(user.first_name, "QA")
            self.assertTrue(user.first_name.strip())
            self.assertTrue(user.last_name.strip())


class SeedOutputTestCase(TestCase):
    """The command must not echo any credential material.

    Each test is already wrapped in a transaction that Django rolls back, so the
    two runs in the counting test genuinely see each other's writes.
    """

    def test_output_never_contains_a_password_or_hash(self):
        provision_qa_logins()
        buffer = io.StringIO()
        call_command("seed_qa_dataset", stdout=buffer)
        output = buffer.getvalue()
        self.assertIn("created=", output)
        self.assertNotIn(TEST_QA_PASSWORD, output)
        lowered = output.lower()
        for marker in ("pbkdf2_", "argon2", "bcrypt", "scrypt", "password"):
            self.assertNotIn(marker, lowered)

    def test_output_reports_per_model_counts_for_both_runs(self):
        provision_qa_logins()
        first = io.StringIO()
        call_command("seed_qa_dataset", stdout=first)
        second = io.StringIO()
        call_command("seed_qa_dataset", stdout=second)

        self.assertIn("RiskAlert", first.getvalue())
        self.assertIn("Grade", first.getvalue())

        def grade_line(text):
            for line in text.splitlines():
                if line.strip().startswith("Grade "):
                    return line
            self.fail(f"no Grade row in report:\n{text}")

        # First run creates, second run reuses every record.
        self.assertNotIn("created=0", grade_line(first.getvalue()))
        self.assertIn("created=0", grade_line(second.getvalue()))
        for label in ("Grade", "AttendanceRecord", "Enrollment", "RiskAlert"):
            self.assertIn(label, second.getvalue())


class SeedIdempotencyTestCase(TestCase):
    """Running the command again must reuse, never duplicate."""

    def test_second_run_creates_nothing_and_changes_no_row_count(self):
        provision_qa_logins()
        run_seed()
        first = snapshot()

        run_seed()
        second = snapshot()

        self.assertEqual(first, second)
        self.assertGreater(sum(first.values()), 3000)

    def test_third_run_is_also_stable(self):
        provision_qa_logins()
        run_seed()
        run_seed()
        after_two = snapshot()
        run_seed()
        self.assertEqual(after_two, snapshot())

    def test_rerun_keeps_one_enrollment_per_student_in_the_current_year(self):
        provision_qa_logins()
        run_seed()
        run_seed()
        year = AcademicYear.objects.get(is_current=True)
        for student in StudentProfile.objects.all():
            self.assertEqual(
                Enrollment.objects.filter(
                    student=student, academic_year=year
                ).count(),
                1,
            )

    def test_rerun_does_not_multiply_grades(self):
        provision_qa_logins()
        run_seed()
        run_seed()
        # Grade's unique_together is (student, subject_assignment, grading_period).
        triples = set(
            Grade.objects.values_list(
                "student_id", "subject_assignment_id", "grading_period_id"
            )
        )
        self.assertEqual(Grade.objects.count(), len(triples))

    def test_rerun_does_not_multiply_questions_or_results(self):
        provision_qa_logins()
        run_seed()
        run_seed()
        assessment = Assessment.objects.get()
        self.assertEqual(
            assessment.questions.count(), len(seed_module.WELLNESS_QUESTIONS)
        )
        self.assertEqual(
            AssessmentResult.objects.filter(assessment=assessment).count(),
            len(seed_module.WELLNESS_RESULT_STUDENTS),
        )
        self.assertEqual(Assessment.objects.count(), 1)

    def test_rerun_preserves_declared_guidance_counts(self):
        provision_qa_logins()
        run_seed()
        run_seed()
        self.assertEqual(
            RiskAlert.objects.count(), len(seed_module.RISK_ALERT_STUDENTS)
        )
        self.assertEqual(
            ConsultationRecord.objects.count(), len(seed_module.CONSULTATIONS)
        )
        self.assertEqual(
            Intervention.objects.count(), len(seed_module.INTERVENTIONS)
        )
        self.assertEqual(
            BehavioralNote.objects.count(), len(seed_module.BEHAVIORAL_NOTES)
        )
        self.assertEqual(
            InterventionStep.objects.count(),
            sum(len(row[4]) for row in seed_module.INTERVENTIONS),
        )
        self.assertEqual(ProgressNote.objects.count(), len(seed_module.INTERVENTIONS))

    def test_rerun_does_not_add_attendance_or_enrollment_rows(self):
        provision_qa_logins()
        run_seed()
        run_seed()
        self.assertEqual(
            AttendanceRecord.objects.count(), TOTAL_STUDENTS * ATTENDANCE_WEEKS * 5
        )
        self.assertEqual(Enrollment.objects.count(), TOTAL_STUDENTS)

    def test_scores_are_reproducible_across_independent_runs(self):
        """The per-record RNG namespace makes scores stable rather than
        call-order dependent."""
        provision_qa_logins()
        run_seed()
        first = sorted(
            Grade.objects.values_list("student_id", "subject_assignment_id", "score")
        )
        run_seed()
        self.assertEqual(
            first,
            sorted(
                Grade.objects.values_list(
                    "student_id", "subject_assignment_id", "score"
                )
            ),
        )


class SeedIsolationTestCase(TestCase):
    """Nothing outside the QA allowlist may be read into, or written by, the seed."""

    def setUp(self):
        provision_qa_logins()
        self.legacy_year = AcademicYear.objects.create(
            name="2019-2020",
            start_date=date(2019, 6, 1),
            end_date=date(2020, 3, 31),
            is_current=False,
        )
        self.legacy_grade_level = GradeLevel.objects.create(
            name="Grade 11", level_number=11
        )
        self.outsider = User.objects.create_user(
            email="e2e.student@aegis.dev",
            password=OUTSIDER_PASSWORD,
            first_name="Outsider",
            last_name="Dev",
            role=User.Role.STUDENT,
        )
        self.outsider_profile = StudentProfile.objects.create(
            user=self.outsider,
            student_id="STU-OUTSIDE-001",
            grade_level=self.legacy_grade_level,
            section=None,
            enrollment_date=date(2019, 6, 1),
        )
        self.outsider_section = Section.objects.create(
            name="Legacy",
            grade_level=self.legacy_grade_level,
            academic_year=self.legacy_year,
        )
        Enrollment.objects.create(
            student=self.outsider_profile,
            section=self.outsider_section,
            academic_year=self.legacy_year,
            date_enrolled=date(2019, 6, 1),
            is_active=True,
        )
        self.outsider_profile.section = self.outsider_section
        self.outsider_profile.save(update_fields=["section"])

    def test_non_qa_account_and_its_records_are_untouched(self):
        run_seed()
        outsider = User.objects.get(email="e2e.student@aegis.dev")
        self.assertEqual(outsider.first_name, "Outsider")
        self.assertEqual(outsider.last_name, "Dev")
        self.assertEqual(outsider.role, User.Role.STUDENT)
        self.assertTrue(
            outsider.check_password(OUTSIDER_PASSWORD),
            "the seed must never reset an unrelated account's password",
        )
        profile = StudentProfile.objects.get(pk=self.outsider_profile.pk)
        self.assertEqual(profile.student_id, "STU-OUTSIDE-001")
        self.assertEqual(profile.grade_level, self.legacy_grade_level)
        self.assertEqual(profile.section, self.outsider_section)
        self.assertEqual(
            Enrollment.objects.filter(student=profile).count(),
            1,
            "the seed must not enroll an unrelated student in the QA year",
        )

    def test_seed_creates_no_records_for_a_non_qa_account(self):
        run_seed()
        profile = StudentProfile.objects.get(pk=self.outsider_profile.pk)
        self.assertFalse(AttendanceRecord.objects.filter(student=profile).exists())
        self.assertFalse(Grade.objects.filter(student=profile).exists())
        self.assertFalse(RiskAlert.objects.filter(student=profile).exists())
        self.assertFalse(BehavioralNote.objects.filter(student=profile).exists())
        self.assertFalse(Intervention.objects.filter(student=profile).exists())
        self.assertFalse(ConsultationRecord.objects.filter(student=profile).exists())
        self.assertFalse(AssessmentResult.objects.filter(student=profile).exists())

    def test_a_preexisting_legacy_year_is_preserved_but_demoted_from_current(self):
        run_seed()
        self.legacy_year.refresh_from_db()
        self.assertFalse(self.legacy_year.is_current)
        self.assertTrue(Section.objects.filter(pk=self.outsider_section.pk).exists())
        self.assertTrue(AcademicYear.objects.filter(name="2019-2020").exists())

    def test_command_refuses_to_run_without_the_qa_logins(self):
        User.objects.filter(
            email__in=[
                seed_module.QA_FACULTY_EMAIL,
                seed_module.QA_GUIDANCE_EMAIL,
                seed_module.QA_STUDENT_EMAIL,
                seed_module.QA_PARENT_EMAIL,
            ]
        ).delete()
        with self.assertRaises(CommandError) as ctx:
            run_seed()
        self.assertIn("provision_qa_accounts", str(ctx.exception))
        self.assertFalse(
            StudentProfile.objects.filter(
                student_id__startswith=seed_module.QA_CODE_PREFIX
            ).exists(),
            "a refused run must not seed anything",
        )


class SeedHelperTestCase(TestCase):
    """Cheap checks on the helpers themselves; no dataset is seeded."""

    def test_rand_is_namespaced_not_call_order_dependent(self):
        command = SeedCommand()
        first = command._rand("grade", "AEGIS-QA-S0001").gauss(0, 1)
        command._rand("attendance", "AEGIS-QA-S0001").random()
        second = command._rand("grade", "AEGIS-QA-S0001").gauss(0, 1)
        self.assertEqual(first, second)

    def test_school_days_are_distinct_weekdays_strictly_before_today(self):
        command = SeedCommand()
        command._today = timezone.localdate()
        days = command._school_days(ATTENDANCE_WEEKS)
        self.assertEqual(len(days), ATTENDANCE_WEEKS * 5)
        self.assertEqual(len(set(days)), len(days))
        for day in days:
            self.assertLess(day, command._today)
            self.assertLess(day.weekday(), 5)

    def test_grade_scale_maps_deped_descriptors(self):
        cases = {
            95: ("A", "Outstanding"),
            87: ("B+", "Very Satisfactory"),
            82: ("B", "Satisfactory"),
            77: ("C+", "Fairly Satisfactory"),
            72: ("C", "Fairly Satisfactory"),
            66: ("D", "Fairly Satisfactory"),
            61: ("F", "Failed"),
            0: ("F", "Failed"),
            100: ("A", "Outstanding"),
        }
        for score, expected in cases.items():
            self.assertEqual(SeedCommand._letter_and_remark(score), expected)

    def test_names_are_deterministic_and_drawn_from_the_pools(self):
        self.assertEqual(SeedCommand._first_name(3), SeedCommand._first_name(3))
        for index in range(TOTAL_STUDENTS):
            self.assertIn(SeedCommand._first_name(index), seed_module.FIRST_NAMES)
            surname = SeedCommand._surname(index)
            self.assertTrue(surname)
            # A compound surname such as "De la Cruz" is a single pool entry, so
            # match on containment rather than on a whitespace split.
            self.assertTrue(
                any(name in surname for name in seed_module.SURNAMES),
                f"{surname!r} is not drawn from the surname pool",
            )

    def test_phone_numbers_are_synthetic_ph_formats(self):
        for index in (0, 1, 99, 400):
            phone = SeedCommand._phone(index)
            self.assertTrue(phone.startswith("+63917"))
            self.assertEqual(len(phone), 12)


# ---------------------------------------------------------------------------
# Grade lifecycle under a frozen "today"
# ---------------------------------------------------------------------------

#: Dates the lifecycle is asserted at, chosen to land inside a different term so
#: the date-driven transition is proven rather than assumed:
#:   2026-10-03 -> Term 1 closed, Term 2 open,  Term 3 not started
#:   2027-02-15 -> Term 1 closed, Term 2 closed, Term 3 open
#:   2027-05-01 -> all three closed
LIFECYCLE_DATES = (date(2026, 10, 3), date(2027, 2, 15), date(2027, 5, 1))


class SeedTermLifecycleTestCase(TestCase):
    """Seed with ``today`` pinned, so the term lifecycle is deterministic."""

    def setUp(self):
        provision_qa_logins()

    def _seed_as_of(self, today):
        with mock.patch.object(
            timezone, "localdate", return_value=today
        ):
            run_seed()

    def _period(self, name):
        return GradingPeriod.objects.get(
            academic_year=AcademicYear.objects.get(is_current=True), name=name
        )

    def _statuses(self, period_name):
        return set(
            Grade.objects.filter(grading_period=self._period(period_name)).values_list(
                "status", flat=True
            )
        )

    def _assert_lifecycle(self, today):
        """Assert the term-by-term grade lifecycle implied by ``today``."""
        subject_count = len(seed_module.LEARNING_AREAS)
        periods = {
            name: (start, end)
            for name, _order, start, end in seed_module.GRADING_PERIODS
        }

        for name, (_start, end) in periods.items():
            statuses = self._statuses(name)
            if _start > today:
                # A term that has not begun must have no grades at all, and in
                # particular no finalized ones.
                self.assertEqual(
                    statuses,
                    set(),
                    f"{name} starts after {today} but already has grades: {statuses}",
                )
                self.assertFalse(
                    Grade.objects.filter(
                        grading_period=self._period(name),
                        status=Grade.StatusChoices.FINALIZED,
                    ).exists(),
                    f"{name} has not started but holds finalized grades",
                )
            elif end < today:
                self.assertEqual(
                    statuses,
                    {Grade.StatusChoices.FINALIZED},
                    f"{name} closed before {today} but holds {statuses}",
                )
            else:
                # An open term carries pending encoding work, never finalized.
                self.assertEqual(
                    statuses,
                    {Grade.StatusChoices.DRAFT, Grade.StatusChoices.SUBMITTED},
                    f"{name} is open on {today} but holds {statuses}",
                )

        expected_total = subject_count * TOTAL_STUDENTS * sum(
            1 for start, _end in (periods.values()) if start <= today
        )
        self.assertEqual(
            Grade.objects.count(),
            expected_total,
            f"grade count on {today} does not match the number of opened terms",
        )

    def test_lifecycle_on_2026_10_03_term1_final_term2_pending_term3_empty(self):
        """The QA reference date: Term 1 closed, Term 2 open, Term 3 unopened."""
        self._seed_as_of(date(2026, 10, 3))
        self.assertEqual(self._statuses("Term 1"), {Grade.StatusChoices.FINALIZED})
        self.assertEqual(
            self._statuses("Term 2"),
            {Grade.StatusChoices.DRAFT, Grade.StatusChoices.SUBMITTED},
        )
        self.assertEqual(self._statuses("Term 3"), set())
        # 100 students x 8 learning areas x (1 closed + 1 open) term.
        self.assertEqual(Grade.objects.count(), 1600)
        self.assertEqual(
            Grade.objects.filter(
                grading_period=self._period("Term 1"),
                status=Grade.StatusChoices.FINALIZED,
            ).count(),
            800,
        )
        self.assertEqual(
            Grade.objects.filter(grading_period=self._period("Term 2")).count(), 800
        )
        self._assert_lifecycle(date(2026, 10, 3))

    def test_lifecycle_advances_when_term_2_closes(self):
        """As time moves into 2027 Term 2 must finalize and Term 3 must open."""
        self._seed_as_of(date(2027, 2, 15))
        self.assertEqual(self._statuses("Term 1"), {Grade.StatusChoices.FINALIZED})
        self.assertEqual(self._statuses("Term 2"), {Grade.StatusChoices.FINALIZED})
        self.assertEqual(
            self._statuses("Term 3"),
            {Grade.StatusChoices.DRAFT, Grade.StatusChoices.SUBMITTED},
        )
        self.assertEqual(Grade.objects.count(), 2400)
        self._assert_lifecycle(date(2027, 2, 15))

    def test_lifecycle_never_finalizes_an_unopened_term(self):
        """After the school year every term is closed and finalized, and no
        term was ever finalized before it started."""
        self._seed_as_of(date(2027, 5, 1))
        for name, (_start, _end) in (
            (row[0], (row[2], row[3])) for row in seed_module.GRADING_PERIODS
        ):
            self.assertEqual(
                self._statuses(name),
                {Grade.StatusChoices.FINALIZED},
                f"{name} is not finalized after the school year closed",
            )
        self._assert_lifecycle(date(2027, 5, 1))

    def test_no_attendance_or_guidance_date_is_in_the_future_at_any_lifecycle_date(
        self,
    ):
        for today in LIFECYCLE_DATES:
            with self.subTest(today=today):
                for model, field in (
                    (AttendanceRecord, "date"),
                    (BehavioralNote, "date_recorded"),
                    (ConsultationRecord, "session_date"),
                ):
                    with mock.patch.object(timezone, "localdate", return_value=today):
                        run_seed()
                        future = model.objects.filter(**{f"{field}__gt": today})
                        self.assertFalse(
                            future.exists(),
                            f"{model.__name__}.{field} is dated after {today}",
                        )

    def test_attendance_dates_stay_weekdays_and_strictly_past(self):
        for today in LIFECYCLE_DATES:
            with self.subTest(today=today):
                with mock.patch.object(timezone, "localdate", return_value=today):
                    run_seed()
                    latest = AttendanceRecord.objects.order_by("-date").first()
                    self.assertLess(latest.date, today)
                    self.assertLess(latest.date.weekday(), 5)


class SeedLegacyQuarterReconciliationTestCase(TestCase):
    """A database seeded before the move to three terms must reconcile cleanly."""

    def _seed_the_legacy_calendar(self):
        """
        Recreate exactly what the four-quarter revision of the seed wrote.

        ``LEGACY_GRADING_PERIODS`` is emptied for the duration so the reconciler
        does not immediately retire the rows it is building; the fixture needs
        them left in place so the following run has something to reconcile.
        """
        module = seed_module
        original_periods = module.GRADING_PERIODS
        original_legacy = module.LEGACY_GRADING_PERIODS
        module.GRADING_PERIODS = module.LEGACY_GRADING_PERIODS
        module.LEGACY_GRADING_PERIODS = ()
        try:
            run_seed()
        finally:
            module.GRADING_PERIODS = original_periods
            module.LEGACY_GRADING_PERIODS = original_legacy

        year = AcademicYear.objects.get(name=seed_module.ACADEMIC_YEAR_NAME)
        return year, GradingPeriod.objects.get(
            academic_year=year, name="1st Quarter"
        )

    def test_legacy_four_quarter_dataset_is_reconciled_to_three_terms(self):
        provision_qa_logins()
        year, legacy_q1 = self._seed_the_legacy_calendar()
        self.assertEqual(
            GradingPeriod.objects.filter(academic_year=year).count(),
            4,
            "the legacy fixture should have written four quarters",
        )
        self.assertEqual(Grade.objects.filter(grading_period=legacy_q1).count(), 800)

        # Now run the current command against that legacy database.
        run_seed()

        periods = list(
            GradingPeriod.objects.filter(academic_year=year).order_by("order")
        )
        self.assertEqual(
            [(p.name, p.order, p.start_date, p.end_date) for p in periods],
            [
                ("Term 1", 1, date(2026, 6, 8), date(2026, 9, 15)),
                ("Term 2", 2, date(2026, 9, 16), date(2026, 12, 18)),
                ("Term 3", 3, date(2027, 1, 4), date(2027, 4, 8)),
            ],
            "the legacy quarters were not fully replaced by the three terms",
        )
        self.assertFalse(
            GradingPeriod.objects.filter(
                name__in=["1st Quarter", "2nd Quarter", "3rd Quarter", "4th Quarter"]
            ).exists(),
            "a superseded quarter survived reconciliation",
        )

    def test_reconciliation_leaves_no_orphaned_or_duplicate_grades(self):
        provision_qa_logins()
        year, _legacy = self._seed_the_legacy_calendar()
        run_seed()

        # No grade may reference a period outside this academic year, and the
        # (student, subject, period) natural key must stay unique.
        self.assertFalse(
            Grade.objects.exclude(grading_period__academic_year=year).exists(),
            "a grade points at a grading period outside the QA academic year",
        )
        triples = set(
            Grade.objects.values_list(
                "student_id", "subject_assignment_id", "grading_period_id"
            )
        )
        self.assertEqual(Grade.objects.count(), len(triples))

        # The legacy two graded quarters collapse onto Term 1 and Term 2, so the
        # row count is unchanged and no grade is lost.
        self.assertEqual(Grade.objects.count(), 1600)
        by_term = {
            period.name: Grade.objects.filter(grading_period=period).count()
            for period in GradingPeriod.objects.filter(academic_year=year)
        }
        self.assertEqual(by_term["Term 1"], 800)
        self.assertEqual(by_term["Term 2"], 800)
        self.assertEqual(by_term["Term 3"], 0)

    def test_reconciliation_repairs_statuses_to_match_the_current_calendar(self):
        """Term 1 is closed on the QA reference date, so the legacy finalized
        quarter that lands on it stays finalized and Term 2 stays pending."""
        provision_qa_logins()
        with mock.patch.object(timezone, "localdate", return_value=date(2026, 10, 3)):
            self._seed_the_legacy_calendar()
            run_seed()
            term_1 = GradingPeriod.objects.get(name="Term 1")
            term_2 = GradingPeriod.objects.get(name="Term 2")
            self.assertEqual(
                set(
                    Grade.objects.filter(grading_period=term_1).values_list(
                        "status", flat=True
                    )
                ),
                {Grade.StatusChoices.FINALIZED},
            )
            self.assertEqual(
                set(
                    Grade.objects.filter(grading_period=term_2).values_list(
                        "status", flat=True
                    )
                ),
                {Grade.StatusChoices.DRAFT, Grade.StatusChoices.SUBMITTED},
            )

    def test_reconciliation_repoints_the_assessment_quarter_link(self):
        """Assessment.quarter is SET_NULL, so it is re-pointed before the legacy
        period is deleted rather than being silently blanked."""
        provision_qa_logins()
        self._seed_the_legacy_calendar()

        assessment = Assessment.objects.get()
        self.assertEqual(assessment.quarter.name, "2nd Quarter")

        run_seed()
        assessment.refresh_from_db()
        self.assertIsNotNone(
            assessment.quarter, "the assessment lost its grading period link"
        )
        self.assertEqual(assessment.quarter.name, "Term 2")

    def test_reconciliation_is_idempotent(self):
        provision_qa_logins()
        self._seed_the_legacy_calendar()
        run_seed()
        grades_before = Grade.objects.count()
        periods_before = GradingPeriod.objects.count()
        run_seed()
        run_seed()
        self.assertEqual(Grade.objects.count(), grades_before)
        self.assertEqual(GradingPeriod.objects.count(), periods_before)
        self.assertEqual(GradingPeriod.objects.count(), 3)

    def test_unrelated_grading_period_on_the_same_year_is_left_untouched(self):
        """A period a school or tester created must survive reconciliation even
        though it sits on the seed's academic year."""
        provision_qa_logins()
        self._seed_the_legacy_calendar()
        run_seed()
        year = AcademicYear.objects.get(name=seed_module.ACADEMIC_YEAR_NAME)
        hand_made = GradingPeriod.objects.create(
            academic_year=year,
            name="Extracurricular Program",
            order=7,
            start_date=date(2026, 6, 8),
            end_date=date(2027, 4, 8),
        )
        run_seed()
        hand_made.refresh_from_db()
        self.assertTrue(GradingPeriod.objects.filter(pk=hand_made.pk).exists())
        self.assertEqual(hand_made.name, "Extracurricular Program")
        self.assertEqual(hand_made.order, 7)
        self.assertEqual(GradingPeriod.objects.filter(name="Term 1").count(), 1)
        self.assertEqual(GradingPeriod.objects.filter(name="Term 2").count(), 1)
        self.assertEqual(GradingPeriod.objects.filter(name="Term 3").count(), 1)

    def test_edited_legacy_row_is_detected_but_not_deleted(self):
        """Ownership requires an exact name/order/date match, so a legacy row a
        tester edited is reported rather than destroyed."""
        provision_qa_logins()
        run_seed()
        year = AcademicYear.objects.get(name=seed_module.ACADEMIC_YEAR_NAME)
        edited = GradingPeriod.objects.create(
            academic_year=year,
            name="1st Quarter",
            order=1,
            start_date=date(2026, 6, 8),
            end_date=date(2026, 9, 1),  # not the legacy signature
        )
        buffer = io.StringIO()
        call_command("seed_qa_dataset", stdout=buffer)
        self.assertTrue(
            GradingPeriod.objects.filter(pk=edited.pk).exists(),
            "an edited legacy row was deleted; ownership match was too loose",
        )
        self.assertIn("left untouched", buffer.getvalue())

