"""
Phase 10.8 test suite — Sensitive-data ACCESS auditing.

Verifies that meaningful, sensitive READ operations write ``access``
AuditLog events through the PH10.4 central audit service, and — equally
important — that ordinary reads and list endpoints do NOT.

    Authorized sensitive read
        |
        v
    PH10.8 access hook (record_object_access)
        |
        v
    PH10.6 request/actor context (get_audit_context)
        |
        v
    PH10.4 record_audit(action="access")
        |
        v
    AuditLog

Selected ACCESS matrix (the authoritative set):

    model_name                      endpoint (detail read)                  why
    ------------------------------  ------------------------------------   -----------------------------
    guidance.BehavioralNote         GET /guidance/behavioral-notes/{id}/     behavioral narrative
    guidance.ConsultationRecord     GET /guidance/consultations/{id}/        session notes / recommendations
    guidance.RiskAlert              GET /guidance/risk-alerts/{id}/          risk factors / risk level
    guidance.Intervention           GET /guidance/interventions/{id}/        intervention plan
    accounts.StudentProfile         GET /guidance/reports/student/{id}/      aggregated guidance report
    assessments.AssessmentResult    GET /assessments/assessment-results/{id}/ student answers / scored result

Explicitly NOT audited (verified here so the noise rule is enforced):
    - all list endpoints (behavioral-notes, consultations, risk-alerts,
      interventions, assessment-results)
    - intervention nested steps / notes list reads
    - attendance records (operational, lower sensitivity)
    - self-service /accounts/me/ reads
    - any generic authenticated GET

No sensitive content is ever stored: each ACCESS record carries only
model metadata (model_name, object UUID, ``<ModelName>:<UUID>`` repr),
the actor, request metadata, and timestamp.  The content being viewed is
never copied into the audit record, and ``changes`` is always NULL.
"""

