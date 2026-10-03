"""
Phase 5 test suite for AEGIS Guidance.

Covers: model validation, API endpoints, scoped querysets,
role-based permissions, notification dispatch, status transitions,
risk alert workflow, intervention workflow, and guidance report.
"""

from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
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
    GradeLevel,
    Section,
    Subject,
    SubjectAssignment,
)
from apps.guidance.models import (
    BehavioralNote,
    ConsultationRecord,
    Intervention,
    InterventionStep,
    ProgressNote,
    RiskAlert,
)
from apps.notifications.models import Notification

User = get_user_model()


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class GuidanceTestBase(TestCase):
    """Shared setUp for guidance tests."""

    def setUp(self):
        # --- Users ---
        self.admin_user = User.objects.create_user(
            email="admin_guid@test.com", password="pass12345",
            first_name="Admin", last_name="User", role="admin",
        )
        self.faculty_user = User.objects.create_user(
            email="faculty_guid@test.com", password="pass12345",
            first_name="Fac", last_name="ulty", role="faculty",
        )
        self.faculty2_user = User.objects.create_user(
            email="faculty2_guid@test.com", password="pass12345",
            first_name="Fac2", last_name="ulty2", role="faculty",
        )
        self.student_user = User.objects.create_user(
            email="student_guid@test.com", password="pass12345",
            first_name="Stu", last_name="Dent", role="student",
        )
        self.student2_user = User.objects.create_user(
            email="student2_guid@test.com", password="pass12345",
            first_name="Stu2", last_name="Dent2", role="student",
        )
        self.parent_user = User.objects.create_user(
            email="parent_guid@test.com", password="pass12345",
            first_name="Par", last_name="Ent", role="parent",
        )
        self.guidance_user = User.objects.create_user(
            email="guidance_guid@test.com", password="pass12345",
            first_name="Guid", last_name="Ance", role="guidance",
        )
        self.guidance2_user = User.objects.create_user(
            email="guidance2_guid@test.com", password="pass12345",
            first_name="Guid2", last_name="Ance2", role="guidance",
        )

        # --- Profiles ---
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="EMP-GR-001", department="Math",
            is_adviser=True,
        )
        self.faculty2_profile = FacultyProfile.objects.create(
            user=self.faculty2_user, employee_id="EMP-GR-002", department="Science",
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user, student_id="STU-GR-001",
            enrollment_date="2025-06-01",
        )
        self.student2_profile = StudentProfile.objects.create(
            user=self.student2_user, student_id="STU-GR-002",
            enrollment_date="2025-06-01",
        )
        self.parent_profile = ParentProfile.objects.create(
            user=self.parent_user, relationship_to_student="mother",
        )
        ParentStudentLink.objects.create(
            parent=self.parent_profile, student=self.student_profile,
            is_primary=True,
        )
        self.guidance_profile = GuidanceProfile.objects.create(
            user=self.guidance_user, employee_id="GDE-GR-001",
            specialization="Student Counseling",
        )
        self.guidance2_profile = GuidanceProfile.objects.create(
            user=self.guidance2_user, employee_id="GDE-GR-002",
            specialization="Behavioral",
        )

        # --- Academic structure ---
        self.ay = AcademicYear.objects.create(
            name="2025-2026", start_date="2025-06-01",
            end_date="2026-03-31", is_current=True,
        )
        self.g7 = GradeLevel.objects.create(name="Grade 7", level_number=7)

        self.section_a = Section.objects.create(
            name="Einstein", grade_level=self.g7, academic_year=self.ay,
            adviser=self.faculty_profile,
        )
        self.section_b = Section.objects.create(
            name="Newton", grade_level=self.g7, academic_year=self.ay,
        )

        self.math = Subject.objects.create(
            name="Mathematics", code="MATH-GR-7", grade_level=self.g7,
        )
        self.sa_math = SubjectAssignment.objects.create(
            subject=self.math, faculty=self.faculty_profile,
            section=self.section_a, academic_year=self.ay,
        )

        self.enrollment1 = Enrollment.objects.create(
            student=self.student_profile, section=self.section_a,
            academic_year=self.ay, date_enrolled="2025-06-01",
        )
        self.enrollment2 = Enrollment.objects.create(
            student=self.student2_profile, section=self.section_b,
            academic_year=self.ay, date_enrolled="2025-06-01",
        )

        self.student_profile.section = self.section_a
        self.student_profile.grade_level = self.g7
        self.student_profile.save()
        self.student2_profile.section = self.section_b
        self.student2_profile.grade_level = self.g7
        self.student2_profile.save()

        # --- Dates ---
        self.today = timezone.localdate()
        self.yesterday = self.today - timedelta(days=1)

        # --- Seed data ---
        self.behavioral_note1 = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="warning",
            note_text="Disruptive behavior in class.",
            date_recorded=self.yesterday,
        )
        self.behavioral_note2 = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="Excellent participation.",
            date_recorded=self.yesterday,
        )
        self.behavioral_note3 = BehavioralNote.objects.create(
            student=self.student2_profile,
            recorded_by=self.faculty2_profile,
            note_type="incident",
            note_text="Fighting with another student.",
            date_recorded=self.yesterday,
        )

        self.risk_alert1 = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="moderate",
            risk_factors=["Multiple behavioral warnings", "Declining grades"],
            source="manual",
            status="active",
            generated_at=timezone.now(),
        )

        self.intervention1 = Intervention.objects.create(
            student=self.student_profile,
            risk_alert=self.risk_alert1,
            assigned_counselor=self.guidance_profile,
            plan_start_date=self.today,
            status="active",
        )

        self.client = APIClient()

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken

        return str(RefreshToken.for_user(user).access_token)


