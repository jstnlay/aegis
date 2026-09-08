"""
PH10.9 — Import / Export audit tests.

Verifies the PH10.9 import/export auditing integration end to end:

    Import/Export operation
        ↓
    PH10.9 hook
        ↓
    PH10.6 context
        ↓
    PH10.4 record_audit()
        ↓
    AuditLog

Coverage groups (per the PH10.9 authorization brief):

IMPORT  (1-11): one event per successful import, actor/IP/user-agent,
        changes NULL, model/object semantics, safe object_repr, no
        successful IMPORT on failure/unauthorized/rollback, one event for
        a multi-row import.
EXPORT  (12-21): one event per successful export, actor/IP/user-agent,
        changes NULL, model/object semantics, safe object_repr, no event
        on failure/unauthorized, one event for a multi-row export.
SECURITY (22-26): file contents, row data, sensitive domain values,
        passwords/tokens/credentials, and the Authorization header are
        never stored.
CONTEXT (27-29): PH10.6 context is used, contexts do not leak, a
        background/system operation uses user=None when appropriate.
DUPLICATION (30-31): one operation creates exactly one event.
COMPATIBILITY (32-33): existing data_import + PH10.4 tests remain green
        (guarded by running those suites separately; here we assert the
        audit integration does not regress the underlying operations).
"""

import io
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.data_import.constants import JobStatus, RecordStatus
from apps.data_import.models import ImportJob

User = get_user_model()

from apps.accounts.models import FacultyProfile, StudentProfile  # noqa: E402
from apps.academics.models import (  # noqa: E402
    AcademicYear,
    Enrollment,
    Grade,
    GradeLevel,
    GradingPeriod,
    Section,
    Subject,
    SubjectAssignment,
)
from apps.attendance.models import AttendanceRecord  # noqa: E402

#: Test IP / UA used to prove PH10.6 context is threaded through.
_TEST_IP = "203.0.113.77"
_TEST_UA = "AegisPH10.9/1.0"