from unittest import mock

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
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
)
from apps.assessments.models import (
    Assessment,
    AssessmentQuestion,
    AssessmentResult,
)
from apps.audit.models import AuditLog
from apps.guidance.models import (
    BehavioralNote,
    ConsultationRecord,
    Intervention,
    InterventionStep,
    ProgressNote,
    RiskAlert,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Sensitive-content markers (never permitted inside an AuditLog row)
# ---------------------------------------------------------------------------

MARKER_NOTE_TEXT = "TOP-SECRET-BEHAVIORAL-NARRATIVE"
MARKER_SESSION_NOTES = "TOP-SECRET-SESSION-NOTES"
MARKER_RECOMMENDATION = "TOP-SECRET-RECOMMENDATION"
MARKER_RISK_FACTOR = "top-secret-risk-factor-tag"
MARKER_STEP_DESCRIPTION = "TOP-SECRET-INTERVENTION-STEP"
MARKER_PROGRESS_NOTE = "TOP-SECRET-PROGRESS-NOTE"
MARKER_ANSWER = "TOP-SECRET-ASSESSMENT-ANSWER"
MARKER_PASSWORD = "top-secret-password-value"
MARKER_ACCESS_TOKEN = "TOP-SECRET-ACCESS-TOKEN-VALUE"
MARKER_REFRESH_TOKEN = "TOP-SECRET-REFRESH-TOKEN-VALUE"
MARKER_AUTHZ_HEADER = "Bearer TOP-SECRET-AUTHZ-HEADER-VALUE"

ALL_MARKERS = (
    MARKER_NOTE_TEXT,
    MARKER_SESSION_NOTES,
    MARKER_RECOMMENDATION,
    MARKER_RISK_FACTOR,
    MARKER_STEP_DESCRIPTION,
    MARKER_PROGRESS_NOTE,
    MARKER_ANSWER,
    MARKER_PASSWORD,
    MARKER_ACCESS_TOKEN,
    MARKER_REFRESH_TOKEN,
    MARKER_AUTHZ_HEADER,
)


def _clear_audit():
    AuditLog.objects.all().delete()


def _serialize_log(log):
    """Flatten every saved AuditLog field into one searchable string."""
    chunks = [
        str(getattr(log, field, "") or "")
        for field in (
            "user_id",
            "action",
            "model_name",
            "object_id",
            "object_repr",
            "ip_address",
            "user_agent",
            "timestamp",
        )
    ]
    if log.changes:
        chunks.append(str(log.changes))
    return "\n".join(chunks)


def _access_logs():
    return AuditLog.objects.filter(action="access").order_by("timestamp")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


class AccessTestBase(TestCase):
    """Common users, profiles, academic structure, and domain fixtures."""

    def setUp(self):
        self.client = APIClient()
        self._make_users()
        self._make_staff_profiles()
        self._make_academics()
        self._make_student_profiles()
        _clear_audit()

    def _make_users(self):
        self.admin_user = User.objects.create_user(
            email="access-admin@test.com", password="pass12345",
            first_name="Admin", last_name="User", role="admin",
        )
        self.faculty_user = User.objects.create_user(
            email="access-faculty@test.com", password="pass12345",
            first_name="Fac", last_name="ulty", role="faculty",
        )
        self.guidance_user = User.objects.create_user(
            email="access-guid@test.com", password="pass12345",
            first_name="Guid", last_name="ance", role="guidance",
        )
        self.guidance2_user = User.objects.create_user(
            email="access-guid2@test.com", password="pass12345",
            first_name="Guid", last_name="ance2", role="guidance",
        )
        self.student_user = User.objects.create_user(
            email="access-student@test.com", password="pass12345",
            first_name="Stu", last_name="dent", role="student",
        )
        self.student2_user = User.objects.create_user(
            email="access-student2@test.com", password="pass12345",
            first_name="Stu", last_name="dent2", role="student",
        )
        self.parent_user = User.objects.create_user(
            email="access-parent@test.com", password="pass12345",
            first_name="Par", last_name="ent", role="parent",
        )

    def _make_academics(self):
        self.ay = AcademicYear.objects.create(
            name="2025-2026", start_date="2025-06-01",
            end_date="2026-03-31", is_current=True,
        )
        self.grade_level = GradeLevel.objects.create(
            name="Grade 7", level_number=7,
        )
        self.section = Section.objects.create(
            name="AccessSection", grade_level=self.grade_level,
            academic_year=self.ay, adviser=self.faculty_profile,
        )
        self.section2 = Section.objects.create(
            name="AccessSection2", grade_level=self.grade_level,
            academic_year=self.ay,
        )

    def _make_staff_profiles(self):
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="EMP-ACC-001", department="Math",
        )
        self.guidance_profile = GuidanceProfile.objects.create(
            user=self.guidance_user, employee_id="EMP-ACC-002",
        )
        self.guidance2_profile = GuidanceProfile.objects.create(
            user=self.guidance2_user, employee_id="EMP-ACC-003",
        )

    def _make_student_profiles(self):
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user, student_id="STU-ACC-001",
            enrollment_date="2025-06-01", section=self.section,
            grade_level=self.grade_level, is_active=True,
        )
        self.student2_profile = StudentProfile.objects.create(
            user=self.student2_user, student_id="STU-ACC-002",
            enrollment_date="2025-06-01", section=self.section2,
            grade_level=self.grade_level, is_active=True,
        )
        self.parent_profile = ParentProfile.objects.create(
            user=self.parent_user, relationship_to_student="mother",
        )
        ParentStudentLink.objects.create(
            parent=self.parent_profile, student=self.student_profile, is_primary=True,
        )
        Enrollment.objects.create(
            student=self.student_profile, section=self.section,
            academic_year=self.ay, date_enrolled="2025-06-01", is_active=True,
        )
        Enrollment.objects.create(
            student=self.student2_profile, section=self.section2,
            academic_year=self.ay, date_enrolled="2025-06-01", is_active=True,
        )

    def _get_with(self, user, url, ip="203.0.113.10", ua="AccessSpec-UA/1.0"):
        """Authenticate as *user* and GET *url*, injecting request metadata."""
        self.client.force_authenticate(user=user)
        return self.client.get(url, REMOTE_ADDR=ip, HTTP_USER_AGENT=ua)


# ---------------------------------------------------------------------------
# Endpoint-agnostic ACCESS assertions (shared by the six detail endpoints)
# ---------------------------------------------------------------------------


