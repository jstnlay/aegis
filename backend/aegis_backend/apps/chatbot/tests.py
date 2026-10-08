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
    detect_urgent,
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


class ChatbotParentDataTest(ChatbotAPIBase):
    """
    A parent is allowed ask_grade / ask_attendance, but had no data path.

    `handle_message` gated the lookup on `hasattr(user, "student_profile")`,
    which no parent has, so a parent received the intent and a canned reply with
    no `data` block at all. Resolving the linked child closes that gap — and the
    multi-child case is the reason `resolve_target_student` refuses to guess.
    """

    def setUp(self):
        super().setUp()

        self.parent_user = User.objects.create_user(
            email="chat_parent@test.com", password="pass12345",
            first_name="Chat", last_name="Parent", role="parent",
        )
        self.parent_profile = ParentProfile.objects.create(
            user=self.parent_user,
            relationship_to_student=ParentProfile.RelationshipType.MOTHER,
        )
        ParentStudentLink.objects.create(
            parent=self.parent_profile, student=self.student_profile
        )

    def _add_second_child(self, first_name="Second"):
        user = User.objects.create_user(
            email=f"chat_{first_name.lower()}@test.com", password="pass12345",
            first_name=first_name, last_name="Child", role="student",
        )
        profile = StudentProfile.objects.create(
            user=user,
            student_id=f"CH{first_name[:3].upper()}",
            grade_level=self.grade_level,
            section=self.section,
            enrollment_date=date(2024, 6, 10),
        )
        ParentStudentLink.objects.create(
            parent=self.parent_profile, student=profile
        )
        return profile

    def test_single_child_grade_query_returns_data(self):
        resp = self.post_message("What is my grade in Math?", self.parent_user)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["intent"], "ask_grade")
        self.assertIn("grade_summary", resp.data["data"])

    def test_two_children_without_a_name_asks_which(self):
        """
        Guessing would report one real child's grades against a question about
        the other. The reply must ask instead.
        """
        self._add_second_child()

        resp = self.post_message("What is my grade in Math?", self.parent_user)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("grade_summary", resp.data["data"])
        self.assertIn("more than one linked student", resp.data["reply"])

    def test_resolve_returns_none_for_multi_child_ambiguity(self):
        from apps.chatbot.service import resolve_target_student

        self._add_second_child()

        self.assertIsNone(resolve_target_student(self.parent_user))

    def test_resolve_returns_the_only_linked_child(self):
        from apps.chatbot.service import resolve_target_student

        self.assertEqual(
            resolve_target_student(self.parent_user), self.student_profile
        )

    def test_naming_a_child_does_not_yet_disambiguate(self):
        """
        Documents the current limit honestly.

        `parse_message` extracts only `subject` and `topic` entities; there is
        no `person` entity type in `ChatEntity`, so a parent's "What is Maria's
        grade?" still resolves to the ambiguous branch. Name disambiguation
        requires a parser change, which belongs with the classifier work — so the
        assertion is that the ambiguity is *asked about*, not that it guesses.
        """
        self._add_second_child(first_name="Maria")

        resp = self.post_message("What is Maria's grade?", self.parent_user)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("grade_summary", resp.data["data"])
        self.assertIn("more than one linked student", resp.data["reply"])

    def test_student_own_data_still_resolves(self):
        from apps.chatbot.service import resolve_target_student

        self.assertEqual(
            resolve_target_student(self.student_user), self.student_profile
        )


