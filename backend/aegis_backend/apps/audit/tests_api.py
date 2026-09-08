"""
Phase 10.10 test suite — Read-only admin AuditLog API.

Verifies the read-only administrator audit API:

    GET /api/v1/audit/logs/
    GET /api/v1/audit/logs/{id}/

Coverage groups
---------------
AUTHORIZATION:
  1. Admin can list logs.
  2. Admin can retrieve log.
  3. Faculty cannot list.
  4. Faculty cannot retrieve.
  5. Guidance cannot list.
  6. Student cannot list.
  7. Parent cannot list.
  8. Anonymous cannot list.

READ-ONLY:
  9. POST rejected.
 10. PUT rejected.
 11. PATCH rejected.
 12. DELETE rejected.

LIST:
 13. List response is paginated.
 14. Newest records appear first.
 15. Deterministic tie-breaking works.
 16. Action filter works.
 17. Model_name filter works.
 18. User filter works.
 19. Object_id filter works.
 20. Timestamp range filtering works.

DETAIL:
 21. Valid ID returns correct record.
 22. Invalid ID returns 404.
 23. Deleted target's AuditLog can still be retrieved.

PRIVACY:
 24. Password data is absent.
 25. Tokens are absent.
 26. Authorization header is absent.
 27. Counseling/session note data is absent.
 28. Risk_factors are absent.
 29. Assessment answers are absent.
 30. Raw file/import/export contents are absent.

DATA INTEGRITY:
 31. AuditLog records are unchanged by GET.
 32. Changes are returned exactly as stored.
 33. NULL user handled correctly.
 34. NULL object_id handled correctly.
 35. Safe object_repr returned correctly.

QUERY PERFORMANCE:
 36. List does not cause obvious N+1 user queries.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import (
    FacultyProfile,
    GuidanceProfile,
    ParentProfile,
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
from apps.assessments.models import Assessment, AssessmentQuestion, AssessmentResult
from apps.audit.models import AuditLog
from apps.audit.services import record_audit
from apps.guidance.models import ConsultationRecord, RiskAlert

User = get_user_model()

URL_LIST = "/api/v1/audit/logs/"

#: Sensitive-content markers that must never appear in an API response.
MARKER_SESSION_NOTES = "TOP-SECRET-SESSION-NOTES"
MARKER_RECOMMENDATION = "TOP-SECRET-RECOMMENDATION"
MARKER_RISK_FACTOR = "top-secret-risk-factor-tag"
MARKER_ANSWER = "TOP-SECRET-ASSESSMENT-ANSWER"
MARKER_AUTHZ_HEADER = "Bearer TOP-SECRET-AUTHZ-HEADER-VALUE"
MARKER_FILE_CONTENT = "BASE64-RAW-IMPORT-EXPORT-BLOB-CONTENTS"

_GRADE_ID = uuid.UUID("00000000-0000-4000-8000-00000000000a")
_GRADE_ID2 = uuid.UUID("00000000-0000-4000-8000-00000000000b")


def _clear_audit():
    AuditLog.objects.all().delete()


class AuditApiTestBase(TestCase):
    """Shared users, profiles, and a minimal valid domain graph."""

    def setUp(self):
        self.client = APIClient()
        self.password = "auditapi-pass123"

        self.admin_user = User.objects.create_user(
            email="audit-admin@test.com", password=self.password,
            first_name="Ad", last_name="Min", role="admin",
        )
        self.faculty_user = User.objects.create_user(
            email="audit-faculty@test.com", password=self.password,
            first_name="Fac", last_name="ulty", role="faculty",
        )
        self.guidance_user = User.objects.create_user(
            email="audit-guid@test.com", password=self.password,
            first_name="Guid", last_name="ance", role="guidance",
        )
        self.student_user = User.objects.create_user(
            email="audit-student@test.com", password=self.password,
            first_name="Stu", last_name="dent", role="student",
        )
        self.parent_user = User.objects.create_user(
            email="audit-parent@test.com", password=self.password,
            first_name="Par", last_name="ent", role="parent",
        )

        self.ay = AcademicYear.objects.create(
            name="2025-2026", start_date="2025-06-01",
            end_date="2026-03-31", is_current=True,
        )
        self.grade_level = GradeLevel.objects.create(
            name="Grade 7", level_number=7,
        )
        self.section = Section.objects.create(
            name="AuditApiSection", grade_level=self.grade_level,
            academic_year=self.ay,
        )
        self.subject = Subject.objects.create(
            name="Math", code="MATH-API", grade_level=self.grade_level,
        )
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="EMP-API-001",
        )
        self.guidance_profile = GuidanceProfile.objects.create(
            user=self.guidance_user, employee_id="EMP-API-002",
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user, student_id="STU-API-001",
            enrollment_date="2025-06-01", section=self.section,
            grade_level=self.grade_level, is_active=True,
        )
        self.parent_profile = ParentProfile.objects.create(
            user=self.parent_user, relationship_to_student="mother",
        )
        Enrollment.objects.create(
            student=self.student_profile, section=self.section,
            academic_year=self.ay, date_enrolled="2025-06-01",
        )
        self.subject_assignment = SubjectAssignment.objects.create(
            subject=self.subject,
            faculty=self.faculty_profile,
            section=self.section,
            academic_year=self.ay,
        )
        self.grading_period = GradingPeriod.objects.create(
            academic_year=self.ay, name="Q1", order=1,
            start_date="2025-06-01", end_date="2025-08-31",
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
        self.consultation = ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=timezone.localdate(),
            session_time=timezone.now().time(),
            session_type="individual_counseling",
            concern_categories=["academic"],
            session_notes=MARKER_SESSION_NOTES,
            recommendations=MARKER_RECOMMENDATION,
            priority_level="low",
            status="ongoing",
        )
        self.alert = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="low",
            risk_factors=[MARKER_RISK_FACTOR],
            status="active",
            generated_at=timezone.now(),
        )
        self.assessment = Assessment.objects.create(
            title="API Academic Check",
            assessment_type="academic",
            created_by=self.faculty_user,
            is_published=True,
        )
        self.question = AssessmentQuestion.objects.create(
            assessment=self.assessment,
            question_text="Scenario?",
            question_type="essay",
            order=1,
        )
        self.result = AssessmentResult.objects.create(
            assessment=self.assessment,
            student=self.student_profile,
            answers={str(self.question.id): MARKER_ANSWER},
            status="completed",
        )

        # The fixtures above legitimately fire the PH10.5 signal receivers.
        # Clear the signal-derived rows so tests control the audit table.
        _clear_audit()

    def _make_log(
        self,
        *,
        user=None,
        action="create",
        model_name="academics.Grade",
        object_id=None,
        object_repr=None,
        changes=None,
        ip_address=None,
        user_agent=None,
        timestamp=None,
        log_id=None,
    ):
        """Create one AuditLog row directly for the scenario under test."""
        if object_id is None:
            object_id = uuid.uuid4()
        if object_repr is None:
            object_repr = f"{model_name.split('.')[-1]}:{object_id}"[:255]
        return AuditLog.objects.create(
            id=log_id if log_id is not None else uuid.uuid4(),
            user=user,
            action=action,
            model_name=model_name,
            object_id=object_id,
            object_repr=object_repr,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=timestamp or timezone.now(),
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _data_url(self, log):
        return f"{URL_LIST}{log.id}/"


# ---------------------------------------------------------------------------
# AUTHORIZATION (1-8)
# ---------------------------------------------------------------------------


class AuthorizationTests(AuditApiTestBase):

    def test_admin_can_list_logs(self):
        self._make_log(user=self.admin_user)
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 1)

    def test_admin_can_retrieve_log(self):
        log = self._make_log(user=self.admin_user)
        self._auth(self.admin_user)
        response = self.client.get(self._data_url(log))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["id"], str(log.id))

    def test_faculty_cannot_list(self):
        self._make_log()
        self._auth(self.faculty_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_faculty_cannot_retrieve(self):
        log = self._make_log()
        self._auth(self.faculty_user)
        response = self.client.get(self._data_url(log))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_guidance_cannot_list(self):
        self._make_log()
        self._auth(self.guidance_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_list(self):
        self._make_log()
        self._auth(self.student_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_parent_cannot_list(self):
        self._make_log()
        self._auth(self.parent_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_list(self):
        self._make_log()
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# READ-ONLY (9-12)
# ---------------------------------------------------------------------------


class ReadOnlyTests(AuditApiTestBase):

    def test_post_rejected(self):
        self._auth(self.admin_user)
        response = self.client.post(URL_LIST, {"action": "create"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_put_rejected(self):
        log = self._make_log(user=self.admin_user)
        count = AuditLog.objects.count()
        self._auth(self.admin_user)
        response = self.client.put(
            self._data_url(log), {"action": "delete"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(AuditLog.objects.count(), count)
        AuditLog.objects.get(pk=log.pk)

    def test_patch_rejected(self):
        log = self._make_log(user=self.admin_user)
        count = AuditLog.objects.count()
        self._auth(self.admin_user)
        response = self.client.patch(
            self._data_url(log), {"action": "delete"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(AuditLog.objects.count(), count)
        self.assertEqual(AuditLog.objects.get(pk=log.pk).action, log.action)

    def test_delete_rejected(self):
        log = self._make_log(user=self.admin_user)
        count = AuditLog.objects.count()
        self._auth(self.admin_user)
        response = self.client.delete(self._data_url(log))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(AuditLog.objects.count(), count)
        AuditLog.objects.get(pk=log.pk)


# ---------------------------------------------------------------------------
# LIST (13-20)
# ---------------------------------------------------------------------------


class ListTests(AuditApiTestBase):

    def test_list_response_is_paginated(self):
        for _ in range(3):
            self._make_log(user=self.admin_user)
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("next", data)
        self.assertIn("previous", data)
        self.assertIn("results", data)
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["results"]), 3)

    def test_newest_records_first(self):
        base = timezone.now()
        old = self._make_log(timestamp=base - timedelta(minutes=20))
        mid = self._make_log(timestamp=base - timedelta(minutes=10))
        new = self._make_log(timestamp=base)
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.json()["results"]]
        self.assertEqual(ids, [str(new.id), str(mid.id), str(old.id)])

    def test_deterministic_tie_breaking(self):
        now = timezone.now()
        small = self._make_log(
            timestamp=now, log_id=_GRADE_ID, user=self.faculty_user,
        )
        big = self._make_log(
            timestamp=now, log_id=_GRADE_ID2, user=self.faculty_user,
        )
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.json()["results"]]
        self.assertEqual(ids, [str(big.id), str(small.id)])

    def test_action_filter_works(self):
        self._make_log(action="create")
        update_log = self._make_log(action="update", user=self.admin_user)
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST, {"action": "update"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["id"], str(update_log.id))

    def test_model_name_filter_works(self):
        grade_log = self._make_log(model_name="academics.Grade")
        self._make_log(model_name="guidance.RiskAlert")
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST, {"model_name": "academics.Grade"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["id"], str(grade_log.id))

    def test_user_filter_works(self):
        self._make_log(user=self.admin_user, action="create")
        faculty_log = self._make_log(user=self.faculty_user, action="update")
        self._make_log(action="access")
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST, {"user": str(self.faculty_user.pk)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["id"], str(faculty_log.id))
        self.assertEqual(data["results"][0]["user"]["id"], str(self.faculty_user.pk))

    def test_object_id_filter_works(self):
        target_id = uuid.uuid4()
        target_log = self._make_log(object_id=target_id)
        self._make_log(object_id=uuid.uuid4())
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST, {"object_id": str(target_id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["id"], str(target_log.id))

    def test_timestamp_range_filtering_works(self):
        base = timezone.now()
        self._make_log(timestamp=base)
        in_log_1 = self._make_log(timestamp=base + timedelta(minutes=20))
        in_log_2 = self._make_log(timestamp=base + timedelta(minutes=30))
        self._make_log(timestamp=base + timedelta(minutes=40))
        self._auth(self.admin_user)
        start = (base + timedelta(minutes=15)).isoformat()
        end = (base + timedelta(minutes=35)).isoformat()
        response = self.client.get(
            URL_LIST, {"start_time": start, "end_time": end}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 2)
        ids = [row["id"] for row in data["results"]]
        self.assertEqual(ids, [str(in_log_2.id), str(in_log_1.id)])


# ---------------------------------------------------------------------------
# DETAIL (21-23)
# ---------------------------------------------------------------------------


class DetailTests(AuditApiTestBase):

    def test_valid_id_returns_correct_record(self):
        timestamp = timezone.now()
        log = self._make_log(
            user=self.faculty_user,
            action="update",
            model_name="academics.Grade",
            object_id=self.grade.pk,
            object_repr=f"Grade:{self.grade.pk}",
            changes={"old": {"status": "draft"}, "new": {"status": "finalized"}},
            ip_address="203.0.113.50",
            user_agent="ApiSpec-UA/1.0",
            timestamp=timestamp,
        )
        self._auth(self.admin_user)
        response = self.client.get(self._data_url(log))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["id"], str(log.id))
        self.assertEqual(data["user"], {
            "id": str(self.faculty_user.pk), "name": "Fac ulty",
        })
        self.assertEqual(data["action"], "update")
        self.assertEqual(data["model_name"], "academics.Grade")
        self.assertEqual(data["object_id"], str(self.grade.pk))
        self.assertEqual(data["object_repr"], f"Grade:{self.grade.pk}")
        self.assertEqual(data["changes"], {
            "old": {"status": "draft"}, "new": {"status": "finalized"},
        })
        self.assertEqual(data["ip_address"], "203.0.113.50")
        self.assertEqual(data["user_agent"], "ApiSpec-UA/1.0")
        self.assertEqual(datetime.fromisoformat(data["timestamp"]), timestamp)

    def test_invalid_id_returns_404(self):
        self._auth(self.admin_user)
        missing = self.client.get(f"{URL_LIST}{uuid.uuid4()}/")
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)
        malformed = self.client.get(f"{URL_LIST}not-a-uuid/")
        self.assertEqual(malformed.status_code, status.HTTP_404_NOT_FOUND)

    def test_deleted_target_audit_log_still_readable(self):
        grade_id = self.grade.pk
        log = record_audit(
            action="create", instance=self.grade, user=self.faculty_user,
        )
        self.grade.delete()
        self.assertFalse(
            Grade.objects.filter(pk=grade_id).exists(),
            "test fixture: the audit target must actually be gone",
        )
        self._auth(self.admin_user)
        response = self.client.get(self._data_url(log))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["id"], str(log.id))
        self.assertEqual(data["object_id"], str(grade_id))
        self.assertEqual(data["object_repr"], f"Grade:{grade_id}")


# ---------------------------------------------------------------------------
# PRIVACY (24-30)
# ---------------------------------------------------------------------------


class PrivacyTests(AuditApiTestBase):

    def _all_rows(self, changes=None, user=None):
        """Create a mix of realistic logs then return the list text."""
        self._make_log(user=user or self.admin_user, action="create")
        self._make_log(user=user or self.faculty_user, action="update",
                       changes=changes)
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.content.decode("utf-8")

    def test_password_data_is_absent(self):
        blob = self._all_rows()
        self.assertNotIn(self.password, blob)
        self.assertNotIn(self.admin_user.password, blob)
        self.assertNotIn(self.faculty_user.password, blob)
        json_data = self.client.get(URL_LIST).json()
        for row in json_data["results"]:
            self.assertNotIn("password", str(row))

    def test_tokens_are_absent(self):
        refresh = RefreshToken.for_user(self.admin_user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        self._make_log(user=self.admin_user)
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        blob = response.content.decode("utf-8")
        self.assertNotIn(access_token, blob)
        self.assertNotIn(refresh_token, blob)
        self.assertNotIn("access_token", blob.lower())
        self.assertNotIn("refresh_token", blob.lower())

    def test_authorization_header_is_absent(self):
        self._make_log(user=self.admin_user)
        self._auth(self.admin_user)
        response = self.client.get(
            URL_LIST, HTTP_AUTHORIZATION=MARKER_AUTHZ_HEADER
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(MARKER_AUTHZ_HEADER, response.content.decode("utf-8"))

    def test_counseling_session_note_data_is_absent(self):
        ConsultationRecord.objects.filter(pk=self.consultation.pk).update(
            status="completed",
        )
        new_consultation = ConsultationRecord.objects.get(pk=self.consultation.pk)
        log = record_audit(
            action="update",
            old_instance=self.consultation,
            new_instance=new_consultation,
            user=self.guidance_user,
        )
        self.assertEqual(log.changes, {
            "old": {"status": "ongoing"},
            "new": {"status": "completed"},
        })
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        blob = response.content.decode("utf-8")
        self.assertNotIn(MARKER_SESSION_NOTES, blob)
        self.assertNotIn(MARKER_RECOMMENDATION, blob)
        self.assertNotIn("session_notes", blob)
        self.assertNotIn("recommendations", blob)

    def test_risk_factors_are_absent(self):
        RiskAlert.objects.filter(pk=self.alert.pk).update(
            status="under_monitoring",
        )
        new_alert = RiskAlert.objects.get(pk=self.alert.pk)
        record_audit(
            action="update",
            old_instance=self.alert,
            new_instance=new_alert,
            user=self.guidance_user,
        )
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        blob = response.content.decode("utf-8")
        self.assertNotIn(MARKER_RISK_FACTOR, blob)
        self.assertNotIn("risk_factors", blob)

    def test_assessment_answers_are_absent(self):
        AssessmentResult.objects.filter(pk=self.result.pk).update(
            status="in_progress",
        )
        new_result = AssessmentResult.objects.get(pk=self.result.pk)
        record_audit(
            action="update",
            old_instance=self.result,
            new_instance=new_result,
            user=self.faculty_user,
        )
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        blob = response.content.decode("utf-8")
        self.assertNotIn(MARKER_ANSWER, blob)
        self.assertNotIn("answers", blob)

    def test_raw_file_import_export_contents_are_absent(self):
        import_id = uuid.uuid4()
        record_audit(
            action="import",
            model_name="data_import.ImportJob",
            object_id=import_id,
            object_repr=f"ImportJob:{import_id}",
            user=self.admin_user,
        )
        record_audit(
            action="export",
            model_name="academics.Grade",
            object_repr="Export",
            user=self.admin_user,
        )
        self._auth(self.admin_user)
        response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        blob = response.content.decode("utf-8")
        self.assertNotIn(MARKER_FILE_CONTENT, blob)
        data = response.json()
        for row in data["results"]:
            self.assertIsNone(row["changes"])
            self.assertNotIn(MARKER_FILE_CONTENT, str(row))


# ---------------------------------------------------------------------------
# DATA INTEGRITY (31-35)
# ---------------------------------------------------------------------------


class DataIntegrityTests(AuditApiTestBase):

    def test_auditlog_records_unchanged_by_get(self):
        for _ in range(3):
            self._make_log(user=self.admin_user)
        before = list(AuditLog.objects.values().order_by("timestamp", "id"))
        self._auth(self.admin_user)
        self.client.get(URL_LIST)
        for log in AuditLog.objects.all()[:1]:
            self.client.get(self._data_url(log))
        after = list(AuditLog.objects.values().order_by("timestamp", "id"))
        self.assertEqual(before, after)

    def test_changes_returned_exactly_as_stored(self):
        Grade.objects.filter(pk=self.grade.pk).update(status="finalized")
        new_grade = Grade.objects.get(pk=self.grade.pk)
        log = record_audit(
            action="update",
            old_instance=self.grade,
            new_instance=new_grade,
            user=self.faculty_user,
        )
        self.assertIsNotNone(log.changes)
        self._auth(self.admin_user)
        response = self.client.get(self._data_url(log))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["changes"], log.changes)

    def test_null_user_handled_correctly(self):
        log = record_audit(action="create", instance=self.grade)
        self.assertIsNone(log.user)
        self._auth(self.admin_user)
        response = self.client.get(self._data_url(log))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIsNone(data["user"])
        self.assertEqual(data["id"], str(log.id))

    def test_null_object_id_handled_correctly(self):
        log = record_audit(action="login", user=self.admin_user)
        self.assertIsNone(log.object_id)
        self.assertEqual(log.object_repr, "Login")
        self._auth(self.admin_user)
        response = self.client.get(self._data_url(log))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIsNone(data["object_id"])
        self.assertEqual(data["object_repr"], "Login")
        self.assertEqual(data["model_name"], "accounts.Authentication")

    def test_safe_object_repr_returned_correctly(self):
        log = record_audit(action="create", instance=self.grade)
        self._auth(self.admin_user)
        response = self.client.get(self._data_url(log))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["object_repr"], log.object_repr)
        self.assertEqual(data["object_id"], str(self.grade.pk))


# ---------------------------------------------------------------------------
# QUERY PERFORMANCE (36)
# ---------------------------------------------------------------------------


class QueryPerformanceTests(AuditApiTestBase):

    def test_list_does_not_cause_n_plus_one_user_queries(self):
        users = [self.admin_user, self.faculty_user, self.guidance_user,
                 self.student_user, self.parent_user]
        for index in range(10):
            self._make_log(user=users[index % len(users)])
        self._auth(self.admin_user)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(URL_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(captured), 5)
        results = response.json()["results"]
        self.assertEqual(len(results), 10)
        for row in results:
            self.assertIn("user", row)