class _DetailAccessMixin:
    """Per-endpoint coverage for one sensitive detail-retrieve endpoint.

    Subclasses must provide::

        detail_url()      -> absolute URL of the detail retrieve
        access_target()   -> the domain object the ACCESS event targets
        expected_model    -> 'app_label.ModelName' string
        authorized_user   -> a user allowed to retrieve the target
        unauthorized_user -> a user NOT allowed to retrieve the target
        access_markers    -> sensitive field values that must never be audited
        isolation_cases   -> [(user, ip, ua, url)] two successful accesses
    """

    def test_authorized_user_can_access_target(self):
        response = self._get_with(self.authorized_user(), self.detail_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_exactly_one_access_record(self):
        self._get_with(self.authorized_user(), self.detail_url())
        self.assertEqual(_access_logs().count(), 1)

    def test_action_is_access(self):
        self._get_with(self.authorized_user(), self.detail_url())
        log = _access_logs().first()
        self.assertEqual(log.action, "access")

    def test_model_name_is_correct(self):
        self._get_with(self.authorized_user(), self.detail_url())
        log = _access_logs().first()
        self.assertEqual(log.model_name, self.expected_model)

    def test_object_id_is_target_pk(self):
        self._get_with(self.authorized_user(), self.detail_url())
        log = _access_logs().first()
        self.assertEqual(log.object_id, self.access_target().pk)

    def test_object_repr_is_safe_model_uuid(self):
        self._get_with(self.authorized_user(), self.detail_url())
        log = _access_logs().first()
        short = self.expected_model.split(".")[-1]
        self.assertEqual(log.object_repr, f"{short}:{self.access_target().pk}")

    def test_correct_actor_recorded(self):
        user = self.authorized_user()
        self._get_with(user, self.detail_url())
        log = _access_logs().first()
        self.assertEqual(log.user_id, user.pk)

    def test_ip_address_from_context(self):
        self._get_with(self.authorized_user(), self.detail_url(), ip="203.0.113.201")
        log = _access_logs().first()
        self.assertEqual(log.ip_address, "203.0.113.201")

    def test_user_agent_from_context(self):
        self._get_with(self.authorized_user(), self.detail_url(), ua="Phase10.8-UA/1.1")
        log = _access_logs().first()
        self.assertEqual(log.user_agent, "Phase10.8-UA/1.1")

    def test_changes_is_null(self):
        self._get_with(self.authorized_user(), self.detail_url())
        log = _access_logs().first()
        self.assertIsNone(log.changes)

    def test_sensitive_target_content_never_copied(self):
        self._get_with(self.authorized_user(), self.detail_url())
        log = _access_logs().first()
        blob = _serialize_log(log)
        for marker in self.access_markers:
            self.assertNotIn(marker, blob)

    def test_unauthorized_user_cannot_access(self):
        response = self._get_with(self.unauthorized_user(), self.detail_url())
        self.assertIn(response.status_code, (status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN))

    def test_unauthorized_access_creates_no_access_event(self):
        self._get_with(self.unauthorized_user(), self.detail_url())
        self.assertEqual(_access_logs().count(), 0)

    def test_hidden_object_404_creates_no_access_event(self):
        self.client.force_authenticate(user=self.authorized_user())
        hidden_url = self.detail_url().replace(
            str(self.access_target().id), str(uuid.uuid4())
        )
        response = self.client.get(hidden_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(_access_logs().count(), 0)

    def test_repeated_access_creates_one_event_per_access(self):
        user = self.authorized_user()
        first = self._get_with(user, self.detail_url(), ip="203.0.113.30", ua="RepeatUA-1")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        second = self._get_with(user, self.detail_url(), ip="203.0.113.30", ua="RepeatUA-1")
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        logs = list(_access_logs())
        self.assertEqual(len(logs), 2)
        self.assertNotEqual(logs[0].id, logs[1].id)

    def test_no_duplicate_events_per_single_access(self):
        # A single successful retrieval produces exactly one ACCESS event —
        # the serializer / nested code paths must not add more.
        self._get_with(self.authorized_user(), self.detail_url())
        self.assertEqual(_access_logs().count(), 1)

    def test_actor_context_does_not_leak_between_requests(self):
        (user_a, ip_a, ua_a, url_a), (user_b, ip_b, ua_b, url_b) = self.isolation_cases
        self._get_with(user_a, url_a, ip=ip_a, ua=ua_a)
        self._get_with(user_b, url_b, ip=ip_b, ua=ua_b)
        logs = list(_access_logs())
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0].user_id, user_a.pk)
        self.assertEqual(logs[0].ip_address, ip_a)
        self.assertEqual(logs[0].user_agent, ua_a)
        self.assertEqual(logs[1].user_id, user_b.pk)
        self.assertEqual(logs[1].ip_address, ip_b)
        self.assertEqual(logs[1].user_agent, ua_b)
        self.assertNotEqual(logs[1].user_id, logs[0].user_id)
        self.assertNotEqual(logs[1].ip_address, logs[0].ip_address)


