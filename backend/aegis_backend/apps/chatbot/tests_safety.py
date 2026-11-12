"""
Tests for the two-layer safety workstream.

What these assert, and why each one exists:

* **Layer 1 alone** decides a message when the model is unavailable, and a
  keyword term an administrator deactivated really stops firing.
* **Layer 2 can raise a severity but never lower one.** A model that calls a
  self-harm message "low" must not be able to talk the application out of
  routing it.
* **A Gemini failure never fails open silently.** The message is still
  screened by Layer 1 and marked for manual review.
* **Routing follows severity.** Critical reaches admin, high does not, medium
  never reaches faculty.
* **A faculty notice carries no content.** No student name, no message, no
  reply, no categories — checked on the notification text and on the API
  payload.
* **The acknowledgment timer has teeth.** An unacknowledged flag is escalated
  to administrators; an acknowledged one is not; escalating twice does
  nothing the second time.
* **A student cannot chat before accepting the notice.**
"""

from datetime import date
from unittest.mock import patch

import base64
import secrets

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    FacultyProfile,
    GuidanceProfile,
    StudentProfile,
)
from apps.academics.models import (
    AcademicYear,
    Enrollment,
    GradeLevel,
    Section,
    Subject,
    SubjectAssignment,
)
from apps.chatbot import gemini_client
from apps.chatbot.agreements import notice_version
from apps.chatbot.detection import detect, layer1_screen
from apps.chatbot.models import (
    AgreementAcceptance,
    ChatMessage,
    Flag,
    FlagAction,
    FlagRecipient,
    KeywordTerm,
)
from apps.chatbot import routing
from apps.chatbot.routing import (
    acknowledge_flag,
    escalate_stale_flags,
    resolve_recipients,
)
from apps.notifications.models import Notification

User = get_user_model()

#: A message Layer 1 must always catch, whatever the model says.
SELF_HARM = "I want to hurt myself"


class SafetyBase(TestCase):
    """A school small enough to route a flag to every role."""

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

        self.student_user = User.objects.create_user(
            email="safe_student@test.com",
            password="pass12345",
            first_name="Safe",
            last_name="Student",
            role="student",
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            student_id="SAFE001",
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
            accepted_at=timezone.now(),
        )

        self.guidance_user = User.objects.create_user(
            email="safe_guidance@test.com",
            password="pass12345",
            first_name="Safe",
            last_name="Counselor",
            role="guidance",
        )
        GuidanceProfile.objects.create(
            user=self.guidance_user, employee_id="SAFEG001"
        )

        self.admin_user = User.objects.create_user(
            email="safe_admin@test.com",
            password="pass12345",
            first_name="Safe",
            last_name="Admin",
            role="admin",
        )

        self.faculty_user = User.objects.create_user(
            email="safe_faculty@test.com",
            password="pass12345",
            first_name="Safe",
            last_name="Faculty",
            role="faculty",
        )
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="SAFEF001"
        )
        self.subject = Subject.objects.create(
            name="Mathematics", code="MATH-7", grade_level=self.grade_level
        )
        SubjectAssignment.objects.create(
            subject=self.subject,
            section=self.section,
            academic_year=self.academic_year,
            faculty=self.faculty_profile,
        )

    def post_message(self, message, user=None):
        self.client.force_authenticate(user=user or self.student_user)
        return self.client.post(
            "/api/v1/chatbot/message/", {"message": message}, format="json"
        )


class LayerOneTest(SafetyBase):
    """Layer 1 is the deterministic floor."""

    def test_policy_pattern_detects_self_harm(self):
        result = layer1_screen(SELF_HARM)
        self.assertTrue(result.sensitive)
        self.assertEqual(result.severity, "critical")

    def test_keyword_term_raises_severity(self):
        KeywordTerm.objects.create(
            term="exam panic",
            match_type=KeywordTerm.MatchType.PHRASE,
            severity="medium",
            category="academic_distress",
        )
        result = layer1_screen("I have exam panic about Friday")
        self.assertTrue(result.sensitive)
        self.assertEqual(result.severity, "medium")
        self.assertIn("academic_distress", result.categories)

    def test_deactivated_term_does_not_fire(self):
        KeywordTerm.objects.create(
            term="vibes",
            match_type=KeywordTerm.MatchType.KEYWORD,
            severity="critical",
            is_active=False,
        )
        result = layer1_screen("bad vibes today")
        self.assertFalse(result.sensitive)

    def test_invalid_regex_does_not_break_screening(self):
        KeywordTerm.objects.create(
            term="([unclosed",
            match_type=KeywordTerm.MatchType.REGEX,
            severity="high",
        )
        result = layer1_screen(SELF_HARM)
        # The built-in pattern still fires even though the admin regex is broken.
        self.assertEqual(result.severity, "critical")

    def test_ordinary_message_is_not_sensitive(self):
        result = layer1_screen("What is my grade in Math?")
        self.assertFalse(result.sensitive)
        self.assertEqual(result.severity, "low")