# ===========================================================================
# Model tests
# ===========================================================================


class BehavioralNoteModelTest(GuidanceTestBase):
    def test_str(self):
        s = str(self.behavioral_note1)
        self.assertIn("Dent", s)
        self.assertIn("Warning", s)

    def test_note_type_choices(self):
        expected = {"positive", "warning", "incident"}
        actual = {choice[0] for choice in BehavioralNote.NoteType.choices}
        self.assertEqual(actual, expected)

    def test_future_date_rejected(self):
        note = BehavioralNote(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="Great work.",
            date_recorded=self.today + timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            note.full_clean()

    def test_empty_note_text_rejected(self):
        note = BehavioralNote(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="   ",
            date_recorded=self.today,
        )
        with self.assertRaises(ValidationError):
            note.full_clean()


class ConsultationRecordModelTest(GuidanceTestBase):
    def test_str(self):
        rec = ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=self.today,
            session_time=time(10, 0),
            session_type="individual_counseling",
            concern_categories=["academic"],
            session_notes="Discussed academic performance.",
            priority_level="medium",
        )
        s = str(rec)
        self.assertIn("Dent", s)
        self.assertIn("Ance", s)

    def test_invalid_concern_category_rejected(self):
        rec = ConsultationRecord(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=self.today,
            session_time=time(10, 0),
            session_type="individual_counseling",
            concern_categories=["invalid_category"],
            session_notes="Test notes.",
            priority_level="medium",
        )
        with self.assertRaises(ValidationError):
            rec.full_clean()


class RiskAlertModelTest(GuidanceTestBase):
    def test_str(self):
        s = str(self.risk_alert1)
        self.assertIn("Dent", s)
        self.assertIn("Moderate", s)

    def test_risk_level_choices(self):
        expected = {"low", "moderate", "high"}
        actual = {choice[0] for choice in RiskAlert.RiskLevel.choices}
        self.assertEqual(actual, expected)

    def test_source_manual_default(self):
        self.assertEqual(self.risk_alert1.source, "manual")


class InterventionModelTest(GuidanceTestBase):
    def test_str(self):
        s = str(self.intervention1)
        self.assertIn("Dent", s)
        self.assertIn("Active", s)

    def test_status_choices(self):
        expected = {"active", "completed", "cancelled"}
        actual = {choice[0] for choice in Intervention.Status.choices}
        self.assertEqual(actual, expected)


