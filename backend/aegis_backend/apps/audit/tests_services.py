"""
Phase 10.4 test suite — Central Audit Service.

Covers the canonical ``record_audit`` entry point: action validation,
object/metadata resolution, safe object_repr, changes integration
through PH10.2 + PH10.3, actor and request-metadata preservation,
transaction behavior, immutability of source instances, and exact
one-record-per-invocation semantics.
"""

import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from decimal import Decimal

from apps.audit.diff import compute_diff
from apps.audit.models import AuditLog
from apps.audit.redact import safe_serialize_fields, get_allowed_fields
from apps.audit.services import (
    AUTH_EVENT_MODEL_NAME,
    InvalidActionError,
    MissingActionError,
    TargetConfigurationError,
    record_audit,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared fixtures (mirrors PH10.2 / PH10.3 scaffolding)
# ---------------------------------------------------------------------------

class PH10_4TestBase(TestCase):
    """Minimal shared fixtures for all PH10.4 service tests."""

    def setUp(self):
        today = date.today()
        past = today - timedelta(days=60)

        self.faculty_user = User.objects.create_user(
            email="faculty-service@example.com",
            password="pass12345",
            first_name="Fac",
            last_name="ulty",
            role="faculty",
        )
        self.student_user = User.objects.create_user(
            email="student-service@example.com",
            password="pass12345",
            first_name="Stu",
            last_name="Dent",
            role="student",
        )

        from apps.accounts.models import FacultyProfile, StudentProfile

        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user,
            employee_id="FAC-SVC-001",
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="STU-SVC-001",
            enrollment_date=past,
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
            name="AY-SVC-2025-2026",
            start_date=date(2025, 6, 1),
            end_date=date(2026, 5, 31),
            is_current=True,
        )
        self.grade_level = GradeLevel.objects.create(
            name="Grade 7",
            level_number=7,
        )
        self.section = Section.objects.create(
            name="ServiceSection",
            grade_level=self.grade_level,
            academic_year=self.academic_year,
        )
        self.subject = Subject.objects.create(
            name="Math",
            code="MATH-SVC",
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

        self.grade = Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=Decimal("80.00"),
            letter_grade="B",
            status="draft",
            encoded_by=self.faculty_profile,
        )

        self._Grade = Grade

        # PH10.5: the Grade fixture above legitimately fires the model-signal
        # audit receiver, producing one CREATE audit record.  The PH10.4
        # service-level assertions assume an empty audit table at test start,
        # so clear any signal-derived records from fixture setup here.
        AuditLog.objects.all().delete()


# ---------------------------------------------------------------------------
# 1-2. CREATE with / without user
# ---------------------------------------------------------------------------

class CreateAuditTest(PH10_4TestBase):

    def test_create_with_user(self):
        log = record_audit(
            action=AuditLog.Action.CREATE,
            instance=self.grade,
            user=self.faculty_user,
        )
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(log.action, "create")
        self.assertEqual(log.model_name, "academics.Grade")
        self.assertEqual(log.object_id, self.grade.pk)
        self.assertEqual(log.object_repr, "Grade:%s" % self.grade.pk)
        self.assertEqual(log.user, self.faculty_user)
        self.assertIsNone(log.changes)

    def test_create_with_none_user(self):
        log = record_audit(
            action="create",
            instance=self.grade,
            user=None,
        )
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(log.action, "create")
        self.assertIsNone(log.user)
        self.assertEqual(log.model_name, "academics.Grade")

    def test_create_with_none_user_omitted(self):
        log = record_audit(action="create", instance=self.grade)
        self.assertIsNone(log.user)

    def test_create_does_not_accept_changes_kwarg(self):
        with self.assertRaises(TypeError):
            record_audit(
                action="create",
                instance=self.grade,
                changes={"old": {}, "new": {}},
            )


# ---------------------------------------------------------------------------
# 3-5. UPDATE: safe diff, unchanged omitted, sensitive absent
# ---------------------------------------------------------------------------