def make_csv(content, name="grades.csv"):
    """Build a SimpleUploadedFile holding CSV bytes."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return SimpleUploadedFile(name, content, content_type="text/csv")


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
        )
    ]
    if log.changes:
        chunks.append(str(log.changes))
    return "\n".join(chunks)


def _build_grade_domain(suffix=""):
    """Build a minimal, valid academic structure for a grade import."""
    ay = AcademicYear.objects.create(
        name=f"2025-2026{suffix}", start_date="2025-06-01",
        end_date="2026-03-31", is_current=True,
    )
    g7 = GradeLevel.objects.create(name=f"Grade 7{suffix}", level_number=7)
    su_user = User.objects.create_user(
        email=f"stu_hop{suffix}@test.com", password="pass12345",
        first_name="Hop", last_name="Grade", role="student",
    )
    sp = StudentProfile.objects.create(
        user=su_user, student_id=f"HOP-001{suffix}", enrollment_date="2025-06-01",
    )
    fp_user = User.objects.create_user(
        email=f"fac_hop{suffix}@test.com", password="pass12345",
        first_name="Fac", last_name="Hop", role="faculty",
    )
    fp = FacultyProfile.objects.create(user=fp_user, employee_id=f"E-HOP{suffix}")
    section = Section.objects.create(
        name=f"HP-7A{suffix}", grade_level=g7, academic_year=ay, adviser=fp,
    )
    subject = Subject.objects.create(name=f"Math{suffix}", code=f"MH{suffix}", grade_level=g7)
    sa = SubjectAssignment.objects.create(subject=subject, faculty=fp, section=section, academic_year=ay)
    gp = GradingPeriod.objects.create(
        academic_year=ay, name=f"Q1{suffix}", order=1,
        start_date="2025-06-01", end_date="2025-08-31",
    )
    Enrollment.objects.create(student=sp, section=section, academic_year=ay, date_enrolled="2025-06-01")
    gp2 = GradingPeriod.objects.create(
        academic_year=ay, name=f"Q2{suffix}", order=2,
        start_date="2025-09-01", end_date="2025-11-30",
    )
    gp3 = GradingPeriod.objects.create(
        academic_year=ay, name=f"Q3{suffix}", order=3,
        start_date="2025-12-01", end_date="2026-02-28",
    )
    return {
        "student_id": f"HOP-001{suffix}",
        "subject_assignment": str(sa.pk),
        "grading_period": str(gp.pk),
        "grading_period2": str(gp2.pk),
        "grading_period3": str(gp3.pk),
        "ay": ay,
        "section_obj": section,
        "faculty_profile": fp,
        "student_profile": sp,
    }


def _build_attendance_domain(suffix=""):
    """Build a minimal, valid attendance structure for an attendance import."""
    ay = AcademicYear.objects.create(
        name=f"2026{suffix}", start_date="2026-01-01",
        end_date="2026-12-31", is_current=True,
    )
    g7 = GradeLevel.objects.create(name=f"Grade 7{suffix}", level_number=7)
    fp_user = User.objects.create_user(
        email=f"fac_att{suffix}@test.com", password="pass12345",
        first_name="Fac", last_name="AttHop", role="faculty",
    )
    fp = FacultyProfile.objects.create(user=fp_user, employee_id=f"E-AT{suffix}")
    section = Section.objects.create(name=f"AH-7A{suffix}", grade_level=g7, academic_year=ay, adviser=fp)
    su_user = User.objects.create_user(
        email=f"stu_att{suffix}@test.com", password="pass12345",
        first_name="Stu", last_name="AttHop", role="student",
    )
    sp = StudentProfile.objects.create(
        user=su_user, student_id=f"ATH-001{suffix}", enrollment_date="2026-01-01",
    )
    Enrollment.objects.create(student=sp, section=section, academic_year=ay, date_enrolled="2026-01-01")
    return {
        "student_id": f"ATH-001{suffix}",
        "section": str(section.pk),
        "section_obj": section,
        "ay": ay,
        "faculty_profile": fp,
        "student_profile": sp,
    }


class ImportExportAuditBase(TestCase):
    """Shared users, auth helper, and clean audit table for the suite."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin_ie@test.com", password="pass12345",
            first_name="Ad", last_name="Min", role="admin",
        )
        self.faculty_user = User.objects.create_user(
            email="faculty_ie@test.com", password="pass12345",
            first_name="Fac", last_name="U", role="faculty",
        )
        self.student_user = User.objects.create_user(
            email="student_ie@test.com", password="pass12345",
            first_name="Stu", last_name="D", role="student",
        )
        self.parent_user = User.objects.create_user(
            email="parent_ie@test.com", password="pass12345",
            first_name="Par", last_name="Ent", role="parent",
        )
        self.client = APIClient()
        _clear_audit()

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _post(self, csv_content, import_type="grades", name="grades.csv", **extra):
        return self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": make_csv(csv_content, name=name), "import_type": import_type},
            format="multipart",
            REMOTE_ADDR=_TEST_IP,
            HTTP_USER_AGENT=_TEST_UA,
            **extra,
        )

    def _get_export(self, path, user, **params):
        self._auth(user)
        return self.client.get(
            path, params,
            REMOTE_ADDR=_TEST_IP,
            HTTP_USER_AGENT=_TEST_UA,
        )

    def _import_logs(self):
        return AuditLog.objects.filter(action="import")

    def _export_logs(self):
        return AuditLog.objects.filter(action="export")


# ---------------------------------------------------------------------------
# IMPORT — successful import semantics
# ---------------------------------------------------------------------------

