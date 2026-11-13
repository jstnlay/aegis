"""
The assistant has to answer the question it was asked.

The client's report was that the chatbot is "not accurate". The cause was
not the model: `_deterministic_reply` had no branch for a grade, an
attendance or a resource question, so every one of them fell through to a
generic tail — while the facts that answer them had already been fetched
and were sitting unused in `data`. With the Gemini key unavailable, that
tail was the *only* answer a student ever received.

These tests fix the answer text in place, without a model: the numbers a
student is shown must be the numbers in their record, the absent case must
read as absent rather than as a template, and the reply must never claim a
capability the assistant does not have.

The Gemini key is blanked in `config.settings.test`, so nothing here
touches the network and every assertion is about the deterministic path —
which is the path a school without an API key actually runs.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import (
    FacultyProfile,
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
    Section,
    Subject,
    SubjectAssignment,
)
from apps.attendance.models import AttendanceRecord
from apps.chatbot.agreements import notice_version
from apps.chatbot.models import AgreementAcceptance
from apps.cms.models import LearningItem

User = get_user_model()


class AccuracyBase(TestCase):
    """One student with a record, one student without one."""

    def setUp(self):
        self.client = APIClient()

        self.grade_level = GradeLevel.objects.create(name="Grade 7", level_number=7)
        self.academic_year = AcademicYear.objects.create(
            name="2024-2025",
            start_date=date(2024, 6, 10),
            end_date=date(2025, 3, 25),
            is_current=True,
        )
        self.section = Section.objects.create(
            name="Einstein",
            grade_level=self.grade_level,
            academic_year=self.academic_year,
        )

        self.faculty_user = User.objects.create_user(
            email="acc_faculty@test.com",
            password="pass12345",
            first_name="Acc",
            last_name="Faculty",
            role="faculty",
        )
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="ACCF001"
        )

        self.student_user = User.objects.create_user(
            email="acc_student@test.com",
            password="pass12345",
            first_name="Ana",
            last_name="Reyes",
            role="student",
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            student_id="ACC001",
            grade_level=self.grade_level,
            section=self.section,
            enrollment_date=date(2024, 6, 10),
        )
        Enrollment.objects.create(
            student=self.student,
            section=self.section,
            academic_year=self.academic_year,
            date_enrolled=date(2024, 6, 10),
            is_active=True,
        )
        AgreementAcceptance.objects.create(
            user=self.student_user,
            notice_version=notice_version(),
            accepted_at=date(2024, 6, 10),
        )

        self.subject = Subject.objects.create(
            name="Mathematics", code="MATH-7", grade_level=self.grade_level
        )
        self.assignment = SubjectAssignment.objects.create(
            subject=self.subject,
            section=self.section,
            academic_year=self.academic_year,
            faculty=self.faculty_profile,
        )
        self.period = GradingPeriod.objects.create(
            academic_year=self.academic_year,
            name="1st Quarter",
            order=1,
            start_date=date(2024, 6, 10),
            end_date=date(2024, 8, 20),
        )
        Grade.objects.create(
            student=self.student,
            subject_assignment=self.assignment,
            grading_period=self.period,
            score=Decimal("88"),
            status="finalized",
            encoded_by=self.faculty_profile,
        )

        # Two present days and one late arrival: the late day is a day the
        # student was in school and the answer must count it as one.
        for offset, status in enumerate(
            (AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.PRESENT,
             AttendanceRecord.Status.LATE)
        ):
            AttendanceRecord.objects.create(
                student=self.student,
                section=self.section,
                date=date(2024, 6, 10 + offset),
                status=status,
                recorded_by=self.faculty_profile,
            )

        LearningItem.objects.create(
            item_type=LearningItem.ItemType.LEARNING_RESOURCE,
            title="Algebra Practice Set",
            subject=self.subject,
            topic="Algebra",
            lifecycle_status=LearningItem.LifecycleStatus.APPROVED,
            is_active=True,
        )
        LearningItem.objects.create(
            item_type=LearningItem.ItemType.LEARNING_RESOURCE,
            title="Draft Item Nobody Approved",
            subject=self.subject,
            lifecycle_status=LearningItem.LifecycleStatus.DRAFT,
            is_active=True,
        )

        # A second student with a record of nothing at all.
        self.empty_user = User.objects.create_user(
            email="acc_empty@test.com",
            password="pass12345",
            first_name="Ben",
            last_name="Cruz",
            role="student",
        )
        self.empty_student = StudentProfile.objects.create(
            user=self.empty_user,
            student_id="ACC002",
            grade_level=self.grade_level,
            section=self.section,
            enrollment_date=date(2024, 6, 10),
        )
        # The message endpoint refuses a student who has not accepted the
        # notice (428), so the record-less student has to accept it too or
        # every test below would be measuring the gate, not the answer.
        AgreementAcceptance.objects.create(
            user=self.empty_user,
            notice_version=notice_version(),
            accepted_at=date(2024, 6, 10),
        )

        self.parent_user = User.objects.create_user(
            email="acc_parent@test.com",
            password="pass12345",
            first_name="Cara",
            last_name="Reyes",
            role="parent",
        )
        self.parent = ParentProfile.objects.create(
            user=self.parent_user,
            relationship_to_student=ParentProfile.RelationshipType.MOTHER,
        )

    def ask(self, message, user=None):
        self.client.force_authenticate(user=user or self.student_user)
        return self.client.post(
            "/api/v1/chatbot/message/", {"message": message}, format="json"
        )


class GradeAnswerTest(AccuracyBase):
    """A grade question is answered with the student's grade."""

    def test_reply_states_the_average_and_the_count(self):
        resp = self.ask("What is my grade in Math?")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["intent"], "ask_grade")
        self.assertIn("88.00", resp.data["reply"])
        self.assertIn("1 finalized grade", resp.data["reply"])

    def test_reply_no_longer_falls_through_to_the_generic_tail(self):
        resp = self.ask("What is my grade in Math?")
        self.assertNotIn("I can help you with that", resp.data["reply"])

    def test_student_is_addressed_in_the_second_person(self):
        resp = self.ask("What is my grade in Math?")
        self.assertIn("You have", resp.data["reply"])

    def test_a_student_with_no_finalized_grades_is_told_so(self):
        resp = self.ask("What is my grade?", self.empty_user)
        self.assertEqual(resp.data["intent"], "ask_grade")
        self.assertIn("no finalized grades yet", resp.data["reply"])
        # Never a number where there is none.
        self.assertNotIn("averaging", resp.data["reply"])

    def test_performance_question_is_answered_from_the_same_record(self):
        resp = self.ask("How am I doing academically?")
        self.assertIn("88.00", resp.data["reply"])