class UpdateAuditTest(PH10_4TestBase):

    def _updated_grade(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(status="finalized")
        return self._Grade.objects.get(pk=self.grade.pk)

    def test_update_generates_safe_diff(self):
        new_grade = self._updated_grade()
        log = record_audit(
            action=AuditLog.Action.UPDATE,
            old_instance=self.grade,
            new_instance=new_grade,
            user=self.faculty_user,
        )
        self.assertEqual(log.action, "update")
        expected = compute_diff(self.grade, new_grade)
        self.assertEqual(log.changes, expected)
        self.assertEqual(log.changes, {
            "old": {"status": "draft"},
            "new": {"status": "finalized"},
        })

    def test_update_unchanged_allowlisted_fields_omitted(self):
        new_grade = self._updated_grade()
        record_audit(
            action="update",
            old_instance=self.grade,
            new_instance=new_grade,
        )
        log = AuditLog.objects.get()
        self.assertNotIn("score", log.changes["old"])
        self.assertNotIn("score", log.changes["new"])
        self.assertNotIn("letter_grade", log.changes["old"])
        self.assertNotIn("letter_grade", log.changes["new"])

    def test_sensitive_fields_absent_from_update_diff(self):
        from apps.guidance.models import ConsultationRecord

        from apps.accounts.models import GuidanceProfile

        counselor = User.objects.create_user(
            email="counselor-service@example.com",
            password="pass12345",
            first_name="Cou",
            last_name="nselor",
            role="guidance",
        )
        gp = GuidanceProfile.objects.create(
            user=counselor, employee_id="GDE-SVC-001",
        )
        consultation = ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=gp,
            session_date=date.today() - timedelta(days=30),
            session_time="10:00:00",
            session_type="individual_counseling",
            concern_categories=["academic"],
            session_notes="Sensitive session notes.",
            recommendations="Sensitive recommendations.",
            priority_level="low",
            status="ongoing",
        )
        ConsultationRecord.objects.filter(pk=consultation.pk).update(
            status="completed",
        )
        new_consultation = ConsultationRecord.objects.get(pk=consultation.pk)

        record_audit(
            action="update",
            old_instance=consultation,
            new_instance=new_consultation,
        )
        # PH10.5: the ConsultationRecord fixture above now fires the model
        # signal, so target the UPDATE record under test.
        log = AuditLog.objects.filter(action="update").get()
        self.assertEqual(log.changes["old"], {"status": "ongoing"})
        self.assertEqual(log.changes["new"], {"status": "completed"})
        for section in ("old", "new"):
            for key in log.changes[section]:
                self.assertNotIn("session_notes", key)
                self.assertNotIn("recommendations", key)

    def test_sensitive_fields_never_in_any_changes(self):
        new_grade = self._updated_grade()
        record_audit(
            action="update",
            old_instance=self.grade,
            new_instance=new_grade,
        )
        log = AuditLog.objects.get()
        for section in ("old", "new"):
            for key in log.changes[section]:
                self.assertNotIn("password", key.lower())
                self.assertNotIn("token", key.lower())
                self.assertNotIn("secret", key.lower())
                self.assertNotIn("risk_factors", key)


# ---------------------------------------------------------------------------
# 6. DELETE
# ---------------------------------------------------------------------------

class DeleteAuditTest(PH10_4TestBase):

    def test_delete_supported_target_representation(self):
        log = record_audit(
            action=AuditLog.Action.DELETE,
            instance=self.grade,
            user=self.faculty_user,
        )
        self.assertEqual(log.action, "delete")
        self.assertEqual(log.model_name, "academics.Grade")
        self.assertEqual(log.object_id, self.grade.pk)
        self.assertTrue(log.object_repr.startswith("Grade:"))
        self.assertIsNone(log.changes)

    def test_delete_explicit_metadata_without_instance(self):
        object_id = uuid.uuid4()
        log = record_audit(
            action="delete",
            model_name="guidance.RiskAlert",
            object_id=object_id,
            user=self.faculty_user,
        )
        self.assertEqual(log.model_name, "guidance.RiskAlert")
        self.assertEqual(log.object_id, object_id)
        self.assertEqual(log.object_repr, "RiskAlert:%s" % object_id)
        self.assertIsNone(log.changes)