# ---------------------------------------------------------------------------
# 1. BehavioralNote detail read
# ---------------------------------------------------------------------------


class BehavioralNoteAccessAuditTest(_DetailAccessMixin, AccessTestBase):
    expected_model = "guidance.BehavioralNote"
    access_markers = (MARKER_NOTE_TEXT,)

    def setUp(self):
        super().setUp()
        self.note = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="incident",
            note_text=(
                f"Student showed signs of distress. {MARKER_NOTE_TEXT}. "
                f"{MARKER_PASSWORD}"
            ),
            date_recorded=timezone.localdate(),
        )

    def detail_url(self):
        return f"/api/v1/guidance/behavioral-notes/{self.note.id}/"

    def access_target(self):
        return self.note

    def authorized_user(self):
        return self.guidance_user

    def unauthorized_user(self):
        return self.student2_user

    @property
    def isolation_cases(self):
        return [
            (self.guidance_user, "203.0.113.41", "NoteIsolationUA/1", self.detail_url()),
            (self.student_user, "203.0.113.42", "NoteIsolationUA/2", self.detail_url()),
        ]


# ---------------------------------------------------------------------------
# 2. ConsultationRecord detail read
# ---------------------------------------------------------------------------


class ConsultationRecordAccessAuditTest(_DetailAccessMixin, AccessTestBase):
    expected_model = "guidance.ConsultationRecord"
    access_markers = (MARKER_SESSION_NOTES, MARKER_RECOMMENDATION)

    def setUp(self):
        super().setUp()
        self.consultation = ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=timezone.localdate(),
            session_time=timezone.now().time(),
            session_type="individual_counseling",
            concern_categories=["emotional"],
            session_notes=f"Student opened up. {MARKER_SESSION_NOTES}.",
            recommendations=f"Regular follow-up. {MARKER_RECOMMENDATION}.",
            priority_level="high",
            status="ongoing",
        )
        self.consultation2 = ConsultationRecord.objects.create(
            student=self.student2_profile,
            counselor=self.guidance2_profile,
            session_date=timezone.localdate(),
            session_time=timezone.now().time(),
            session_type="group",
            concern_categories=["academic"],
            session_notes="Second counselor's notes.",
            priority_level="low",
            status="ongoing",
        )

    def detail_url(self):
        return f"/api/v1/guidance/consultations/{self.consultation.id}/"

    def access_target(self):
        return self.consultation

    def authorized_user(self):
        return self.guidance_user

    def unauthorized_user(self):
        return self.guidance2_user

    @property
    def isolation_cases(self):
        return [
            (self.guidance_user, "203.0.113.51", "ConsulIsolationUA/1", self.detail_url()),
            (
                self.guidance2_user, "203.0.113.52", "ConsulIsolationUA/2",
                f"/api/v1/guidance/consultations/{self.consultation2.id}/",
            ),
        ]


# ---------------------------------------------------------------------------
# 3. RiskAlert detail read
# ---------------------------------------------------------------------------


class RiskAlertAccessAuditTest(_DetailAccessMixin, AccessTestBase):
    expected_model = "guidance.RiskAlert"
    access_markers = (MARKER_RISK_FACTOR,)

    def setUp(self):
        super().setUp()
        self.alert = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="high",
            risk_factors=[MARKER_RISK_FACTOR, "recent academic decline"],
            status="active",
            generated_at=timezone.now(),
        )

    def detail_url(self):
        return f"/api/v1/guidance/risk-alerts/{self.alert.id}/"

    def access_target(self):
        return self.alert

    def authorized_user(self):
        return self.guidance_user

    def unauthorized_user(self):
        return self.student2_user

    @property
    def isolation_cases(self):
        return [
            (self.guidance_user, "203.0.113.61", "RiskIsolationUA/1", self.detail_url()),
            (self.student_user, "203.0.113.62", "RiskIsolationUA/2", self.detail_url()),
        ]


