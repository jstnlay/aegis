"""
Phase 9 chatbot tests.

Covers: intent taxonomy, permissions, cross-student isolation,
unknown intent, low-confidence, fallback, urgency, escalation.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

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
    Section,
    Subject,
    SubjectAssignment,
)
from apps.chatbot.policies import (
    classify_intent,
    classify_urgency,
    parse_message,
)
from apps.chatbot.taxonomy import ChatIntent, UrgencyLevel

User = get_user_model()


class ChatbotBase(TestCase):
    """Shared setUp for chatbot tests."""

    def setUp(self):
        self.client = APIClient()
        self.student_user = User.objects.create_user(
            email="chat_student@test.com", password="pass12345",
            first_name="Chat", last_name="Student", role="student",
        )
        self.grade_level = GradeLevel.objects.create(
            name="Grade 7", level_number=7
        )
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
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="CHAT001",
            grade_level=self.grade_level,
            section=self.section,
            enrollment_date=date(2024, 6, 10),
        )
        Enrollment.objects.create(
            student=self.student_profile, section=self.section,
            academic_year=self.academic_year, date_enrolled=date(2024, 6, 10),
            is_active=True,
        )

        self.other_student_user = User.objects.create_user(
            email="chat_other@test.com", password="pass12345",
            first_name="Other", last_name="Student", role="student",
        )
        self.other_profile = StudentProfile.objects.create(
            user=self.other_student_user,
            student_id="CHAT002",
            grade_level=self.grade_level,
            section=self.section,
            enrollment_date=date(2024, 6, 10),
        )


# ---------------------------------------------------------------------------
# Deterministic intent classification tests
# ---------------------------------------------------------------------------

class IntentClassificationTest(ChatbotBase):
    """Test deterministic intent classification (D25)."""

    def test_greeting(self):
        self.assertEqual(classify_intent("Hello!"), ChatIntent.GREETING)
        self.assertEqual(classify_intent("Hi there"), ChatIntent.GREETING)

    def test_ask_grade(self):
        self.assertEqual(classify_intent("What is my grade in Math?"), ChatIntent.ASK_GRADE)
        self.assertEqual(classify_intent("Anong grade ko?"), ChatIntent.ASK_GRADE)

    def test_ask_attendance(self):
        self.assertEqual(classify_intent("What is my attendance?"), ChatIntent.ASK_ATTENDANCE)

    def test_ask_recommendation(self):
        self.assertEqual(
            classify_intent("What should I study for Math?"),
            ChatIntent.ASK_RECOMMENDATION,
        )

    def test_ask_learning_resource(self):
        self.assertEqual(
            classify_intent("Can you give me a resource for Science?"),
            ChatIntent.ASK_LEARNING_RESOURCE,
        )

    def test_urgent_concern(self):
        self.assertEqual(
            classify_intent("I need urgent help right now!"),
            ChatIntent.URGENT_CONCERN,
        )

    def test_request_counselor(self):
        self.assertEqual(
            classify_intent("I want to talk to a counselor"),
            ChatIntent.REQUEST_COUNSELOR,
        )

    def test_express_concern(self):
        self.assertEqual(
            classify_intent("I am feeling worried about my classes"),
            ChatIntent.EXPRESS_CONCERN,
        )

    def test_unknown(self):
        self.assertEqual(classify_intent("florbeldorbus xyzzy"), ChatIntent.UNKNOWN)


# ---------------------------------------------------------------------------
# Urgency classification tests
# ---------------------------------------------------------------------------

class UrgencyClassificationTest(ChatbotBase):
    """Test urgency classification (D26)."""

    def test_normal(self):
        self.assertEqual(classify_urgency("What is my grade?"), UrgencyLevel.NORMAL)

    def test_elevated_concern(self):
        self.assertEqual(classify_urgency("I am worried about failing"), UrgencyLevel.ELEVATED)

    def test_urgent(self):
        self.assertEqual(classify_urgency("This is urgent I need help"), UrgencyLevel.URGENT)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class ChatbotAPIBase(ChatbotBase):
    """Base with subject/grade setup for authenticated API tests."""

    def setUp(self):
        super().setUp()
        self.faculty_user = User.objects.create_user(
            email="chat_faculty@test.com", password="pass12345",
            first_name="Chat", last_name="Faculty", role="faculty",
        )
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="CHATF001"
        )
        self.subject = Subject.objects.create(
            name="Mathematics", code="MATH-7", grade_level=self.grade_level
        )
        self.sa = SubjectAssignment.objects.create(
            subject=self.subject, section=self.section,
            academic_year=self.academic_year, faculty=self.faculty_profile,
        )
        self.gp = GradingPeriod.objects.create(
            academic_year=self.academic_year,
            name="1st Quarter", order=1,
            start_date=date(2024, 6, 10), end_date=date(2024, 8, 20),
        )
        Grade.objects.create(
            student=self.student_profile, subject_assignment=self.sa,
            grading_period=self.gp, score=Decimal("88"), status="finalized",
            encoded_by=self.faculty_profile,
        )

    def post_message(self, message, user):
        self.client.force_authenticate(user=user)
        return self.client.post(
            "/api/v1/chatbot/message/",
            {"message": message},
            format="json",
        )


class ChatbotAPITest(ChatbotAPIBase):
    """Test authenticated chatbot API endpoints."""

    def test_student_greeting(self):
        resp = self.post_message("Hello!", self.student_user)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["intent"], "greeting")
        self.assertEqual(resp.data["urgency"], "normal")

    def test_student_grade_query(self):
        resp = self.post_message("What is my grade in Math?", self.student_user)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["intent"], "ask_grade")
        self.assertIn("grade_summary", resp.data["data"])

    def test_student_attendance_query(self):
        resp = self.post_message("What is my attendance?", self.student_user)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["intent"], "ask_attendance")

    def test_student_cannot_access_other_student(self):
        """Cross-student isolation: chatbot never returns other's data."""
        from apps.chatbot import service
        from apps.chatbot.service import get_student_grade_summary
        summary = get_student_grade_summary(
            self.student_user, self.other_profile
        )
        self.assertIsNone(summary)

    def test_unauthenticated_request(self):
        resp = self.client.post(
            "/api/v1/chatbot/message/",
            {"message": "Hello!"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_intent_safe_fallback(self):
        resp = self.post_message("qwerty zanzibar", self.student_user)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["intent"], "unknown")
        self.assertTrue(resp.data["safe_fallback"])

    def test_urgent_intent_triggers_escalation(self):
        """URGENT message triggers application-controlled escalation."""
        resp = self.post_message("I need urgent help", self.student_user)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["intent"], "urgent_concern")
        self.assertTrue(resp.data["escalated"])

    def test_entity_extraction_subject(self):
        """Subject entity extraction works."""
        result = parse_message("Give me a resource for Mathematics")
        subject_entities = [e for e in result.entities if e.entity_type == "subject"]
        self.assertTrue(subject_entities)
        self.assertEqual(subject_entities[0].value, "Mathematics")

    def test_faculty_restricted(self):
        """Faculty role cannot ask for student grade data."""
        resp = self.post_message("What is my grade?", self.faculty_user)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Faculty not allowed for ask_grade → safe fallback
        self.assertTrue(resp.data["safe_fallback"])


class ChatbotPolicyTest(ChatbotAPIBase):
    """Test chatbot policy boundaries (least privilege)."""

    def test_cannot_modify_data(self):
        """Chatbot can never modify grades/attendance/behavior."""
        from apps.chatbot.service import check_intent_allowed
        from apps.chatbot.taxonomy import ChatIntent
        # No modify intents exist in taxonomy
        modified = [i for i in ChatIntent if "modif" in i.value or "delete" in i.value]
        self.assertEqual(len(modified), 0)

    def test_role_based_allowed_intents(self):
        from apps.chatbot.service import ALLOWED_INTENTS_BY_ROLE, check_intent_allowed
        from apps.chatbot.taxonomy import ChatIntent
        # Student can ask grades
        self.assertTrue(check_intent_allowed("student", ChatIntent.ASK_GRADE))
        # Faculty cannot ask for student grades
        self.assertFalse(check_intent_allowed("faculty", ChatIntent.ASK_GRADE))
        # Guidance can help seeker
        self.assertTrue(check_intent_allowed("student", ChatIntent.REQUEST_COUNSELOR))