class AttendanceAnswerTest(AccuracyBase):
    """An attendance question is answered with the student's record."""

    def test_reply_counts_each_status(self):
        resp = self.ask("What is my attendance?")
        self.assertEqual(resp.status_code, 200)
        reply = resp.data["reply"]
        self.assertIn("3 recorded days", reply)
        self.assertIn("2 present", reply)
        self.assertIn("1 late", reply)
        self.assertIn("0 absent", reply)

    def test_a_late_arrival_counts_as_a_day_attended(self):
        # 3 of 3 days attended, so the rate is 100% — a late day is not an
        # absence.
        resp = self.ask("What is my attendance?")
        self.assertIn("attended 3 of 3", resp.data["reply"])
        self.assertIn("100.0%", resp.data["reply"])

    def test_a_student_with_no_records_is_told_so(self):
        resp = self.ask("What is my attendance?", self.empty_user)
        self.assertIn("no recorded attendance days yet", resp.data["reply"])


class LearningResourceAnswerTest(AccuracyBase):
    """A resource question names the approved resources."""

    def test_reply_names_the_approved_item(self):
        resp = self.ask("Do you have a module for Algebra?")
        self.assertIn("Algebra Practice Set", resp.data["reply"])

    def test_an_unapproved_item_is_never_offered(self):
        resp = self.ask("Do you have a module for Algebra?")
        self.assertNotIn("Draft Item Nobody Approved", resp.data["reply"])

    def test_nothing_available_is_stated_plainly(self):
        # With no approved item in the bank there is nothing to offer, and the
        # answer says so rather than inventing a resource.
        LearningItem.objects.all().delete()
        resp = self.ask("Do you have a module for Algebra?")
        self.assertIn("don't have an approved learning resource", resp.data["reply"])

    def test_an_unrelated_question_offers_nothing(self):
        # The lookup is relevance-filtered now, so a question naming nothing in
        # the item bank returns nothing. Before the filter this replied with
        # the algebra module — a real answer to a question nobody asked, which
        # is the client's accuracy complaint in one sentence.
        resp = self.ask("Do you have a module for Underwater Basket Weaving?")
        self.assertIn("don't have an approved learning resource", resp.data["reply"])
        self.assertNotIn("Algebra Practice Set", resp.data["reply"])


class ParentResolutionTest(AccuracyBase):
    """A parent with a record that could be two children is asked which."""

    def test_two_children_without_a_name_asks_which_child(self):
        ParentStudentLink.objects.create(parent=self.parent, student=self.student)
        ParentStudentLink.objects.create(parent=self.parent, student=self.empty_student)
        resp = self.ask("What is my child's grade?", self.parent_user)
        self.assertIn("more than one linked student", resp.data["reply"])

    def test_one_linked_child_is_answered_by_name(self):
        ParentStudentLink.objects.create(parent=self.parent, student=self.student)
        resp = self.ask("What is my child's grade?", self.parent_user)
        self.assertIn("Ana Reyes has", resp.data["reply"])
        self.assertIn("88.00", resp.data["reply"])


class HonestTailTest(AccuracyBase):
    """An answer the assistant does not have is refused, not invented."""

    def test_a_student_asking_for_a_draft_is_told_it_cannot(self):
        resp = self.ask("draft a quiz about study habits")
        self.assertEqual(resp.data["intent"], "ask_assessment")
        self.assertIn("I don't have an answer for this one", resp.data["reply"])

    def test_the_refusal_names_what_it_can_do(self):
        resp = self.ask("draft a quiz about study habits")
        self.assertIn("grades, attendance and approved learning resources",
                      resp.data["reply"])

    def test_no_reachable_data_intent_returns_the_old_generic_tail(self):
        for message in (
            "What is my grade in Math?",
            "What is my attendance?",
            "How am I doing academically?",
            "Do you have a module for Algebra?",
        ):
            with self.subTest(message=message):
                resp = self.ask(message)
                self.assertNotIn("I can help you with that", resp.data["reply"])
                self.assertTrue(resp.data["reply"].strip())