class ImportSuccessTest(ImportExportAuditBase):
    def setUp(self):
        super().setUp()
        self.dom = _build_grade_domain("is")

    def _valid_csv(self):
        return (
            "student_id,subject_assignment,grading_period,score\n"
            f"{self.dom['student_id']},{self.dom['subject_assignment']},{self.dom['grading_period']},90\n"
        )

    def test_successful_import_creates_exactly_one_import_log(self):
        self._auth(self.admin_user)
        resp = self._post(self._valid_csv())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.COMPLETED)
        logs = self._import_logs()
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs[0].action, "import")

    def test_correct_actor(self):
        self._auth(self.admin_user)
        self._post(self._valid_csv())
        log = self._import_logs().get()
        self.assertEqual(log.user_id, self.admin_user.pk)

    def test_correct_ip(self):
        self._auth(self.admin_user)
        self._post(self._valid_csv())
        log = self._import_logs().get()
        self.assertEqual(log.ip_address, _TEST_IP)

    def test_correct_user_agent(self):
        self._auth(self.admin_user)
        self._post(self._valid_csv())
        log = self._import_logs().get()
        self.assertEqual(log.user_agent, _TEST_UA)

    def test_changes_is_null(self):
        self._auth(self.admin_user)
        self._post(self._valid_csv())
        log = self._import_logs().get()
        self.assertIsNone(log.changes)

    def test_correct_model_and_object_semantics(self):
        self._auth(self.admin_user)
        resp = self._post(self._valid_csv())
        job = ImportJob.objects.get(pk=resp.data["id"])
        log = self._import_logs().get()
        self.assertEqual(log.model_name, "data_import.ImportJob")
        self.assertEqual(log.object_id, job.id)
        self.assertEqual(log.object_repr, f"ImportJob:{job.id}")

    def test_safe_object_repr(self):
        self._auth(self.admin_user)
        self._post(self._valid_csv())
        log = self._import_logs().get()
        self.assertEqual(log.object_repr, f"ImportJob:{log.object_id}")
        self.assertLessEqual(len(log.object_repr), 255)
        # No row-level data, names, grades, or credentials in the repr.
        self.assertNotIn("Hop", log.object_repr)
        self.assertNotIn("student_id", log.object_repr)
        self.assertNotIn("password", log.object_repr)


class ImportFailureTest(ImportExportAuditBase):
    def test_failed_import_creates_no_successful_import(self):
        self._auth(self.admin_user)
        resp = self._post("\nAlice,90\nBob,88\n")  # missing header -> FAILED
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(self._import_logs().count(), 0)

    def test_unauthorized_import_creates_no_import(self):
        self._auth(self.student_user)
        resp = self._post("student_id,name\nS1,Ann\n")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._import_logs().count(), 0)

    def test_faculty_cannot_import_students_no_import(self):
        self._auth(self.faculty_user)
        resp = self._post("student_id,name\nS1,Ann\n", import_type="students")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._import_logs().count(), 0)

    def test_unauthenticated_import_creates_no_import(self):
        self.client.logout()
        resp = self._post("student_id,score\nS1,90\n")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self._import_logs().count(), 0)


class ImportRollbackTest(ImportExportAuditBase):
    def setUp(self):
        super().setUp()
        self.dom = _build_grade_domain("rb")

    def test_rollback_leaves_no_successful_import_audit(self):
        # Simulate an atomic import that writes an audit then rolls back:
        # the success import audit must not remain.
        from django.db import transaction
        from apps.audit.import_export_hooks import audit_successful_import

        self._auth(self.admin_user)
        job = ImportJob.objects.create(
            uploaded_by=self.admin_user,
            file=make_csv("student_id,subject_assignment,grading_period,score\nx,1,2,90\n"),
            file_type="csv",
            import_type="grades",
            status=JobStatus.COMPLETED,
        )
        try:
            with transaction.atomic():
                audit_successful_import(job)
                self.assertEqual(self._import_logs().count(), 1)
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        self.assertEqual(self._import_logs().count(), 0)

    def test_view_rollback_does_not_audit_failed_import(self):
        # A pipeline-level failure (500 path) must not produce an IMPORT audit.
        from unittest import mock

        self.client.raise_request_exception = False
        self._auth(self.admin_user)
        with mock.patch(
            "apps.data_import.views.ImportJobViewSet._run_job",
            side_effect=RuntimeError("boom"),
        ):
            resp = self._post("student_id,score\nS1,90\n")
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(self._import_logs().count(), 0)