class DefaultTermPrecisionTest(TestCase):
    """
    The shipped default terms must not fire on ordinary school sentences.

    PH12 established the rule this module applies: a screening channel that
    pages a counselor about a history project about gun violence is one staff
    learn to ignore, and a real disclosure is then less likely to be read.

    These assertions run against the terms the migration actually seeded, so
    a default that gets broadened fails here rather than in production.
    """

    #: A school sentence that mentions a sensitive word without disclosing
    #: anything. None of these may raise a flag.
    BENIGN = [
        "Our history project is about gun violence in the Philippines",
        "The drug abuse seminar is on Friday",
        "How do I write a report about substance abuse education?",
        "Can you give me a resource for Science?",
    ]

    #: A disclosure that must be caught.
    DISCLOSURES = [
        ("I am being abused at home", "high"),
        ("They threatened me after class", "high"),
        ("I am bullied every day", "medium"),
        ("I feel hopeless about the quarter", "medium"),
        ("I want to drop out of school", "medium"),
    ]

    def test_benign_messages_do_not_raise_a_flag(self):
        for message in self.BENIGN:
            with self.subTest(message=message):
                result = layer1_screen(message)
                self.assertFalse(result.sensitive, message)

    def test_disclosures_are_caught_at_the_right_severity(self):
        for message, severity in self.DISCLOSURES:
            with self.subTest(message=message):
                result = layer1_screen(message)
                self.assertTrue(result.sensitive, message)
                self.assertEqual(result.severity, severity, message)

    def test_the_broad_single_word_terms_are_not_shipped(self):
        from apps.chatbot.defaults import DEFAULT_KEYWORD_TERMS

        shipped = {term for term, *_ in DEFAULT_KEYWORD_TERMS}
        for retired in ("gun", "abuse", "threaten", "bully", "depressed", "hopeless"):
            self.assertNotIn(retired, shipped)


class LayerTwoTest(SafetyBase):
    """Layer 2 augments Layer 1 and can never lower it."""

    @override_settings(GEMINI_API_KEY="")
    def test_missing_api_key_falls_back_to_layer_one(self):
        result = detect(SELF_HARM, use_gemini=True)
        self.assertTrue(result.sensitive)
        self.assertEqual(result.severity, "critical")
        self.assertTrue(result.manual_review)
        self.assertFalse(result.layer2.available)

    def test_model_failure_keeps_layer_one_answer(self):
        with patch.object(
            gemini_client,
            "classify",
            side_effect=gemini_client.GeminiError("call_failed", "boom"),
        ):
            result = detect(SELF_HARM, use_gemini=True)
        self.assertEqual(result.severity, "critical")
        self.assertTrue(result.manual_review)

    def test_model_cannot_lower_a_layer_one_severity(self):
        with patch.object(
            gemini_client,
            "classify",
            return_value={
                "sensitive": False,
                "severity": "low",
                "categories": [],
                "rationale": "",
                "confidence": 0.9,
            },
        ):
            result = detect(SELF_HARM, use_gemini=True)
        self.assertEqual(result.severity, "critical")
        self.assertTrue(result.sensitive)

    def test_model_can_raise_severity_and_add_categories(self):
        with patch.object(
            gemini_client,
            "classify",
            return_value={
                "sensitive": True,
                "severity": "high",
                "categories": ["bullying"],
                "rationale": "reports being bullied",
                "confidence": 0.8,
            },
        ):
            result = detect("Someone keeps taking my things", use_gemini=True)
        self.assertEqual(result.severity, "high")
        self.assertIn("bullying", result.categories)
        self.assertEqual(result.source, "gemini")

    def test_union_of_categories(self):
        KeywordTerm.objects.create(
            term="bullied",
            match_type=KeywordTerm.MatchType.KEYWORD,
            severity="medium",
            category="bullying",
        )
        with patch.object(
            gemini_client,
            "classify",
            return_value={
                "sensitive": True,
                "severity": "high",
                "categories": ["distress"],
                "rationale": "",
                "confidence": 0.7,
            },
        ):
            result = detect("I am bullied every day", use_gemini=True)
        self.assertIn("bullying", result.categories)
        self.assertIn("distress", result.categories)
        self.assertEqual(result.source, "combined")