# ---------------------------------------------------------------------------
# 7-8. LOGIN / LOGOUT authentication events
# ---------------------------------------------------------------------------

class AuthenticationAuditTest(PH10_4TestBase):

    def test_login(self):
        log = record_audit(
            action=AuditLog.Action.LOGIN,
            user=self.faculty_user,
        )
        self.assertEqual(log.action, "login")
        self.assertEqual(log.model_name, AUTH_EVENT_MODEL_NAME)
        self.assertIsNone(log.object_id)
        self.assertEqual(log.object_repr, "Login")
        self.assertIsNone(log.changes)
        self.assertEqual(log.user, self.faculty_user)

    def test_logout(self):
        log = record_audit(
            action=AuditLog.Action.LOGOUT,
            user=self.faculty_user,
        )
        self.assertEqual(log.action, "logout")
        self.assertEqual(log.model_name, AUTH_EVENT_MODEL_NAME)
        self.assertIsNone(log.object_id)
        self.assertEqual(log.object_repr, "Logout")
        self.assertIsNone(log.changes)
        self.assertEqual(log.user, self.faculty_user)

    def test_login_with_none_user_system_event(self):
        log = record_audit(action="login", user=None)
        self.assertIsNone(log.user)
        self.assertEqual(log.object_repr, "Login")

    def test_login_rejects_strange_model_name(self):
        with self.assertRaises(TargetConfigurationError):
            record_audit(action="login", model_name="academics.Grade")

    def test_login_does_not_accept_changes_kwarg(self):
        with self.assertRaises(TypeError):
            record_audit(
                action="login",
                changes={"old": {}, "new": {}},
            )


# ---------------------------------------------------------------------------
# 9-11. IMPORT / EXPORT / ACCESS
# ---------------------------------------------------------------------------

class EventActionAuditTest(PH10_4TestBase):

    def test_import(self):
        object_id = uuid.uuid4()
        log = record_audit(
            action=AuditLog.Action.IMPORT,
            model_name="data_import.ImportJob",
            object_id=object_id,
            user=self.faculty_user,
        )
        self.assertEqual(log.action, "import")
        self.assertEqual(log.model_name, "data_import.ImportJob")
        self.assertEqual(log.object_id, object_id)
        self.assertEqual(log.object_repr, "ImportJob:%s" % object_id)
        self.assertIsNone(log.changes)

    def test_export(self):
        object_id = uuid.uuid4()
        log = record_audit(
            action=AuditLog.Action.EXPORT,
            model_name="data_import.ImportJob",
            object_id=object_id,
            user=self.faculty_user,
        )
        self.assertEqual(log.action, "export")
        self.assertEqual(log.model_name, "data_import.ImportJob")
        self.assertEqual(log.object_id, object_id)
        self.assertIsNone(log.changes)

    def test_access(self):
        log = record_audit(
            action=AuditLog.Action.ACCESS,
            instance=self.grade,
            user=self.student_user,
        )
        self.assertEqual(log.action, "access")
        self.assertEqual(log.model_name, "academics.Grade")
        self.assertEqual(log.object_id, self.grade.pk)
        self.assertIsNone(log.changes)


# ---------------------------------------------------------------------------
# 12. Invalid action rejection
# ---------------------------------------------------------------------------

