"""
Tests for the encrypted columns outside the chatbot app.

The chatbot's own encryption is covered in ``apps/chatbot/tests_safety.py``.
What matters here is that the counseling narrative — a counselor's session
notes, a teacher's observation, an intervention step, a progress note — is
ciphertext in the column and plain text in the application, and that the
model rationale JSON round-trips as a dict.
"""

import base64
import secrets
from datetime import date, time

from django.test import TestCase, override_settings

from apps.accounts.models import FacultyProfile, GuidanceProfile, StudentProfile, User
from apps.chatbot.models import ChatMessage
from apps.guidance.models import (
    BehavioralNote,
    ConsultationRecord,
    Intervention,
    InterventionStep,
    ProgressNote,
)


def _key() -> str:
    return base64.b64encode(secrets.token_bytes(64)).decode("ascii")


class EncryptionFixture(TestCase):
    """A student, a counselor and a teacher to hang the notes on."""

    def setUp(self):
        super().setUp()
        student_user = User.objects.create_user(
            email="enc_student@test.com", password="pass12345", role="student"
        )
        self.student = StudentProfile.objects.create(
            user=student_user, student_id="ENC001", enrollment_date=date(2025, 6, 1)
        )

        guidance_user = User.objects.create_user(
            email="enc_counselor@test.com", password="pass12345", role="guidance"
        )
        self.counselor = GuidanceProfile.objects.create(
            user=guidance_user, employee_id="ENC-G001"
        )

        faculty_user = User.objects.create_user(
            email="enc_teacher@test.com", password="pass12345", role="faculty"
        )
        self.teacher = FacultyProfile.objects.create(
            user=faculty_user, employee_id="ENC-F001"
        )

    def _raw(self, table, column, pk):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {column} FROM {table} WHERE id = %s",
                [str(pk).replace("-", "")],
            )
            row = cursor.fetchone()
        return row[0] if row else None

    def _consultation(self, notes="The student disclosed they are being bullied."):
        return ConsultationRecord.objects.create(
            student=self.student,
            counselor=self.counselor,
            session_date=date(2025, 9, 1),
            session_time=time(10, 0),
            session_type="individual_counseling",
            concern_categories=["emotional"],
            session_notes=notes,
            priority_level="medium",
        )

    def _intervention(self):
        return Intervention.objects.create(
            student=self.student,
            assigned_counselor=self.counselor,
            plan_start_date=date(2025, 9, 1),
            status="active",
        )


class EncryptedNarrativeTest(EncryptionFixture):
    """The counseling text is ciphertext in the column."""

    def test_a_consultation_note_is_encrypted_in_the_column(self):
        with override_settings(
            FIELD_ENCRYPTION_KEYS=f"k1:{_key()}", FIELD_ENCRYPTION_KEY=""
        ):
            record = self._consultation()
            # The application sees the plain text.
            fresh = ConsultationRecord.objects.get(id=record.id)
            self.assertIn("being bullied", fresh.session_notes)
            # The column does not.
            raw = self._raw("guidance_consultationrecord", "session_notes", record.id)
            self.assertNotIn("bullied", raw)
            self.assertTrue(raw.startswith("enc1:"))

    def test_a_behavioral_note_is_encrypted_in_the_column(self):
        with override_settings(
            FIELD_ENCRYPTION_KEYS=f"k1:{_key()}", FIELD_ENCRYPTION_KEY=""
        ):
            note = BehavioralNote.objects.create(
                student=self.student,
                recorded_by=self.teacher,
                note_type="warning",
                note_text="Sat alone at lunch and appeared withdrawn.",
                date_recorded=date(2025, 9, 1),
            )
            fresh = BehavioralNote.objects.get(id=note.id)
            self.assertIn("withdrawn", fresh.note_text)
            raw = self._raw("guidance_behavioralnote", "note_text", note.id)
            self.assertNotIn("withdrawn", raw)

    def test_an_intervention_step_is_encrypted_in_the_column(self):
        with override_settings(
            FIELD_ENCRYPTION_KEYS=f"k1:{_key()}", FIELD_ENCRYPTION_KEY=""
        ):
            step = InterventionStep.objects.create(
                intervention=self._intervention(),
                title="Call home",
                description="Speak with the parent about the weekly plan.",
                status="scheduled",
                order=1,
            )
            fresh = InterventionStep.objects.get(id=step.id)
            self.assertIn("Speak with the parent", fresh.description)
            raw = self._raw("guidance_interventionstep", "description", step.id)
            self.assertNotIn("parent", raw)

    def test_a_progress_note_is_encrypted_in_the_column(self):
        with override_settings(
            FIELD_ENCRYPTION_KEYS=f"k1:{_key()}", FIELD_ENCRYPTION_KEY=""
        ):
            note = ProgressNote.objects.create(
                intervention=self._intervention(),
                note_text="Student engaged; mood improving.",
                recorded_by=self.counselor,
            )
            fresh = ProgressNote.objects.get(id=note.id)
            self.assertIn("mood improving", fresh.note_text)
            raw = self._raw("guidance_progressnote", "note_text", note.id)
            self.assertNotIn("mood", raw)