class ImportMultiRowTest(ImportExportAuditBase):
    def setUp(self):
        super().setUp()
        self.dom = _build_grade_domain("mr")

    def test_multi_row_import_creates_exactly_one_import_event(self):
        self._auth(self.admin_user)
        csv_text = (
            "student_id,subject_assignment,grading_period,score\n"
            f"{self.dom['student_id']},{self.dom['subject_assignment']},{self.dom['grading_period']},90\n"
            f"{self.dom['student_id']},{self.dom['subject_assignment']},{self.dom['grading_period2']},88\n"
            f"{self.dom['student_id']},{self.dom['subject_assignment']},{self.dom['grading_period3']},91\n"
        )
        resp = self._post(csv_text)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.records.count(), 3)
        self.assertEqual(Grade.objects.count(), 3)
        self.assertEqual(self._import_logs().count(), 1)


# ---------------------------------------------------------------------------
# EXPORT — successful export semantics
# ---------------------------------------------------------------------------

class ExportSuccessTest(ImportExportAuditBase):
    def setUp(self):
        super().setUp()
        self.dom = _build_grade_domain("ex")
        self.grade = Grade.objects.create(
            student=self.dom["student_profile"],
            subject_assignment=SubjectAssignment.objects.get(pk=self.dom["subject_assignment"]),
            grading_period=GradingPeriod.objects.get(pk=self.dom["grading_period"]),
            score=90, letter_grade="A", remarks="Excellent",
            encoded_by=self.dom["faculty_profile"], status="finalized",
        )
        _clear_audit()

    def test_successful_export_creates_exactly_one_export_log(self):
        resp = self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        logs = self._export_logs()
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs[0].action, "export")

    def test_correct_actor(self):
        self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        log = self._export_logs().get()
        self.assertEqual(log.user_id, self.admin_user.pk)

    def test_correct_ip(self):
        self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        log = self._export_logs().get()
        self.assertEqual(log.ip_address, _TEST_IP)

    def test_correct_user_agent(self):
        self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        log = self._export_logs().get()
        self.assertEqual(log.user_agent, _TEST_UA)

    def test_changes_is_null(self):
        self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        log = self._export_logs().get()
        self.assertIsNone(log.changes)

    def test_correct_model_and_object_semantics(self):
        self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        log = self._export_logs().get()
        # A grades export targets the REAL Grade dataset — not ImportJob,
        # and not a fabricated ExportJob.  object_id is NULL because an
        # export is an operation-level event with no persistent target row.
        self.assertEqual(log.model_name, "academics.Grade")
        self.assertNotEqual(log.model_name, "data_import.ImportJob")
        self.assertIsNone(log.object_id)

    def test_export_target_model_is_real_domain_model(self):
        resp = self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        log = self._export_logs().get()
        self.assertTrue(
            any(
                log.model_name.endswith(f".{label}")
                for label in ("Grade", "AttendanceRecord", "StudentProfile")
            ),
            log.model_name,
        )

    def test_attendance_export_targets_attendance_record(self):
        dom = _build_attendance_domain("att")
        AttendanceRecord.objects.create(
            student=dom["student_profile"],
            section=dom["section_obj"],
            date=date(2026, 2, 1),
            status="present",
            recorded_by=dom["faculty_profile"],
        )
        _clear_audit()
        self._auth(self.admin_user)
        resp = self._get_export(
            "/api/v1/data-import/exports/attendance/", self.admin_user, file_format="csv",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        log = self._export_logs().get()
        self.assertEqual(log.model_name, "attendance.AttendanceRecord")
        self.assertIsNone(log.object_id)

    def test_students_export_targets_student_profile(self):
        self._auth(self.admin_user)
        resp = self._get_export(
            "/api/v1/data-import/exports/students/", self.admin_user, file_format="csv",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        log = self._export_logs().get()
        self.assertEqual(log.model_name, "accounts.StudentProfile")
        self.assertIsNone(log.object_id)

    def test_safe_object_repr(self):
        self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        log = self._export_logs().get()
        self.assertEqual(log.object_repr, "Export")
        self.assertLessEqual(len(log.object_repr), 255)


class ExportFailureTest(ImportExportAuditBase):
    def test_failed_export_creates_no_successful_export(self):
        from unittest import mock

        self._auth(self.admin_user)
        with mock.patch(
            "apps.data_import.views.rows_for_queryset",
            side_effect=RuntimeError("boom"),
        ):
            resp = self.client.get("/api/v1/data-import/exports/grades/?file_format=csv")
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(self._export_logs().count(), 0)

    def test_invalid_format_creates_no_export(self):
        resp = self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="pdf")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._export_logs().count(), 0)

    def test_unauthorized_export_creates_no_export(self):
        resp = self._get_export("/api/v1/data-import/exports/students/", self.faculty_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._export_logs().count(), 0)

    def test_unauthenticated_export_creates_no_export(self):
        resp = self.client.get("/api/v1/data-import/exports/grades/?file_format=csv")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self._export_logs().count(), 0)