class InvalidActionTest(PH10_4TestBase):

    def test_missing_action_rejected(self):
        with self.assertRaises(MissingActionError):
            record_audit(instance=self.grade)

    def test_invalid_action_rejected(self):
        for bad in ("failure", "error", "login_failed", "grade_posted",
                    "risk_generated", "recommendation", "escalation"):
            with self.assertRaises(InvalidActionError):
                record_audit(action=bad, instance=self.grade)

    def test_nonexistent_action_rejected(self):
        with self.assertRaises(InvalidActionError):
            record_audit(action="not_an_action", instance=self.grade)

    def test_invalid_action_creates_no_record(self):
        with self.assertRaises(InvalidActionError):
            record_audit(action="failure", instance=self.grade)
        self.assertEqual(AuditLog.objects.count(), 0)


# ---------------------------------------------------------------------------
# 12b. Caller-supplied raw changes are structurally impossible
# ---------------------------------------------------------------------------

class RawChangesNeverSupportedTest(PH10_4TestBase):
    """The public API accepts NO caller-supplied ``changes`` (Option A).

    ``changes`` is not a keyword of ``record_audit`` any more, so any
    attempt to inject a raw ``{"old": ..., "new": ...}`` payload — even
    one carrying sensitive data — fails with ``TypeError`` before the
    service body runs and no AuditLog row is created.  ``AuditLog.changes``
    is populated exclusively via the PH10.3 ``compute_diff`` utility (which
    serializes through PH10.2 allowlists) for UPDATE events.  "Valid safe
    changes" therefore exist only through that canonical path; there is no
    other route into ``changes``.
    """

    def _assert_changes_kwarg_rejected(self, payload):
        for action in (
            AuditLog.Action.DELETE,
            AuditLog.Action.IMPORT,
            AuditLog.Action.EXPORT,
            AuditLog.Action.ACCESS,
        ):
            with self.assertRaises(TypeError):
                record_audit(
                    action=action,
                    instance=self.grade,
                    object_id=self.grade.pk,
                    changes=payload,
                )
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_raw_changes_with_password_rejected(self):
        self._assert_changes_kwarg_rejected({
            "old": {"password": "hunter2"},
            "new": {"password": "hunter3"},
        })

    def test_raw_changes_with_session_notes_rejected(self):
        self._assert_changes_kwarg_rejected({
            "old": {"session_notes": "Sensitive session notes."},
            "new": {"session_notes": "More sensitive session notes."},
        })

    def test_raw_changes_with_risk_factors_rejected(self):
        self._assert_changes_kwarg_rejected({
            "old": {"risk_factors": ["attendance_pattern"]},
            "new": {"risk_factors": ["declining_grades"]},
        })

    def test_raw_changes_with_assessment_answers_rejected(self):
        self._assert_changes_kwarg_rejected({
            "old": {"answers": {"q1": "A"}},
            "new": {"answers": {"q1": "B"}},
        })

    def test_raw_changes_with_nested_structures_rejected(self):
        self._assert_changes_kwarg_rejected({
            "old": {"profile": {"name": "x", "meta": [1, 2]}},
            "new": {"profile": {"name": "y", "meta": [3, 4]}},
        })

    def test_raw_changes_with_unknown_field_names_rejected(self):
        self._assert_changes_kwarg_rejected({
            "old": {"totally_unknown_field": "value"},
            "new": {"totally_unknown_field": "other"},
        })

    def test_update_also_rejects_changes_kwarg(self):
        with self.assertRaises(TypeError):
            record_audit(
                action="update",
                old_instance=self.grade,
                new_instance=self.grade,
                changes={
                    "old": {"status": "draft"},
                    "new": {"status": "finalized"},
                },
            )

    def test_stored_changes_are_null_for_non_update_actions(self):
        for action in (
            AuditLog.Action.DELETE,
            AuditLog.Action.IMPORT,
            AuditLog.Action.EXPORT,
            AuditLog.Action.ACCESS,
        ):
            log = record_audit(
                action=action,
                instance=self.grade,
                object_id=self.grade.pk,
            )
            self.assertIsNone(log.changes)

    def test_access_stored_changes_are_null(self):
        log = record_audit(
            action=AuditLog.Action.ACCESS,
            instance=self.grade,
            object_id=self.grade.pk,
        )
        self.assertEqual(log.action, "access")
        self.assertEqual(log.model_name, "academics.Grade")
        self.assertEqual(log.object_id, self.grade.pk)
        self.assertIsNone(log.changes)