class RoutingTest(SafetyBase):
    """Severity decides who hears about a flag."""

    def _flag(self, severity, message="a message"):
        chat_message = ChatMessage.objects.create(
            user=self.student_user, message=message, reply="reply"
        )
        return Flag.objects.create(
            student=self.student,
            user=self.student_user,
            chat_message=chat_message,
            severity=severity,
            source="keyword",
            categories=["distress"],
        )

    def test_critical_reaches_guidance_admin_and_faculty(self):
        flag = self._flag("critical")
        recipients = resolve_recipients(flag)
        self.assertEqual(len(recipients["guidance"]), 1)
        self.assertEqual(len(recipients["admin"]), 1)
        self.assertEqual(len(recipients["faculty"]), 1)

    def test_high_reaches_guidance_and_faculty_but_not_admin(self):
        flag = self._flag("high")
        recipients = resolve_recipients(flag)
        self.assertEqual(len(recipients["guidance"]), 1)
        self.assertEqual(len(recipients["faculty"]), 1)
        self.assertEqual(len(recipients["admin"]), 0)

    def test_medium_reaches_guidance_only(self):
        flag = self._flag("medium")
        recipients = resolve_recipients(flag)
        self.assertEqual(len(recipients["guidance"]), 1)
        self.assertEqual(len(recipients["faculty"]), 0)
        self.assertEqual(len(recipients["admin"]), 0)

    def test_faculty_notice_carries_no_content(self):
        """The notice says a student needs support and nothing else."""
        response = self.post_message(SELF_HARM)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        notification = Notification.objects.filter(
            recipient=self.faculty_user
        ).first()
        self.assertIsNotNone(notification)
        body = f"{notification.title} {notification.message}".lower()
        self.assertNotIn("safe student", body)
        self.assertNotIn("hurt myself", body)
        self.assertNotIn(self.student.student_id.lower(), body)
        self.assertNotIn("self_harm", body)

    def test_faculty_feed_payload_has_no_content(self):
        self.post_message(SELF_HARM)
        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.get("/api/v1/chatbot/flags/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["results"][0]
        for forbidden in (
            "student",
            "student_name",
            "message",
            "reply",
            "summary",
            "categories",
        ):
            self.assertNotIn(forbidden, row)

    def test_student_cannot_read_the_flag_inbox(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/v1/chatbot/flags/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AcknowledgmentTimerTest(SafetyBase):
    """The timer is data, not a daemon, but it still has to fire."""

    def _flag(self, severity="high"):
        chat_message = ChatMessage.objects.create(
            user=self.student_user, message="please help", reply="ok"
        )
        return Flag.objects.create(
            student=self.student,
            user=self.student_user,
            chat_message=chat_message,
            severity=severity,
            source="keyword",
            categories=["distress"],
            escalation_due_at=timezone.now() - timezone.timedelta(minutes=1),
        )

    def test_unacknowledged_flag_is_escalated_to_admin(self):
        flag = self._flag()
        escalated = escalate_stale_flags()
        self.assertEqual([row.id for row in escalated], [flag.id])
        flag.refresh_from_db()
        self.assertIsNotNone(flag.escalated_at)
        self.assertEqual(flag.status, Flag.Status.UNDER_REVIEW)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.admin_user,
                deduplication_key=f"chat_flag_escalated:{flag.id}",
            ).exists()
        )

    def test_acknowledged_flag_is_not_escalated(self):
        flag = self._flag()
        acknowledge_flag(flag, user=self.guidance_user)
        self.assertEqual(escalate_stale_flags(), [])
        flag.refresh_from_db()
        self.assertIsNone(flag.escalated_at)

    def test_escalation_is_idempotent(self):
        self._flag()
        self.assertEqual(len(escalate_stale_flags()), 1)
        self.assertEqual(len(escalate_stale_flags()), 0)

    def test_faculty_cannot_acknowledge(self):
        flag = self._flag()
        # The faculty member has to be a recipient for the flag to be visible
        # to them at all; the question here is what they may do with it.
        FlagRecipient.objects.create(
            flag=flag, user=self.faculty_user, role_snapshot="faculty"
        )
        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.post(
            f"/api/v1/chatbot/flags/{flag.id}/acknowledge/", {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_guidance_acknowledge_records_the_action(self):
        flag = self._flag()
        self.client.force_authenticate(user=self.guidance_user)
        response = self.client.post(
            f"/api/v1/chatbot/flags/{flag.id}/acknowledge/",
            {"note": "On it."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        flag.refresh_from_db()
        self.assertIsNotNone(flag.acknowledged_at)
        self.assertEqual(flag.acknowledged_by_id, self.guidance_user.id)
        self.assertTrue(
            FlagAction.objects.filter(
                flag=flag, action=FlagAction.Action.ACKNOWLEDGED
            ).exists()
        )


class FlagLifecycleTest(SafetyBase):
    """Notes, resolution and false positives, with the role checks."""

    def _flag(self):
        chat_message = ChatMessage.objects.create(
            user=self.student_user, message="please help", reply="ok"
        )
        return Flag.objects.create(
            student=self.student,
            user=self.student_user,
            chat_message=chat_message,
            severity="medium",
            source="keyword",
            categories=["distress"],
        )

    def test_case_note_is_private(self):
        flag = self._flag()
        self.client.force_authenticate(user=self.guidance_user)
        response = self.client.post(
            f"/api/v1/chatbot/flags/{flag.id}/notes/",
            {"note": "Called the adviser."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        action = FlagAction.objects.get(flag=flag, action=FlagAction.Action.NOTE)
        self.assertTrue(action.is_private)

    def test_resolve_closes_the_flag(self):
        flag = self._flag()
        self.client.force_authenticate(user=self.guidance_user)
        response = self.client.post(
            f"/api/v1/chatbot/flags/{flag.id}/resolve/",
            {"note": "Handled."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        flag.refresh_from_db()
        self.assertEqual(flag.status, Flag.Status.RESOLVED)
        self.assertIsNotNone(flag.resolved_at)

    def test_false_positive_is_recorded_for_feedback(self):
        flag = self._flag()
        self.client.force_authenticate(user=self.guidance_user)
        response = self.client.post(
            f"/api/v1/chatbot/flags/{flag.id}/false-positive/",
            {"note": "Slang, not a disclosure."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        flag.refresh_from_db()
        self.assertEqual(flag.status, Flag.Status.FALSE_POSITIVE)

    def test_student_cannot_add_a_case_note(self):
        flag = self._flag()
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(
            f"/api/v1/chatbot/flags/{flag.id}/notes/",
            {"note": "not mine"},
            format="json",
        )
        # 404, not 403: a student is not a recipient, so the flag does not
        # exist as far as they are concerned. Naming it would disclose that a
        # counselor was told something about them.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_guidance_sees_the_message_and_faculty_does_not(self):
        flag = self._flag()
        self.client.force_authenticate(user=self.guidance_user)
        response = self.client.get(f"/api/v1/chatbot/flags/{flag.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "please help")

        FlagRecipient.objects.create(
            flag=flag, user=self.faculty_user, role_snapshot="faculty"
        )
        self.client.force_authenticate(user=self.faculty_user)
        response = self.client.get(f"/api/v1/chatbot/flags/{flag.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AdminConsoleTest(SafetyBase):
    """The administrator's console, and the false-positive feedback loop."""

    def _flag(self, severity="medium"):
        chat_message = ChatMessage.objects.create(
            user=self.student_user, message="please help", reply="ok"
        )
        return Flag.objects.create(
            student=self.student,
            user=self.student_user,
            chat_message=chat_message,
            severity=severity,
            source="keyword",
            categories=["distress"],
        )

    def test_dashboard_is_admin_only(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/v1/chatbot/admin/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dashboard_reports_the_model_status(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/api/v1/chatbot/admin/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("model", response.data)
        self.assertEqual(response.data["acknowledgment"]["timer_minutes"], 15)

    def test_false_positives_are_listed_for_the_admin(self):
        flag = self._flag()
        flag.status = Flag.Status.FALSE_POSITIVE
        flag.resolution_note = "Slang, not a disclosure."
        flag.save()

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/api/v1/chatbot/admin/dashboard/")
        self.assertEqual(response.data["false_positives"]["total"], 1)
        recent = response.data["false_positives"]["recent"]
        self.assertEqual(recent[0]["id"], str(flag.id))
        self.assertEqual(recent[0]["note"], "Slang, not a disclosure.")

    def test_false_positive_listing_does_not_repeat_the_message(self):
        flag = self._flag()
        flag.status = Flag.Status.FALSE_POSITIVE
        flag.save()

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/api/v1/chatbot/admin/dashboard/")
        row = response.data["false_positives"]["recent"][0]
        self.assertNotIn("message", row)
        self.assertNotIn("reply", row)

    def test_keyword_crud_is_admin_only(self):
        self.client.force_authenticate(user=self.guidance_user)
        response = self.client.post(
            "/api/v1/chatbot/admin/keywords/",
            {"term": "test", "match_type": "keyword", "severity": "low"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_and_deactivate_a_keyword(self):
        self.client.force_authenticate(user=self.admin_user)
        created = self.client.post(
            "/api/v1/chatbot/admin/keywords/",
            {
                "term": "test phrase",
                "match_type": "phrase",
                "severity": "medium",
                "category": "distress",
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        updated = self.client.patch(
            f"/api/v1/chatbot/admin/keywords/{created.data['id']}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertFalse(updated.data["is_active"])


class RetentionTest(SafetyBase):
    """The retention job deletes only what the school agreed to lose."""

    def _old(self, days=40):
        return timezone.now() - timezone.timedelta(days=days)

    def _message(self, days=40, text="old"):
        message = ChatMessage.objects.create(
            user=self.student_user,
            message=text,
            reply="ok",
        )
        # `created_at` is `auto_now_add`, so a value passed to create() is
        # overwritten. Backdate with a queryset update instead.
        ChatMessage.objects.filter(id=message.id).update(created_at=self._old(days))
        return message

    def _flag(self, days=40, status=Flag.Status.RESOLVED, message=None):
        chat_message = message or self._message(days=days, text=f"flag {status}")
        flag = Flag.objects.create(
            student=self.student,
            user=self.student_user,
            chat_message=chat_message,
            severity="medium",
            source="keyword",
            categories=["distress"],
            status=status,
        )
        Flag.objects.filter(id=flag.id).update(created_at=self._old(days))
        return flag

    def test_the_job_refuses_without_a_window(self):
        from django.core.management import CommandError, call_command

        with self.assertRaises(CommandError):
            call_command("purge_chatbot_data")

    def test_a_closed_flag_and_its_message_go(self):
        from django.core.management import call_command

        flag = self._flag()
        call_command("purge_chatbot_data", "--days", "30")
        self.assertFalse(Flag.objects.filter(id=flag.id).exists())
        self.assertFalse(
            ChatMessage.objects.filter(id=flag.chat_message_id).exists()
        )

    def test_an_open_flag_survives_whatever_its_age(self):
        from django.core.management import call_command

        flag = self._flag(status=Flag.Status.OPEN)
        call_command("purge_chatbot_data", "--days", "30")
        self.assertTrue(Flag.objects.filter(id=flag.id).exists())
        self.assertTrue(
            ChatMessage.objects.filter(id=flag.chat_message_id).exists()
        )

    def test_a_recent_message_survives(self):
        from django.core.management import call_command

        message = ChatMessage.objects.create(
            user=self.student_user, message="fresh", reply="ok"
        )
        call_command("purge_chatbot_data", "--days", "30")
        self.assertTrue(ChatMessage.objects.filter(id=message.id).exists())

    def test_the_window_comes_from_the_setting(self):
        from django.core.management import call_command

        from apps.cms.models import SystemSetting

        SystemSetting.objects.filter(key="chatbot.retention_days").update(value="30")
        flag = self._flag()
        call_command("purge_chatbot_data")
        self.assertFalse(Flag.objects.filter(id=flag.id).exists())

    def test_a_dry_run_deletes_nothing(self):
        from django.core.management import call_command

        flag = self._flag()
        call_command("purge_chatbot_data", "--days", "30", "--dry-run")
        self.assertTrue(Flag.objects.filter(id=flag.id).exists())


class PerSeverityTimerTest(SafetyBase):
    """A severity may have its own acknowledgment window."""

    def test_the_school_wide_window_is_the_default(self):
        from apps.cms.models import SystemSetting

        SystemSetting.objects.filter(
            key="chatbot.acknowledgment_timer_minutes"
        ).update(value="20")
        self.assertEqual(routing.acknowledgment_minutes("critical"), 20)
        self.assertEqual(routing.acknowledgment_minutes(), 20)

    def test_a_per_severity_window_overrides_it(self):
        from apps.cms.models import SystemSetting

        SystemSetting.objects.filter(
            key="chatbot.acknowledgment_timer_minutes"
        ).update(value="20")
        SystemSetting.objects.filter(
            key="chatbot.acknowledgment_timer_minutes.critical"
        ).update(value="5")
        self.assertEqual(routing.acknowledgment_minutes("critical"), 5)
        self.assertEqual(routing.acknowledgment_minutes("high"), 20)

    def test_a_blank_override_falls_back(self):
        from apps.cms.models import SystemSetting

        SystemSetting.objects.filter(
            key="chatbot.acknowledgment_timer_minutes.high"
        ).update(value="")
        self.assertEqual(routing.acknowledgment_minutes("high"), 15)

    def test_the_flag_due_time_uses_the_severity_window(self):
        from apps.cms.models import SystemSetting

        SystemSetting.objects.filter(
            key="chatbot.acknowledgment_timer_minutes.critical"
        ).update(value="5")
        chat_message = ChatMessage.objects.create(
            user=self.student_user, message="I want to hurt myself", reply="ok"
        )
        flag = Flag.objects.create(
            student=self.student,
            user=self.student_user,
            chat_message=chat_message,
            severity="critical",
            source="keyword",
            categories=["self_harm"],
            escalation_due_at=timezone.now()
            + timezone.timedelta(minutes=routing.acknowledgment_minutes("critical")),
        )
        window = (flag.escalation_due_at - flag.created_at).total_seconds() / 60
        self.assertLessEqual(window, 5.1)


class KeyRotationTest(TestCase):
    """
    Fallback keys: read, rotated and never leaked.

    A school's Gemini quota is per key, so a second key is a second budget.
    The rules that matter: the keys are read in order, a key that has spent
    its quota is not tried again, and no key ever reaches a log or a status
    response.
    """

    def setUp(self):
        self._state = gemini_client._KEY_STATE
        self._saved = dict(self._state)
        self._state["index"] = 0
        self._state["exhausted"] = set()

    def tearDown(self):
        self._state["index"] = self._saved["index"]
        self._state["exhausted"] = set(self._saved["exhausted"])

    def test_keys_are_read_from_the_primary_and_the_fallback_list(self):
        with override_settings(GEMINI_API_KEY="primary", GEMINI_API_KEYS="a, b  c"):
            self.assertEqual(
                gemini_client._keys(), ["primary", "a", "b", "c"]
            )

    def test_a_repeated_key_is_only_used_once(self):
        with override_settings(GEMINI_API_KEY="one", GEMINI_API_KEYS="one, two"):
            self.assertEqual(gemini_client._keys(), ["one", "two"])

    def test_no_key_configured_means_not_configured(self):
        with override_settings(GEMINI_API_KEY="", GEMINI_API_KEYS=""):
            self.assertFalse(gemini_client.configured())
            self.assertIsNone(gemini_client._current_key())

    def test_an_exhausted_key_is_skipped(self):
        with override_settings(GEMINI_API_KEY="one", GEMINI_API_KEYS="two"):
            self.assertEqual(gemini_client._current_key(), "one")
            gemini_client._advance_key(exhausted=True)
            self.assertEqual(gemini_client._current_key(), "two")

    def test_every_key_exhausted_means_no_key(self):
        with override_settings(GEMINI_API_KEY="one", GEMINI_API_KEYS="two"):
            gemini_client._advance_key(exhausted=True)
            gemini_client._advance_key(exhausted=True)
            self.assertIsNone(gemini_client._current_key())

    def test_a_rate_limited_key_is_moved_past_but_not_given_up_on(self):
        with override_settings(GEMINI_API_KEY="one", GEMINI_API_KEYS="two"):
            gemini_client._advance_key()
            self.assertEqual(gemini_client._current_key(), "two")
            self.assertEqual(gemini_client._KEY_STATE["exhausted"], set())

    def test_the_log_slot_is_a_position_not_a_key(self):
        with override_settings(GEMINI_API_KEY="secret-one", GEMINI_API_KEYS="secret-two"):
            self.assertEqual(gemini_client._key_slot("secret-two"), 2)

    def test_status_never_returns_a_key(self):
        with override_settings(GEMINI_API_KEY="secret-one", GEMINI_API_KEYS="secret-two"):
            status = gemini_client.status()
        rendered = repr(status)
        self.assertNotIn("secret-one", rendered)
        self.assertNotIn("secret-two", rendered)
        self.assertEqual(status["key_count"], 2)

    def test_the_quota_error_is_recognised(self):
        """'Plan and billing' means spent; a per-minute burst does not."""
        spent = Exception(
            "429 RESOURCE_EXHAUSTED. You exceeded your current quota, please "
            "check your plan and billing details."
        )
        burst = Exception("429 RESOURCE_EXHAUSTED. Quota exceeded for quota metric.")
        self.assertTrue(gemini_client._is_quota_exhausted(spent))
        self.assertFalse(gemini_client._is_quota_exhausted(burst))
        self.assertTrue(gemini_client._is_rate_limit(burst))
        self.assertFalse(gemini_client._is_retryable(spent))
        self.assertTrue(gemini_client._is_retryable(burst))

    def test_a_saturated_model_is_recognised(self):
        """503 high demand is about the model, not the key."""
        saturated = Exception(
            "503 UNAVAILABLE. This model is currently experiencing high demand."
        )
        deadline = Exception("504 DEADLINE_EXCEEDED. Deadline expired.")
        self.assertTrue(gemini_client._is_saturation(saturated))
        self.assertTrue(gemini_client._is_saturation(deadline))
        self.assertFalse(gemini_client._is_saturation(Exception("bad request")))


class ModelFallbackTest(TestCase):
    """
    A model can be saturated while the account is healthy.

    That is a reason to try a different model, not a different key, so the two
    lists rotate independently.
    """

    def setUp(self):
        self._model_state = gemini_client._MODEL_STATE
        self._saved = self._model_state["index"]
        self._model_state["index"] = 0

    def tearDown(self):
        self._model_state["index"] = self._saved

    def test_models_are_read_from_the_primary_and_the_fallback_list(self):
        with override_settings(
            GEMINI_MODEL="primary", GEMINI_MODEL_FALLBACKS="a, b"
        ):
            self.assertEqual(gemini_client._models(), ["primary", "a", "b"])

    def test_the_primary_model_is_used_first(self):
        with override_settings(
            GEMINI_MODEL="primary", GEMINI_MODEL_FALLBACKS="fallback"
        ):
            self.assertEqual(gemini_client._current_model(), "primary")

    def test_advancing_moves_to_the_fallback(self):
        with override_settings(
            GEMINI_MODEL="primary", GEMINI_MODEL_FALLBACKS="fallback"
        ):
            gemini_client._advance_model()
            self.assertEqual(gemini_client._current_model(), "fallback")

    def test_status_lists_the_models_and_never_a_key(self):
        with override_settings(
            GEMINI_MODEL="model-one",
            GEMINI_MODEL_FALLBACKS="model-two",
            GEMINI_API_KEY="secret-one",
        ):
            status = gemini_client.status()
        self.assertEqual(status["models"], ["model-one", "model-two"])
        self.assertNotIn("secret-one", repr(status))


class FieldEncryptionTest(SafetyBase):
    """
    Student free text is encrypted in the column, plain in the application.

    Both halves matter. The column must not hold the plaintext — that is the
    whole point — and the application must still see the plaintext, or the
    counselor cannot read the message they were told to read.
    """

    def _raw(self, table, column, pk):
        from django.db import connection

        with connection.cursor() as cursor:
            # SQLite stores a UUID as 32 hex characters without dashes, and it
            # will not bind a UUID object, so the id is passed the way the
            # column holds it.
            cursor.execute(
                f"SELECT {column} FROM {table} WHERE id = %s",
                [str(pk).replace("-", "")],
            )
            row = cursor.fetchone()
        return row[0] if row else None

    def test_the_message_column_holds_ciphertext(self):
        with override_settings(
            FIELD_ENCRYPTION_KEYS=f"k1:{base64.b64encode(secrets.token_bytes(64)).decode()}",
            FIELD_ENCRYPTION_KEY="",
        ):
            self.post_message("I am being bullied every day")
            message = ChatMessage.objects.order_by("-created_at").first()

            # The application sees the plain text...
            self.assertEqual(message.message, "I am being bullied every day")
            # ...and the column does not.
            raw = self._raw("chatbot_chatmessage", "message", message.id)
            self.assertNotIn("bullied", raw)
            self.assertTrue(raw.startswith("enc1:"))

    def test_the_student_sees_the_plain_text_over_the_api(self):
        with override_settings(
            FIELD_ENCRYPTION_KEYS=f"k1:{base64.b64encode(secrets.token_bytes(64)).decode()}",
            FIELD_ENCRYPTION_KEY="",
        ):
            response = self.post_message("What is my grade in Math?")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("chat_message_id", response.data["data"])

            row = ChatMessage.objects.get(
                id=response.data["data"]["chat_message_id"]
            )
            self.assertEqual(row.message, "What is my grade in Math?")

    def test_a_case_note_is_encrypted_in_the_column(self):
        with override_settings(
            FIELD_ENCRYPTION_KEYS=f"k1:{base64.b64encode(secrets.token_bytes(64)).decode()}",
            FIELD_ENCRYPTION_KEY="",
        ):
            chat_message = ChatMessage.objects.create(
                user=self.student_user, message="private", reply="ok"
            )
            flag = Flag.objects.create(
                student=self.student,
                user=self.student_user,
                chat_message=chat_message,
                severity="medium",
                source="keyword",
                categories=["distress"],
            )
            self.client.force_authenticate(user=self.guidance_user)
            self.client.post(
                f"/api/v1/chatbot/flags/{flag.id}/notes/",
                {"note": "Called the adviser about the situation."},
                format="json",
            )

            note = FlagAction.objects.filter(
                flag=flag, action=FlagAction.Action.NOTE
            ).first()
            self.assertIsNotNone(note)
            self.assertEqual(note.note, "Called the adviser about the situation.")
            raw = self._raw("chatbot_flagaction", "note", note.id)
            self.assertNotIn("adviser", raw)

    def test_without_a_key_the_text_is_stored_in_the_clear(self):
        """Development works without a key — and the console says so."""
        with override_settings(FIELD_ENCRYPTION_KEYS="", FIELD_ENCRYPTION_KEY=""):
            self.post_message("What is my grade in Math?")
            message = ChatMessage.objects.order_by("-created_at").first()
            raw = self._raw("chatbot_chatmessage", "message", message.id)
            self.assertEqual(raw, "What is my grade in Math?")

    def test_the_admin_console_reports_the_encryption_state(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/api/v1/chatbot/admin/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("encryption", response.data)
        self.assertIn("enabled", response.data["encryption"])


class NoticeGateTest(SafetyBase):
    """A student chats only after accepting the current notice."""

    def test_student_without_acceptance_is_refused(self):
        AgreementAcceptance.objects.filter(user=self.student_user).delete()
        response = self.post_message("Hello!")
        self.assertEqual(response.status_code, status.HTTP_428_PRECONDITION_REQUIRED)
        self.assertTrue(response.data["notice_required"])
        self.assertEqual(response.data["notice"]["version"], notice_version())

    def test_acceptance_unlocks_the_chatbot(self):
        AgreementAcceptance.objects.filter(user=self.student_user).delete()
        self.post_message("Hello!")
        self.client.force_authenticate(user=self.student_user)
        accept = self.client.post(
            "/api/v1/chatbot/notice/", {"version": notice_version()}, format="json"
        )
        self.assertEqual(accept.status_code, status.HTTP_201_CREATED)
        response = self.post_message("Hello!")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_stale_version_is_refused(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(
            "/api/v1/chatbot/notice/", {"version": "1999-01-01"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_public_notice_is_readable_without_a_token(self):
        response = self.client.get("/api/v1/chatbot/notice/public/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["version"], notice_version())
        self.assertTrue(response.data["text"])


class ChatPersistenceTest(SafetyBase):
    """Turns are stored, and a student sees only their own."""

    def test_message_is_persisted(self):
        self.post_message("What is my grade in Math?")
        self.assertTrue(
            ChatMessage.objects.filter(
                user=self.student_user, message="What is my grade in Math?"
            ).exists()
        )

    def test_history_returns_only_the_callers_turns(self):
        self.post_message("What is my grade in Math?")
        other = User.objects.create_user(
            email="safe_other@test.com",
            password="pass12345",
            first_name="Other",
            last_name="Student",
            role="student",
        )
        self.post_message("What is my attendance?", user=other)

        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/v1/chatbot/history/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_sensitive_message_creates_a_flag_and_notifies_guidance(self):
        response = self.post_message(SELF_HARM)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        flag = Flag.objects.get(chat_message__message=SELF_HARM)
        self.assertEqual(flag.severity, "critical")
        self.assertTrue(
            FlagRecipient.objects.filter(flag=flag, user=self.guidance_user).exists()
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.guidance_user).exists()
        )

    def test_one_crisis_produces_one_notification_per_counselor(self):
        """
        The old FR-031 notice and the flag workflow both fire on a crisis.

        Leaving both on meant a counselor got two notifications about the same
        student, which is how a channel gets ignored. The flag workflow
        reaches every guidance counselor, the administrators and the
        student's faculty, so it is the escalation path and the old notice is
        suppressed for it.
        """
        self.post_message(SELF_HARM)
        for counselor in (self.guidance_user, self.admin_user, self.faculty_user):
            with self.subTest(user=counselor.email):
                self.assertEqual(
                    Notification.objects.filter(recipient=counselor).count(),
                    1,
                    f"{counselor.email} was told twice about one message.",
                )

    @override_settings(GEMINI_API_KEY="")
    def test_model_unavailable_marks_the_flag_for_manual_review(self):
        self.post_message(SELF_HARM)
        flag = Flag.objects.get(chat_message__message=SELF_HARM)
        self.assertTrue(flag.manual_review)

    def test_the_flag_summary_names_what_matched(self):
        """The inbox line says what fired, not the message itself."""
        self.post_message(SELF_HARM)
        flag = Flag.objects.get(chat_message__message=SELF_HARM)
        self.assertIn("Keyword match", flag.summary)
        # The matched term is named; the student's sentence is not repeated.
        self.assertNotIn(SELF_HARM.lower(), flag.summary.lower())

    def test_a_disclosure_is_not_answered_with_i_did_not_understand(self):
        """
        A student who reports bullying must not be told the bot failed.

        The intent layer does not recognise "I am being bullied every day",
        so the deterministic answer is the safe fallback. On a sensitive
        message that fallback is wrong: the student has just said something
        that needs a counselor, and the reply has to say that.
        """
        response = self.post_message("I am being bullied every day")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("didn't fully understand", response.data["reply"].lower())
        self.assertIn("guidance", response.data["reply"].lower())