# ---------------------------------------------------------------------------
# 4. Intervention detail read
# ---------------------------------------------------------------------------


class InterventionAccessAuditTest(_DetailAccessMixin, AccessTestBase):
    expected_model = "guidance.Intervention"
    access_markers = (MARKER_STEP_DESCRIPTION, MARKER_PROGRESS_NOTE)

    def setUp(self):
        super().setUp()
        self.intervention = Intervention.objects.create(
            student=self.student_profile,
            assigned_counselor=self.guidance_profile,
            plan_start_date=timezone.localdate(),
            status="active",
        )
        self.step = InterventionStep.objects.create(
            intervention=self.intervention,
            title="Weekly check-in",
            description=f"Scheduled guidance session. {MARKER_STEP_DESCRIPTION}.",
            status="in_progress",
            order=1,
        )
        ProgressNote.objects.create(
            intervention=self.intervention,
            note_text=f"Student progress tracked. {MARKER_PROGRESS_NOTE}.",
            recorded_by=self.guidance_profile,
        )
        self.intervention2 = Intervention.objects.create(
            student=self.student2_profile,
            assigned_counselor=self.guidance2_profile,
            plan_start_date=timezone.localdate(),
            status="active",
        )

    def detail_url(self):
        return f"/api/v1/guidance/interventions/{self.intervention.id}/"

    def access_target(self):
        return self.intervention

    def authorized_user(self):
        return self.guidance_user

    def unauthorized_user(self):
        return self.guidance2_user

    @property
    def isolation_cases(self):
        return [
            (self.guidance_user, "203.0.113.71", "InvIsolationUA/1", self.detail_url()),
            (
                self.guidance2_user, "203.0.113.72", "InvIsolationUA/2",
                f"/api/v1/guidance/interventions/{self.intervention2.id}/",
            ),
        ]


# ---------------------------------------------------------------------------
# 5. Guidance report for a student
# ---------------------------------------------------------------------------


class GuidanceReportAccessAuditTest(_DetailAccessMixin, AccessTestBase):
    expected_model = "accounts.StudentProfile"

    def setUp(self):
        super().setUp()
        self.student_full_name = self.student_user.get_full_name()

    @property
    def access_markers(self):
        return (self.student_full_name,)

    def detail_url(self):
        return f"/api/v1/guidance/reports/student/{self.student_profile.id}/"

    def access_target(self):
        return self.student_profile

    def authorized_user(self):
        return self.guidance_user

    def unauthorized_user(self):
        return self.faculty_user

    @property
    def isolation_cases(self):
        return [
            (self.guidance_user, "203.0.113.81", "ReportIsolationUA/1", self.detail_url()),
            (self.guidance2_user, "203.0.113.82", "ReportIsolationUA/2", self.detail_url()),
        ]


# ---------------------------------------------------------------------------
# 6. AssessmentResult detail read
# ---------------------------------------------------------------------------


class AssessmentResultAccessAuditTest(_DetailAccessMixin, AccessTestBase):
    expected_model = "assessments.AssessmentResult"
    access_markers = (MARKER_ANSWER,)

    def setUp(self):
        super().setUp()
        self.assessment = Assessment.objects.create(
            title="Q1 Academic Check",
            description="Periodic academic check",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        self.question = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="Emergency contact?",
            question_type="essay",
            order=1,
        )
        self.result = AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={str(self.question.id): MARKER_ANSWER},
            status="completed",
        )

    def detail_url(self):
        return f"/api/v1/assessments/assessment-results/{self.result.id}/"

    def access_target(self):
        return self.result

    def authorized_user(self):
        return self.student_user

    def unauthorized_user(self):
        return self.student2_user

    @property
    def isolation_cases(self):
        return [
            (self.faculty_user, "203.0.113.91", "ResultIsolationUA/1", self.detail_url()),
            (self.admin_user, "203.0.113.92", "ResultIsolationUA/2", self.detail_url()),
        ]


# ---------------------------------------------------------------------------
# Noise control: list / nested / low-sensitivity reads create NO ACCESS events
# ---------------------------------------------------------------------------