# ---------------------------------------------------------------------------
# 13. Unknown / unallowlisted model — safe behavior
# ---------------------------------------------------------------------------

class UnknownModelTest(PH10_4TestBase):

    def test_unknown_model_safe_record(self):
        log = record_audit(
            action=AuditLog.Action.ACCESS,
            instance=self.faculty_user,
        )
        self.assertEqual(log.model_name, "accounts.User")
        self.assertEqual(log.object_repr, "User:%s" % self.faculty_user.pk)
        self.assertIsNone(log.changes)

    def test_unallowlisted_model_update_has_none_changes(self):
        self.faculty_user.first_name = "Renamed"
        record_audit(
            action="update",
            old_instance=self.student_user,
            new_instance=self.faculty_user,
        )
        log = AuditLog.objects.get()
        self.assertIsNone(log.changes)

    def test_unknown_model_no_size_leak(self):
        data = safe_serialize_fields("accounts.User", self.faculty_user)
        self.assertEqual(data, {})
        self.assertTrue(len(self.faculty_user.password) > 0)


# ---------------------------------------------------------------------------
# 14. Mismatched old/new update models → TypeError preserved
# ---------------------------------------------------------------------------

class MismatchedUpdateModelsTest(PH10_4TestBase):

    def test_mismatched_models_raise_type_error(self):
        from apps.assessments.models import Assessment

        assessment = Assessment.objects.create(
            title="Service Exam",
            assessment_type="academic",
            creator_role="faculty",
            created_by=self.faculty_user,
            is_published=False,
        )
        with self.assertRaises(TypeError):
            record_audit(
                action="update",
                old_instance=self.grade,
                new_instance=assessment,
            )

    def test_object_id_mismatch_rejected_clearly(self):
        with self.assertRaises(TargetConfigurationError):
            record_audit(
                action="update",
                old_instance=self.grade,
                new_instance=self.grade,
                object_id=uuid.uuid4(),
            )

    def test_update_without_snapshots_rejected(self):
        with self.assertRaises(ValueError):
            record_audit(action="update", instance=self.grade)


# ---------------------------------------------------------------------------
# 15-17. Request metadata
# ---------------------------------------------------------------------------

class RequestMetadataTest(PH10_4TestBase):

    def test_ip_address_stored(self):
        log = record_audit(
            action="access",
            instance=self.grade,
            user=self.student_user,
            ip_address="192.168.1.100",
        )
        self.assertEqual(log.ip_address, "192.168.1.100")

    def test_user_agent_stored(self):
        log = record_audit(
            action="access",
            instance=self.grade,
            user=self.student_user,
            user_agent="Mozilla/5.0 (Test UA)",
        )
        self.assertEqual(log.user_agent, "Mozilla/5.0 (Test UA)")

    def test_null_request_metadata(self):
        log = record_audit(
            action="access",
            instance=self.grade,
            user=self.student_user,
            ip_address=None,
            user_agent=None,
        )
        self.assertIsNone(log.ip_address)
        self.assertIsNone(log.user_agent)


# ---------------------------------------------------------------------------
# 18-20. Timestamp / object_repr properties
# ---------------------------------------------------------------------------