class InterventionStepModelTest(GuidanceTestBase):
    def test_step_creation(self):
        step = InterventionStep.objects.create(
            intervention=self.intervention1,
            title="Initial Assessment",
            description="Conduct initial assessment.",
            status="pending",
            order=1,
        )
        self.assertEqual(step.intervention, self.intervention1)
        self.assertEqual(step.order, 1)

    def test_step_str(self):
        step = InterventionStep.objects.create(
            intervention=self.intervention1,
            title="Parent Meeting",
            description="Meet with parents.",
            status="scheduled",
            order=2,
        )
        s = str(step)
        self.assertIn("Parent Meeting", s)
        self.assertIn("Scheduled", s)


class ProgressNoteModelTest(GuidanceTestBase):
    def test_note_creation(self):
        note = ProgressNote.objects.create(
            intervention=self.intervention1,
            note_text="Student showed improvement.",
            recorded_by=self.guidance_profile,
        )
        self.assertEqual(note.intervention, self.intervention1)
        self.assertEqual(note.recorded_by, self.guidance_profile)

    def test_empty_note_text_rejected(self):
        note = ProgressNote(
            intervention=self.intervention1,
            note_text="  ",
            recorded_by=self.guidance_profile,
        )
        with self.assertRaises(ValidationError):
            note.full_clean()


# ===========================================================================
# API tests — Authentication required
# ===========================================================================


class GuidanceUnauthenticatedTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_behavioral_notes_unauthenticated(self):
        response = self.client.get("/api/v1/guidance/behavioral-notes/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_consultations_unauthenticated(self):
        response = self.client.get("/api/v1/guidance/consultations/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_risk_alerts_unauthenticated(self):
        response = self.client.get("/api/v1/guidance/risk-alerts/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_interventions_unauthenticated(self):
        response = self.client.get("/api/v1/guidance/interventions/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ===========================================================================
# BehavioralNote API tests
# ===========================================================================


class BehavioralNoteCreateTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )

    def test_faculty_creates_positive_note(self):
        response = self.client.post(
            "/api/v1/guidance/behavioral-notes/",
            {
                "student": str(self.student_profile.id),
                "note_type": "positive",
                "note_text": "Outstanding project work.",
                "date_recorded": str(self.today),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(BehavioralNote.objects.count(), 4)

    def test_faculty_creates_warning_note_dispatches_notification(self):
        response = self.client.post(
            "/api/v1/guidance/behavioral-notes/",
            {
                "student": str(self.student_profile.id),
                "note_type": "warning",
                "note_text": "Repeated tardiness.",
                "date_recorded": str(self.today),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Check notifications dispatched to guidance users
        notifs = Notification.objects.filter(
            notification_type="BEHAVIORAL_WARNING"
        )
        self.assertEqual(notifs.count(), 2)  # both guidance users
        self.assertIn(self.guidance_user.id, notifs.values_list("recipient", flat=True))
        self.assertIn(self.guidance2_user.id, notifs.values_list("recipient", flat=True))

    def test_faculty_creates_incident_note_dispatches_notification(self):
        response = self.client.post(
            "/api/v1/guidance/behavioral-notes/",
            {
                "student": str(self.student_profile.id),
                "note_type": "incident",
                "note_text": "Physical altercation with another student.",
                "date_recorded": str(self.today),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notifs = Notification.objects.filter(
            notification_type="BEHAVIORAL_INCIDENT"
        )
        self.assertEqual(notifs.count(), 2)  # both guidance users

    def test_positive_note_no_notification(self):
        response = self.client.post(
            "/api/v1/guidance/behavioral-notes/",
            {
                "student": str(self.student_profile.id),
                "note_type": "positive",
                "note_text": "Helped classmates.",
                "date_recorded": str(self.today),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # No notifications should be created for positive notes
        notifs = Notification.objects.filter(notification_type="BEHAVIORAL_WARNING")
        self.assertEqual(notifs.count(), 0)

    def test_faculty_creates_note_sets_recorded_by(self):
        response = self.client.post(
            "/api/v1/guidance/behavioral-notes/",
            {
                "student": str(self.student_profile.id),
                "note_type": "positive",
                "note_text": "Great teamwork.",
                "date_recorded": str(self.today),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        note = BehavioralNote.objects.get(id=response.data["id"])
        self.assertEqual(note.recorded_by, self.faculty_profile)

    def test_faculty_cannot_create_for_non_enrolled_student(self):
        # student2 is in section_b, faculty is adviser of section_a
        # but faculty doesn't teach section_b, and student2 isn't enrolled there
        # Actually student2 IS in section_b. Faculty needs to be adviser or
        # subject-teacher for section_a only.
        # Create a student with no enrollment
        unenrolled_user = User.objects.create_user(
            email="unenrolled_guid@test.com", password="pass12345",
            first_name="Un", last_name="Enrolled", role="student",
        )
        unenrolled_profile = StudentProfile.objects.create(
            user=unenrolled_user, student_id="STU-GR-UN",
            enrollment_date="2025-06-01",
        )
        response = self.client.post(
            "/api/v1/guidance/behavioral-notes/",
            {
                "student": str(unenrolled_profile.id),
                "note_type": "warning",
                "note_text": "Test.",
                "date_recorded": str(self.today),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_faculty_cannot_create_for_out_of_scope_student(self):
        # student2 is in section_b which faculty has no access to
        response = self.client.post(
            "/api/v1/guidance/behavioral-notes/",
            {
                "student": str(self.student2_profile.id),
                "note_type": "warning",
                "note_text": "Test.",
                "date_recorded": str(self.today),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_future_date_rejected(self):
        response = self.client.post(
            "/api/v1/guidance/behavioral-notes/",
            {
                "student": str(self.student_profile.id),
                "note_type": "warning",
                "note_text": "Test.",
                "date_recorded": str(self.today + timedelta(days=5)),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BehavioralNoteImmutableTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )

    def test_cannot_update_behavioral_note(self):
        response = self.client.patch(
            f"/api/v1/guidance/behavioral-notes/{self.behavioral_note1.id}/",
            {"note_text": "Modified text."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_cannot_delete_behavioral_note(self):
        response = self.client.delete(
            f"/api/v1/guidance/behavioral-notes/{self.behavioral_note1.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class BehavioralNoteReadScopedTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()

    def test_guidance_reads_all_notes(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.get("/api/v1/guidance/behavioral-notes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)

    def test_faculty_reads_own_section_notes(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )
        response = self.client.get("/api/v1/guidance/behavioral-notes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in response.data["results"]]
        self.assertIn(str(self.behavioral_note1.id), ids)
        self.assertIn(str(self.behavioral_note2.id), ids)
        self.assertNotIn(str(self.behavioral_note3.id), ids)

    def test_student_reads_own_notes(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.student_user)}"
        )
        response = self.client.get("/api/v1/guidance/behavioral-notes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)

    def test_student_cannot_see_other_student_notes(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.student_user)}"
        )
        response = self.client.get(
            f"/api/v1/guidance/behavioral-notes/{self.behavioral_note3.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_parent_reads_linked_child_notes(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.parent_user)}"
        )
        response = self.client.get("/api/v1/guidance/behavioral-notes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)

    def test_parent_does_not_see_unlinked_student_notes(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.parent_user)}"
        )
        response = self.client.get(
            f"/api/v1/guidance/behavioral-notes/{self.behavioral_note3.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_faculty_cannot_create_notes(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.post(
            "/api/v1/guidance/behavioral-notes/",
            {
                "student": str(self.student_profile.id),
                "note_type": "warning",
                "note_text": "Test.",
                "date_recorded": str(self.today),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ===========================================================================
# ConsultationRecord API tests
# ===========================================================================


class ConsultationCreateTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )

    def test_guidance_creates_consultation(self):
        response = self.client.post(
            "/api/v1/guidance/consultations/",
            {
                "student": str(self.student_profile.id),
                "session_date": str(self.today),
                "session_time": "10:00:00",
                "session_type": "individual_counseling",
                "concern_categories": ["academic", "behavioral"],
                "session_notes": "Discussed academic concerns and behavior.",
                "priority_level": "high",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        rec = ConsultationRecord.objects.get(id=response.data["id"])
        self.assertEqual(rec.counselor, self.guidance_profile)

    def test_guidance_creates_with_next_session_dispatches_notification(self):
        response = self.client.post(
            "/api/v1/guidance/consultations/",
            {
                "student": str(self.student_profile.id),
                "session_date": str(self.today),
                "session_time": "10:00:00",
                "session_type": "follow_up",
                "concern_categories": ["emotional"],
                "session_notes": "Follow-up session scheduled.",
                "priority_level": "medium",
                "next_session_date": str(self.today + timedelta(days=7)),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notifs = Notification.objects.filter(
            notification_type="CONSULTATION_SCHEDULED"
        )
        # Student + parent = 2 notifications
        self.assertEqual(notifs.count(), 2)

    def test_guidance_cannot_create_for_other_counselor(self):
        response = self.client.post(
            "/api/v1/guidance/consultations/",
            {
                "student": str(self.student_profile.id),
                "counselor": str(self.guidance2_profile.id),
                "session_date": str(self.today),
                "session_time": "10:00:00",
                "session_type": "individual_counseling",
                "concern_categories": ["academic"],
                "session_notes": "Test.",
                "priority_level": "low",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        rec = ConsultationRecord.objects.get(id=response.data["id"])
        self.assertEqual(rec.counselor, self.guidance_profile)

    def test_non_guidance_cannot_create_consultation(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )
        response = self.client.post(
            "/api/v1/guidance/consultations/",
            {
                "student": str(self.student_profile.id),
                "session_date": str(self.today),
                "session_time": "10:00:00",
                "session_type": "individual_counseling",
                "concern_categories": ["academic"],
                "session_notes": "Test.",
                "priority_level": "low",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ConsultationReadScopedTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()
        self.consultation1 = ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=self.today,
            session_time=time(10, 0),
            session_type="individual_counseling",
            concern_categories=["academic"],
            session_notes="Initial consultation.",
            priority_level="medium",
        )

    def test_guidance_reads_own_consultations(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.get("/api/v1/guidance/consultations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_student_reads_own_consultations(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.student_user)}"
        )
        response = self.client.get("/api/v1/guidance/consultations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_parent_reads_linked_child_consultations(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.parent_user)}"
        )
        response = self.client.get("/api/v1/guidance/consultations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_faculty_no_access_to_consultations(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )
        response = self.client.get("/api/v1/guidance/consultations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_guidance_updates_own_consultation(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.patch(
            f"/api/v1/guidance/consultations/{self.consultation1.id}/",
            {"status": "completed", "recommendations": "Continue monitoring."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.consultation1.refresh_from_db()
        self.assertEqual(self.consultation1.status, "completed")


# ===========================================================================
# RiskAlert API tests
# ===========================================================================


class RiskAlertCreateTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )

    def test_guidance_creates_manual_risk_alert(self):
        response = self.client.post(
            "/api/v1/guidance/risk-alerts/",
            {
                "student": str(self.student_profile.id),
                "risk_level": "high",
                "risk_factors": ["Frequent absences", "Declining grades"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        alert = RiskAlert.objects.get(id=response.data["id"])
        self.assertEqual(alert.source, "manual")
        self.assertEqual(alert.status, "active")

    def test_source_forced_to_manual(self):
        response = self.client.post(
            "/api/v1/guidance/risk-alerts/",
            {
                "student": str(self.student_profile.id),
                "risk_level": "low",
                "risk_factors": [],
                "source": "decision_tree",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        alert = RiskAlert.objects.get(id=response.data["id"])
        self.assertEqual(alert.source, "manual")

    def test_non_guidance_cannot_create_alert(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )
        response = self.client.post(
            "/api/v1/guidance/risk-alerts/",
            {
                "student": str(self.student_profile.id),
                "risk_level": "high",
                "risk_factors": ["Test"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RiskAlertStatusTransitionTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )

    def test_acknowledge_active_alert(self):
        response = self.client.post(
            f"/api/v1/guidance/risk-alerts/{self.risk_alert1.id}/acknowledge/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.risk_alert1.refresh_from_db()
        self.assertEqual(self.risk_alert1.status, "under_monitoring")

    def test_cannot_acknowledge_non_active_alert(self):
        self.risk_alert1.status = "resolved"
        self.risk_alert1.save()
        response = self.client.post(
            f"/api/v1/guidance/risk-alerts/{self.risk_alert1.id}/acknowledge/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_escalate_active_alert(self):
        response = self.client.post(
            f"/api/v1/guidance/risk-alerts/{self.risk_alert1.id}/escalate/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.risk_alert1.refresh_from_db()
        self.assertEqual(self.risk_alert1.status, "escalated")

    def test_escalate_under_monitoring_alert(self):
        self.risk_alert1.status = "under_monitoring"
        self.risk_alert1.save()
        response = self.client.post(
            f"/api/v1/guidance/risk-alerts/{self.risk_alert1.id}/escalate/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.risk_alert1.refresh_from_db()
        self.assertEqual(self.risk_alert1.status, "escalated")

    def test_cannot_escalate_resolved_alert(self):
        self.risk_alert1.status = "resolved"
        self.risk_alert1.save()
        response = self.client.post(
            f"/api/v1/guidance/risk-alerts/{self.risk_alert1.id}/escalate/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resolve_active_alert(self):
        response = self.client.post(
            f"/api/v1/guidance/risk-alerts/{self.risk_alert1.id}/resolve/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.risk_alert1.refresh_from_db()
        self.assertEqual(self.risk_alert1.status, "resolved")

    def test_resolve_under_monitoring_alert(self):
        self.risk_alert1.status = "under_monitoring"
        self.risk_alert1.save()
        response = self.client.post(
            f"/api/v1/guidance/risk-alerts/{self.risk_alert1.id}/resolve/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.risk_alert1.refresh_from_db()
        self.assertEqual(self.risk_alert1.status, "resolved")

    def test_cannot_resolve_escalated_alert(self):
        self.risk_alert1.status = "escalated"
        self.risk_alert1.save()
        response = self.client.post(
            f"/api/v1/guidance/risk-alerts/{self.risk_alert1.id}/resolve/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class RiskAlertReadScopedTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()

    def test_faculty_reads_alerts_for_advisory_students(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )
        response = self.client.get("/api/v1/guidance/risk-alerts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_student_reads_own_alerts(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.student_user)}"
        )
        response = self.client.get("/api/v1/guidance/risk-alerts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_student_cannot_see_other_student_alerts(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.student2_user)}"
        )
        response = self.client.get(
            f"/api/v1/guidance/risk-alerts/{self.risk_alert1.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_parent_reads_linked_child_alerts(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.parent_user)}"
        )
        response = self.client.get("/api/v1/guidance/risk-alerts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)


# ===========================================================================
# Intervention API tests
# ===========================================================================


class InterventionCreateTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )

    def test_guidance_creates_intervention(self):
        response = self.client.post(
            "/api/v1/guidance/interventions/",
            {
                "student": str(self.student_profile.id),
                "plan_start_date": str(self.today),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        intervention = Intervention.objects.get(id=response.data["id"])
        self.assertEqual(intervention.assigned_counselor, self.guidance_profile)
        self.assertEqual(intervention.status, "active")

    def test_guidance_creates_with_optional_risk_alert(self):
        response = self.client.post(
            "/api/v1/guidance/interventions/",
            {
                "student": str(self.student_profile.id),
                "risk_alert": str(self.risk_alert1.id),
                "plan_start_date": str(self.today),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_non_guidance_cannot_create_intervention(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )
        response = self.client.post(
            "/api/v1/guidance/interventions/",
            {
                "student": str(self.student_profile.id),
                "plan_start_date": str(self.today),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class InterventionCreateValidationTest(GuidanceTestBase):
    """Regression cover for intervention creation returning HTTP 500.

    ``assigned_counselor`` is non-nullable and is filled from the caller's
    GuidanceProfile. A guidance account without one used to reach
    ``Intervention.save()`` with ``assigned_counselor=None``; ``full_clean()``
    then raised a Django ValidationError, which DRF does not handle, so the
    request surfaced as a 500.
    """

    def setUp(self):
        super().setUp()

        # A guidance-role account deliberately created without a GuidanceProfile
        # row - the state provision_qa_accounts produces before the QA dataset
        # attaches one.
        self.profileless_user = User.objects.create_user(
            email="guidance_noprofile@test.com", password="pass12345",
            first_name="No", last_name="Profile", role="guidance",
        )

    def _payload(self, **overrides):
        payload = {
            "student": str(self.student_profile.id),
            "plan_start_date": str(self.today),
        }
        payload.update(overrides)
        return payload

    def test_guidance_without_profile_is_forbidden_not_a_server_error(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.profileless_user)}"
        )
        response = self.client.post(
            "/api/v1/guidance/interventions/",
            self._payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["error"]["code"], "PERMISSION_DENIED"
        )
        self.assertEqual(
            response.data["error"]["message"], "No guidance profile found."
        )
        self.assertEqual(Intervention.objects.count(), 1)

    def test_reversed_review_date_is_a_bad_request(self):
        """The date-ordering rule must be a 400, not a model-level 500."""
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.post(
            "/api/v1/guidance/interventions/",
            self._payload(
                plan_start_date=str(self.today),
                target_review_date=str(self.yesterday),
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(
            response.data["error"]["details"]["target_review_date"],
            ["Target review date cannot be before the plan start date."],
        )
        self.assertEqual(Intervention.objects.count(), 1)

    def test_review_date_on_the_start_date_is_accepted(self):
        """Equal dates are not "before" - the boundary stays valid."""
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.post(
            "/api/v1/guidance/interventions/",
            self._payload(
                plan_start_date=str(self.today),
                target_review_date=str(self.today),
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_review_date_after_start_date_is_accepted(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.post(
            "/api/v1/guidance/interventions/",
            self._payload(
                plan_start_date=str(self.today),
                target_review_date=str(self.today + timedelta(days=30)),
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Intervention.objects.exclude(
            id=self.intervention1.id
        ).get()
        self.assertEqual(created.assigned_counselor, self.guidance_profile)
        self.assertEqual(created.status, Intervention.Status.ACTIVE)

    def test_valid_creation_without_review_date_is_unchanged(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.post(
            "/api/v1/guidance/interventions/",
            self._payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Intervention.objects.exclude(
            id=self.intervention1.id
        ).get()
        self.assertIsNone(created.target_review_date)

    def test_patching_to_a_reversed_review_date_is_a_bad_request(self):
        """The rule is enforced on update as well as create."""
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.patch(
            f"/api/v1/guidance/interventions/{self.intervention1.id}/",
            {"target_review_date": "2000-01-01"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.intervention1.refresh_from_db()
        self.assertIsNone(self.intervention1.target_review_date)


class InterventionStepsTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )

    def test_add_step_to_intervention(self):
        response = self.client.post(
            f"/api/v1/guidance/interventions/{self.intervention1.id}/steps/",
            {
                "title": "Initial Assessment",
                "description": "Conduct initial assessment.",
                "status": "pending",
                "order": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(InterventionStep.objects.count(), 1)

    def test_list_steps(self):
        InterventionStep.objects.create(
            intervention=self.intervention1,
            title="Step 1",
            description="First step.",
            order=1,
        )
        response = self.client.get(
            f"/api/v1/guidance/interventions/{self.intervention1.id}/steps/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_update_step_status_dispatches_notification(self):
        step = InterventionStep.objects.create(
            intervention=self.intervention1,
            title="Parent Meeting",
            description="Meet with parents.",
            status="pending",
            order=1,
        )
        response = self.client.patch(
            f"/api/v1/guidance/interventions/{self.intervention1.id}/steps/{step.id}/",
            {"status": "in_progress"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notifs = Notification.objects.filter(
            notification_type="INTERVENTION_UPDATE"
        )
        self.assertGreaterEqual(notifs.count(), 1)


class InterventionNotesTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )

    def test_add_progress_note(self):
        response = self.client.post(
            f"/api/v1/guidance/interventions/{self.intervention1.id}/notes/",
            {
                "note_text": "Student showed improvement in behavior.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        note = ProgressNote.objects.get(id=response.data["id"])
        self.assertEqual(note.recorded_by, self.guidance_profile)

    def test_list_notes(self):
        ProgressNote.objects.create(
            intervention=self.intervention1,
            note_text="Initial note.",
            recorded_by=self.guidance_profile,
        )
        response = self.client.get(
            f"/api/v1/guidance/interventions/{self.intervention1.id}/notes/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class InterventionCompleteTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )

    def test_complete_active_intervention(self):
        response = self.client.post(
            f"/api/v1/guidance/interventions/{self.intervention1.id}/complete/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.intervention1.refresh_from_db()
        self.assertEqual(self.intervention1.status, "completed")

    def test_completing_intervention_resolves_linked_alert(self):
        response = self.client.post(
            f"/api/v1/guidance/interventions/{self.intervention1.id}/complete/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.risk_alert1.refresh_from_db()
        self.assertEqual(self.risk_alert1.status, "resolved")

    def test_cannot_complete_non_active_intervention(self):
        self.intervention1.status = "completed"
        self.intervention1.save()
        response = self.client.post(
            f"/api/v1/guidance/interventions/{self.intervention1.id}/complete/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_intervention_list_scoped_to_assigned_counselor(self):
        # guidance2 should not see intervention assigned to guidance
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance2_user)}"
        )
        response = self.client.get("/api/v1/guidance/interventions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)


# ===========================================================================
# Guidance Report tests
# ===========================================================================


class GuidanceReportTest(GuidanceTestBase):
    def setUp(self):
        super().setUp()
        # Seed additional data for report
        ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=self.today,
            session_time=time(10, 0),
            session_type="individual_counseling",
            concern_categories=["academic"],
            session_notes="Initial.",
            priority_level="medium",
        )
        InterventionStep.objects.create(
            intervention=self.intervention1,
            title="Assessment",
            description="Initial assessment.",
            status="completed",
            order=1,
        )

    def test_guidance_generates_report(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.get(
            f"/api/v1/guidance/reports/student/{self.student_profile.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["student_name"], "Stu Dent")
        self.assertEqual(response.data["student_id_code"], "STU-GR-001")

    def test_report_contains_behavioral_note_counts(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.get(
            f"/api/v1/guidance/reports/student/{self.student_profile.id}/"
        )
        counts = response.data["behavioral_note_counts"]
        self.assertEqual(counts["warning"], 1)
        self.assertEqual(counts["positive"], 1)
        self.assertEqual(counts["incident"], 0)

    def test_report_contains_consultation_summary(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.get(
            f"/api/v1/guidance/reports/student/{self.student_profile.id}/"
        )
        summary = response.data["consultation_summary"]
        self.assertEqual(summary["total"], 1)

    def test_report_contains_intervention_summary(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.get(
            f"/api/v1/guidance/reports/student/{self.student_profile.id}/"
        )
        summary = response.data["intervention_summary"]
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["active"], 1)

    def test_report_contains_risk_alert_history(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )
        response = self.client.get(
            f"/api/v1/guidance/reports/student/{self.student_profile.id}/"
        )
        history = response.data["risk_alert_history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["risk_level"], "moderate")

    def test_non_guidance_cannot_access_report(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )
        response = self.client.get(
            f"/api/v1/guidance/reports/student/{self.student_profile.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