class ExcludedReadsCreateNoAccessEventTest(AccessTestBase):
    """List endpoints and lower-sensitivity reads must stay silent."""

    def setUp(self):
        super().setUp()
        self.note = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="Positive observation.",
            date_recorded=timezone.localdate(),
        )
        self.consultation = ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=timezone.localdate(),
            session_time=timezone.now().time(),
            session_type="individual_counseling",
            concern_categories=["academic"],
            session_notes="Notes.",
            priority_level="low",
            status="ongoing",
        )
        self.alert = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="low",
            risk_factors=["minor concern"],
            status="active",
            generated_at=timezone.now(),
        )
        self.intervention = Intervention.objects.create(
            student=self.student_profile,
            assigned_counselor=self.guidance_profile,
            plan_start_date=timezone.localdate(),
            status="active",
        )
        InterventionStep.objects.create(
            intervention=self.intervention,
            title="Step one",
            description="Description.",
            status="pending",
            order=1,
        )
        self.assessment = Assessment.objects.create(
            title="Q2 Academic Check",
            description="Desc",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        self.result = AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={},
            status="completed",
        )

    def _assert_no_access_events(self, user, url):
        response = self._get_with(user, url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_access_logs().count(), 0)

    def test_behavioral_notes_list_no_access_event(self):
        self._assert_no_access_events(
            self.guidance_user, "/api/v1/guidance/behavioral-notes/"
        )

    def test_consultations_list_no_access_event(self):
        self._assert_no_access_events(
            self.guidance_user, "/api/v1/guidance/consultations/"
        )

    def test_risk_alerts_list_no_access_event(self):
        self._assert_no_access_events(
            self.guidance_user, "/api/v1/guidance/risk-alerts/"
        )

    def test_interventions_list_no_access_event(self):
        self._assert_no_access_events(
            self.guidance_user, "/api/v1/guidance/interventions/"
        )

    def test_assessment_results_list_no_access_event(self):
        self._assert_no_access_events(
            self.faculty_user, "/api/v1/assessments/assessment-results/"
        )

    def test_intervention_steps_list_no_access_event(self):
        self._assert_no_access_events(
            self.guidance_user, f"/api/v1/guidance/interventions/{self.intervention.id}/steps/"
        )

    def test_intervention_notes_list_no_access_event(self):
        self._assert_no_access_events(
            self.guidance_user, f"/api/v1/guidance/interventions/{self.intervention.id}/notes/"
        )

    def test_intervention_step_detail_no_access_event(self):
        self._assert_no_access_events(
            self.guidance_user,
            f"/api/v1/guidance/interventions/{self.intervention.id}/steps/{self.step_id()}/",
        )

    def test_attendance_record_reads_no_access_event(self):
        self._assert_no_access_events(
            self.student_user, f"/api/v1/attendance/records/?student={self.student_profile.id}"
        )

    def test_self_profile_read_no_access_event(self):
        self._assert_no_access_events(self.student_user, "/api/v1/accounts/me/")

    def step_id(self):
        from apps.guidance.models import InterventionStep

        return InterventionStep.objects.get(intervention=self.intervention, order=1).id


# ---------------------------------------------------------------------------
# Global sensitive-data regression: no content anywhere in any ACCESS row
# ---------------------------------------------------------------------------


