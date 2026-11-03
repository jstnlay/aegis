"""
Phase 9 chatbot tests.

Covers: intent taxonomy, permissions, cross-student isolation,
unknown intent, low-confidence, fallback, urgency, escalation.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
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
from apps.attendance.models import AttendanceRecord
from apps.chatbot.policies import (
    classify_intent,
    classify_urgency,
    detect_urgent,
    parse_message,
)
from apps.chatbot.providers import (
    ChainProvider,
    ChatProviderRequest,
    OllamaProvider,
    OpenAICompatProvider,
    redact,
)
from apps.chatbot.taxonomy import ChatIntent, UrgencyLevel
from apps.guidance.models import RiskAlert

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

    def test_full_subject_name_reaches_subject_help(self):
        """
        The real subject names, not only the abbreviations.

        "Mathematics" is what the grade book stores; a bare `\bmath\b` does not
        match it, so the message used to fall through to HELP.
        """
        self.assertEqual(
            classify_intent("I need help with Mathematics"),
            ChatIntent.ASK_SUBJECT_HELP,
        )
        self.assertEqual(
            classify_intent("Can you help me with Edukasyon?"),
            ChatIntent.ASK_SUBJECT_HELP,
        )

    def test_assessment_plural_reaches_assessment(self):
        """"What assessments do I have?" is the natural phrasing."""
        self.assertEqual(
            classify_intent("What assessments do I have?"),
            ChatIntent.ASK_ASSESSMENT,
        )
        self.assertEqual(
            classify_intent("Do I have any quizzes?"),
            ChatIntent.ASK_ASSESSMENT,
        )


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
            ("am i at risk", ChatIntent.ASK_RISK_STATUS),
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


class ChatbotDynamicDataTest(ChatbotAPIBase):
    """
    The bot answers from imported records, not templates.

    The existing templates are still the fallback shape; these assertions pin
    the data path that replaced the static numbers.
    """

    def _make_student(self, email, student_id):
        user = User.objects.create_user(
            email=email, password="pass12345",
            first_name="Data", last_name="Student", role="student",
        )
        profile = StudentProfile.objects.create(
            user=user,
            student_id=student_id,
            grade_level=self.grade_level,
            section=self.section,
            enrollment_date=date(2024, 6, 10),
        )
        Enrollment.objects.create(
            student=profile, section=self.section,
            academic_year=self.academic_year, date_enrolled=date(2024, 6, 10),
            is_active=True,
        )
        return user, profile

    def test_grade_query_returns_status_and_recommendations(self):
        resp = self.post_message("How are my grades?", self.student_user)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["intent"], "ask_grade")
        payload = resp.data["data"]
        self.assertIn("grade_summary", payload)
        self.assertIn("academic_status", payload)
        self.assertIn("recommendations", payload)
        self.assertEqual(payload["grade_summary"]["data_status"], "finalized")
        self.assertEqual(payload["grade_summary"]["subject_count"], 1)
        self.assertEqual(payload["academic_status"]["status"], "on_track")

    def test_imported_draft_grades_are_reported_as_provisional(self):
        user, profile = self._make_student("chat_draft@test.com", "CHATDRAFT")
        Grade.objects.create(
            student=profile, subject_assignment=self.sa,
            grading_period=self.gp, score=Decimal("62"), status="draft",
            encoded_by=self.faculty_profile,
        )

        resp = self.post_message("What is my grade?", user)

        payload = resp.data["data"]["grade_summary"]
        self.assertEqual(payload["data_status"], "pending_finalization")
        self.assertTrue(resp.data["data"]["academic_status"]["provisional"])
        self.assertEqual(payload["average"], 62.0)

    def test_at_risk_student_reported_for_risk_question(self):
        user, profile = self._make_student("chat_risk@test.com", "CHATRISK")
        Grade.objects.create(
            student=profile, subject_assignment=self.sa,
            grading_period=self.gp, score=Decimal("60"), status="finalized",
            encoded_by=self.faculty_profile,
        )

        resp = self.post_message("Am I at risk?", user)

        self.assertEqual(resp.data["intent"], "ask_risk_status")
        status_payload = resp.data["data"]["academic_status"]
        self.assertEqual(status_payload["status"], "at_risk")
        self.assertIn("at-risk band", resp.data["reply"])

    def test_grade_reply_names_every_weak_subject(self):
        """
        The reply lists all of them, never a first few.

        Five is deliberate: the reply used to stop at three, which read as if
        the missing subjects were fine.
        """
        user, profile = self._make_student("chat_weak@test.com", "CHATWEAK")
        names = []
        for index, score in enumerate(["51", "52", "53", "54", "55"]):
            subject = Subject.objects.create(
                name=f"Weak Subject {index}",
                code=f"WEAK-{index}",
                grade_level=self.grade_level,
            )
            assignment = SubjectAssignment.objects.create(
                subject=subject, section=self.section,
                academic_year=self.academic_year, faculty=self.faculty_profile,
            )
            Grade.objects.create(
                student=profile, subject_assignment=assignment,
                grading_period=self.gp, score=Decimal(score),
                status="finalized", encoded_by=self.faculty_profile,
            )
            names.append(subject.name)

        resp = self.post_message("How are my grades?", user)

        weak = resp.data["data"]["academic_status"]["weak_subjects"]
        self.assertEqual(len(weak), 5)
        for name in names:
            self.assertIn(name, resp.data["reply"])

    def test_subject_help_quotes_the_grade_book_not_a_guess(self):
        """
        "help me with Mathematics" names the student's own score.

        The provider used to answer this intent and produced "the overall
        average for Mathematics is a C-. You are currently on track" for a
        student whose Mathematics grade was 55. The number comes from the
        summary, so an invented one is impossible here.
        """
        user, profile = self._make_student("chat_help@test.com", "CHATHELP")
        Grade.objects.create(
            student=profile, subject_assignment=self.sa,
            grading_period=self.gp, score=Decimal("55"), status="finalized",
            encoded_by=self.faculty_profile,
        )

        resp = self.post_message("I need help with Mathematics", user)

        self.assertEqual(resp.data["intent"], "ask_subject_help")
        self.assertIn("55.00%", resp.data["reply"])
        self.assertIn("Mathematics", resp.data["reply"])

    def test_study_strategy_names_the_weak_subjects(self):
        user, profile = self._make_student("chat_strategy@test.com", "CHATSTRAT")
        Grade.objects.create(
            student=profile, subject_assignment=self.sa,
            grading_period=self.gp, score=Decimal("58"), status="finalized",
            encoded_by=self.faculty_profile,
        )

        resp = self.post_message("How should I study?", user)

        self.assertEqual(resp.data["intent"], "ask_study_strategy")
        self.assertIn("Mathematics", resp.data["reply"])

    def test_assessment_question_is_honest_about_missing_coverage(self):
        resp = self.post_message("What assessments do I have?", self.student_user)

        self.assertEqual(resp.data["intent"], "ask_assessment")
        self.assertIn("teacher", resp.data["reply"])

    def test_attendance_query_uses_imported_records(self):
        AttendanceRecord.objects.create(
            student=self.student_profile, section=self.section,
            date=date(2024, 6, 11), status="present",
            recorded_by=self.faculty_profile,
        )
        AttendanceRecord.objects.create(
            student=self.student_profile, section=self.section,
            date=date(2024, 6, 12), status="late",
            recorded_by=self.faculty_profile,
        )
        AttendanceRecord.objects.create(
            student=self.student_profile, section=self.section,
            date=date(2024, 6, 13), status="absent",
            recorded_by=self.faculty_profile,
        )

        resp = self.post_message("What is my attendance?", self.student_user)

        summary = resp.data["data"]["attendance_summary"]
        self.assertEqual(summary["present_count"], 1)
        self.assertEqual(summary["late_count"], 1)
        self.assertEqual(summary["absent_count"], 1)
        self.assertEqual(len(summary["recent_records"]), 3)

    def test_recommendation_intent_uses_computed_recommendations(self):
        from apps.cms.models import LearningItem

        LearningItem.objects.create(
            item_type=LearningItem.ItemType.LEARNING_RESOURCE,
            title="Mathematics practice set",
            lifecycle_status=LearningItem.LifecycleStatus.APPROVED,
            is_active=True,
            grade_level=self.grade_level,
            subject=self.subject,
        )

        resp = self.post_message("Any suggestions for improving?", self.student_user)

        payload = resp.data["data"]["recommendations"]
        self.assertIn("recommendations", payload)
        self.assertIn("method", payload)


class ChatbotSafetyEscalationTest(ChatbotAPIBase):
    """
    A distress signal reaches Guidance through the same risk surface staff
    already monitor, without quoting the student's message back at them.
    """

    def setUp(self):
        super().setUp()
        User.objects.create_user(
            email="chat_guidance_safety@test.com", password="pass12345",
            first_name="Safe", last_name="Guidance", role="guidance",
        )

    def test_crisis_message_creates_one_open_risk_alert(self):
        from apps.notifications.models import Notification

        Notification.objects.all().delete()
        resp = self.post_message("I want to kill myself", self.student_user)

        self.assertTrue(resp.data["escalated"])
        alerts = RiskAlert.objects.filter(
            student=self.student_profile, source=RiskAlert.Source.CHATBOT
        )
        self.assertEqual(alerts.count(), 1)
        self.assertEqual(alerts.first().risk_level, RiskAlert.RiskLevel.HIGH)
        # The message body is never persisted into the alert.
        self.assertNotIn("kill", str(alerts.first().risk_factors).lower())
        self.assertEqual(Notification.objects.count(), 1)

    def test_repeated_crisis_does_not_duplicate_open_alert(self):
        self.post_message("I want to kill myself", self.student_user)
        self.post_message("I want to hurt myself", self.student_user)

        alerts = RiskAlert.objects.filter(
            student=self.student_profile, source=RiskAlert.Source.CHATBOT
        )
        self.assertEqual(alerts.count(), 1)

    def test_ordinary_concern_does_not_create_risk_alert(self):
        resp = self.post_message("I am worried about my grades", self.student_user)

        self.assertFalse(resp.data["escalated"])
        self.assertFalse(
            RiskAlert.objects.filter(
                student=self.student_profile, source=RiskAlert.Source.CHATBOT
            ).exists()
        )

    @override_settings(AEGIS_CRISIS_HELPLINE="1553")
    def test_distress_reply_includes_configured_helpline(self):
        resp = self.post_message("I want to hurt myself", self.student_user)

        self.assertIn("1553", resp.data["reply"])
        self.assertIn("911", resp.data["reply"])


class ChatbotProviderTest(ChatbotAPIBase):
    """
    The provider abstraction is a boundary: a provider gets authorized data
    and returns prose, and any failure falls back to the deterministic reply.
    """

    class GoodProvider:
        def __init__(self):
            self.requests = []

        def generate(self, request):
            self.requests.append(request)
            return "Provider-generated answer."

    class FailingProvider:
        def generate(self, request):
            raise RuntimeError("provider offline")

    def test_provider_reply_is_used_when_it_succeeds(self):
        from apps.chatbot import service

        provider = self.GoodProvider()
        response = service.handle_message(
            self.student_user,
            "How should I study for Math?",
            use_llm=True,
            provider=provider,
        )

        self.assertEqual(response.reply, "Provider-generated answer.")
        self.assertFalse(response.degraded)
        self.assertEqual(provider.requests[0].user_role, "student")
        # The advice intent is handed the weak subjects, not the whole record.
        self.assertIn("weak_subjects", provider.requests[0].data)
        self.assertNotIn("grade_summary", provider.requests[0].data)

    def test_provider_is_not_consulted_for_a_grade_question(self):
        """
        The record-keeping answers are the application's, not a model's.

        The local model reversed a comparison — "68.6, which is above the
        required 75 to pass" — with every number in the sentence correct, so no
        value check could catch it. Grade, status, risk, attendance and
        recommendation questions therefore never reach a provider.
        """
        from apps.chatbot import service

        for question in (
            "What is my grade in Math?",
            "How am I doing academically?",
            "Am I at risk?",
            "What is my attendance?",
            "What should I study?",
        ):
            provider = self.GoodProvider()
            response = service.handle_message(
                self.student_user, question, use_llm=True, provider=provider
            )
            self.assertEqual(
                provider.requests, [], f"provider consulted for {question!r}"
            )
            self.assertFalse(response.degraded)

    class EnumLeakingProvider:
        """A provider that quotes internal field values back at the student."""

        def generate(self, request):
            return 'Your status is "at_risk" and you are on_track elsewhere.'

    def test_internal_field_values_never_reach_the_student(self):
        """
        The reply must not contain a database value, even if a provider does.

        The local model wrote "you are at_risk" verbatim, so this is enforced on
        the way out rather than requested in the prompt.
        """
        from apps.chatbot import service

        response = service.handle_message(
            self.student_user,
            "How should I study for Math?",
            use_llm=True,
            provider=self.EnumLeakingProvider(),
        )

        self.assertNotIn("at_risk", response.reply)
        self.assertNotIn("on_track", response.reply)
        self.assertIn("at risk", response.reply)

    class PayloadDumpingProvider:
        """A provider that restates the record instead of giving advice."""

        def generate(self, request):
            # No digits, so only the section-label check can reject this.
            return (
                "**Academic Status:** you are at risk. "
                "**Recommendations:** Content-based study activity - Mathematics"
            )

    def test_payload_dump_is_discarded(self):
        """
        The advice reply must be advice.

        Asked how to study, the local model copied the sections it was handed
        and invented a recommendation title no record held. The provider is no
        longer given those sections, and a reply that prints a section label is
        discarded in favour of the deterministic advice.
        """
        from apps.chatbot import service

        response = service.handle_message(
            self.student_user,
            "How should I study for Math?",
            use_llm=True,
            provider=self.PayloadDumpingProvider(),
        )

        self.assertTrue(response.degraded)
        self.assertNotIn("Academic Status", response.reply)
        self.assertNotIn("Content-based study activity", response.reply)

    class InventingProvider:
        """A provider that states a grade it was never given."""

        def generate(self, request):
            return "Your average in Math is 85%. You are on track."

    def test_ungrounded_number_is_discarded(self):
        """
        A number the provider was not handed is treated as an invention.

        The API fixture's only grade is 88, so 85 cannot come from the
        authorized data. The deterministic reply must stand instead.
        """
        from apps.chatbot import service

        response = service.handle_message(
            self.student_user,
            "How should I study for Math?",
            use_llm=True,
            provider=self.InventingProvider(),
        )

        self.assertTrue(response.degraded)
        self.assertNotIn("85", response.reply)
        self.assertIn("grade_summary", response.data)

    def test_provider_failure_falls_back_to_structured_reply(self):
        from apps.chatbot import service

        response = service.handle_message(
            self.student_user,
            "How should I study for Math?",
            use_llm=True,
            provider=self.FailingProvider(),
        )

        self.assertTrue(response.degraded)
        self.assertIn("grade_summary", response.data)
        self.assertNotEqual(response.reply, "")

    def test_provider_receives_no_cross_student_data(self):
        from apps.chatbot import service

        provider = self.GoodProvider()
        service.handle_message(
            self.student_user,
            "How should I study for Math?",
            use_llm=True,
            provider=provider,
        )

        request = provider.requests[0]
        self.assertNotIn(str(self.other_profile.id), str(request.data))

    def test_provider_is_not_consulted_for_a_distress_signal(self):
        from apps.chatbot import service

        provider = self.GoodProvider()
        response = service.handle_message(
            self.student_user,
            "I want to kill myself",
            use_llm=True,
            provider=provider,
        )

        self.assertTrue(response.escalated)
        self.assertEqual(provider.requests, [])

    def test_provider_is_not_consulted_for_a_non_eligible_intent(self):
        from apps.chatbot import service

        provider = self.GoodProvider()
        response = service.handle_message(
            self.student_user,
            "hello there",
            use_llm=True,
            provider=provider,
        )

        # A greeting is answered deterministically, so the model is never asked
        # and this is a deliberate path, not a degraded one.
        self.assertEqual(provider.requests, [])
        self.assertFalse(response.degraded)
        self.assertEqual(response.intent, "greeting")


class _StubProvider:
    """A provider that records what it was given and returns a fixed reply."""

    offsite = False

    def __init__(self, reply=None):
        self.reply = reply
        self.calls = 0
        self.seen = None

    def generate(self, request):
        self.calls += 1
        self.seen = request
        return self.reply


class _OffsiteStub(_StubProvider):
    offsite = True


class _BoomProvider:
    offsite = False

    def generate(self, request):
        raise RuntimeError("provider offline")


class ChatbotProviderChainTest(SimpleTestCase):
    """
    The chain is the deployment shape: a local model plus optional offsite
    models, first usable reply wins, a failure never blocks the next, and an
    offsite provider never sees a direct student identifier.
    """

    def _request(self, data=None):
        return ChatProviderRequest(
            user_role="student",
            message="What is my grade in Math?",
            intent="ask_grade",
            urgency="normal",
            data=(
                data
                if data is not None
                else {
                    "grade_summary": {
                        "student_id": "ABC-123",
                        "student_name": "Ana Dela Cruz",
                        "average": 82.0,
                    }
                }
            ),
        )

    def test_chain_uses_the_first_provider_that_replies(self):
        first = _StubProvider(reply=None)
        second = _StubProvider(reply="second answer")

        reply = ChainProvider([first, second]).generate(self._request())

        self.assertEqual(reply, "second answer")
        self.assertEqual(first.calls, 1)

    def test_chain_skips_a_failing_provider(self):
        good = _StubProvider(reply="still works")

        reply = ChainProvider([_BoomProvider(), good]).generate(self._request())

        self.assertEqual(reply, "still works")
        self.assertEqual(good.calls, 1)

    def test_chain_returns_none_when_every_provider_fails(self):
        chain = ChainProvider([_BoomProvider(), _StubProvider(reply=None)])

        self.assertIsNone(chain.generate(self._request()))

    def test_offsite_provider_receives_a_redacted_payload(self):
        offsite = _OffsiteStub(reply="ok")
        request = self._request()

        ChainProvider([offsite]).generate(request)

        summary = offsite.seen.data["grade_summary"]
        self.assertNotIn("student_id", summary)
        self.assertNotIn("student_name", summary)
        self.assertEqual(summary["average"], 82.0)
        # The caller's own request object is untouched.
        self.assertIn("student_name", request.data["grade_summary"])

    def test_local_provider_receives_the_full_payload(self):
        local = _StubProvider(reply="ok")

        ChainProvider([local]).generate(self._request())

        self.assertIn("student_name", local.seen.data["grade_summary"])

    @override_settings(AEGIS_CHATBOT_REDACT_OFFSITE=False)
    def test_redaction_can_be_disabled(self):
        offsite = _OffsiteStub(reply="ok")

        ChainProvider([offsite]).generate(self._request())

        self.assertIn("student_name", offsite.seen.data["grade_summary"])

    def test_redact_keeps_non_identifying_data(self):
        clean = redact(
            {
                "student_id": "ABC-123",
                "grade_summary": {"student_name": "Ana", "average": 82.0},
                "recommendations": {"student_id": "ABC-123", "method": "cf"},
            }
        )

        self.assertNotIn("student_id", clean)
        self.assertEqual(clean["grade_summary"], {"average": 82.0})
        self.assertEqual(clean["recommendations"]["method"], "cf")

    def test_ollama_provider_parses_and_blank_is_no_reply(self):
        with patch("apps.chatbot.providers._post_json") as post:
            post.return_value = {"response": "  local answer  "}
            self.assertEqual(
                OllamaProvider().generate(self._request()), "local answer"
            )
            post.return_value = {"response": ""}
            self.assertIsNone(OllamaProvider().generate(self._request()))

    @override_settings(
        AEGIS_CHATBOT_OPENAI_BASE_URL="https://api.example.com/v1",
        AEGIS_CHATBOT_OPENAI_MODEL="llama-3.1-8b-instant",
        AEGIS_CHATBOT_OPENAI_API_KEY="test-key",
    )
    def test_openai_compat_provider_parses_choices(self):
        with patch("apps.chatbot.providers._post_json") as post:
            post.return_value = {
                "choices": [{"message": {"content": " cloud answer "}}]
            }
            self.assertEqual(
                OpenAICompatProvider().generate(self._request()), "cloud answer"
            )

    @override_settings(AEGIS_CHATBOT_OPENAI_BASE_URL="", AEGIS_CHATBOT_OPENAI_MODEL="")
    def test_openai_compat_provider_without_config_is_unavailable(self):
        self.assertIsNone(OpenAICompatProvider().generate(self._request()))

    @override_settings(
        AEGIS_CHATBOT_PROVIDER_CHAIN=(
            "apps.chatbot.providers.OpenAICompatProvider,"
            "apps.chatbot.providers.OllamaProvider"
        ),
        AEGIS_CHATBOT_OPENAI_BASE_URL="https://api.example.com/v1",
        AEGIS_CHATBOT_OPENAI_MODEL="llama-3.1-8b-instant",
        AEGIS_CHATBOT_OPENAI_API_KEY="test-key",
    )
    def test_get_provider_builds_a_chain_and_falls_through_to_local(self):
        from apps.chatbot import providers

        with patch.object(providers, "_post_json") as post:
            post.side_effect = [
                RuntimeError("cloud offline"),
                {"response": "local answer"},
            ]
            provider = providers.get_provider()
            reply = provider.generate(self._request())

        self.assertIsInstance(provider, ChainProvider)
        self.assertEqual(reply, "local answer")
        self.assertIn(
            "chat/completions", post.call_args_list[0].args[0]
        )
        self.assertIn("/api/generate", post.call_args_list[1].args[0])

    def test_default_chain_is_local_first_with_cloud_fallback(self):
        from django.conf import settings

        paths = [
            path.strip()
            for path in settings.AEGIS_CHATBOT_PROVIDER_CHAIN.split(",")
            if path.strip()
        ]

        self.assertEqual(
            paths,
            [
                "apps.chatbot.providers.OllamaProvider",
                "apps.chatbot.providers.OpenAICompatProvider",
            ],
        )

    @override_settings(
        AEGIS_CHATBOT_PROVIDER_CHAIN=(
            "apps.chatbot.providers.OllamaProvider,"
            "apps.chatbot.providers.OpenAICompatProvider"
        ),
        AEGIS_CHATBOT_OPENAI_BASE_URL="https://api.example.com/v1",
        AEGIS_CHATBOT_OPENAI_MODEL="llama-3.1-8b-instant",
        AEGIS_CHATBOT_OPENAI_API_KEY="test-key",
    )
    def test_local_provider_wins_and_the_cloud_is_not_called(self):
        from apps.chatbot import providers

        with patch.object(providers, "_post_json") as post:
            post.return_value = {"response": "local answer"}
            reply = providers.get_provider().generate(self._request())

        self.assertEqual(reply, "local answer")
        self.assertEqual(post.call_count, 1)
        self.assertIn("/api/generate", post.call_args_list[0].args[0])