class ExportMultiRowTest(ImportExportAuditBase):
    def setUp(self):
        super().setUp()
        self.dom = _build_grade_domain("mx")
        sa = SubjectAssignment.objects.get(pk=self.dom["subject_assignment"])
        for gp_key, name, score in (
            ("grading_period", "Q1", 90),
            ("grading_period2", "Q2", 88),
            ("grading_period3", "Q3", 91),
        ):
            gp = GradingPeriod.objects.get(pk=self.dom[gp_key])
            Grade.objects.create(
                student=self.dom["student_profile"], subject_assignment=sa,
                grading_period=gp, score=score, letter_grade="A",
                encoded_by=self.dom["faculty_profile"], status="finalized",
            )
        _clear_audit()

    def test_multi_row_export_creates_exactly_one_export_event(self):
        resp = self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Grade.objects.count(), 3)
        self.assertEqual(self._export_logs().count(), 1)


class ExportNoFakeModelTest(ImportExportAuditBase):
    """Confirm no fake ExportJob model exists and is never referenced.

    Exports have no job model of their own; the audit must point at real,
    existing domain models only.
    """

    def test_no_exportjob_model_exists_in_codebase(self):
        from django.apps import apps as django_apps

        registered = {m._meta.label_lower for m in django_apps.get_models()}
        self.assertNotIn("data_import.exportjob", registered)
        self.assertNotIn("data_import.export", registered)
        self.assertNotIn("data_import.exportrecord", registered)

    def test_export_log_never_references_fake_model_name(self):
        dom = _build_grade_domain("nfm")
        sa = SubjectAssignment.objects.get(pk=dom["subject_assignment"])
        gp = GradingPeriod.objects.get(pk=dom["grading_period"])
        Grade.objects.create(
            student=dom["student_profile"], subject_assignment=sa,
            grading_period=gp, score=90, letter_grade="A",
            encoded_by=dom["faculty_profile"], status="finalized",
        )
        _clear_audit()
        resp = self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for log in self._export_logs():
            self.assertNotIn("ExportJob", log.model_name)
            self.assertNotEqual(log.model_name, "data_import.Export")
            self.assertTrue(log.model_name.endswith(".Grade"))


# ---------------------------------------------------------------------------
# SECURITY — file/row/sensitive data never stored
# ---------------------------------------------------------------------------

