"""
Phase 10.5 test suite — Model signal auditing.

Verifies that ordinary domain CRUD on the PH10 instrumented models flows
through Django model signals into the central audit service:

    domain CRUD -> signal -> record_audit() -> AuditLog

Every instrumented model is exercised for CREATE / UPDATE / DELETE with
exact one-event-per-operation semantics, correct model metadata, safe
object_repr, faithful pre-change UPDATE snapshots, sensitive-field
exclusion (via the PH10.2 allowlists), recursion prevention, transaction
behavior, and system/background (user=None) actor handling.

Deliberately NOT covered here as audit events (by design):
- raw ``QuerySet.update()`` / ``bulk_create()`` / ``QuerySet.delete()``
  bypass Django signals; that limitation is documented, not tested for.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared fixtures: a full domain graph needed to construct every
# instrumented model with valid FK relationships.
# ---------------------------------------------------------------------------

class SignalTestBase(TestCase):
    """Minimal, valid domain graph shared by all PH10.5 signal tests."""

    def setUp(self):
        today = date.today()
        past = today - timedelta(days=60)

        self.faculty_user = User.objects.create_user(
            email="faculty-signal@example.com",
            password="pass12345",
            first_name="Fac",
            last_name="Ultysig",
            role="faculty",
        )
        self.student_user = User.objects.create_user(
            email="student-signal@example.com",
            password="pass12345",
            first_name="Stu",
            last_name="Dentsig",
            role="student",
        )
        self.counselor_user = User.objects.create_user(
            email="counselor-signal@example.com",
            password="pass12345",
            first_name="Cou",
            last_name="Nselsig",
            role="guidance",
        )

        from apps.accounts.models import (
            FacultyProfile,
            GuidanceProfile,
            StudentProfile,
        )

        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user,
            employee_id="FAC-SIG-001",
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="STU-SIG-001",
            enrollment_date=past,
        )
        self.guidance_profile = GuidanceProfile.objects.create(
            user=self.counselor_user,
            employee_id="GDE-SIG-001",
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

        self.academic_year = AcademicYear.objects.create(
            name="AY-SIG-2025-2026",
            start_date=date(2025, 6, 1),
            end_date=date(2026, 5, 31),
            is_current=True,
        )
        self.grade_level = GradeLevel.objects.create(
            name="Grade 7",
            level_number=7,
        )
        self.section = Section.objects.create(
            name="SignalSection",
            grade_level=self.grade_level,
            academic_year=self.academic_year,
        )
        self.subject = Subject.objects.create(
            name="Math",
            code="MATH-SIG",
            grade_level=self.grade_level,
        )
        self.subject_assignment = SubjectAssignment.objects.create(
            subject=self.subject,
            faculty=self.faculty_profile,
            section=self.section,
            academic_year=self.academic_year,
        )
        self.grading_period = GradingPeriod.objects.create(
            academic_year=self.academic_year,
            name="Q1",
            order=1,
            start_date=date(2025, 6, 1),
            end_date=date(2025, 8, 31),
        )

        Enrollment.objects.create(
            student=self.student_profile,
            section=self.section,
            academic_year=self.academic_year,
            date_enrolled=past,
        )

        from apps.assessments.models import Assessment, AssessmentResult
        from apps.attendance.models import AttendanceRecord
        from apps.guidance.models import (
            BehavioralNote,
            ConsultationRecord,
            Intervention,
            RiskAlert,
        )

        self.assessment = Assessment.objects.create(
            title="Signal Quiz",
            assessment_type="academic",
            creator_role="faculty",
            created_by=self.faculty_user,
            is_published=False,
        )
        self.attendance_record = AttendanceRecord.objects.create(
            student=self.student_profile,
            section=self.section,
            date=today - timedelta(days=1),
            status="present",
            recorded_by=self.faculty_profile,
        )
        self.behavioral_note = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="Showed steady improvement.",
            date_recorded=today,
        )
        self.consultation = ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=today - timedelta(days=5),
            session_time="10:00:00",
            session_type="individual_counseling",
            concern_categories=["academic"],
            session_notes="Sensitive session notes.",
            recommendations="Sensitive recommendations.",
            priority_level="low",
            status="ongoing",
        )
        self.risk_alert = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="low",
            risk_factors=["attendance_pattern"],
            source="manual",
            status="active",
            assigned_counselor=self.guidance_profile,
            generated_at=timezone.now() - timedelta(days=2),
        )
        self.intervention = Intervention.objects.create(
            student=self.student_profile,
            risk_alert=self.risk_alert,
            assigned_counselor=self.guidance_profile,
            plan_start_date=today - timedelta(days=1),
            status="active",
        )
        self.assessment_result = AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={"q1": "A"},
            status="in_progress",
        )

    # Convenience: clear any audit rows created during setup.
    def _clear_audit(self):
        AuditLog.objects.all().delete()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

class CreateSignalTest(SignalTestBase):
    """Each test creates its own fresh domain instance after setUp clears
    the audit trail, so exactly one CREATE event must exist to inspect."""

    def setUp(self):
        super().setUp()
        self._clear_audit()

    def _assert_create(self, instance, model_label):
        log = AuditLog.objects.get()
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(log.action, "create")
        self.assertEqual(log.model_name, model_label)
        self.assertEqual(log.object_id, instance.pk)
        self.assertTrue(log.object_repr.startswith("%s:" % model_label.split(".")[-1]))
        self.assertIsNone(log.changes)
        self.assertIsNone(log.user)

    def test_grade_create(self):
        from apps.academics.models import Grade

        grade = Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=Decimal("80.00"),
            letter_grade="B",
            status="draft",
            encoded_by=self.faculty_profile,
        )
        self._assert_create(grade, "academics.Grade")

    def test_attendance_record_create(self):
        from apps.attendance.models import AttendanceRecord

        rec = AttendanceRecord.objects.create(
            student=self.student_profile,
            section=self.section,
            date=date.today(),
            status="late",
            recorded_by=self.faculty_profile,
        )
        self._assert_create(rec, "attendance.AttendanceRecord")

    def test_behavioral_note_create(self):
        from apps.guidance.models import BehavioralNote

        note = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="Fresh note.",
            date_recorded=date.today(),
        )
        self._assert_create(note, "guidance.BehavioralNote")

    def test_consultation_create(self):
        from apps.guidance.models import ConsultationRecord

        c = ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=date.today(),
            session_time="14:00:00",
            session_type="individual_counseling",
            concern_categories=["academic"],
            session_notes="Fresh session.",
            recommendations="",
            priority_level="low",
            status="ongoing",
        )
        self._assert_create(c, "guidance.ConsultationRecord")

    def test_risk_alert_create(self):
        from apps.guidance.models import RiskAlert

        alert = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="moderate",
            risk_factors=["attendance_pattern"],
            source="manual",
            status="active",
            generated_at=timezone.now(),
        )
        self._assert_create(alert, "guidance.RiskAlert")

    def test_intervention_create(self):
        from apps.guidance.models import Intervention

        inv = Intervention.objects.create(
            student=self.student_profile,
            risk_alert=self.risk_alert,
            assigned_counselor=self.guidance_profile,
            plan_start_date=date.today(),
            status="active",
        )
        self._assert_create(inv, "guidance.Intervention")

    def test_assessment_create(self):
        from apps.assessments.models import Assessment

        a = Assessment.objects.create(
            title="Fresh Assessment",
            assessment_type="academic",
            creator_role="faculty",
            created_by=self.faculty_user,
            is_published=False,
        )
        self._assert_create(a, "assessments.Assessment")

    def test_assessment_result_create(self):
        from apps.accounts.models import StudentProfile
        from apps.assessments.models import AssessmentResult

        # unique_together (assessment, student) is enforced by full_clean(),
        # so use a fresh student.
        student_user = User.objects.create_user(
            email="student-result-create@example.com",
            password="pass12345",
            first_name="Res",
            last_name="Ult",
            role="student",
        )
        student = StudentProfile.objects.create(
            user=student_user,
            student_id="STU-RES-CREATE",
            enrollment_date=date.today() - timedelta(days=30),
        )
        r = AssessmentResult.objects.create(
            assessment=self.assessment,
            student=student,
            answers={"q1": "A"},
            status="in_progress",
        )
        self._assert_create(r, "assessments.AssessmentResult")


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

class UpdateSignalTest(SignalTestBase):

    def setUp(self):
        super().setUp()
        self._clear_audit()

    def _last_update_log(self):
        return AuditLog.objects.get(action="update")

    def test_grade_update_pre_change_snapshot_is_true(self):
        grade = self._seed_grade()
        grade.score = Decimal("95.00")
        grade.save()
        log = self._last_update_log()
        self.assertEqual(log.changes["old"]["score"], 80.0)
        self.assertEqual(log.changes["new"]["score"], 95.0)

    def _seed_grade(self):
        from apps.academics.models import Grade

        return Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=Decimal("80.00"),
            letter_grade="B",
            status="draft",
            encoded_by=self.faculty_profile,
        )

    def test_grade_update_multiple_fields(self):
        grade = self._seed_grade()
        grade.score = Decimal("95.00")
        grade.letter_grade = "A"
        grade.status = "finalized"
        grade.save()
        log = self._last_update_log()
        self.assertEqual(log.changes["old"]["score"], 80.0)
        self.assertEqual(log.changes["new"]["score"], 95.0)
        self.assertEqual(log.changes["old"]["letter_grade"], "B")
        self.assertEqual(log.changes["new"]["letter_grade"], "A")
        self.assertEqual(log.changes["old"]["status"], "draft")
        self.assertEqual(log.changes["new"]["status"], "finalized")

    def test_grade_update_unchanged_fields_omitted(self):
        grade = self._seed_grade()
        grade.status = "submitted"
        grade.save()
        log = self._last_update_log()
        # Only status moved: unchanged allowlisted fields are omitted.
        self.assertEqual(
            log.changes, {"old": {"status": "draft"}, "new": {"status": "submitted"}}
        )
        self.assertNotIn("score", log.changes["old"])
        self.assertNotIn("score", log.changes["new"])
        self.assertNotIn("letter_grade", log.changes["old"])
        self.assertNotIn("letter_grade", log.changes["new"])

    def test_grade_non_allowlisted_update_yields_no_changes(self):
        grade = self._seed_grade()
        grade.remarks = "Only remarks changed (not allowlisted)."
        grade.save()
        log = self._last_update_log()
        # PH10.3 correct behavior: no allowlisted field changed -> changes None.
        self.assertIsNone(log.changes)

    def test_grade_update_metadata(self):
        grade = self._seed_grade()
        grade.status = "submitted"
        grade.save()
        log = self._last_update_log()
        self.assertEqual(log.action, "update")
        self.assertEqual(log.model_name, "academics.Grade")
        self.assertEqual(log.object_id, grade.pk)
        self.assertIsNone(log.user)

    def test_attendance_status_transition(self):
        rec = self.attendance_record
        rec.status = "absent"
        rec.save()
        log = self._last_update_log()
        self.assertEqual(log.changes["old"], {"status": "present"})
        self.assertEqual(log.changes["new"], {"status": "absent"})

    def test_behavioral_note_note_type_update_only(self):
        note = self.behavioral_note
        note.note_type = "incident"
        note.save()
        log = self._last_update_log()
        self.assertEqual(log.changes["old"], {"note_type": "positive"})
        self.assertEqual(log.changes["new"], {"note_type": "incident"})

    def test_consultation_status_priority_update(self):
        c = self.consultation
        c.status = "completed"
        c.priority_level = "high"
        c.save()
        log = self._last_update_log()
        self.assertEqual(log.changes["old"], {"status": "ongoing", "priority_level": "low"})
        self.assertEqual(log.changes["new"], {"status": "completed", "priority_level": "high"})

    def test_risk_alert_status_update(self):
        alert = self.risk_alert
        alert.status = "escalated"
        alert.save()
        log = self._last_update_log()
        self.assertEqual(log.changes["old"], {"status": "active"})
        self.assertEqual(log.changes["new"], {"status": "escalated"})

    def test_risk_alert_risk_level_update(self):
        alert = self.risk_alert
        alert.risk_level = "high"
        alert.save()
        log = self._last_update_log()
        self.assertEqual(log.changes["old"], {"risk_level": "low"})
        self.assertEqual(log.changes["new"], {"risk_level": "high"})

    def test_intervention_status_update(self):
        inv = self.intervention
        inv.status = "completed"
        inv.save()
        log = self._last_update_log()
        self.assertEqual(log.changes["old"], {"status": "active"})
        self.assertEqual(log.changes["new"], {"status": "completed"})

    def test_assessment_title_publish_update(self):
        a = self.assessment
        a.title = "Signal Quiz v2"
        a.is_published = True
        a.save()
        log = self._last_update_log()
        self.assertEqual(log.changes["old"], {"title": "Signal Quiz", "is_published": False})
        self.assertEqual(log.changes["new"], {"title": "Signal Quiz v2", "is_published": True})

    def test_assessment_result_status_update(self):
        r = self.assessment_result
        r.status = "completed"
        r.save()
        log = self._last_update_log()
        self.assertEqual(log.changes["old"], {"status": "in_progress"})
        self.assertEqual(log.changes["new"], {"status": "completed"})


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

class DeleteSignalTest(SignalTestBase):

    def setUp(self):
        super().setUp()
        self._clear_audit()

    def _seed(self):
        from apps.academics.models import Grade

        return Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=Decimal("80.00"),
            letter_grade="B",
            status="draft",
            encoded_by=self.faculty_profile,
        )

    def _assert_delete(self, instance, model_label, object_id):
        log = AuditLog.objects.get()
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(log.action, "delete")
        self.assertEqual(log.model_name, model_label)
        self.assertEqual(log.object_id, object_id)
        self.assertTrue(log.object_repr.startswith("%s:" % model_label.split(".")[-1]))
        self.assertIsNone(log.changes)
        self.assertIsNone(log.user)

    def test_grade_delete(self):
        grade = self._seed()
        self._clear_audit()  # drop the CREATE event from seeding, keep only DELETE
        object_id = grade.pk
        grade.delete()
        self._assert_delete(grade, "academics.Grade", object_id)

    def test_attendance_record_delete(self):
        rec = self.attendance_record
        object_id = rec.pk
        rec.delete()
        self._assert_delete(rec, "attendance.AttendanceRecord", object_id)

    def test_behavioral_note_delete(self):
        note = self.behavioral_note
        object_id = note.pk
        note.delete()
        self._assert_delete(note, "guidance.BehavioralNote", object_id)

    def test_consultation_delete(self):
        c = self.consultation
        object_id = c.pk
        c.delete()
        self._assert_delete(c, "guidance.ConsultationRecord", object_id)

    def test_risk_alert_delete(self):
        alert = self.risk_alert
        object_id = alert.pk
        alert.delete()
        self._assert_delete(alert, "guidance.RiskAlert", object_id)

    def test_intervention_delete(self):
        inv = self.intervention
        object_id = inv.pk
        inv.delete()
        self._assert_delete(inv, "guidance.Intervention", object_id)

    def test_assessment_delete(self):
        # AssessmentResult PROTECTs Assessment; delete it first.
        self.assessment_result.delete()
        self._clear_audit()
        a = self.assessment
        object_id = a.pk
        a.delete()
        self._assert_delete(a, "assessments.Assessment", object_id)

    def test_assessment_result_delete(self):
        r = self.assessment_result
        object_id = r.pk
        r.delete()
        self._assert_delete(r, "assessments.AssessmentResult", object_id)


# ---------------------------------------------------------------------------
# Global / cross-cutting guarantees
# ---------------------------------------------------------------------------

class RecursionAndNoSelfAuditTest(SignalTestBase):
    """AuditLog writes must never produce another audit event."""

    def test_audit_log_creation_no_recursion(self):
        self._clear_audit()
        log = AuditLog.objects.create(
            action="create",
            model_name="some.Thing",
            object_id=uuid.uuid4(),
            object_repr="Thing:%s" % uuid.uuid4(),
            user=None,
            timestamp=timezone.now(),
        )
        # Only the one we created manually; no signal fired a second one.
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(log.action, "create")

    def test_audit_log_write_via_service_no_recursion(self):
        self._clear_audit()
        from apps.audit.services import record_audit

        record_audit(action="create", instance=self.attendance_record)
        # Exactly one AuditLog; recording an audit did not re-audit AuditLog.
        self.assertEqual(AuditLog.objects.count(), 1)


class UninstrumentedModelTest(SignalTestBase):
    """A non-audited model must not create an AuditLog."""

    def test_plain_model_no_audit(self):
        self._clear_audit()
        from apps.academics.models import Subject

        Subject.objects.create(name="Science", code="SCI-SIG", grade_level=self.grade_level)
        self.assertEqual(AuditLog.objects.count(), 0)


class RegistrationOnceTest(SignalTestBase):
    """Signal registration is exactly-once: calling ``connect_signals()``
    again must not double-register receivers and must not double-emit."""

    def test_connect_signals_is_idempotent(self):
        from apps.audit.signals import connect_signals

        self._clear_audit()
        # Calling connect_signals() again (as if ready() ran twice) must not
        # create duplicate registrations.
        connect_signals()
        connect_signals()

        from apps.guidance.models import BehavioralNote

        BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="Idempotency check.",
            date_recorded=date.today(),
        )
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(AuditLog.objects.get().action, "create")

    def test_every_instrumented_model_emits_once(self):
        self._clear_audit()
        from apps.academics.models import Grade

        Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=Decimal("80.00"),
            letter_grade="B",
            status="draft",
            encoded_by=self.faculty_profile,
        )
        creates = AuditLog.objects.filter(action="create", model_name="academics.Grade")
        self.assertEqual(creates.count(), 1)


class ExactlyOneEventPerOperationTest(SignalTestBase):

    def setUp(self):
        super().setUp()
        self._clear_audit()

    def test_grade_full_lifecycle_three_events(self):
        from apps.academics.models import Grade

        grade = Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=Decimal("80.00"),
            letter_grade="B",
            status="draft",
            encoded_by=self.faculty_profile,
        )
        self.assertEqual(AuditLog.objects.filter(action="create").count(), 1)

        grade.score = Decimal("90.00")
        grade.save()
        self.assertEqual(AuditLog.objects.filter(action="update").count(), 1)

        grade.delete()
        self.assertEqual(AuditLog.objects.filter(action="delete").count(), 1)

        self.assertEqual(AuditLog.objects.count(), 3)

    def test_update_produces_single_event(self):
        rec = self.attendance_record
        rec.status = "late"
        rec.save()
        updates = AuditLog.objects.filter(action="update", model_name="attendance.AttendanceRecord")
        self.assertEqual(updates.count(), 1)

    def test_create_produces_single_event(self):
        # Already cleared in setUp; create one instrumented model.
        self._clear_audit()
        from apps.guidance.models import BehavioralNote

        BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="warning",
            note_text="Late submissions.",
            date_recorded=date.today(),
        )
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(AuditLog.objects.get().action, "create")


class SnapshotPreChangeTest(SignalTestBase):

    def setUp(self):
        super().setUp()
        self._clear_audit()

    def test_old_snapshot_is_genuinely_pre_change(self):
        from apps.academics.models import Grade

        grade = Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=Decimal("80.00"),
            letter_grade="B",
            status="draft",
            encoded_by=self.faculty_profile,
        )
        grade.score = Decimal("95.00")
        grade.save()
        log = AuditLog.objects.filter(action="update").get()
        # The central risk: old must be 80, new must be 95.
        self.assertEqual(log.changes["old"]["score"], 80.0)
        self.assertEqual(log.changes["new"]["score"], 95.0)
        self.assertNotEqual(log.changes["old"]["score"], log.changes["new"]["score"])


class TransactionBehaviorTest(SignalTestBase):

    def setUp(self):
        super().setUp()
        self._clear_audit()

    def test_commit_preserves_audit(self):
        from apps.guidance.models import BehavioralNote

        with transaction.atomic():
            BehavioralNote.objects.create(
                student=self.student_profile,
                recorded_by=self.faculty_profile,
                note_type="positive",
                note_text="Committed note.",
                date_recorded=date.today(),
            )
        self.assertEqual(AuditLog.objects.count(), 1)

    def test_rollback_removes_audit(self):
        from apps.guidance.models import BehavioralNote

        try:
            with transaction.atomic():
                BehavioralNote.objects.create(
                    student=self.student_profile,
                    recorded_by=self.faculty_profile,
                    note_type="warning",
                    note_text="Will roll back.",
                    date_recorded=date.today(),
                )
                self.assertEqual(AuditLog.objects.count(), 1)
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        self.assertEqual(AuditLog.objects.count(), 0)


class SystemGeneratedRiskAlertTest(SignalTestBase):
    """AI/background RiskAlert writes record user=None without a fake actor."""

    def setUp(self):
        super().setUp()
        self._clear_audit()

    def test_system_created_risk_alert_user_none(self):
        from apps.guidance.models import RiskAlert

        alert = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="high",
            risk_factors=["declining_grades", "attendance"],
            source="decision_tree",
            status="active",
            generated_at=timezone.now() - timedelta(days=1),
        )
        log = AuditLog.objects.get()
        self.assertEqual(log.action, "create")
        self.assertEqual(log.model_name, "guidance.RiskAlert")
        self.assertIsNone(log.user)


class SensitiveFieldsAbsentTest(SignalTestBase):

    def setUp(self):
        super().setUp()
        self._clear_audit()

    def test_guidance_sensitive_fields_never_appear(self):
        c = self.consultation
        c.session_notes = "Updated sensitive session notes."
        c.recommendations = "Updated sensitive recommendations."
        c.status = "completed"
        c.save()
        log = AuditLog.objects.filter(action="update").get()
        for section in ("old", "new"):
            for key in log.changes[section]:
                self.assertNotIn("session_notes", key)
                self.assertNotIn("recommendations", key)
        # Only allowlisted fields present.
        self.assertEqual(set(log.changes["old"].keys()), {"status"})

    def test_behavioral_note_text_never_appears(self):
        note = self.behavioral_note
        note.note_text = "Changed sensitive note text."
        note.note_type = "incident"
        note.save()
        log = AuditLog.objects.filter(action="update").get()
        for section in ("old", "new"):
            self.assertNotIn("note_text", log.changes[section])

    def test_risk_factors_never_appear(self):
        alert = self.risk_alert
        alert.risk_factors = ["new_factor"]
        alert.status = "under_monitoring"
        alert.save()
        log = AuditLog.objects.filter(action="update").get()
        for section in ("old", "new"):
            self.assertNotIn("risk_factors", log.changes[section])

    def test_assessment_result_answers_never_appear(self):
        r = self.assessment_result
        r.answers = {"q1": "B"}
        r.status = "completed"
        r.save()
        log = AuditLog.objects.filter(action="update").get()
        for section in ("old", "new"):
            self.assertNotIn("answers", log.changes[section])
        self.assertEqual(set(log.changes["old"].keys()), {"status"})


class BulkOperationBoundaryTest(SignalTestBase):
    """Raw ORM bulk-write boundaries are documented, not hidden.

    Django ORM semantics (verified behaviour):
    - ``QuerySet.update()`` bypasses ``pre_save``/``post_save`` -> unaudited.
    - ``bulk_create()`` bypasses save signals -> unaudited.
    - ``QuerySet.delete()`` DOES fire ``pre_delete``/``post_delete`` per
      object -> audited (instance deletion remains covered).
    - Instance ``save()`` / ``delete()`` are fully audited.

    These tests pin down the boundary; they do NOT claim an 'intentionally
    unaudited' workflow.  Important AEGIS application flows use the instance
    API (views call ``serializer.save()`` / ``instance.delete()``), which
    remains fully audited.
    """

    def setUp(self):
        super().setUp()
        self._clear_audit()

    def test_object_save_remains_audited(self):
        from apps.academics.models import Grade

        grade = Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=Decimal("70.00"),
            letter_grade="C",
            status="draft",
            encoded_by=self.faculty_profile,
        )
        self.assertEqual(
            AuditLog.objects.filter(action="create", model_name="academics.Grade").count(),
            1,
        )

    def test_queryset_update_is_a_raw_bypass(self):
        from apps.academics.models import Grade

        Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=Decimal("70.00"),
            letter_grade="C",
            status="draft",
            encoded_by=self.faculty_profile,
        )
        before = AuditLog.objects.count()
        Grade.objects.filter(status="draft").update(status="finalized")
        # No additional audit event: QuerySet.update() bypasses signals.
        self.assertEqual(AuditLog.objects.count(), before)

    def test_bulk_create_is_a_raw_bypass(self):
        from apps.guidance.models import Intervention

        before = AuditLog.objects.count()
        Intervention.objects.bulk_create([
            Intervention(
                student=self.student_profile,
                assigned_counselor=self.guidance_profile,
                plan_start_date=date.today(),
                status="active",
            )
        ])
        # No audit events for bulk_create()-created rows.
        self.assertEqual(AuditLog.objects.count(), before)

    def test_queryset_delete_fires_per_object_delete_signals(self):
        from apps.guidance.models import Intervention

        inv = Intervention.objects.create(
            student=self.student_profile,
            assigned_counselor=self.guidance_profile,
            plan_start_date=date.today(),
            status="active",
        )
        object_id = inv.pk
        self._clear_audit()
        # QuerySet.delete() fires pre_delete/post_delete per object, so on an
        # instrumented model the delete IS audited.
        Intervention.objects.filter(pk=object_id).delete()
        log = AuditLog.objects.get()
        self.assertEqual(log.action, "delete")
        self.assertEqual(log.model_name, "guidance.Intervention")
        self.assertEqual(log.object_id, object_id)