class UrgencyEscalationPrecisionTest(ChatbotBase):
    """
    P0. A URGENT match dispatches a real `BEHAVIORAL_WARNING` notification to a
    guidance counselor (`service.create_escalation`).

    The previous pattern list matched a bare `\\bhurt\\b` and `\\bkill\\b`, so
    "I hurt my ankle playing basketball" and "I'm killing it in math" each paged
    a counselor. A channel that cries wolf about a sprained ankle is one staff
    learn to ignore, which makes a real crisis notice less likely to be read.

    These assertions exist because the failure mode is invisible in a unit test
    of `classify_intent` — the escalation lives in `classify_urgency`, on a
    different code path entirely.
    """

    # Ordinary messages that must never reach a counselor.
    MUST_NOT_ESCALATE = [
        "my tooth hurts",
        "i hurt my ankle playing basketball",
        "i hurt my back carrying books",
        "i'm killing it in math",
        "that test was killing me",
        "this is a stressful semester",
        "i am nervous about the quiz",
        "i'm worried about my grades",
    ]

    # Genuine self-harm phrasing that must always escalate.
    MUST_ESCALATE = [
        "i want to hurt myself",
        "i want to kill myself",
        "i have been hurting myself",
        "planning to harm myself",
        "i keep hurting myself",
        "i don't want to live",
        "i want to disappear",
        "i feel suicidal",
        "i am in a crisis",
        "this is an emergency",
        "help me now",
    ]

    def test_ordinary_messages_do_not_escalate(self):
        for text in self.MUST_NOT_ESCALATE:
            with self.subTest(text=text):
                self.assertNotEqual(classify_urgency(text), UrgencyLevel.URGENT)

    def test_self_harm_phrasing_always_escalates(self):
        for text in self.MUST_ESCALATE:
            with self.subTest(text=text):
                self.assertEqual(classify_urgency(text), UrgencyLevel.URGENT)

    def test_bare_hurt_and_kill_are_not_triggers(self):
        """
        The regression in its simplest form: the verb alone, with no
        self-directed object, must not escalate.
        """
        self.assertFalse(detect_urgent("hurt"))
        self.assertFalse(detect_urgent("kill"))
        self.assertFalse(detect_urgent("i hurt my knee"))
        self.assertFalse(detect_urgent("killing it in english"))

    def test_escalation_still_dispatches_for_real_crisis(self):
        """
        The precision fix must not have broken the FR-031 path end to end.
        """
        from apps.chatbot import service
        from apps.notifications.models import Notification

        # `create_escalation` routes to the first guidance user; with none
        # present it returns "no_recipient" and dispatches nothing.
        User.objects.create_user(
            email="chat_guidance_x@test.com", password="pass12345",
            first_name="Chat", last_name="GuidanceX", role="guidance",
        )
        student = User.objects.create_user(
            email="chat_crisis@test.com", password="pass12345",
            first_name="Crisis", last_name="Case", role="student",
        )

        Notification.objects.all().delete()
        response = service.handle_message(student, "I want to hurt myself")

        self.assertTrue(response.escalated)
        self.assertEqual(Notification.objects.count(), 1)


class WiredIntentReachabilityTest(ChatbotBase):
    """
    P1. `ASSESSMENT_INSTRUCTIONS` and `ASK_ATTENDANCE_STATUS` were declared in
    `taxonomy.ChatIntent`, gated per role by `ALLOWED_INTENTS_BY_ROLE`, listed
    by `IntentsView` and mirrored in the frontend — but `classify_intent` had no
    branch that could return either, so they were unreachable states in the
    contract.
    """

    def test_every_declared_intent_is_reachable(self):
        """
        Guards against a future intent being added to the taxonomy with no
        classifier branch to match it.
        """
        probes = [
            ("hello", ChatIntent.GREETING),
            ("what can you do?", ChatIntent.HELP),
            ("how do i navigate to the assessments page",
             ChatIntent.SYSTEM_NAVIGATION),
            ("asdkjhasd", ChatIntent.UNKNOWN),
            ("what is my grade", ChatIntent.ASK_GRADE),
            ("how am i performing", ChatIntent.ASK_ACADEMIC_PERFORMANCE),
            ("help me with math", ChatIntent.ASK_SUBJECT_HELP),
            ("do you have a module for algebra", ChatIntent.ASK_LEARNING_RESOURCE),
            ("how do i study better", ChatIntent.ASK_STUDY_STRATEGY),
            ("any suggestions for improving", ChatIntent.ASK_RECOMMENDATION),
            ("what is my attendance", ChatIntent.ASK_ATTENDANCE),
            ("am i doing okay with my attendance",
             ChatIntent.ASK_ATTENDANCE_STATUS),
            ("what is the assessment about", ChatIntent.ASK_ASSESSMENT),
            ("when is the quiz", ChatIntent.ASSESSMENT_SCHEDULE),
            ("how many questions is the quiz",
             ChatIntent.ASSESSMENT_INSTRUCTIONS),
            ("is guidance available", ChatIntent.GUIDANCE_HELP),
            ("i am worried about classes", ChatIntent.EXPRESS_CONCERN),
            ("i want to talk to a counselor", ChatIntent.REQUEST_COUNSELOR),
            ("i am in a crisis", ChatIntent.URGENT_CONCERN),
        ]

        produced = {classify_intent(text) for text, _ in probes}
        declared = set(ChatIntent)

        self.assertEqual(
            declared - produced, set(), "intents with no classifier branch"
        )

    def test_attendance_status_is_distinct_from_attendance(self):
        """
        A status question and a count question get different answers, so they
        must not collapse into one intent.
        """
        self.assertEqual(
            classify_intent("am i doing okay with my attendance?"),
            ChatIntent.ASK_ATTENDANCE_STATUS,
        )
        self.assertEqual(
            classify_intent("how many absences do i have?"),
            ChatIntent.ASK_ATTENDANCE,
        )

    def test_assessment_instructions_is_distinct_from_schedule(self):
        self.assertEqual(
            classify_intent("how many questions is the quiz?"),
            ChatIntent.ASSESSMENT_INSTRUCTIONS,
        )
        self.assertEqual(
            classify_intent("when is the quiz?"),
            ChatIntent.ASSESSMENT_SCHEDULE,
        )