class SecurityTest(ImportExportAuditBase):
    def _run_and_return_logs(self):
        dom = _build_grade_domain("sec")
        sa = SubjectAssignment.objects.get(pk=dom["subject_assignment"])
        gp = GradingPeriod.objects.get(pk=dom["grading_period"])
        Grade.objects.create(
            student=dom["student_profile"], subject_assignment=sa,
            grading_period=gp, score=97, letter_grade="A", remarks="ConfidentialNote",
            encoded_by=dom["faculty_profile"], status="finalized",
        )
        _clear_audit()
        # Import a file whose row content is sensitive-looking.
        self._auth(self.admin_user)
        csv_text = (
            "student_id,subject_assignment,grading_period,score\n"
            f"{dom['student_id']},{dom['subject_assignment']},{dom['grading_period']},97\n"
        )
        self._post(csv_text)
        # Export grades.
        self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        return list(AuditLog.objects.all())

    def _all_log_text(self, logs):
        return "\n".join(_serialize_log(log) for log in logs)

    def test_file_contents_never_stored(self):
        logs = self._run_and_return_logs()
        text = self._all_log_text(logs)
        self.assertNotIn("student_id,subject_assignment", text)

    def test_row_data_never_stored(self):
        logs = self._run_and_return_logs()
        text = self._all_log_text(logs)
        self.assertNotIn("97", text)
        dom_col = None
        for log in logs:
            self.assertNotIn("grading_period", _serialize_log(log))

    def test_sensitive_domain_values_never_stored(self):
        logs = self._run_and_return_logs()
        text = self._all_log_text(logs)
        self.assertNotIn("ConfidentialNote", text)
        self.assertNotIn("removed", text)

    def test_passwords_tokens_credentials_never_stored(self):
        for u in User.objects.all():
            u.set_password("SuperSecretAEGIS99!")
            u.save()
        logged = {}
        _clear_audit()
        resp = self._get_export("/api/v1/data-import/exports/students/", self.admin_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        logs = list(AuditLog.objects.filter(action="export"))
        text = self._all_log_text(logs)
        self.assertNotIn("SuperSecretAEGIS99", text)
        self.assertNotIn("pbkdf2_sha256", text)
        self.assertNotIn("must_change_password", text)

    def test_authorization_header_never_stored(self):
        self._auth(self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer AEGIS-SECRET-TOKEN-000")
        resp = self.client.get(
            "/api/v1/data-import/exports/grades/?file_format=csv",
            REMOTE_ADDR=_TEST_IP, HTTP_USER_AGENT=_TEST_UA,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        logs = list(AuditLog.objects.filter(action="export"))
        text = self._all_log_text(logs)
        self.assertNotIn("AEGIS-SECRET-TOKEN-000", text)


# ---------------------------------------------------------------------------
# CONTEXT
# ---------------------------------------------------------------------------

class ContextTest(ImportExportAuditBase):
    def setUp(self):
        super().setUp()
        self.dom = _build_grade_domain("ctx")

    def test_ph10_6_context_is_used(self):
        # The audit log carries exactly the PH10.6 context values (actor,
        # IP, UA), proving the hook consumes get_audit_context().
        self._auth(self.admin_user)
        self._post(
            "student_id,subject_assignment,grading_period,score\n"
            f"{self.dom['student_id']},{self.dom['subject_assignment']},{self.dom['grading_period']},90\n",
        )
        log = self._import_logs().get()
        self.assertEqual(log.user_id, self.admin_user.pk)
        self.assertEqual(log.ip_address, _TEST_IP)
        self.assertEqual(log.user_agent, _TEST_UA)

    def test_faculty_actor_from_context(self):
        # A faculty actor (not the domain 'encoded_by') is the recorded actor.
        self._auth(self.dom["faculty_profile"].user)
        self._post(
            "student_id,subject_assignment,grading_period,score\n"
            f"{self.dom['student_id']},{self.dom['subject_assignment']},{self.dom['grading_period']},90\n",
        )
        log = self._import_logs().get()
        self.assertEqual(log.user_id, self.dom["faculty_profile"].user.pk)

    def test_request_contexts_do_not_leak(self):
        from apps.audit.context import get_audit_context

        self._auth(self.admin_user)
        self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self._post(
            "student_id,subject_assignment,grading_period,score\n"
            f"{self.dom['student_id']},{self.dom['subject_assignment']},{self.dom['grading_period']},90\n",
        )
        # After the request completes the context is empty (no cross-request leak).
        ctx = get_audit_context()
        self.assertIsNone(ctx.user)
        self.assertIsNone(ctx.ip_address)
        self.assertIsNone(ctx.user_agent)

    def test_background_operation_uses_none_user(self):
        from apps.audit.import_export_hooks import audit_successful_import

        job = ImportJob.objects.create(
            uploaded_by=self.admin_user,
            file=make_csv("a,b\n1,2\n"),
            file_type="csv", import_type="grades", status=JobStatus.COMPLETED,
        )
        _clear_audit()
        audit_successful_import(job)  # no request context -> all None
        log = self._import_logs().get()
        self.assertIsNone(log.user)
        self.assertIsNone(log.ip_address)
        self.assertIsNone(log.user_agent)


# ---------------------------------------------------------------------------
# DUPLICATION
# ---------------------------------------------------------------------------

class DuplicationTest(ImportExportAuditBase):
    def setUp(self):
        super().setUp()
        self.dom = _build_grade_domain("dup")

    def test_one_import_operation_does_not_create_multiple_import_events(self):
        self._auth(self.admin_user)
        self._post(
            "student_id,subject_assignment,grading_period,score\n"
            f"{self.dom['student_id']},{self.dom['subject_assignment']},{self.dom['grading_period']},90\n"
            f"{self.dom['student_id']},{self.dom['subject_assignment']},{self.dom['grading_period2']},91\n",
        )
        self.assertEqual(self._import_logs().count(), 1)

    def test_one_export_operation_does_not_create_multiple_export_events(self):
        sa = SubjectAssignment.objects.get(pk=self.dom["subject_assignment"])
        gp = GradingPeriod.objects.get(pk=self.dom["grading_period"])
        Grade.objects.create(
            student=self.dom["student_profile"], subject_assignment=sa,
            grading_period=gp, score=95, letter_grade="A",
            encoded_by=self.dom["faculty_profile"], status="finalized",
        )
        _clear_audit()
        resp = self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(self._export_logs().count(), 1)


# ---------------------------------------------------------------------------
# COMPATIBILITY
# ---------------------------------------------------------------------------

class CompatibilityTest(ImportExportAuditBase):
    def test_underlying_import_operation_unchanged(self):
        # A successful import still creates the ImportJob + records (the
        # audit integration must not perturb the business operation).
        dom = _build_grade_domain("comp")
        self._auth(self.admin_user)
        csv_text = (
            "student_id,subject_assignment,grading_period,score\n"
            f"{dom['student_id']},{dom['subject_assignment']},{dom['grading_period']},90\n"
        )
        resp = self._post(csv_text)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.records.count(), 1)
        self.assertEqual(Grade.objects.count(), 1)

    def test_underlying_export_operation_unchanged(self):
        dom = _build_grade_domain("compx")
        sa = SubjectAssignment.objects.get(pk=dom["subject_assignment"])
        gp = GradingPeriod.objects.get(pk=dom["grading_period"])
        Grade.objects.create(
            student=dom["student_profile"], subject_assignment=sa,
            grading_period=gp, score=90, letter_grade="A",
            encoded_by=dom["faculty_profile"], status="finalized",
        )
        _clear_audit()
        resp = self._get_export("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", resp["Content-Type"])
        self.assertEqual(AuditLog.objects.filter(action="export").count(), 1)