class AccessSensitiveDataRegressionTest(AccessTestBase):
    """Scan the COMPLETE AuditLog row, not just `changes`."""

    def setUp(self):
        super().setUp()
        self.note = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="incident",
            note_text=MARKER_NOTE_TEXT,
            date_recorded=timezone.localdate(),
        )
        self.consultation = ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=timezone.localdate(),
            session_time=timezone.now().time(),
            session_type="individual_counseling",
            concern_categories=["emotional"],
            session_notes=MARKER_SESSION_NOTES,
            recommendations=MARKER_RECOMMENDATION,
            priority_level="high",
            status="ongoing",
        )
        self.alert = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="moderate",
            risk_factors=[MARKER_RISK_FACTOR],
            status="active",
            generated_at=timezone.now(),
        )
        self.intervention = Intervention.objects.create(
            student=self.student_profile,
            assigned_counselor=self.guidance_profile,
            plan_start_date=timezone.localdate(),
            status="active",
        )
        InterventionStep.objects.create(
            intervention=self.intervention,
            title="Step",
            description=MARKER_STEP_DESCRIPTION,
            status="pending",
            order=1,
        )
        ProgressNote.objects.create(
            intervention=self.intervention,
            note_text=MARKER_PROGRESS_NOTE,
            recorded_by=self.guidance_profile,
        )
        self.assessment = Assessment.objects.create(
            title="Sensitive Sweep Assessment",
            description="Desc",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        self.question = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="Describe.",
            question_type="essay",
            order=1,
        )
        self.result = AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={str(self.question.id): MARKER_ANSWER},
            status="completed",
        )
        _clear_audit()

    def _make_all_access_events(self):
        # A request carrying an Authorization header so header/credential
        # privacy is exercised end-to-end.
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + MARKER_AUTHZ_HEADER)

        response = self._get_with(
            self.guidance_user, f"/api/v1/guidance/behavioral-notes/{self.note.id}/",
            ip="203.0.113.130", ua="SweepUA/1",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self._get_with(
            self.guidance_user, f"/api/v1/guidance/consultations/{self.consultation.id}/",
            ip="203.0.113.131", ua="SweepUA/2",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self._get_with(
            self.guidance_user, f"/api/v1/guidance/risk-alerts/{self.alert.id}/",
            ip="203.0.113.132", ua="SweepUA/3",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self._get_with(
            self.guidance_user, f"/api/v1/guidance/interventions/{self.intervention.id}/",
            ip="203.0.113.133", ua="SweepUA/4",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self._get_with(
            self.guidance_user,
            f"/api/v1/guidance/reports/student/{self.student_profile.id}/",
            ip="203.0.113.134", ua="SweepUA/5",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self._get_with(
            self.faculty_user, f"/api/v1/assessments/assessment-results/{self.result.id}/",
            ip="203.0.113.135", ua="SweepUA/6",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_all_six_access_events_created(self):
        self._make_all_access_events()
        self.assertEqual(_access_logs().count(), 6)

    def test_complete_audit_row_contains_no_sensitive_content(self):
        self._make_all_access_events()
        for log in _access_logs():
            blob = _serialize_log(log)
            for marker in ALL_MARKERS:
                self.assertNotIn(marker, blob)

    def test_no_access_row_stores_any_agent_password_or_token(self):
        self._make_all_access_events()
        for log in _access_logs():
            self.assertIsNone(log.changes)
            blob = _serialize_log(log)
            for forbidden in (
                "password",
                "access_token",
                "refresh_token",
                "authorization",
                "Bearer ",
            ):
                self.assertNotIn(forbidden.lower(), blob.lower())

    def test_access_rows_contain_only_target_metadata_and_actor(self):
        self._make_all_access_events()
        found = set(_access_logs().values_list("model_name", flat=True))
        self.assertEqual(
            found,
            {
                "guidance.BehavioralNote",
                "guidance.ConsultationRecord",
                "guidance.RiskAlert",
                "guidance.Intervention",
                "accounts.StudentProfile",
                "assessments.AssessmentResult",
            },
        )


# ---------------------------------------------------------------------------
# Failure isolation: an audit hiccup never breaks an authorized read
# ---------------------------------------------------------------------------


class AccessFailureIsolationTest(AccessTestBase):
    """ACCESS auditing is fail-open (PH10.7 philosophy)."""

    def setUp(self):
        super().setUp()
        self.note = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="warning",
            note_text="Warning observation.",
            date_recorded=timezone.localdate(),
        )

    def test_authorized_read_succeeds_when_audit_write_raises(self):
        with mock.patch(
            "apps.audit.access.record_audit", side_effect=RuntimeError("db down")
        ):
            response = self._get_with(
                self.guidance_user, f"/api/v1/guidance/behavioral-notes/{self.note.id}/",
                ip="203.0.113.140", ua="FailIsolationUA/1",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_audit_write_failure_produces_no_partial_access_row(self):
        with mock.patch(
            "apps.audit.access.record_audit", side_effect=ValueError("boom")
        ):
            self._get_with(
                self.guidance_user, f"/api/v1/guidance/behavioral-notes/{self.note.id}/",
                ip="203.0.113.141", ua="FailIsolationUA/2",
            )
        self.assertEqual(_access_logs().count(), 0)

    def test_ctx_vars_are_empty_outside_a_request(self):
        from apps.audit.context import get_audit_context

        ctx = get_audit_context()
        self.assertIsNone(ctx.user)
        self.assertIsNone(ctx.ip_address)
        self.assertIsNone(ctx.user_agent)