class RepresentationSafetyTest(PH10_4TestBase):

    def test_timestamp_is_timezone_aware(self):
        log = record_audit(action="access", instance=self.grade)
        self.assertTrue(timezone.is_aware(log.timestamp))
        self.assertTrue(timezone.is_naive(timezone.now()) is False)

    def test_object_repr_not_over_255(self):
        for action in (AuditLog.Action.CREATE, AuditLog.Action.DELETE,
                       AuditLog.Action.ACCESS):
            log = record_audit(action=action, instance=self.grade)
            self.assertLessEqual(len(log.object_repr), 255)

    def test_object_repr_cannot_exceed_255(self):
        overlong = "X" * 256
        with self.assertRaises(TargetConfigurationError):
            record_audit(
                action="import",
                model_name="data_import.ImportJob",
                object_id=uuid.uuid4(),
                object_repr=overlong,
            )

    def test_object_repr_has_no_user_pii(self):
        log = record_audit(action="access", instance=self.grade)
        self.assertNotIn("student", log.object_repr)
        self.assertNotIn("Fac", log.object_repr)
        self.assertNotIn("ulty", log.object_repr)
        self.assertNotIn("MATH", log.object_repr)


# ---------------------------------------------------------------------------
# 21. Source instances are not mutated
# ---------------------------------------------------------------------------

class NoMutationTest(PH10_4TestBase):

    def test_service_does_not_mutate_sources(self):
        old_score = self.grade.score
        old_status = self.grade.status

        self._Grade.objects.filter(pk=self.grade.pk).update(
            score=Decimal("95.00"), status="finalized",
        )
        new_grade = self._Grade.objects.get(pk=self.grade.pk)
        new_score = new_grade.score
        new_status = new_grade.status

        record_audit(
            action="update",
            old_instance=self.grade,
            new_instance=new_grade,
        )

        self.assertEqual(self.grade.score, old_score)
        self.assertEqual(self.grade.status, old_status)
        self.assertEqual(new_grade.score, new_score)
        self.assertEqual(new_grade.status, new_status)


# ---------------------------------------------------------------------------
# 22. Exactly one AuditLog per invocation
# ---------------------------------------------------------------------------

class SingleRecordTest(PH10_4TestBase):

    def test_one_invocation_one_record(self):
        record_audit(action="create", instance=self.grade)
        record_audit(action="access", instance=self.grade)
        self.assertEqual(AuditLog.objects.count(), 2)

    def test_repeated_invocations_create_separate_records(self):
        record_audit(action="create", instance=self.grade)
        record_audit(action="create", instance=self.grade)
        self.assertEqual(AuditLog.objects.count(), 2)


# ---------------------------------------------------------------------------
# 23-24. Transaction behavior
# ---------------------------------------------------------------------------

class TransactionBehaviorTest(PH10_4TestBase):

    def test_rollback_removes_audit_record(self):
        try:
            with transaction.atomic():
                record_audit(
                    action="create",
                    instance=self.grade,
                    user=self.faculty_user,
                )
                self.assertEqual(AuditLog.objects.count(), 1)
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_commit_persists_audit_record(self):
        with transaction.atomic():
            record_audit(
                action="create",
                instance=self.grade,
                user=self.faculty_user,
            )
        self.assertEqual(AuditLog.objects.count(), 1)


# ---------------------------------------------------------------------------
# 25-26. PH10.2 / PH10.3 compatibility intact
# ---------------------------------------------------------------------------

class CompatibilityTest(PH10_4TestBase):

    def test_ph10_2_allowlist_intact(self):
        self.assertEqual(
            get_allowed_fields("academics.Grade"),
            ("score", "letter_grade", "status"),
        )
        data = safe_serialize_fields("academics.Grade", self.grade)
        self.assertEqual(set(data.keys()), {"score", "letter_grade", "status"})

    def test_ph10_3_diff_uses_same_allowlist(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(status="finalized")
        new_grade = self._Grade.objects.get(pk=self.grade.pk)
        changes = compute_diff(self.grade, new_grade)
        self.assertEqual(changes, {
            "old": {"status": "draft"},
            "new": {"status": "finalized"},
        })

    def test_service_changes_match_ph10_3(self):
        self._Grade.objects.filter(pk=self.grade.pk).update(status="finalized")
        new_grade = self._Grade.objects.get(pk=self.grade.pk)
        log = record_audit(
            action="update",
            old_instance=self.grade,
            new_instance=new_grade,
        )
        self.assertEqual(log.changes, compute_diff(self.grade, new_grade))