class EncryptedDetectionDetailTest(EncryptionFixture):
    """The model's rationale is ciphertext; the application still gets a dict."""

    def test_the_detail_round_trips_as_a_dict(self):
        payload = {
            "sensitive": True,
            "severity": "medium",
            "categories": ["bullying"],
            "layer2": {"detail": "The student reports being bullied every day."},
        }
        with override_settings(
            FIELD_ENCRYPTION_KEYS=f"k1:{_key()}", FIELD_ENCRYPTION_KEY=""
        ):
            row = ChatMessage.objects.create(
                user=self.student.user,
                message="I am being bullied every day",
                reply="ok",
                detection_detail=payload,
            )
            fresh = ChatMessage.objects.get(id=row.id)
            self.assertIsInstance(fresh.detection_detail, dict)
            self.assertEqual(fresh.detection_detail, payload)

    def test_the_column_does_not_hold_the_rationale(self):
        from django.db import connection

        payload = {"layer2": {"detail": "The student reports being bullied."}}
        with override_settings(
            FIELD_ENCRYPTION_KEYS=f"k1:{_key()}", FIELD_ENCRYPTION_KEY=""
        ):
            row = ChatMessage.objects.create(
                user=self.student.user,
                message="hello",
                reply="ok",
                detection_detail=payload,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT detection_detail FROM chatbot_chatmessage WHERE id = %s",
                    [str(row.id).replace("-", "")],
                )
                raw = cursor.fetchone()[0]
        self.assertNotIn("bullied", str(raw))
        self.assertIn("enc1:", str(raw))

    def test_without_a_key_the_detail_is_still_a_dict(self):
        """
        No key must not change what the application sees.

        The column keeps holding a JSON object rather than a JSON string, so a
        deployment without a key behaves the same from the inside.
        """
        payload = {"sensitive": False, "severity": "low"}
        with override_settings(
            FIELD_ENCRYPTION_KEYS="", FIELD_ENCRYPTION_KEY=""
        ):
            row = ChatMessage.objects.create(
                user=self.student.user,
                message="hello",
                reply="ok",
                detection_detail=payload,
            )
            fresh = ChatMessage.objects.get(id=row.id)
        self.assertEqual(fresh.detection_detail, payload)


class PostureCommandTest(TestCase):
    """The command reports the posture without printing a key."""

    def test_the_command_runs_and_names_the_encrypted_columns(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("security_posture", stdout=out)
        text = out.getvalue()

        self.assertIn("Field encryption", text)
        self.assertIn("chatbot.ChatMessage.message", text)
        self.assertIn("guidance.ConsultationRecord.session_notes", text)
        self.assertIn("Acknowledgment window", text)
        self.assertIn("Retention window", text)

    def test_the_command_never_prints_a_key(self):
        from io import StringIO

        from django.core.management import call_command

        key = _key()
        with override_settings(
            FIELD_ENCRYPTION_KEYS=f"k1:{key}", FIELD_ENCRYPTION_KEY=""
        ):
            out = StringIO()
            call_command("security_posture", stdout=out)
        self.assertNotIn(key, out.getvalue())
        # The key id is not a secret and is useful to an operator.
        self.assertIn("k1", out.getvalue())