class TaglishIntentTest(ChatbotBase):
    """
    Taglish — Tagalog function words with English loanwords, no diacritics.

    This is the form most questions actually arrive in at HIS CARE, and it is a
    separate problem from typos. Correctly-spelled Taglish was 82% before the
    `absen` and `makipag-usap` stems were added, because the patterns were
    English-only in two specific places:

      "ilang absen ko"                 -> UNKNOWN (no `absen` stem)
      "gusto ko makipag-usap sa ... "  -> GUIDANCE_HELP (bare `counselor`)

    The second is the more serious of the two: the student asked to talk to
    someone and was answered "Guidance is available to support you", which reads
    as being deflected rather than helped.
    """

    def test_taglish_grade(self):
        self.assertEqual(
            classify_intent("anong grade ko sa math"), ChatIntent.ASK_GRADE
        )
        self.assertEqual(
            classify_intent("magkano grade ko"), ChatIntent.ASK_GRADE
        )

    def test_taglish_attendance_uses_the_absen_stem(self):
        """
        `absen` is the Filipino stem. The English-only `absent\\w*` never
        matched it, so this fell through to UNKNOWN and the bot replied "I'm
        sorry, I didn't fully understand".
        """
        self.assertEqual(
            classify_intent("ilang absen ko"), ChatIntent.ASK_ATTENDANCE
        )

    def test_taglish_attendance_status(self):
        self.assertEqual(
            classify_intent("okay ba attendance ko"),
            ChatIntent.ASK_ATTENDANCE_STATUS,
        )

    def test_taglish_schedule(self):
        self.assertEqual(
            classify_intent("kailan ang quiz"),
            ChatIntent.ASSESSMENT_SCHEDULE,
        )
        self.assertEqual(
            classify_intent("kailan yung assessment"),
            ChatIntent.ASSESSMENT_SCHEDULE,
        )

    def test_taglish_subject_help(self):
        self.assertEqual(
            classify_intent("tolong sa math"), ChatIntent.ASK_SUBJECT_HELP
        )

    def test_taglish_resource_and_recommendation(self):
        self.assertEqual(
            classify_intent("may resource kayo for algebra"),
            ChatIntent.ASK_LEARNING_RESOURCE,
        )
        self.assertEqual(
            classify_intent("may suggestion kayo"),
            ChatIntent.ASK_RECOMMENDATION,
        )

    def test_taglish_request_counselor_is_not_deflected(self):
        """
        The regression that mattered: this used to resolve to GUIDANCE_HELP,
        because the message contains `counselor` and GUIDANCE_HELP_PATTERNS
        matched it. An explicit "I want to talk to someone" is a request for a
        person, not a question about whether the office exists.
        """
        self.assertEqual(
            classify_intent("gusto ko makipag-usap sa counselor"),
            ChatIntent.REQUEST_COUNSELOR,
        )

    def test_guidance_help_is_still_distinguishable(self):
        """
        Narrowing the counselor patterns must not collapse the two intents.
        """
        self.assertEqual(
            classify_intent("is guidance available?"),
            ChatIntent.GUIDANCE_HELP,
        )

    def test_taglish_concern(self):
        self.assertEqual(
            classify_intent("nervous ako sa klase"), ChatIntent.EXPRESS_CONCERN
        )


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
