"""
PH8.1 — Data Import Foundation tests.

Verifies the app skeleton is installed and the approved import-surface
constants (file types, import types, role authority matrix, limits) are
locked in as the single source of truth for subsequent sub-phases.
"""

from django.conf import settings
from django.test import SimpleTestCase

from apps.data_import.constants import (
    ADMIN_ONLY_IMPORT_TYPES,
    ALL_ADMIN_IMPORT_TYPES,
    ALL_FACULTY_IMPORT_TYPES,
    ALLOWED_EXTENSIONS,
    FileType,
    ImportErrorCode,
    ImportType,
    JobStatus,
    MAX_IMPORT_FILE_SIZE,
    MAX_IMPORT_ROWS,
    RecordStatus,
)

from config import api_v1

APP_NAME = "apps.data_import"


class DataImportAppInstalledTest(SimpleTestCase):
    def test_app_is_installed(self):
        self.assertIn(APP_NAME, settings.INSTALLED_APPS)


class DataImportRoutingTest(SimpleTestCase):
    def test_data_import_route_is_wired(self):
        patterns = [str(p.pattern) for p in api_v1.urlpatterns]
        self.assertIn("data-import/", patterns)


class FileTypeConstantsTest(SimpleTestCase):
    def test_supported_file_types(self):
        self.assertEqual(
            set(FileType.CHOICES),
            {(FileType.CSV, "CSV"), (FileType.XLSX, "XLSX")},
        )

    def test_allowed_extensions_match_file_types(self):
        # ``.xlsm`` is the macro-enabled spelling of the same XLSX file type.
        self.assertEqual(ALLOWED_EXTENSIONS, {".csv", ".xlsx", ".xlsm"})

    def test_legacy_xls_is_not_supported(self):
        # XLSX-ONLY decision confirmed with project owner.
        self.assertNotIn(".xls", ALLOWED_EXTENSIONS)
        self.assertNotIn(FileType.XLSX + "x", FileType.ALL)  # no .xls pseudo-type


class ImportTypeConstantsTest(SimpleTestCase):
    def test_approved_import_types(self):
        approved = {
            ImportType.GRADES,
            ImportType.ATTENDANCE,
            ImportType.STUDENTS,
            ImportType.GUIDANCE_RECORDS,
        }
        self.assertEqual({c[0] for c in ImportType.CHOICES}, approved)


class RoleAuthorityTest(SimpleTestCase):
    def test_admin_can_import_all_types(self):
        self.assertEqual(
            ALL_ADMIN_IMPORT_TYPES,
            frozenset(
                {
                    ImportType.GRADES,
                    ImportType.ATTENDANCE,
                    ImportType.STUDENTS,
                    ImportType.GUIDANCE_RECORDS,
                }
            ),
        )

    def test_faculty_limited_to_grades_and_attendance(self):
        self.assertEqual(ALL_FACULTY_IMPORT_TYPES, {ImportType.GRADES, ImportType.ATTENDANCE})

    def test_students_and_guidance_are_admin_only(self):
        self.assertEqual(ADMIN_ONLY_IMPORT_TYPES, {ImportType.STUDENTS, ImportType.GUIDANCE_RECORDS})
        self.assertFalse(ADMIN_ONLY_IMPORT_TYPES & ALL_FACULTY_IMPORT_TYPES)


class LimitConstantsTest(SimpleTestCase):
    def test_limits_are_positive(self):
        self.assertGreater(MAX_IMPORT_FILE_SIZE, 0)
        self.assertGreater(MAX_IMPORT_ROWS, 0)


class StatusConstantsTest(SimpleTestCase):
    def test_job_statuses(self):
        statuses = {c[0] for c in JobStatus.CHOICES}
        self.assertEqual(
            statuses,
            {JobStatus.PENDING, JobStatus.PROCESSING, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PARTIAL},
        )

    def test_record_statuses(self):
        statuses = {c[0] for c in RecordStatus.CHOICES}
        self.assertEqual(statuses, {RecordStatus.SUCCESS, RecordStatus.ERROR, RecordStatus.SKIPPED})

    def test_error_codes_are_unique(self):
        codes = [v for k, v in vars(ImportErrorCode).items() if k.isupper()]
        self.assertEqual(len(codes), len(set(codes)))


class SanitizedFilenameTest(SimpleTestCase):
    def test_strips_path_components(self):
        from apps.data_import.constants import sanitized_filename

        self.assertEqual(sanitized_filename("C:/evil/../grades.csv"), "grades.csv")
        self.assertEqual(sanitized_filename("..\\..\\students.xlsx"), "students.xlsx")

    def test_empty_filename_is_safe(self):
        from apps.data_import.constants import sanitized_filename

        self.assertEqual(sanitized_filename(""), "")


# ===========================================================================
# PH8.2 / PH8.3 — Import Job Tracking + CSV Pipeline
# ===========================================================================

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient
from unittest import mock

from apps.data_import.constants import (
    FileType,
    ImportErrorCode,
    ImportType,
    JobStatus,
    MAX_IMPORT_ROWS,
    RecordStatus,
)
from apps.data_import.csv_pipeline import (
    CsvValidationError,
    parse_csv_bytes,
    sanitize_csv_cell,
    safe_filename,
)
from apps.data_import.models import ImportJob, ImportRecord

User = get_user_model()

from apps.accounts.models import FacultyProfile, ParentProfile, ParentStudentLink, StudentProfile  # noqa: E402
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


def make_csv(content, name="grades.csv"):
    """Build a SimpleUploadedFile holding CSV bytes."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return SimpleUploadedFile(name, content, content_type="text/csv")


def _build_grade_domain(suffix=""):
    """Build a minimal, SEC-013-valid academic structure for a grade import.

    Returns a dict with the identifiers needed to author a valid CSV/XLSX
    grade row: student_id, subject_assignment, grading_period.
    """
    ay = AcademicYear.objects.create(
        name=f"2025-2026{suffix}", start_date="2025-06-01",
        end_date="2026-03-31", is_current=True,
    )
    g7 = GradeLevel.objects.create(name=f"Grade 7{suffix}", level_number=7)
    fp_user = User.objects.create_user(
        email=f"fac_grade{suffix}@test.com", password="pass12345",
        first_name="Fac", last_name="Grade", role="faculty",
    )
    fp = FacultyProfile.objects.create(user=fp_user, employee_id=f"E-GR{suffix}")
    section = Section.objects.create(
        name=f"G-7A{suffix}", grade_level=g7, academic_year=ay, adviser=fp,
    )
    subject = Subject.objects.create(name=f"Math{suffix}", code=f"MG7{suffix}", grade_level=g7)
    sa = SubjectAssignment.objects.create(
        subject=subject, faculty=fp, section=section, academic_year=ay,
    )
    gp = GradingPeriod.objects.create(
        academic_year=ay, name=f"Q1{suffix}", order=1,
        start_date="2025-06-01", end_date="2025-08-31",
    )
    su_user = User.objects.create_user(
        email=f"stu_grade{suffix}@test.com", password="pass12345",
        first_name="Stu", last_name="Grade", role="student",
    )
    sp = StudentProfile.objects.create(
        user=su_user, student_id=f"STU-001{suffix}", enrollment_date="2025-06-01",
    )
    Enrollment.objects.create(
        student=sp, section=section, academic_year=ay, date_enrolled="2025-06-01",
    )
    # A second subject assignment on a different faculty (for scope tests).
    other_fp_user = User.objects.create_user(
        email=f"fac_other{suffix}@test.com", password="pass12345",
        first_name="Fac", last_name="Other", role="faculty",
    )
    other_fp = FacultyProfile.objects.create(user=other_fp_user, employee_id=f"E-OT{suffix}")
    other_sa = SubjectAssignment.objects.create(
        subject=Subject.objects.create(name=f"Sci{suffix}", code=f"SG7{suffix}", grade_level=g7),
        faculty=other_fp, section=section, academic_year=ay,
    )
    return {
        "student_id": f"STU-001{suffix}",
        "subject_assignment": str(sa.pk),
        "other_subject_assignment": str(other_sa.pk),
        "grading_period": str(gp.pk),
        "section": str(section.pk),
        "ay": ay,
        "section_obj": section,
        "faculty_profile": fp,
        "student_profile": sp,
    }


def _build_attendance_domain(suffix=""):
    """Build a minimal, valid attendance structure for an attendance import.

    Returns a dict with: student_id, section, and the section_obj/faculty
    needed for scope assertions.
    """
    ay = AcademicYear.objects.create(
        name=f"2026{suffix}", start_date="2026-01-01",
        end_date="2026-12-31", is_current=True,
    )
    g7 = GradeLevel.objects.create(name=f"Grade 7{suffix}", level_number=7)
    fp_user = User.objects.create_user(
        email=f"fac_att{suffix}@test.com", password="pass12345",
        first_name="Fac", last_name="Att", role="faculty",
    )
    fp = FacultyProfile.objects.create(user=fp_user, employee_id=f"E-AT{suffix}")
    section = Section.objects.create(
        name=f"A-7A{suffix}", grade_level=g7, academic_year=ay, adviser=fp,
    )
    su_user = User.objects.create_user(
        email=f"stu_att{suffix}@test.com", password="pass12345",
        first_name="Stu", last_name="Att", role="student",
    )
    sp = StudentProfile.objects.create(
        user=su_user, student_id=f"ATU-001{suffix}", enrollment_date="2026-01-01",
    )
    Enrollment.objects.create(
        student=sp, section=section, academic_year=ay, date_enrolled="2026-01-01",
    )
    return {
        "student_id": f"ATU-001{suffix}",
        "section": str(section.pk),
        "section_obj": section,
        "ay": ay,
        "faculty_profile": fp,
        "student_profile": sp,
    }


class DataImportApiBase(TestCase):
    """Shared users + auth helper for the PH8.2/8.3 API tests."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin_di@test.com", password="pass12345", first_name="Ad", last_name="Min", role="admin"
        )
        self.faculty_user = User.objects.create_user(
            email="faculty_di@test.com", password="pass12345", first_name="Fac", last_name="U", role="faculty"
        )
        self.student_user = User.objects.create_user(
            email="student_di@test.com", password="pass12345", first_name="Stu", last_name="D", role="student"
        )
        self.parent_user = User.objects.create_user(
            email="parent_di@test.com", password="pass12345", first_name="Par", last_name="Ent", role="parent"
        )
        self.client = APIClient()

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _upload(self, csv_content, import_type="grades", name="grades.csv"):
        return self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": make_csv(csv_content, name=name), "import_type": import_type},
            format="multipart",
        )


# ---------------------------------------------------------------------------
# PH8.2 — Model behavior
# ---------------------------------------------------------------------------


class ImportJobModelTest(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="model_admin@test.com", password="pass12345", role="admin"
        )

    def _job(self, **overrides):
        kwargs = dict(
            uploaded_by=self.admin_user,
            file=SimpleUploadedFile("grades.csv", b"a,b\n1,2", content_type="text/csv"),
            file_type=FileType.CSV,
            import_type=ImportType.GRADES,
            status=JobStatus.PENDING,
        )
        kwargs.update(overrides)
        return ImportJob.objects.create(**kwargs)

    def test_default_status_is_pending(self):
        job = self._job()
        self.assertEqual(job.status, JobStatus.PENDING)
        job.refresh_from_db()
        self.assertEqual(job.total_rows, 0)
        self.assertEqual(job.error_log, [])

    def test_pending_processing_completed_transition(self):
        job = self._job(status=JobStatus.PENDING)
        job.status = JobStatus.PROCESSING
        job.save()
        job.status = JobStatus.COMPLETED
        job.save()
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertIsNotNone(job.completed_at)

    def test_processing_partial_is_allowed(self):
        job = self._job(status=JobStatus.PROCESSING)
        job.status = JobStatus.PARTIAL
        job.save()
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.PARTIAL)

    def test_pending_to_completed_is_rejected(self):
        job = self._job(status=JobStatus.PENDING)
        job.status = JobStatus.COMPLETED
        with self.assertRaises(ValidationError):
            job.save()

    def test_completed_to_processing_is_rejected(self):
        job = self._job(status=JobStatus.COMPLETED)
        job.status = JobStatus.PROCESSING
        with self.assertRaises(ValidationError):
            job.save()

    def test_clean_rejects_invalid_transition(self):
        job = self._job(status=JobStatus.PENDING)
        job.status = JobStatus.COMPLETED
        with self.assertRaises(ValidationError):
            job.full_clean()


class ImportRecordModelTest(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="rec_admin@test.com", password="pass12345", role="admin"
        )
        self.job = ImportJob.objects.create(
            uploaded_by=self.admin_user,
            file=SimpleUploadedFile("grades.csv", b"a,b\n1,2", content_type="text/csv"),
            file_type=FileType.CSV,
            import_type=ImportType.GRADES,
            status=JobStatus.PENDING,
        )

    def test_record_creation_and_row_number_unique(self):
        ImportRecord.objects.create(job=self.job, row_number=1, data={"a": "1"}, status=RecordStatus.SUCCESS)
        with self.assertRaises(Exception):
            ImportRecord.objects.create(job=self.job, row_number=1, data={"a": "x"}, status=RecordStatus.ERROR)

    def test_records_related_to_job(self):
        r = ImportRecord.objects.create(job=self.job, row_number=1, data={"a": "1"}, status=RecordStatus.SUCCESS)
        self.assertIn(r, self.job.records.all())


# ---------------------------------------------------------------------------
# PH8.2 — API: job creation / list / retrieve
# ---------------------------------------------------------------------------


class ImportJobCreateApiTest(DataImportApiBase):
    def test_admin_can_create_grade_job(self):
        dom = _build_grade_domain("job")
        gp2 = GradingPeriod.objects.create(
            academic_year=dom["ay"], name="Q2", order=2,
            start_date="2025-09-01", end_date="2025-11-30",
        )
        self._auth(self.admin_user)
        csv_text = (
            "student_id,subject_assignment,grading_period,score\n"
            f"{dom['student_id']},{dom['subject_assignment']},{dom['grading_period']},90\n"
            f"{dom['student_id']},{dom['subject_assignment']},{str(gp2.pk)},88\n"
        )
        resp = self._upload(csv_text)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.import_type, ImportType.GRADES)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.total_rows, 2)
        self.assertEqual(job.processed_rows, 2)
        self.assertEqual(job.error_rows, 0)
        self.assertEqual(job.records.count(), 2)
        self.assertEqual(Grade.objects.count(), 2)

    def test_faculty_can_create_attendance_job(self):
        self._auth(self.faculty_user)
        resp = self._upload("student_id,date,status\nS1,2026-01-01,present\n", import_type="attendance")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["import_type"], "attendance")

    def test_student_cannot_create_job(self):
        self._auth(self.student_user)
        resp = self._upload("a,b\n1,2\n")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_parent_cannot_create_job(self):
        self._auth(self.parent_user)
        resp = self._upload("a,b\n1,2\n")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_import_type_without_an_importer_never_reports_success(self):
        # The honesty guarantee, driven directly at the dispatch seam. Every
        # approved import type has a domain importer as of PH11 (including
        # guidance_records), so the view layer can no longer produce this
        # state; the branch is kept for the next type that ships without one.
        # If that happens, parsing the file must not be presented as a
        # completed import — the rows were never stored, so they are skipped,
        # the job fails, and no successful-import audit event is written.
        from apps.audit.models import AuditLog

        from apps.data_import.runner import dispatch_domain_processing

        job = ImportJob.objects.create(
            uploaded_by=self.admin_user,
            file="imports/no-importer.csv",
            file_type=FileType.CSV,
            import_type="future_type",
            status=JobStatus.PROCESSING,
        )
        record = ImportRecord.objects.create(
            job=job,
            row_number=1,
            data={"student_id": "S1"},
            status=RecordStatus.ERROR,
        )

        dispatch_domain_processing(job, [record], ["student_id"])

        job.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.total_rows, 1)
        self.assertEqual(job.processed_rows, 0)
        self.assertEqual(job.error_rows, 0)
        self.assertEqual(
            job.error_log[0]["code"], ImportErrorCode.UNSUPPORTED_IMPORT_TYPE
        )
        self.assertEqual(record.status, RecordStatus.SKIPPED)
        self.assertFalse(
            AuditLog.objects.filter(
                action="import", object_id=str(job.id)
            ).exists()
        )

    def test_faculty_cannot_import_students(self):
        self._auth(self.faculty_user)
        resp = self._upload("student_id,name\nS1,Ann\n", import_type="students")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_import_type_rejected(self):
        self._auth(self.admin_user)
        resp = self._upload("a,b\n1,2\n", import_type="bogus")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthorized_user_rejected(self):
        resp = self._upload("a,b\n1,2\n")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_academic_records_created(self):
        self._auth(self.admin_user)
        self._upload("student_id,score\nS1,90\n")
        from apps.attendance.models import AttendanceRecord
        from apps.academics.models import Grade  # noqa: F401  (import guard)

        self.assertEqual(AttendanceRecord.objects.count(), 0)


class ImportJobListRetrieveApiTest(DataImportApiBase):
    def _make_job(self, user, csv="a,b\n1,2\n", import_type="grades"):
        return ImportJob.objects.create(
            uploaded_by=user,
            file=SimpleUploadedFile("grades.csv", csv.encode(), content_type="text/csv"),
            file_type=FileType.CSV,
            import_type=import_type,
            status=JobStatus.COMPLETED,
        )

    def test_list_shows_own_jobs(self):
        self._make_job(self.faculty_user)
        self._auth(self.faculty_user)
        resp = self.client.get("/api/v1/data-import/jobs/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

    def test_list_requires_auth(self):
        resp = self.client.get("/api/v1/data-import/jobs/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_student_forbidden_from_list(self):
        self._make_job(self.admin_user)
        self._auth(self.student_user)
        resp = self.client.get("/api/v1/data-import/jobs/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_exposes_per_row_records(self):
        job = self._make_job(self.admin_user)
        ImportRecord.objects.create(job=job, row_number=1, data={"a": "1"}, status=RecordStatus.SUCCESS)
        self._auth(self.admin_user)
        resp = self.client.get(f"/api/v1/data-import/jobs/{job.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["record_summary"]["success"], 1)
        self.assertEqual(len(resp.data["records"]), 1)
        self.assertEqual(resp.data["records"][0]["row_number"], 1)

    def test_faculty_cannot_see_other_job(self):
        job = self._make_job(self.admin_user)
        self._auth(self.faculty_user)
        resp = self.client.get(f"/api/v1/data-import/jobs/{job.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_see_any_job(self):
        job = self._make_job(self.faculty_user)
        self._auth(self.admin_user)
        resp = self.client.get(f"/api/v1/data-import/jobs/{job.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_no_sensitive_details_leaked(self):
        job = self._make_job(self.admin_user)
        self._auth(self.admin_user)
        resp = self.client.get(f"/api/v1/data-import/jobs/{job.pk}/")
        body = str(resp.data)
        self.assertNotIn("SECRET_KEY", body)
        self.assertNotIn("password", body.lower())
        self.assertNotIn("C:/", body)
        self.assertNotIn("\\Users", body)


# ---------------------------------------------------------------------------
# PH8.3 — CSV pipeline validation
# ---------------------------------------------------------------------------


class CsvSanitizeTest(TestCase):
    def test_formula_prefixes_neutralized(self):
        for dangerous in ("=1+1", "+SUM(A1:A9)", "-cmd", "@SUM(A1)", "\t=x", "\r=x"):
            self.assertTrue(sanitize_csv_cell(dangerous).startswith("'"))

    def test_legitimate_values_untouched(self):
        for safe in ("90", "Alice", "20/20", "B+", "1-2", "a=b", "math=2"):
            self.assertEqual(sanitize_csv_cell(safe), safe)

    def test_empty_untouched(self):
        self.assertEqual(sanitize_csv_cell(""), "")

    def test_dangerous_prefix_preserved_verbatim_after_hint(self):
        # The integer is sanitized once; the remainder is kept verbatim.
        self.assertEqual(sanitize_csv_cell("=SUM(x)"), "'=SUM(x)")


class CsvFilenameTest(TestCase):
    def test_path_traversal_stripped(self):
        self.assertNotIn("..", safe_filename("../../etc/passwd.csv"))
        self.assertEqual(safe_filename("..\\..\\evil.csv"), "evil.csv")

    def test_backslash_and_slashes_stripped(self):
        self.assertEqual(safe_filename("C:\\tmp\\data.csv"), "data.csv")

    def test_empty_safe(self):
        self.assertEqual(safe_filename(""), "")


class CsvParseTest(TestCase):
    def test_valid_csv_parses_rows(self):
        result = parse_csv_bytes(b"name,score\nAlice,90\nBob,88\n")
        self.assertEqual(result.headers, ["name", "score"])
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.rows[0]["name"], "Alice")
        self.assertEqual(result.rows[0]["score"], "90")

    def test_row_numbering_correct(self):
        result = parse_csv_bytes(b"a,b\n1,2\n3,4\n")
        # row numbers are 1-based within the parsed result rows.
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.raw_row_count, 2)

    def test_empty_csv_rejected(self):
        with self.assertRaises(CsvValidationError) as ctx:
            parse_csv_bytes(b"")
        self.assertEqual(ctx.exception.code, ImportErrorCode.FILE_EMPTY)

    def test_blank_csv_rejected(self):
        with self.assertRaises(CsvValidationError):
            parse_csv_bytes(b"\n\n")

    def test_missing_header_rejected(self):
        with self.assertRaises(CsvValidationError) as ctx:
            parse_csv_bytes(b"\nAlice,90\nBob,88\n")
        self.assertEqual(ctx.exception.code, ImportErrorCode.MISSING_REQUIRED_COLUMN)

    def test_malformed_header_rejected(self):
        with self.assertRaises(CsvValidationError) as ctx:
            parse_csv_bytes(b"a,,b\n1,2,3\n")
        self.assertEqual(ctx.exception.code, ImportErrorCode.MALFORMED_HEADER)

    def test_duplicate_headers_rejected(self):
        with self.assertRaises(CsvValidationError) as ctx:
            parse_csv_bytes(b"a,a\n1,2\n")
        self.assertEqual(ctx.exception.code, ImportErrorCode.MALFORMED_HEADER)

    def test_unexpected_header_count_rejected(self):
        with self.assertRaises(CsvValidationError):
            parse_csv_bytes(b"a\n1,2,3,4\n")  # row wider than header

    def test_excessive_columns_rejected(self):
        header = ",".join(f"c{i}" for i in range(61))
        with self.assertRaises(CsvValidationError) as ctx:
            parse_csv_bytes((header + "\n").encode())
        self.assertEqual(ctx.exception.code, ImportErrorCode.BAD_COLUMN_COUNT)

    def test_blank_trailing_rows_skipped(self):
        result = parse_csv_bytes(b"a,b\n1,2\n\n\n")
        self.assertEqual(len(result.rows), 1)

    def test_utf8_bom_handled(self):
        result = parse_csv_bytes(b"\xef\xbb\xbfa,b\n1,2\n")
        self.assertEqual(result.headers[0], "a")
        self.assertEqual(len(result.rows), 1)

    def test_utf8_content_decoded(self):
        result = parse_csv_bytes("nombre,nota\nMaría,95\n".encode("utf-8"))
        self.assertEqual(result.rows[0]["nombre"], "María")

    def test_windows1252_fallback(self):
        raw = "nombre,nota\nJosé,90\n".encode("windows-1252")
        result = parse_csv_bytes(raw)
        self.assertEqual(result.rows[0]["nombre"], "José")

    def test_cell_sanitization_applied_on_parse(self):
        result = parse_csv_bytes(b"note\n=1+1\n+SUM(x)\n@cmd\n-safe\n")
        self.assertTrue(result.rows[0]["note"].startswith("'"))
        self.assertTrue(result.rows[1]["note"].startswith("'"))
        self.assertTrue(result.rows[2]["note"].startswith("'"))
        self.assertTrue(result.rows[3]["note"].startswith("'"))

    def test_excessive_rows_rejected(self):
        many = "a,b\n" + "\n".join("1,2" for _ in range(MAX_IMPORT_ROWS + 1))
        with self.assertRaises(CsvValidationError):
            parse_csv_bytes(many.encode())


class CsvUploadValidationTest(DataImportApiBase):
    def test_invalid_extension_rejected(self):
        self._auth(self.admin_user)
        resp = self._upload("a,b\n1,2\n", name="grades.xlsx")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.INVALID_FILE_EXTENSION)

    def test_empty_file_rejected(self):
        # An empty file is rejected at the serializer level (allow_empty_file=False).
        self._auth(self.admin_user)
        resp = self._upload("")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_header_rejected(self):
        self._auth(self.admin_user)
        resp = self._upload("\nAlice,90\nBob,88\n")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.MISSING_REQUIRED_COLUMN)

    def test_max_file_size_enforced(self):
        self._auth(self.admin_user)
        with mock.patch(
            "apps.data_import.views.validate_raw_csv",
            side_effect=CsvValidationError(ImportErrorCode.FILE_TOO_LARGE, "too large"),
        ):
            resp = self._upload("a,b\n1,2\n", name="big.csv")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.FILE_TOO_LARGE)

    def test_malicious_filename_handled_safely(self):
        self._auth(self.admin_user)
        resp = self._upload("a,b\n1,2\n", name="C:\\evil\\..\\grades.csv")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        stored_name = ImportJob.objects.get(pk=resp.data["id"]).file.name
        self.assertNotIn("..", stored_name)
        self.assertNotIn("evil", stored_name)

    def test_malformed_csv_handled(self):
        # Unsupported UTF-16 BOM content is deterministically rejected -- the
        # pipeline refuses to mis-decode rather than silently corrupt data.
        self._auth(self.admin_user)
        raw = "a,b\n1,2\n".encode("utf-16")
        resp = self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": SimpleUploadedFile("grades.csv", raw, content_type="text/csv"), "import_type": "grades"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertTrue(job.error_log)

    def test_csv_injection_sanitized_on_upload(self):
        self._auth(self.admin_user)
        resp = self._upload("note\n=1+1\nAlice\n")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        rec = ImportRecord.objects.get(job__pk=resp.data["id"], row_number=1)
        self.assertTrue(rec.data["note"].startswith("'"))

    def test_safe_error_message_no_internals(self):
        self._auth(self.admin_user)
        resp = self._upload("a,,b\n1,2,3\n")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        body = str(job.error_log)
        self.assertNotIn("Traceback", body)
        self.assertNotIn("C:/", body)
        self.assertNotIn("\\Users", body)

    def test_no_path_traversal(self):
        self._auth(self.admin_user)
        resp = self._upload("a,b\n1,2\n", name="../../../etc/passwd")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.INVALID_FILE_EXTENSION)


# ---------------------------------------------------------------------------
# PH8.2 — Security: throttling
# ---------------------------------------------------------------------------


class ImportThrottlingTest(DataImportApiBase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_upload_throttled(self):
        self._auth(self.admin_user)
        with mock.patch.dict(
            "core.throttling.DataImportRateThrottle.THROTTLE_RATES",
            {"data_import": "1/min"},
        ):
            cache.clear()
            first = self.client.post(
                "/api/v1/data-import/jobs/",
                {"file": make_csv("a,b\n1,2\n"), "import_type": "grades"},
                format="multipart",
                REMOTE_ADDR="192.0.2.50",
            )
            self.assertEqual(first.status_code, status.HTTP_201_CREATED)
            second = self.client.post(
                "/api/v1/data-import/jobs/",
                {"file": make_csv("a,b\n1,2\n"), "import_type": "grades"},
                format="multipart",
                REMOTE_ADDR="192.0.2.50",
            )
            self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


# ===========================================================================
# PH8.4 — XLSX pipeline
# ===========================================================================

import datetime as dt
import io
import time
import zipfile

from openpyxl import Workbook

from apps.data_import.constants import (
    MAX_IMPORT_FILE_SIZE,
    XLSX_MAX_COLUMNS,
)
from apps.data_import.views import _detect_file_type
from apps.data_import.xlsx_pipeline import (
    XlsxValidationError,
    _select_worksheet,
    normalize_xlsx_cell,
    parse_xlsx_bytes,
    validate_raw_xlsx,
)

_XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_XLS_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def build_workbook_bytes(sheets):
    """
    Build an in-memory XLSX workbook.

    ``sheets`` is a list of dicts: ``title`` (str), and either ``rows``
    (iterable of row iterables, appended via ws.append) or ``cells``
    (mapping of coordinate -> value for sparse placement).  Optional
    ``state`` selects the sheet visibility ('visible' default).
    """
    wb = Workbook()
    wb.remove(wb.active)
    for spec in sheets:
        ws = wb.create_sheet(title=spec["title"])
        for row in spec.get("rows", ()):
            ws.append(row)
        for coord, value in spec.get("cells", {}).items():
            ws[coord] = value
        ws.sheet_state = spec.get("state", "visible")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def make_xlsx(sheets, name="grades.xlsx"):
    """Build a SimpleUploadedFile holding a real XLSX workbook."""
    return SimpleUploadedFile(
        name, build_workbook_bytes(sheets), content_type=_XLSX_MIME
    )


def _one_sheet(rows, title="Data"):
    return [{"title": title, "rows": rows}]


# ---------------------------------------------------------------------------
# PH8.4 — cell normalization
# ---------------------------------------------------------------------------


class XlsxCellNormalizeTest(SimpleTestCase):
    def test_none_becomes_empty(self):
        self.assertEqual(normalize_xlsx_cell(None), "")

    def test_boolean_true_false(self):
        self.assertEqual(normalize_xlsx_cell(True), "TRUE")
        self.assertEqual(normalize_xlsx_cell(False), "FALSE")

    def test_date_iso(self):
        self.assertEqual(normalize_xlsx_cell(dt.date(2026, 1, 15)), "2026-01-15")

    def test_datetime_iso(self):
        value = dt.datetime(2026, 1, 15, 8, 30, 45)
        self.assertEqual(normalize_xlsx_cell(value), "2026-01-15T08:30:45")

    def test_midnight_datetime_emitted_as_date(self):
        # openpyxl reads date-typed cells back as midnight datetimes.
        value = dt.datetime(2026, 1, 15, 0, 0, 0)
        self.assertEqual(normalize_xlsx_cell(value), "2026-01-15")

    def test_integer_string(self):
        self.assertEqual(normalize_xlsx_cell(90), "90")
        self.assertEqual(normalize_xlsx_cell(-5), "-5")

    def test_whole_float_drops_decimal(self):
        self.assertEqual(normalize_xlsx_cell(90.0), "90")

    def test_fractional_float_preserved(self):
        self.assertEqual(normalize_xlsx_cell(88.5), "88.5")

    def test_decimal_string(self):
        from decimal import Decimal

        self.assertEqual(normalize_xlsx_cell(Decimal("87.25")), "87.25")

    def test_string_collapsed_and_capped(self):
        self.assertEqual(normalize_xlsx_cell("  Alice   Smith  "), "Alice Smith")

    def test_string_injection_sanitized(self):
        for dangerous in ("=1+1", "+SUM(A1)", "@SUM(A1)", "\t=x"):
            self.assertTrue(normalize_xlsx_cell(dangerous).startswith("'"))

    def test_negative_number_preserved_not_sanitized(self):
        # A numeric (non-string) negative value is not a formula vector.
        self.assertEqual(normalize_xlsx_cell(-5), "-5")

    def test_negative_string_sanitized(self):
        # A *string* beginning with '-' is a potential injection vector.
        self.assertEqual(normalize_xlsx_cell("-5"), "'-5")

    def test_legitimate_string_untouched(self):
        self.assertEqual(normalize_xlsx_cell("20/20"), "20/20")
        self.assertEqual(normalize_xlsx_cell("B+"), "B+")

    def test_overlong_string_truncated(self):
        value = "x" * 5000
        self.assertLessEqual(len(normalize_xlsx_cell(value)), 4096)


# ---------------------------------------------------------------------------
# PH8.4 — workbook / header / data parsing
# ---------------------------------------------------------------------------


class XlsxParseTest(SimpleTestCase):
    def test_valid_single_sheet(self):
        result = parse_xlsx_bytes(
            build_workbook_bytes(_one_sheet([["name", "score"], ["Alice", 90], ["Bob", 88.5]]))
        )
        self.assertEqual(result.headers, ["name", "score"])
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.rows[0], {"name": "Alice", "score": "90"})
        self.assertEqual(result.rows[1]["score"], "88.5")

    def test_empty_worksheet_rejected(self):
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(_one_sheet([])))
        self.assertEqual(ctx.exception.code, ImportErrorCode.EMPTY_WORKSHEET)

    def test_missing_header_rejected(self):
        # Data exists below row 1 but no header row is present.
        sheets = [{"title": "D", "cells": {"A2": "Alice", "B2": 90}}]
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(sheets))
        self.assertEqual(ctx.exception.code, ImportErrorCode.MISSING_REQUIRED_COLUMN)

    def test_blank_headers_rejected(self):
        # A header row of empty strings is the XLSX analogue of a blank CSV
        # header line: treated as a missing header row.
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(_one_sheet([["", ""]])))
        self.assertEqual(ctx.exception.code, ImportErrorCode.MISSING_REQUIRED_COLUMN)

    def test_blank_col_gap_header_rejected(self):
        # Header present at A1 and C1 but B1 empty -> blank header cell.
        sheets = [{"title": "D", "cells": {"A1": "a", "C1": "c", "A2": 1, "C2": 2}}]
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(sheets))
        self.assertEqual(ctx.exception.code, ImportErrorCode.MALFORMED_HEADER)

    def test_duplicate_headers_rejected(self):
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(_one_sheet([["a", "a"]])))
        self.assertEqual(ctx.exception.code, ImportErrorCode.MALFORMED_HEADER)

    def test_whitespace_collision_headers_rejected(self):
        # Normalization collapses whitespace: the two headers become one.
        sheets = [{"title": "D", "rows": [["Student ID", "Student  ID"], [1, 2]]}]
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(sheets))
        self.assertEqual(ctx.exception.code, ImportErrorCode.MALFORMED_HEADER)

    def test_case_sensitive_headers_remain_distinct(self):
        # "Student ID" and "student_id" normalize to distinct names; no silent merge.
        sheets = [{"title": "D", "rows": [["Student ID", "student_id"], [1, 2]]}]
        result = parse_xlsx_bytes(build_workbook_bytes(sheets))
        self.assertEqual(result.headers, ["Student ID", "student_id"])
        self.assertEqual(result.rows[0], {"Student ID": "1", "student_id": "2"})

    def test_unknown_headers_preserved_for_domain_layer(self):
        # Parse layer accepts arbitrary columns; domain validators decide later.
        sheets = [{"title": "D", "rows": [["name", "extra_col"], ["Alice", "x"]]}]
        result = parse_xlsx_bytes(build_workbook_bytes(sheets))
        self.assertIn("extra_col", result.headers)
        self.assertEqual(result.rows[0]["extra_col"], "x")

    def test_multiple_worksheets_rejected(self):
        sheets = [
            {"title": "A", "rows": [["x"], [1]]},
            {"title": "B", "rows": [["y"], [2]]},
        ]
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(sheets))
        self.assertEqual(ctx.exception.code, ImportErrorCode.MULTIPLE_WORKSHEETS)
        # The message names the visible worksheets so the caller knows what
        # to pass back in the `sheet` field.
        self.assertIn("A", ctx.exception.message)
        self.assertIn("B", ctx.exception.message)

    def test_worksheet_selected_by_title(self):
        sheets = [
            {"title": "README", "rows": [["notes"], ["read me"]]},
            {"title": "Data", "rows": [["a", "b"], [1, 2]]},
        ]
        result = parse_xlsx_bytes(build_workbook_bytes(sheets), sheet="Data")
        self.assertEqual(result.headers, ["a", "b"])
        self.assertEqual(result.rows[0], {"a": "1", "b": "2"})

    def test_worksheet_selected_by_position(self):
        sheets = [
            {"title": "README", "rows": [["notes"], ["read me"]]},
            {"title": "Data", "rows": [["a", "b"], [1, 2]]},
        ]
        result = parse_xlsx_bytes(build_workbook_bytes(sheets), sheet="2")
        self.assertEqual(result.headers, ["a", "b"])

    def test_worksheet_title_trimmed(self):
        sheets = [
            {"title": "README", "rows": [["notes"], ["read me"]]},
            {"title": "Data", "rows": [["a"], [1]]},
        ]
        result = parse_xlsx_bytes(build_workbook_bytes(sheets), sheet="  Data  ")
        self.assertEqual(result.headers, ["a"])

    def test_unknown_worksheet_rejected(self):
        sheets = [
            {"title": "A", "rows": [["x"], [1]]},
            {"title": "B", "rows": [["y"], [2]]},
        ]
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(sheets), sheet="Missing")
        self.assertEqual(ctx.exception.code, ImportErrorCode.WORKSHEET_NOT_FOUND)
        self.assertIn("A", ctx.exception.message)
        self.assertIn("B", ctx.exception.message)

    def test_out_of_range_position_rejected(self):
        sheets = [
            {"title": "A", "rows": [["x"], [1]]},
            {"title": "B", "rows": [["y"], [2]]},
        ]
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(sheets), sheet="3")
        self.assertEqual(ctx.exception.code, ImportErrorCode.WORKSHEET_NOT_FOUND)

    def test_hidden_worksheet_cannot_be_selected(self):
        sheets = [
            {"title": "Visible", "rows": [["a"], [1]]},
            {"title": "Hidden", "rows": [["secret"], [9]], "state": "hidden"},
        ]
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(sheets), sheet="Hidden")
        self.assertEqual(ctx.exception.code, ImportErrorCode.WORKSHEET_NOT_FOUND)

    def test_named_worksheet_ignores_other_sheets(self):
        # Selecting one sheet never validates or imports the others: the
        # malformed sheet below is not read at all.
        sheets = [
            {"title": "Good", "rows": [["a", "b"], [1, 2]]},
            {"title": "Broken", "rows": [["x", "x"], [1, 2]]},
        ]
        result = parse_xlsx_bytes(build_workbook_bytes(sheets), sheet="Good")
        self.assertEqual(result.headers, ["a", "b"])
        self.assertEqual(len(result.rows), 1)

    def test_hidden_worksheet_skipped(self):
        sheets = [
            {"title": "Visible", "rows": [["a", "b"], [1, 2]]},
            {"title": "Hidden", "rows": [["secret"], [9]], "state": "hidden"},
        ]
        result = parse_xlsx_bytes(build_workbook_bytes(sheets))
        self.assertEqual(result.headers, ["a", "b"])
        self.assertEqual(len(result.rows), 1)
        self.assertNotIn("secret", result.headers)

    def test_all_hidden_rejected(self):
        # openpyxl refuses to *save* an all-hidden workbook, so exercise the
        # selection logic directly: no visible worksheet -> EMPTY_WORKSHEET.
        wb = Workbook()
        ws = wb.active
        ws.sheet_state = "hidden"
        with self.assertRaises(XlsxValidationError) as ctx:
            _select_worksheet(wb)
        self.assertEqual(ctx.exception.code, ImportErrorCode.EMPTY_WORKSHEET)

    def test_unicode_filipino_content(self):
        rows = [
            ["first_name", "last_name", "city"],
            ["Juan", "Dela Cruz", "Cebu City"],
            ["María", "José", "Muntinlupa"],
            ["Súan", "Reyes", "Quezón City"],
        ]
        result = parse_xlsx_bytes(build_workbook_bytes(_one_sheet(rows)))
        self.assertEqual(result.rows[0]["city"], "Cebu City")
        self.assertEqual(result.rows[1]["first_name"], "María")
        self.assertEqual(result.rows[2]["last_name"], "Reyes")
        self.assertEqual(result.rows[2]["city"], "Quezón City")

    def test_numeric_values(self):
        rows = [["a", "b"], [1, 2.5], [3, 4.0]]
        result = parse_xlsx_bytes(build_workbook_bytes(_one_sheet(rows)))
        self.assertEqual(result.rows[0], {"a": "1", "b": "2.5"})
        self.assertEqual(result.rows[1]["b"], "4")

    def test_date_values(self):
        rows = [
            ["date", "ts"],
            [dt.date(2026, 1, 15), dt.datetime(2026, 1, 15, 8, 30, 0)],
        ]
        result = parse_xlsx_bytes(build_workbook_bytes(_one_sheet(rows)))
        self.assertEqual(result.rows[0]["date"], "2026-01-15")
        self.assertEqual(result.rows[0]["ts"], "2026-01-15T08:30:00")

    def test_boolean_values(self):
        rows = [["flag"], [True], [False]]
        result = parse_xlsx_bytes(build_workbook_bytes(_one_sheet(rows)))
        self.assertEqual(result.rows[0]["flag"], "TRUE")
        self.assertEqual(result.rows[1]["flag"], "FALSE")

    def test_blank_cells_become_empty_strings(self):
        rows = [["a", "b"], ["x", None]]
        result = parse_xlsx_bytes(build_workbook_bytes(_one_sheet(rows)))
        self.assertEqual(result.rows[0], {"a": "x", "b": ""})

    def test_formula_cells_not_executed(self):
        # A formula cell with no cached value reads back as None -> "".
        rows = [["a", "b", "sum"], [1, 2, "=A2+B2"]]
        result = parse_xlsx_bytes(build_workbook_bytes(_one_sheet(rows)))
        self.assertEqual(result.rows[0]["sum"], "")

    def test_negative_numbers_preserved(self):
        rows = [["n"], [-5], [-7.25]]
        result = parse_xlsx_bytes(build_workbook_bytes(_one_sheet(rows)))
        self.assertEqual(result.rows[0]["n"], "-5")
        self.assertEqual(result.rows[1]["n"], "-7.25")

    def test_excessive_columns_rejected(self):
        header = [f"c{i}" for i in range(XLSX_MAX_COLUMNS + 1)]
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(_one_sheet([header])))
        self.assertEqual(ctx.exception.code, ImportErrorCode.BAD_COLUMN_COUNT)

    def test_excessive_rows_rejected(self):
        import apps.data_import.constants as constants

        limit = constants.MAX_IMPORT_ROWS
        rows = [["a", "b"]] + [[i, i] for i in range(limit + 1)]
        with self.assertRaises(XlsxValidationError) as ctx:
            parse_xlsx_bytes(build_workbook_bytes(_one_sheet(rows)))
        self.assertEqual(ctx.exception.code, ImportErrorCode.INVALID_FILE_CONTENT)

    def test_large_string_truncated_on_parse(self):
        big = "z" * 6000
        result = parse_xlsx_bytes(build_workbook_bytes(_one_sheet([["note"], [big]])))
        self.assertLessEqual(len(result.rows[0]["note"]), 4096)


# ---------------------------------------------------------------------------
# PH8.4 — file-level validation
# ---------------------------------------------------------------------------


class XlsxFileValidationTest(SimpleTestCase):
    def _file(self, content, name="grades.xlsx"):
        return SimpleUploadedFile(name, content, content_type=_XLSX_MIME)

    def test_extension_and_magic_checked(self):
        self.assertEqual(_detect_file_type(self._file(b"PK\x03\x04rest")), FileType.XLSX)
        self.assertEqual(_detect_file_type(self._file(b"a,b\n1,2\n")), FileType.CSV)

    def test_non_xlsx_extension_rejected(self):
        content = build_workbook_bytes(_one_sheet([["a"], [1]]))
        with self.assertRaises(XlsxValidationError) as ctx:
            validate_raw_xlsx(self._file(content, name="grades.csv"), "grades.csv")
        self.assertEqual(ctx.exception.code, ImportErrorCode.INVALID_FILE_EXTENSION)

    def test_dot_xls_extension_rejected(self):
        content = build_workbook_bytes(_one_sheet([["a"], [1]]))
        with self.assertRaises(XlsxValidationError) as ctx:
            validate_raw_xlsx(self._file(content, name="grades.xls"), "grades.xls")
        self.assertEqual(ctx.exception.code, ImportErrorCode.INVALID_FILE_EXTENSION)

    def test_empty_bytes_rejected(self):
        with self.assertRaises(XlsxValidationError) as ctx:
            validate_raw_xlsx(self._file(b""), "grades.xlsx")
        self.assertEqual(ctx.exception.code, ImportErrorCode.FILE_EMPTY)

    def test_text_renamed_xlsx_rejected(self):
        with self.assertRaises(XlsxValidationError) as ctx:
            validate_raw_xlsx(self._file(b"a,b\n1,2\n"), "grades.xlsx")
        self.assertEqual(ctx.exception.code, ImportErrorCode.INVALID_FILE_CONTENT)

    def test_corrupt_xlsx_rejected(self):
        corrupt = b"PK\x03\x04" + b"\x00" * 128
        with self.assertRaises(XlsxValidationError) as ctx:
            validate_raw_xlsx(self._file(corrupt), "grades.xlsx")
        self.assertEqual(ctx.exception.code, ImportErrorCode.INVALID_WORKBOOK)

    def test_non_workbook_zip_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("notes.txt", "not an OOXML workbook")
        with self.assertRaises(XlsxValidationError) as ctx:
            validate_raw_xlsx(self._file(buf.getvalue()), "grades.xlsx")
        self.assertEqual(ctx.exception.code, ImportErrorCode.INVALID_WORKBOOK)

    def test_oversize_rejected(self):
        content = build_workbook_bytes(_one_sheet([["a"], [1]]))
        with self.assertRaises(XlsxValidationError) as ctx:
            validate_raw_xlsx(
                self._file(content), "grades.xlsx",
                size=MAX_IMPORT_FILE_SIZE + 1,
            )
        self.assertEqual(ctx.exception.code, ImportErrorCode.FILE_TOO_LARGE)

    def test_malicious_filename_sanitized(self):
        content = build_workbook_bytes(_one_sheet([["a", "b"], [1, 2]]))
        result = validate_raw_xlsx(
            self._file(content, name="C:\\evil\\..\\grades.xlsx"),
            "C:\\evil\\..\\grades.xlsx",
        )
        self.assertEqual(result.headers, ["a", "b"])


# ---------------------------------------------------------------------------
# PH8.4 — API integration
# ---------------------------------------------------------------------------


class XlsxImportApiBase(DataImportApiBase):
    def _upload_xlsx(self, sheets, import_type="grades", name="grades.xlsx", sheet=None):
        payload = {"file": make_xlsx(sheets, name=name), "import_type": import_type}
        if sheet is not None:
            payload["sheet"] = sheet
        return self.client.post(
            "/api/v1/data-import/jobs/",
            payload,
            format="multipart",
        )


class XlsxUploadApiTest(XlsxImportApiBase):
    def test_valid_xlsx_job_success(self):
        dom = _build_grade_domain("xlsx")
        gp2 = GradingPeriod.objects.create(
            academic_year=dom["ay"], name="Q2", order=2,
            start_date="2025-09-01", end_date="2025-11-30",
        )
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet([
            ["student_id", "subject_assignment", "grading_period", "score"],
            [dom["student_id"], dom["subject_assignment"], dom["grading_period"], 90],
            [dom["student_id"], dom["subject_assignment"], str(gp2.pk), 88],
        ]))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.file_type, FileType.XLSX)
        self.assertEqual(job.import_type, ImportType.GRADES)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.total_rows, 2)
        self.assertEqual(job.processed_rows, 2)
        self.assertEqual(job.error_rows, 0)
        self.assertEqual(job.records.count(), 2)
        rec = job.records.get(row_number=1)
        self.assertEqual(rec.status, RecordStatus.SUCCESS)
        self.assertEqual(rec.mapped_to_model, "Grade")
        self.assertEqual(Grade.objects.count(), 2)

    def test_file_type_recorded_as_xlsx(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet([["a", "b"], [1, 2]]))
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.file_type, "xlsx")
        self.assertEqual(resp.data["file_type"], "xlsx")

    def test_faculty_can_import_attendance_xlsx(self):
        self._auth(self.faculty_user)
        resp = self._upload_xlsx(
            _one_sheet([["student_id", "date", "status"], ["S1", dt.date(2026, 1, 15), "present"]]),
            import_type="attendance",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["import_type"], "attendance")

    def test_faculty_cannot_import_students_xlsx(self):
        self._auth(self.faculty_user)
        resp = self._upload_xlsx(_one_sheet([["student_id", "name"], ["S1", "Ann"]]), import_type="students")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_cannot_upload_xlsx(self):
        self._auth(self.student_user)
        resp = self._upload_xlsx(_one_sheet([["a", "b"], [1, 2]]))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dot_xls_rejected(self):
        self._auth(self.admin_user)
        resp = self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": SimpleUploadedFile("grades.xls", _XLS_HEADER + b"\x00" * 32), "import_type": "grades"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.INVALID_FILE_EXTENSION)

    def test_xlsx_renamed_xls_rejected(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet([["a"], [1]]), name="grades.xls")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.INVALID_FILE_EXTENSION)

    def test_invalid_extension_rejected(self):
        self._auth(self.admin_user)
        resp = self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": SimpleUploadedFile("grades.txt", b"a,b\n1,2\n"), "import_type": "grades"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.INVALID_FILE_EXTENSION)

    def test_empty_file_rejected_at_serializer(self):
        self._auth(self.admin_user)
        resp = self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": SimpleUploadedFile("grades.xlsx", b"", content_type=_XLSX_MIME), "import_type": "grades"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_text_renamed_xlsx_rejected(self):
        # Non-ZIP content is routed to the CSV pipeline, which then rejects
        # the mislabeled ".xlsx" extension.
        self._auth(self.admin_user)
        resp = self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": SimpleUploadedFile("grades.xlsx", b"a,b\n1,2\n", content_type=_XLSX_MIME), "import_type": "grades"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.INVALID_FILE_EXTENSION)

    def test_corrupt_xlsx_rejected(self):
        self._auth(self.admin_user)
        resp = self._upload_bytes(b"PK\x03\x04" + b"\x00" * 128)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.INVALID_WORKBOOK)

    def test_non_workbook_zip_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("notes.txt", "not a workbook")
        self._auth(self.admin_user)
        resp = self._upload_bytes(buf.getvalue())
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.INVALID_WORKBOOK)

    def _upload_bytes(self, content, name="grades.xlsx"):
        return self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": SimpleUploadedFile(name, content, content_type=_XLSX_MIME), "import_type": "grades"},
            format="multipart",
        )

    def test_multiple_worksheets_rejected(self):
        self._auth(self.admin_user)
        sheets = [
            {"title": "A", "rows": [["x"], [1]]},
            {"title": "B", "rows": [["y"], [2]]},
        ]
        resp = self._upload_xlsx(sheets)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.MULTIPLE_WORKSHEETS)

    def test_named_sheet_imported(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(
            [
                {"title": "README", "rows": [["note"], ["read me"]]},
                {"title": "Data", "rows": [["x"], [1]]},
            ],
            sheet="Data",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        record = ImportRecord.objects.get(job=job, row_number=1)
        self.assertEqual(record.data, {"x": "1"})
        # The named sheet is the one read, so the file is not rejected for
        # having two worksheets.  It still fails header validation, because
        # "x" is not a grade column, and the job now says so (TC-FAC-12/14).
        codes = [entry["code"] for entry in job.error_log]
        self.assertNotIn(ImportErrorCode.MULTIPLE_WORKSHEETS, codes)
        self.assertEqual(codes, [ImportErrorCode.MISSING_REQUIRED_COLUMN])

    def test_worksheet_position_imported(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(
            [
                {"title": "README", "rows": [["note"], ["read me"]]},
                {"title": "Data", "rows": [["x"], [1]]},
            ],
            sheet="2",
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertTrue(ImportRecord.objects.filter(job=job).exists())
        # Read by position, so the two-sheet file is not the rejection.
        codes = [entry["code"] for entry in job.error_log]
        self.assertNotIn(ImportErrorCode.MULTIPLE_WORKSHEETS, codes)
        self.assertEqual(codes, [ImportErrorCode.MISSING_REQUIRED_COLUMN])

    def test_unknown_sheet_rejected_on_upload(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(
            [
                {"title": "A", "rows": [["x"], [1]]},
                {"title": "B", "rows": [["y"], [2]]},
            ],
            sheet="Missing",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.WORKSHEET_NOT_FOUND)

    def test_blank_sheet_field_behaves_as_unnamed(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(
            [
                {"title": "A", "rows": [["x"], [1]]},
                {"title": "B", "rows": [["y"], [2]]},
            ],
            sheet="",
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.MULTIPLE_WORKSHEETS)

    def test_empty_worksheet_rejected(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet([]))
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.EMPTY_WORKSHEET)

    def test_duplicate_headers_rejected(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet([["a", "a"], [1, 2]]))
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.MALFORMED_HEADER)

    def test_xlsx_injection_sanitized_on_upload(self):
        # NB: openpyxl turns any cell value starting with "=" into a formula
        # (reads back empty in data_only mode — safe), so string-based
        # injection is tested via the "+" / "@" prefixes.
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet([["note"], ["+SUM(A1:A9)"], ["Alice"]]))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        rec = ImportRecord.objects.get(job__pk=resp.data["id"], row_number=1)
        self.assertTrue(rec.data["note"].startswith("'"))

    def test_formula_cell_never_executed_on_upload(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet([["a", "b"], [1, "=1+1"]]))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        rec = ImportRecord.objects.get(job__pk=resp.data["id"], row_number=1)
        # No cached value: the formula is read back as an empty string.
        self.assertEqual(rec.data["b"], "")

    def test_negative_numbers_preserved_on_upload(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet([["score"], [-5], [-7.5]]))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        rec = ImportRecord.objects.get(job__pk=resp.data["id"], row_number=1)
        self.assertEqual(rec.data["score"], "-5")

    def test_unicode_xlsx_round_trip_on_upload(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(
            _one_sheet([["first_name", "last_name"], ["María", "José"], ["Juan", "Dela Cruz"]])
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        rec = ImportRecord.objects.get(job__pk=resp.data["id"], row_number=1)
        self.assertEqual(rec.data["first_name"], "María")
        self.assertEqual(rec.data["last_name"], "José")

    def test_oversize_mocked_rejected(self):
        self._auth(self.admin_user)
        with mock.patch(
            "apps.data_import.views.validate_raw_xlsx",
            side_effect=XlsxValidationError(ImportErrorCode.FILE_TOO_LARGE, "too large"),
        ):
            resp = self._upload_xlsx(_one_sheet([["a"], [1]]), name="big.xlsx")
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.FILE_TOO_LARGE)

    def test_excessive_rows_rejected_on_upload(self):
        import apps.data_import.constants as constants

        limit = constants.MAX_IMPORT_ROWS
        rows = [["a", "b"]] + [[i, i] for i in range(limit + 1)]
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet(rows))
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], ImportErrorCode.INVALID_FILE_CONTENT)

    def test_malicious_filename_xlsx_handled_safely(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(
            _one_sheet([["a", "b"], [1, 2]]),
            name="C:\\evil\\..\\grades.xlsx",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        stored_name = ImportJob.objects.get(pk=resp.data["id"]).file.name
        self.assertNotIn("..", stored_name)
        self.assertNotIn("evil", stored_name)

    def test_no_internals_leaked_on_failure(self):
        self._auth(self.admin_user)
        resp = self._upload_bytes(b"PK\x03\x04" + b"\x00" * 128)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        body = str(job.error_log) + str(resp.data)
        self.assertNotIn("Traceback", body)
        self.assertNotIn("C:/", body)
        self.assertNotIn("\\Users", body)
        self.assertNotIn("SECRET_KEY", body)
        self.assertNotIn("password", body.lower())

    def test_job_status_transitions_completed(self):
        dom = _build_grade_domain("trans")
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet([
            ["student_id", "subject_assignment", "grading_period", "score"],
            [dom["student_id"], dom["subject_assignment"], dom["grading_period"], 91],
        ]))
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertIsNotNone(job.completed_at)
        self.assertEqual(job.records.count(), 1)
        self.assertEqual(Grade.objects.count(), 1)

    def test_no_sensitive_details_in_list_retrieve(self):
        job = ImportJob.objects.create(
            uploaded_by=self.admin_user,
            file=make_xlsx(_one_sheet([["a"], [1]]), name="grades.xlsx"),
            file_type=FileType.XLSX,
            import_type=ImportType.GRADES,
            status=JobStatus.COMPLETED,
        )
        ImportRecord.objects.create(job=job, row_number=1, data={"a": "1"}, status=RecordStatus.SUCCESS)
        self._auth(self.admin_user)
        resp = self.client.get(f"/api/v1/data-import/jobs/{job.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = str(resp.data)
        self.assertNotIn("SECRET_KEY", body)
        self.assertNotIn("password", body.lower())
        self.assertNotIn("C:/", body)
        self.assertNotIn("\\Users", body)


# ---------------------------------------------------------------------------
# PH8.4 — throttling
# ---------------------------------------------------------------------------


class XlsxImportThrottlingTest(XlsxImportApiBase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_xlsx_upload_throttled(self):
        self._auth(self.admin_user)
        with mock.patch.dict(
            "core.throttling.DataImportRateThrottle.THROTTLE_RATES",
            {"data_import": "1/min"},
        ):
            cache.clear()
            first = self.client.post(
                "/api/v1/data-import/jobs/",
                {"file": make_xlsx(_one_sheet([["a"], [1]])), "import_type": "grades"},
                format="multipart",
                REMOTE_ADDR="192.0.2.60",
            )
            self.assertEqual(first.status_code, status.HTTP_201_CREATED)
            second = self.client.post(
                "/api/v1/data-import/jobs/",
                {"file": make_xlsx(_one_sheet([["a"], [1]])), "import_type": "grades"},
                format="multipart",
                REMOTE_ADDR="192.0.2.60",
            )
            self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


# ===========================================================================
# PH8.5 — Grade Import
# ===========================================================================
#
# These tests verify that grade imports write REAL Grade records through the
# domain path (SEC-013), enforce faculty scope, handle duplicates and errors,
# and keep job counters/records accurate.  They use real academic fixtures
# (students, enrollments, sections, subjects, assignments, grading periods).


def _rows_csv(headers, rows):
    """Build a CSV body string from a header list and row-lists."""
    return "\n".join(
        [",".join(headers)] + [",".join(str(c) for c in r) for r in rows]
    ) + "\n"


class GradeImportApiTest(DataImportApiBase):
    def setUp(self):
        super().setUp()
        self.dom = _build_grade_domain("gi")
        self.HEAD = ["student_id", "subject_assignment", "grading_period", "score"]

    def _grade_upload(self, headers, rows, user="admin", import_type="grades"):
        if user == "admin":
            user = self.admin_user
        self._auth(user)
        return self._upload(_rows_csv(headers, rows), import_type=import_type)

    def _upload_xlsx(self, sheets, import_type="grades"):
        return self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": make_xlsx(sheets), "import_type": import_type},
            format="multipart",
        )


class GradeImportDomainTest(GradeImportApiTest):
    def test_valid_grade_import_creates_record(self):
        resp = self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 90]],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        grade = Grade.objects.get()
        self.assertEqual(grade.student.student_id, self.dom["student_id"])
        self.assertEqual(grade.subject_assignment_id, __import__("uuid").UUID(self.dom["subject_assignment"]))
        self.assertEqual(grade.score, __import__("decimal").Decimal("90"))
        self.assertEqual(grade.status, Grade.StatusChoices.DRAFT)

    def test_valid_multiple_row_import(self):
        gp2 = GradingPeriod.objects.create(
            academic_year=self.dom["ay"], name="Q2", order=2,
            start_date="2025-09-01", end_date="2025-11-30",
        )
        resp = self._grade_upload(
            self.HEAD,
            [
                [self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 90],
                [self.dom["student_id"], self.dom["subject_assignment"], str(gp2.pk), 88],
            ],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.processed_rows, 2)
        self.assertEqual(Grade.objects.count(), 2)

    def test_missing_required_column_rejected(self):
        # File-level: header omits 'score'.
        resp = self._grade_upload(
            ["student_id", "subject_assignment", "grading_period"],
            [[self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"]]],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_rows, 1)
        rec = job.records.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertIn("Missing required column", rec.error_message)
        self.assertEqual(Grade.objects.count(), 0)

    def test_missing_required_value_rejected(self):
        # Row-level: 'score' column present but empty.
        resp = self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], ""]],
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        rec = job.records.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertEqual(Grade.objects.count(), 0)

    def test_unknown_column_rejected(self):
        resp = self._grade_upload(
            self.HEAD + ["bogus_column"],
            [[self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 90, "x"]],
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        rec = job.records.get()
        self.assertIn("Unknown column", rec.error_message)

    def test_invalid_student_rejected(self):
        self._grade_upload(
            self.HEAD,
            [["NO-SUCH-STUDENT", self.dom["subject_assignment"], self.dom["grading_period"], 90]],
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertEqual(Grade.objects.count(), 0)

    def test_invalid_enrollment_rejected(self):
        # Student exists but is not enrolled -> SEC-013 rejects.
        su_user = User.objects.create_user(
            email="unenrolled@test.com", password="pass12345", role="student",
        )
        StudentProfile.objects.create(
            user=su_user, student_id="STU-NOT-ENROLLED", enrollment_date="2025-06-01",
        )
        self._grade_upload(
            self.HEAD,
            [["STU-NOT-ENROLLED", self.dom["subject_assignment"], self.dom["grading_period"], 90]],
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertIn("not actively enrolled", rec.error_message)
        self.assertEqual(Grade.objects.count(), 0)

    def test_inactive_enrollment_rejected(self):
        # Enrollment exists but is inactive -> SEC-013 rejects.
        su_user = User.objects.create_user(
            email="inactive@test.com", password="pass12345", role="student",
        )
        sp = StudentProfile.objects.create(
            user=su_user, student_id="STU-INACTIVE", enrollment_date="2025-06-01",
        )
        Enrollment.objects.create(
            student=sp, section=self.dom["section_obj"], academic_year=self.dom["ay"],
            date_enrolled="2025-06-01", is_active=False,
        )
        self._grade_upload(
            self.HEAD,
            [["STU-INACTIVE", self.dom["subject_assignment"], self.dom["grading_period"], 90]],
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertEqual(Grade.objects.count(), 0)

    def test_invalid_subject_assignment_rejected(self):
        self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], "11111111-1111-1111-1111-111111111111", self.dom["grading_period"], 90]],
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertEqual(Grade.objects.count(), 0)

    def test_unknown_import_error_codes_safe(self):
        self._grade_upload(
            self.HEAD,
            [["NO-SUCH-STUDENT", self.dom["subject_assignment"], self.dom["grading_period"], 90]],
        )
        rec = ImportRecord.objects.get()
        body = rec.error_message
        self.assertNotIn("Traceback", body)
        self.assertNotIn("C:/", body)
        self.assertNotIn("SELECT", body.upper())

    def test_wrong_academic_year_rejected(self):
        # A grading period belonging to a DIFFERENT academic year than the
        # subject assignment triggers the SEC-013 academic-year mismatch.
        other_ay = AcademicYear.objects.create(
            name="2030-2031", start_date="2030-06-01", end_date="2031-03-31",
        )
        other_gp = GradingPeriod.objects.create(
            academic_year=other_ay, name="OtherQ", order=1,
            start_date="2030-06-01", end_date="2030-08-31",
        )
        self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["subject_assignment"], str(other_gp.pk), 90]],
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertIn("Grading period", rec.error_message)
        self.assertEqual(Grade.objects.count(), 0)

    def test_invalid_grading_period_rejected(self):
        self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["subject_assignment"], "22222222-2222-2222-2222-222222222222", 90]],
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertEqual(Grade.objects.count(), 0)

    def test_invalid_grade_value_rejected(self):
        for bad in ("150", "-1", "-5", "abc"):
            resp = self._grade_upload(
                self.HEAD,
                [[self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], bad]],
            )
            job = ImportJob.objects.get(pk=resp.data["id"])
            rec = job.records.get()
            self.assertEqual(rec.status, RecordStatus.ERROR)
            self.assertIn("0 and 100", rec.error_message)
            self.assertEqual(Grade.objects.count(), 0)

    def test_faculty_allowed_import(self):
        self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 92]],
            user=self.dom["faculty_profile"].user,
        )
        self.assertEqual(Grade.objects.count(), 1)

    def test_faculty_scope_violation_rejected(self):
        # Faculty authenticated user tries to grade using another faculty's assignment.
        self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["other_subject_assignment"], self.dom["grading_period"], 92]],
            user=self.dom["faculty_profile"].user,
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertIn("not authorized", rec.error_message)
        self.assertEqual(Grade.objects.count(), 0)

    def test_admin_import_allowed(self):
        # Admin can import for any assignment (no faculty scope restriction).
        self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["other_subject_assignment"], self.dom["grading_period"], 85]],
            user=self.admin_user,
        )
        self.assertEqual(Grade.objects.count(), 1)

    def test_duplicate_row_in_same_file_rejected(self):
        resp = self._grade_upload(
            self.HEAD,
            [
                [self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 90],
                [self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 91],
            ],
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.PARTIAL)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 1)
        self.assertEqual(Grade.objects.count(), 1)
        second = job.records.get(row_number=2)
        self.assertEqual(second.status, RecordStatus.ERROR)
        self.assertIn("duplicates another row", second.error_message)

    def test_existing_grade_is_updated_in_place(self):
        # A re-upload applies the corrected score (schools re-upload a
        # corrected sheet); it is not a duplicate error.
        existing = Grade.objects.create(
            student=self.dom["student_profile"],
            subject_assignment=SubjectAssignment.objects.get(pk=self.dom["subject_assignment"]),
            grading_period=GradingPeriod.objects.get(pk=self.dom["grading_period"]),
            score=__import__("decimal").Decimal("70"),
            encoded_by=self.dom["faculty_profile"],
            status=Grade.StatusChoices.DRAFT,
        )
        resp = self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 88]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.COMPLETED)
        rec = job.records.get()
        self.assertEqual(rec.status, RecordStatus.SUCCESS)
        self.assertEqual(Grade.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.score, __import__("decimal").Decimal("88"))
        self.assertEqual(existing.status, Grade.StatusChoices.DRAFT)

    def test_finalized_grade_is_locked(self):
        # A finalized grade is a signed academic record: the importer
        # refuses to overwrite it.
        finalized = Grade.objects.create(
            student=self.dom["student_profile"],
            subject_assignment=SubjectAssignment.objects.get(pk=self.dom["subject_assignment"]),
            grading_period=GradingPeriod.objects.get(pk=self.dom["grading_period"]),
            score=__import__("decimal").Decimal("70"),
            encoded_by=self.dom["faculty_profile"],
            status=Grade.StatusChoices.FINALIZED,
        )
        resp = self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 88]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        rec = job.records.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertIn("finalized", rec.error_message)
        finalized.refresh_from_db()
        self.assertEqual(finalized.score, __import__("decimal").Decimal("70"))

    def test_school_keys_resolve_the_subject_assignment(self):
        # section name + subject_code instead of the assignment UUID.
        section = self.dom["section_obj"]
        assignment = SubjectAssignment.objects.get(pk=self.dom["subject_assignment"])
        period_name = GradingPeriod.objects.get(pk=self.dom["grading_period"]).name
        resp = self._grade_upload(
            ["student_id", "section", "subject_code", "grading_period", "score"],
            [[
                self.dom["student_id"],
                f"{section.grade_level.name} - {section.name}",
                assignment.subject.code,
                period_name,
                91,
            ]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.COMPLETED, job.records.get().error_message)
        grade = Grade.objects.get()
        self.assertEqual(grade.subject_assignment_id, assignment.pk)
        self.assertEqual(grade.score, __import__("decimal").Decimal("91"))

    def test_missing_subject_key_columns_rejected(self):
        # Neither subject_assignment nor section + subject_code -> header error.
        resp = self._grade_upload(
            ["student_id", "grading_period", "score"],
            [[self.dom["student_id"], self.dom["grading_period"], 90]],
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertIn("subject_assignment", job.records.get().error_message)
        self.assertEqual(Grade.objects.count(), 0)

    def test_ambiguous_section_name_rejected(self):
        # Two sections share the bare name; the bare name is ambiguous, the
        # full "Grade N - Name" form still resolves.
        section = self.dom["section_obj"]
        other_level = GradeLevel.objects.create(name="Grade 8gi", level_number=8)
        Section.objects.create(
            name=section.name, grade_level=other_level, academic_year=self.dom["ay"],
        )
        assignment = SubjectAssignment.objects.get(pk=self.dom["subject_assignment"])
        self.client.force_authenticate(user=self.admin_user)
        self._grade_upload(
            ["student_id", "section", "subject_code", "grading_period", "score"],
            [[self.dom["student_id"], section.name, assignment.subject.code, "Q1gi", 90]],
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertIn("matches more than one section", rec.error_message)
        self.assertEqual(Grade.objects.count(), 0)

    def test_student_and_parent_denied(self):
        for user in (self.student_user, self.parent_user):
            self.client.force_authenticate(user=None)
            resp = self._grade_upload(
                self.HEAD,
                [[self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 90]],
                user=user,
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Grade.objects.count(), 0)

    def test_import_record_mapping(self):
        resp = self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 94]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        rec = job.records.get()
        self.assertEqual(rec.mapped_to_model, "Grade")
        grade = Grade.objects.get()
        self.assertEqual(rec.mapped_to_id, grade.pk)
        self.assertEqual(rec.data["student_id"], self.dom["student_id"])

    def test_job_counters_accurate(self):
        gp2 = GradingPeriod.objects.create(
            academic_year=self.dom["ay"], name="Q2", order=2,
            start_date="2025-09-01", end_date="2025-11-30",
        )
        resp = self._grade_upload(
            self.HEAD,
            [
                [self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 90],
                ["NO-SUCH", self.dom["subject_assignment"], self.dom["grading_period"], 90],
                [self.dom["student_id"], self.dom["subject_assignment"], str(gp2.pk), 88],
            ],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.total_rows, 3)
        self.assertEqual(job.processed_rows, 2)
        self.assertEqual(job.error_rows, 1)
        self.assertEqual(job.status, JobStatus.PARTIAL)

    def test_all_error_job_is_failed(self):
        resp = self._grade_upload(
            self.HEAD,
            [["NO-SUCH", self.dom["subject_assignment"], self.dom["grading_period"], 90]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.processed_rows, 0)
        self.assertEqual(job.error_rows, 1)

    def test_transaction_isolation(self):
        # A valid row and an invalid row coexist: only the valid row persists.
        gp2 = GradingPeriod.objects.create(
            academic_year=self.dom["ay"], name="Q2", order=2,
            start_date="2025-09-01", end_date="2025-11-30",
        )
        resp = self._grade_upload(
            self.HEAD,
            [
                ["NO-SUCH", self.dom["subject_assignment"], self.dom["grading_period"], 90],
                [self.dom["student_id"], self.dom["subject_assignment"], str(gp2.pk), 88],
            ],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.PARTIAL)
        self.assertEqual(Grade.objects.count(), 1)
        good = job.records.get(row_number=2)
        self.assertEqual(good.status, RecordStatus.SUCCESS)

    def test_database_failure_isolated_to_row(self):
        # A database failure on one row must not crash the job nor roll back
        # the successful row.
        gp2 = GradingPeriod.objects.create(
            academic_year=self.dom["ay"], name="Q2", order=2,
            start_date="2025-09-01", end_date="2025-11-30",
        )
        payload = _rows_csv(
            self.HEAD,
            [
                [self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 90],
                [self.dom["student_id"], self.dom["subject_assignment"], str(gp2.pk), 88],
            ],
        )
        self._auth(self.admin_user)
        import apps.data_import.importers.grades as grades_mod

        real_save = Grade.save
        calls = {"n": 0}

        def flaky_save(self2, *a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("simulated db failure")
            return real_save(self2, *a, **k)

        with mock.patch.object(grades_mod.Grade, "save", flaky_save):
            resp = self._upload(payload)
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.PARTIAL)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 1)
        self.assertEqual(Grade.objects.count(), 1)
        failed = job.records.get(row_number=2)
        self.assertEqual(failed.status, RecordStatus.ERROR)
        self.assertIn("could not be processed", failed.error_message)


class GradeImportFormatTest(GradeImportApiTest):
    def test_csv_source_works(self):
        resp = self._grade_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 90]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.file_type, FileType.CSV)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(Grade.objects.count(), 1)

    def test_xlsx_source_works(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet([
            self.HEAD,
            [self.dom["student_id"], self.dom["subject_assignment"], self.dom["grading_period"], 90],
        ]))
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.file_type, FileType.XLSX)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(Grade.objects.count(), 1)


# ===========================================================================
# PH8.6 — Attendance Import
# ===========================================================================


class AttendanceImportApiTest(DataImportApiBase):
    def setUp(self):
        super().setUp()
        self.dom = _build_attendance_domain("ai")
        self.HEAD = ["student_id", "section", "date", "status"]

    def _att_upload(self, headers, rows, user="admin", import_type="attendance"):
        if user == "admin":
            user = self.admin_user
        self._auth(user)
        return self._upload(_rows_csv(headers, rows), import_type=import_type)

    def _upload_xlsx(self, sheets, import_type="attendance"):
        return self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": make_xlsx(sheets), "import_type": import_type},
            format="multipart",
        )


class AttendanceImportDomainTest(AttendanceImportApiTest):
    VALID_DATE = "2026-02-15"

    def test_valid_attendance_import_creates_record(self):
        resp = self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], self.VALID_DATE, "present"]],
            user=self.admin_user,
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        rec = AttendanceRecord.objects.get()
        self.assertEqual(rec.student.student_id, self.dom["student_id"])
        self.assertEqual(rec.status, AttendanceRecord.Status.PRESENT)
        # Admin import attributes to the section's adviser (server-controlled).
        self.assertEqual(rec.recorded_by_id, self.dom["section_obj"].adviser_id)

    def test_valid_multiple_row_import(self):
        resp = self._att_upload(
            self.HEAD,
            [
                [self.dom["student_id"], self.dom["section"], "2026-02-15", "present"],
                [self.dom["student_id"], self.dom["section"], "2026-02-16", "late"],
            ],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.processed_rows, 2)
        self.assertEqual(AttendanceRecord.objects.count(), 2)

    def test_missing_required_column_rejected(self):
        resp = self._att_upload(
            ["student_id", "section", "status"],
            [[self.dom["student_id"], self.dom["section"], "present"]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        rec = job.records.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertIn("Missing required column", rec.error_message)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_recorded_by_column_forbidden(self):
        resp = self._att_upload(
            self.HEAD + ["recorded_by"],
            [[self.dom["student_id"], self.dom["section"], self.VALID_DATE, "present", "someone@evil.com"]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        rec = job.records.get()
        self.assertIn("recorded_by", rec.error_message)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_invalid_student_rejected(self):
        self._att_upload(
            self.HEAD,
            [["NO-SUCH", self.dom["section"], self.VALID_DATE, "present"]],
            user=self.admin_user,
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_invalid_date_rejected(self):
        self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], "not-a-date", "present"]],
            user=self.admin_user,
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_future_date_rejected(self):
        future = (__import__("django").utils.timezone.localdate() +
                  __import__("datetime").timedelta(days=5)).isoformat()
        self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], future, "present"]],
            user=self.admin_user,
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertIn("future", rec.error_message)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_invalid_status_rejected(self):
        self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], self.VALID_DATE, "tardy"]],
            user=self.admin_user,
        )
        with self.assertRaises(AttendanceRecord.DoesNotExist):
            AttendanceRecord.objects.get()
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertIn("status", rec.error_message)

    def test_no_current_academic_year_rejected(self):
        AcademicYear.objects.update(is_current=False)
        self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], self.VALID_DATE, "present"]],
            user=self.admin_user,
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_not_enrolled_student_rejected(self):
        su_user = User.objects.create_user(
            email="att_unenrolled@test.com", password="pass12345", role="student",
        )
        StudentProfile.objects.create(
            user=su_user, student_id="ATU-NOT-ENROLLED", enrollment_date="2026-01-01",
        )
        self._att_upload(
            self.HEAD,
            [["ATU-NOT-ENROLLED", self.dom["section"], self.VALID_DATE, "present"]],
            user=self.admin_user,
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_faculty_allowed_import(self):
        # The section's adviser imports for their own section.
        self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], self.VALID_DATE, "absent"]],
            user=self.dom["faculty_profile"].user,
        )
        rec = AttendanceRecord.objects.get()
        self.assertEqual(rec.recorded_by_id, self.dom["faculty_profile"].id)

    def test_faculty_scope_violation_rejected(self):
        # Another faculty (not the adviser, not assigned) tries to import.
        other_user = User.objects.create_user(
            email="att_other@test.com", password="pass12345",
            first_name="Fac", last_name="Other", role="faculty",
        )
        FacultyProfile.objects.create(user=other_user, employee_id="E-AT-OTHER")
        self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], self.VALID_DATE, "present"]],
            user=other_user,
        )
        rec = ImportRecord.objects.get()
        self.assertEqual(rec.status, RecordStatus.ERROR)
        self.assertIn("not authorized", rec.error_message)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_admin_import_allowed(self):
        self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], self.VALID_DATE, "present"]],
            user=self.admin_user,
        )
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    def test_student_and_parent_denied(self):
        for user in (self.student_user, self.parent_user):
            self.client.force_authenticate(user=None)
            resp = self._att_upload(
                self.HEAD,
                [[self.dom["student_id"], self.dom["section"], self.VALID_DATE, "present"]],
                user=user,
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_duplicate_row_in_same_file_rejected(self):
        resp = self._att_upload(
            self.HEAD,
            [
                [self.dom["student_id"], self.dom["section"], self.VALID_DATE, "present"],
                [self.dom["student_id"], self.dom["section"], self.VALID_DATE, "absent"],
            ],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.PARTIAL)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 1)
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        second = job.records.get(row_number=2)
        self.assertEqual(second.status, RecordStatus.ERROR)

    def test_existing_attendance_is_updated_in_place(self):
        # A re-upload of the same student and date applies the corrected
        # status instead of rejecting the row.
        existing = AttendanceRecord.objects.create(
            student=self.dom["student_profile"],
            section=self.dom["section_obj"],
            date=__import__("datetime").date(2026, 2, 15),
            status=AttendanceRecord.Status.PRESENT,
            recorded_by=self.dom["faculty_profile"],
        )
        resp = self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], self.VALID_DATE, "absent"]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.COMPLETED)
        rec = job.records.get()
        self.assertEqual(rec.status, RecordStatus.SUCCESS)
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.status, AttendanceRecord.Status.ABSENT)

    def test_section_name_resolves_the_section(self):
        # A school writes the section name, not its UUID.
        section = self.dom["section_obj"]
        resp = self._att_upload(
            self.HEAD,
            [[
                self.dom["student_id"],
                f"{section.grade_level.name} - {section.name}",
                self.VALID_DATE,
                "present",
            ]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.COMPLETED, job.records.get().error_message)
        rec = AttendanceRecord.objects.get()
        self.assertEqual(rec.section_id, section.pk)

    def test_recorded_by_cannot_be_forged(self):
        # Even if a client passes recorded_by, it is ignored; the server
        # controls attribution (adviser for admin import below).
        self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], self.VALID_DATE, "present"]],
            user=self.admin_user,
        )
        rec = AttendanceRecord.objects.get()
        self.assertEqual(rec.recorded_by_id, self.dom["section_obj"].adviser_id)

    def test_import_record_mapping_and_counters(self):
        resp = self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], self.VALID_DATE, "present"]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.total_rows, 1)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 0)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        rec = job.records.get()
        self.assertEqual(rec.mapped_to_model, "AttendanceRecord")
        self.assertEqual(rec.mapped_to_id, AttendanceRecord.objects.get().pk)

    def test_partial_status_with_invalid_row(self):
        resp = self._att_upload(
            self.HEAD,
            [
                [self.dom["student_id"], self.dom["section"], self.VALID_DATE, "present"],
                [self.dom["student_id"], self.dom["section"], "2026-02-16", "present"],
                ["NO-SUCH", self.dom["section"], "2026-02-17", "present"],
            ],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.total_rows, 3)
        self.assertEqual(job.processed_rows, 2)
        self.assertEqual(job.error_rows, 1)
        self.assertEqual(job.status, JobStatus.PARTIAL)
        self.assertEqual(AttendanceRecord.objects.count(), 2)

    def test_transaction_isolation(self):
        resp = self._att_upload(
            self.HEAD,
            [
                ["NO-SUCH", self.dom["section"], self.VALID_DATE, "present"],
                [self.dom["student_id"], self.dom["section"], "2026-02-16", "present"],
            ],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.PARTIAL)
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    def test_database_failure_isolated(self):
        import apps.data_import.importers.attendance as att_mod

        payload = _rows_csv(
            self.HEAD,
            [
                [self.dom["student_id"], self.dom["section"], self.VALID_DATE, "present"],
                [self.dom["student_id"], self.dom["section"], "2026-02-16", "late"],
            ],
        )
        self._auth(self.admin_user)
        real_save = AttendanceRecord.save
        calls = {"n": 0}

        def flaky_save(self2, *a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("simulated db failure")
            return real_save(self2, *a, **k)

        with mock.patch.object(att_mod.AttendanceRecord, "save", flaky_save):
            resp = self._upload(payload, import_type="attendance")
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.PARTIAL)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 1)
        self.assertEqual(AttendanceRecord.objects.count(), 1)


class AttendanceImportFormatTest(AttendanceImportApiTest):
    def test_csv_source_works(self):
        resp = self._att_upload(
            self.HEAD,
            [[self.dom["student_id"], self.dom["section"], "2026-02-15", "present"]],
            user=self.admin_user,
        )
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.file_type, FileType.CSV)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    def test_xlsx_source_works(self):
        self._auth(self.admin_user)
        resp = self._upload_xlsx(_one_sheet([
            self.HEAD,
            [self.dom["student_id"], self.dom["section"], __import__("datetime").date(2026, 2, 15), "present"],
        ]), import_type="attendance")
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.file_type, FileType.XLSX)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    def test_evt02_threshold_notification_secondary(self):
        # Persistence is primary: the validated record survives even if the
        # notification step fails.
        # Reuse self.dom (a single current academic year) so the importer
        # resolves the one current AY deterministically.
        dom2 = self.dom
        # Create two prior absences so this row crosses the threshold (3).
        for d in (__import__("datetime").date(2026, 2, 10), __import__("datetime").date(2026, 2, 11)):
            AttendanceRecord.objects.create(
                student=dom2["student_profile"], section=dom2["section_obj"], date=d,
                status=AttendanceRecord.Status.ABSENT, recorded_by=dom2["faculty_profile"],
            )
        payload = _rows_csv(
            ["student_id", "section", "date", "status"],
            [[dom2["student_id"], dom2["section"], "2026-02-15", "absent"]],
        )
        self._auth(self.admin_user)
        with mock.patch(
            "apps.data_import.importers.attendance.AttendanceImporter._notify_absence_threshold",
            side_effect=RuntimeError("notification failure"),
        ):
            resp = self._upload(payload, import_type="attendance")
        job = ImportJob.objects.get(pk=resp.data["id"])
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 0)
        self.assertEqual(
            AttendanceRecord.objects.filter(
                student=dom2["student_profile"], date=__import__("datetime").date(2026, 2, 15)
            ).count(),
            1,
        )


# ---------------------------------------------------------------------------
# PH8.7 — Student master-data import + account provisioning
# ---------------------------------------------------------------------------


def _build_student_domain(suffix=""):
    """Build a minimal academic structure for student master-data imports.

    Returns human-friendly identifiers (section names, grade names, year
    names) plus the model objects needed for conflict assertions.
    """
    ay = AcademicYear.objects.create(
        name=f"SY-2025-2026{suffix}", start_date="2025-06-01",
        end_date="2026-03-31", is_current=True,
    )
    other_ay = AcademicYear.objects.create(
        name=f"SY-2024-2025{suffix}", start_date="2024-06-01",
        end_date="2025-03-31", is_current=False,
    )
    g7 = GradeLevel.objects.create(name=f"Grade 7{suffix}", level_number=7)
    g10 = GradeLevel.objects.create(name=f"Grade 10{suffix}", level_number=10)
    fp_user = User.objects.create_user(
        email=f"fac_stu{suffix}@test.com", password="pass12345",
        first_name="Fac", last_name="Stu", role="faculty",
    )
    fp = FacultyProfile.objects.create(user=fp_user, employee_id=f"E-ST{suffix}")
    section = Section.objects.create(
        name=f"S-7A{suffix}", grade_level=g7, academic_year=ay, adviser=fp,
    )
    g10_section = Section.objects.create(
        name=f"S-10A{suffix}", grade_level=g10, academic_year=ay, adviser=fp,
    )
    other_section = Section.objects.create(
        name=f"S-7A{suffix}", grade_level=g7, academic_year=other_ay, adviser=fp,
    )
    return {
        "ay": ay,
        "other_ay": other_ay,
        "grade": g7,
        "g10": g10,
        "section": section,
        "g10_section": g10_section,
        "other_section": other_section,
        "year_name": f"SY-2025-2026{suffix}",
        "other_year_name": f"SY-2024-2025{suffix}",
        "grade_name": f"Grade 7{suffix}",
        "g10_name": f"Grade 10{suffix}",
        "section_name": f"S-7A{suffix}",
        "g10_section_name": f"S-10A{suffix}",
        "faculty_profile": fp,
    }


class StudentImportApiTest(DataImportApiBase):
    """Shared domain + upload helpers for PH8.7 tests."""

    def setUp(self):
        super().setUp()
        self.dom = _build_student_domain("st")
        self.HEAD = ["student_id", "first_name", "last_name", "email", "grade_level", "section"]

    def _stu_upload(self, headers, rows, user="admin", import_type="students", name="students.csv"):
        if user == "admin":
            user = self.admin_user
        elif user == "faculty":
            user = self.faculty_user
        self._auth(user)
        return self._upload(_rows_csv(headers, rows), import_type=import_type, name=name)

    def _stu_upload_xlsx(self, sheets, import_type="students"):
        return self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": make_xlsx(sheets, name="students.xlsx"), "import_type": import_type},
            format="multipart",
        )

    def _row(self, student_id="STU-701", email=None, **overrides):
        values = {
            "student_id": student_id,
            "first_name": "Juan",
            "last_name": "Dela Cruz",
            "email": email or f"{student_id.lower()}@test.com",
            "grade_level": self.dom["grade_name"],
            "section": self.dom["section_name"],
        }
        values.update(overrides)
        return [values.get(col, "") for col in self.HEAD]

    def _job_from(self, resp):
        return ImportJob.objects.get(pk=resp.data["id"])

    def _assert_row_failed(self, job, fragment, status=JobStatus.FAILED):
        """Row failed with the given stable error-message fragment."""
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertIn(fragment, record.error_message)
        return record


class StudentImportDomainTest(StudentImportApiTest):
    def test_valid_student_import_provisions_full_db_state(self):
        resp = self._stu_upload(self.HEAD, [self._row()])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 0)
        profile = StudentProfile.objects.get(student_id="STU-701")
        user = profile.user
        self.assertEqual(user.role, "student")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
        enrollment = Enrollment.objects.get(student=profile)
        self.assertEqual(enrollment.section, self.dom["section"])
        self.assertEqual(enrollment.academic_year, self.dom["ay"])
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.SUCCESS)
        self.assertEqual(record.mapped_to_model, "StudentProfile")
        self.assertEqual(record.mapped_to_id, profile.pk)

    def test_multiple_students_import(self):
        rows = [self._row("STU-701"), self._row("STU-702")]
        resp = self._stu_upload(self.HEAD, rows)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.processed_rows, 2)
        self.assertEqual(StudentProfile.objects.count(), 2)
        self.assertEqual(
            User.objects.filter(
                email__in=["stu-701@test.com", "stu-702@test.com"]
            ).count(),
            2,
        )

    def test_existing_student_update_flow(self):
        dom = self.dom
        sp = StudentProfile.objects.create(
            user=User.objects.create_user(
                email="existing01@test.com", password="pass12345",
                first_name="Old", last_name="Name", role="student",
            ),
            student_id="STU-EXIST1", grade_level=dom["grade"], section=dom["section"],
            enrollment_date="2025-06-01",
        )
        Enrollment.objects.create(student=sp, section=dom["section"], academic_year=dom["ay"], date_enrolled="2025-06-01")
        resp = self._stu_upload(
            self.HEAD,
            [[
                "STU-EXIST1", "NewFirst", "NewLast", "existing01@test.com",
                dom["grade_name"], dom["section_name"],
            ]],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        sp.refresh_from_db()
        self.assertEqual(sp.user.first_name, "NewFirst")
        self.assertEqual(sp.user.last_name, "NewLast")
        self.assertEqual(StudentProfile.objects.count(), 1)
        self.assertEqual(User.objects.filter(email="existing01@test.com").count(), 1)
        self.assertEqual(Enrollment.objects.filter(student=sp).count(), 1)

    def test_identity_conflict_email_mismatch(self):
        dom = self.dom
        StudentProfile.objects.create(
            user=User.objects.create_user(
                email="existing02@test.com", password="pass12345",
                first_name="Old", last_name="Name", role="student",
            ),
            student_id="STU-EXIST2", grade_level=dom["grade"], section=dom["section"],
            enrollment_date="2025-06-01",
        )
        resp = self._stu_upload(
            self.HEAD,
            [[
                "STU-EXIST2", "NewFirst", "NewLast", "different02@test.com",
                dom["grade_name"], dom["section_name"],
            ]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        record = job.records.get()
        self.assertIn("login identity cannot be changed", record.error_message)
        user = User.objects.get(email="existing02@test.com")
        self.assertEqual(user.email, "existing02@test.com")

    def test_email_already_belongs_to_another_student(self):
        dom = self.dom
        profile = StudentProfile.objects.create(
            user=User.objects.create_user(
                email="otherstu@test.com", password="pass12345",
                first_name="Other", last_name="Student", role="student",
            ),
            student_id="STU-OTHER", grade_level=dom["grade"], section=dom["section"],
            enrollment_date="2025-06-01",
        )
        Enrollment.objects.create(student=profile, section=dom["section"], academic_year=dom["ay"], date_enrolled="2025-06-01")
        resp = self._stu_upload(
            self.HEAD, [[
                "STU-NEW01", "Juan", "Dela Cruz", "otherstu@test.com",
                dom["grade_name"], dom["section_name"],
            ]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "already belongs to another student")

    def test_email_already_belongs_to_non_student(self):
        dom = self.dom
        User.objects.create_user(
            email="facultyowner@test.com", password="pass12345",
            first_name="Fac", last_name="Owner", role="faculty",
        )
        resp = self._stu_upload(
            self.HEAD, [[
                "STU-NEW02", "Juan", "Dela Cruz", "facultyowner@test.com",
                dom["grade_name"], dom["section_name"],
            ]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "non-student account")

    def test_guardian_contact_with_letters_fails_the_row(self):
        """A non-phone guardian contact is a row error, not a crash.

        TC-FAC-01/02: the QA log recorded the system saving guardian
        contacts carrying letters. The importer validates the format via
        ``apps.accounts.validators``, and that validator raises Django's
        ``ValidationError`` - which does not inherit from ``ValueError``,
        so the guard has to catch the right class or the exception escapes
        the per-row handling and becomes a 500 instead of a failed row.
        """
        headers = self.HEAD + ["guardian_contact"]
        resp = self._stu_upload(
            headers,
            [
                [
                    "STU-GC1", "Juan", "Dela Cruz", "gc1@test.com",
                    self.dom["grade_name"], self.dom["section_name"],
                    "not-a-phone",
                ]
            ],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "phone number of 7-15 digits")
        self.assertFalse(User.objects.filter(email="gc1@test.com").exists())

    def test_guardian_contact_too_short_fails_the_row(self):
        """Digit-count bounds are enforced too, not just the letter check."""
        headers = self.HEAD + ["guardian_contact"]
        resp = self._stu_upload(
            headers,
            [
                [
                    "STU-GC2", "Juan", "Dela Cruz", "gc2@test.com",
                    self.dom["grade_name"], self.dom["section_name"],
                    "123",
                ]
            ],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "phone number of 7-15 digits")

    def test_valid_guardian_contact_is_stored(self):
        """The separators the seed data uses are accepted."""
        headers = self.HEAD + ["guardian_contact"]
        resp = self._stu_upload(
            headers,
            [
                [
                    "STU-GC3", "Juan", "Dela Cruz", "gc3@test.com",
                    self.dom["grade_name"], self.dom["section_name"],
                    "0917-555-0100",
                ]
            ],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        profile = StudentProfile.objects.get(student_id="STU-GC3")
        self.assertEqual(profile.guardian_contact, "0917-555-0100")

    def test_student_user_without_profile_gets_profile(self):
        dom = self.dom
        user = User.objects.create_user(
            email="noprofile@test.com", password="pass12345",
            first_name="Pro", last_name="File", role="student",
        )
        resp = self._stu_upload(
            self.HEAD, [[
                "STU-ATTACH", "Pro", "File", "noprofile@test.com",
                dom["grade_name"], dom["section_name"],
            ]],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        profile = StudentProfile.objects.get(student_id="STU-ATTACH")
        self.assertEqual(profile.user.pk, user.pk)
        self.assertEqual(User.objects.filter(email="noprofile@test.com").count(), 1)
        self.assertEqual(profile.user.must_change_password, False)

    def test_duplicate_student_id_in_file(self):
        rows = [self._row("STU-DUP-1"), self._row("STU-DUP-1", email="dup1b@test.com")]
        resp = self._stu_upload(self.HEAD, rows)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.PARTIAL)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 1)
        messages = [r.error_message for r in job.records.order_by("row_number")]
        self.assertEqual("", messages[0])
        self.assertIn("student_id appears more than once in the file", messages[1])

    def test_duplicate_email_in_file(self):
        rows = [self._row("STU-EM-1", email="same@test.com"), self._row("STU-EM-2", email="same@test.com")]
        resp = self._stu_upload(self.HEAD, rows)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.PARTIAL)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 1)
        messages = [r.error_message for r in job.records.order_by("row_number")]
        self.assertEqual("", messages[0])
        self.assertIn("email appears more than once in the file", messages[1])

    def test_duplicate_student_id_in_db_updates_not_duplicates(self):
        dom = self.dom
        sp = StudentProfile.objects.create(
            user=User.objects.create_user(
                email="dbdup@test.com", password="pass12345",
                first_name="Old", last_name="Name", role="student",
            ),
            student_id="STU-DB1", grade_level=dom["grade"], section=dom["section"],
            enrollment_date="2025-06-01",
        )
        Enrollment.objects.create(student=sp, section=dom["section"], academic_year=dom["ay"], date_enrolled="2025-06-01")
        resp = self._stu_upload(
            self.HEAD, [["STU-DB1", "Juan", "Dela Cruz", "dbdup@test.com", dom["grade_name"], dom["section_name"]]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(StudentProfile.objects.filter(student_id__iexact="STU-DB1").count(), 1)
        self.assertEqual(User.objects.filter(email="dbdup@test.com").count(), 1)

    def test_invalid_section(self):
        resp = self._stu_upload(
            self.HEAD, [["STU-SEC1", "Juan", "Dela Cruz", "secbad@test.com", self.dom["grade_name"], "NOPE-9"]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "does not exist in the selected academic year")

    def test_invalid_grade_level(self):
        resp = self._stu_upload(
            self.HEAD, [["STU-GR1", "Juan", "Dela Cruz", "grbad@test.com", "Grade 99", self.dom["section_name"]]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "does not match")

    def test_grade_level_mismatches_section(self):
        resp = self._stu_upload(
            self.HEAD, [["STU-GM1", "Juan", "Dela Cruz", "gmmismatch@test.com", self.dom["g10_name"], self.dom["section_name"]]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "does not match")

    def test_invalid_academic_year(self):
        resp = self._stu_upload(
            ["student_id", "first_name", "last_name", "email", "grade_level", "section", "academic_year"],
            [["STU-AY1", "Juan", "Dela Cruz", "aybad@test.com", self.dom["grade_name"], self.dom["section_name"], "NOPE-9999"]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "does not match a known academic year")

    def test_previous_year_academic_year_column(self):
        headers = ["student_id", "first_name", "last_name", "email", "grade_level", "section", "academic_year"]
        resp = self._stu_upload(
            headers,
            [["STU-PY1", "Juan", "Dela Cruz", "pyear@test.com", self.dom["grade_name"], self.dom["section_name"], self.dom["other_year_name"]]],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        profile = StudentProfile.objects.get(student_id="STU-PY1")
        self.assertEqual(
            Enrollment.objects.get(student=profile).academic_year, self.dom["other_ay"]
        )

    def test_invalid_student_id_charset(self):
        resp = self._stu_upload(
            self.HEAD, [["bad id!", "Juan", "Dela Cruz", "badid@test.com", self.dom["grade_name"], self.dom["section_name"]]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "must be 1-20 letters")

    def test_missing_student_id_value(self):
        resp = self._stu_upload(
            self.HEAD, [["", "Juan", "Dela Cruz", "missingid@test.com", self.dom["grade_name"], self.dom["section_name"]]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "student_id is required")

    def test_duplicate_enrollment_conflict(self):
        dom = self.dom
        sp = StudentProfile.objects.create(
            user=User.objects.create_user(
                email="enrconflict@test.com", password="pass12345",
                first_name="Enr", last_name="Conflict", role="student",
            ),
            student_id="STU-ENR1", grade_level=dom["g10"], section=dom["g10_section"],
            enrollment_date="2025-06-01",
        )
        Enrollment.objects.create(student=sp, section=dom["g10_section"], academic_year=dom["ay"], date_enrolled="2025-06-01")
        resp = self._stu_upload(
            self.HEAD, [["STU-ENR1", "Enr", "Conflict", "enrconflict@test.com", dom["grade_name"], dom["section_name"]]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "already enrolled in a different section")

    def test_same_section_enrollment_idempotent(self):
        dom = self.dom
        sp = StudentProfile.objects.create(
            user=User.objects.create_user(
                email="enrSame@test.com", password="pass12345",
                first_name="Enr", last_name="Same", role="student",
            ),
            student_id="STU-ENR2", grade_level=dom["grade"], section=dom["section"],
            enrollment_date="2025-06-01",
        )
        Enrollment.objects.create(student=sp, section=dom["section"], academic_year=dom["ay"], date_enrolled="2025-06-01")
        resp = self._stu_upload(
            self.HEAD, [["STU-ENR2", "Enr", "Same", "enrSame@test.com", dom["grade_name"], dom["section_name"]]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(Enrollment.objects.filter(student=sp).count(), 1)

    def test_invalid_date_of_birth(self):
        resp = self._stu_upload(
            ["student_id", "first_name", "last_name", "email", "grade_level", "section", "date_of_birth"],
            [["STU-DOB1", "Juan", "Dela Cruz", "dobbad@test.com", self.dom["grade_name"], self.dom["section_name"], "2030-01-01"]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "cannot be in the future")

    def test_invalid_enrollment_date(self):
        resp = self._stu_upload(
            ["student_id", "first_name", "last_name", "email", "grade_level", "section", "enrollment_date"],
            [["STU-ED1", "Juan", "Dela Cruz", "edbad@test.com", self.dom["grade_name"], self.dom["section_name"], "yesterday"]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "enrollment_date must use")

    def test_lrn_column_rejected_as_unknown(self):
        resp = self._stu_upload(
            ["student_id", "first_name", "last_name", "email", "grade_level", "section", "lrn"],
            [["STU-LRN1", "Juan", "Dela Cruz", "lrn@test.com", self.dom["grade_name"], self.dom["section_name"], "12345678901"]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "not supported by this import")
        self.assertEqual(StudentProfile.objects.count(), 0)

    def test_middle_name_column_rejected_as_unknown(self):
        resp = self._stu_upload(
            ["student_id", "first_name", "middle_name", "last_name", "email", "grade_level", "section"],
            [["STU-MN1", "Juan", "Santos", "Dela Cruz", "mn@test.com", self.dom["grade_name"], self.dom["section_name"]]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "not supported by this import")


class StudentImportFormatTest(StudentImportApiTest):
    def test_missing_required_column(self):
        headers = ["student_id", "first_name", "last_name", "grade_level", "section"]
        resp = self._stu_upload(headers, [["STU-F1", "Juan", "Dela Cruz", self.dom["grade_name"], self.dom["section_name"]]])
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "Missing required column(s)")

    def test_password_column_rejected(self):
        headers = self.HEAD + ["password"]
        resp = self._stu_upload(
            headers,
            [["STU-F2", "Juan", "Dela Cruz", "pw@test.com", self.dom["grade_name"], self.dom["section_name"], "hunter2"]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "never carry credentials")
        self.assertFalse(User.objects.filter(email="pw@test.com").exists())

    def test_default_password_column_rejected(self):
        headers = self.HEAD + ["default_password"]
        resp = self._stu_upload(
            headers,
            [["STU-F3", "Juan", "Dela Cruz", "dpw@test.com", self.dom["grade_name"], self.dom["section_name"], "x"]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "never carry credentials")

    def test_role_column_rejected(self):
        headers = self.HEAD + ["role"]
        resp = self._stu_upload(
            headers,
            [["STU-F4", "Juan", "Dela Cruz", "rl@test.com", self.dom["grade_name"], self.dom["section_name"], "admin"]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "Column 'role' is not accepted")
        self.assertFalse(User.objects.filter(email="rl@test.com").exists())

    def test_unknown_column_rejected(self):
        resp = self._stu_upload(
            self.HEAD + ["random_meta"],
            [["STU-F5", "Juan", "Dela Cruz", "uk@test.com", self.dom["grade_name"], self.dom["section_name"], "x"]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "not supported by this import")


class StudentImportXlsxTest(StudentImportApiTest):
    def _xlsx_rows(self, sheets):
        self._auth(self.admin_user)
        return self._stu_upload_xlsx(sheets)

    def test_valid_xlsx_student_import(self):
        headers = ["student_id", "first_name", "last_name", "email", "grade_level", "section"]
        rows = [["STU-X1", "Juan", "Dela Cruz", "xlsx1@test.com", self.dom["grade_name"], self.dom["section_name"]]]
        resp = self._xlsx_rows(_one_sheet([headers] + rows))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        profile = StudentProfile.objects.get(student_id="STU-X1")
        self.assertTrue(profile.user.must_change_password)
        self.assertEqual(Enrollment.objects.filter(student=profile).count(), 1)

    def test_xlsx_password_column_rejected(self):
        headers = ["student_id", "first_name", "last_name", "email", "grade_level", "section", "password"]
        rows = [["STU-X2", "Juan", "Dela Cruz", "xlsx2@test.com", self.dom["grade_name"], self.dom["section_name"], "x"]]
        resp = self._xlsx_rows(_one_sheet([headers] + rows))
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "never carry credentials")

    def test_xlsx_role_column_rejected(self):
        headers = ["student_id", "first_name", "last_name", "email", "grade_level", "section", "role"]
        rows = [["STU-X3", "Juan", "Dela Cruz", "xlsx3@test.com", self.dom["grade_name"], self.dom["section_name"], "faculty"]]
        resp = self._xlsx_rows(_one_sheet([headers] + rows))
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "Column 'role' is not accepted")

    def test_xlsx_unknown_column_rejected(self):
        headers = ["student_id", "first_name", "last_name", "email", "grade_level", "section", "lrn"]
        rows = [["STU-X4", "Juan", "Dela Cruz", "xlsx4@test.com", self.dom["grade_name"], self.dom["section_name"], "123"]]
        resp = self._xlsx_rows(_one_sheet([headers] + rows))
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        self._assert_row_failed(job, "not supported by this import")

    def test_xlsx_multiple_rows(self):
        headers = ["student_id", "first_name", "last_name", "email", "grade_level", "section"]
        rows = [
            ["STU-X5", "Juan", "Dela Cruz", "xlsx5@test.com", self.dom["grade_name"], self.dom["section_name"]],
            ["STU-X6", "Ana", "Santos", "xlsx6@test.com", self.dom["grade_name"], self.dom["section_name"]],
        ]
        resp = self._xlsx_rows(_one_sheet([headers] + rows))
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.processed_rows, 2)
        self.assertEqual(StudentProfile.objects.count(), 2)


class StudentPrivilegeTest(StudentImportApiTest):
    def setUp(self):
        super().setUp()
        self.guidance_user = User.objects.create_user(
            email="guidance_di@test.com", password="pass12345",
            first_name="Gui", last_name="Dance", role="guidance",
        )

    def test_admin_allowed(self):
        resp = self._stu_upload(self.HEAD, [self._row()])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_faculty_denied(self):
        resp = self._stu_upload(self.HEAD, [self._row()], user="faculty")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_denied(self):
        self._auth(self.student_user)
        resp = self._upload(_rows_csv(self.HEAD, [self._row()]), import_type="students")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_parent_denied(self):
        self._auth(self.parent_user)
        resp = self._upload(_rows_csv(self.HEAD, [self._row()]), import_type="students")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_guidance_denied(self):
        self._auth(self.guidance_user)
        resp = self._upload(_rows_csv(self.HEAD, [self._row()]), import_type="students")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_denied_imports_create_no_records(self):
        resp = self._stu_upload(self.HEAD, [self._row()], user="faculty")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ImportJob.objects.count(), 0)
        self.assertEqual(StudentProfile.objects.count(), 0)


class StudentAccountProvisioningTest(StudentImportApiTest):
    def test_provisioned_account_role_is_student(self):
        self._stu_upload(self.HEAD, [self._row("STU-PROV1")])
        user = StudentProfile.objects.get(student_id="STU-PROV1").user
        self.assertEqual(user.role, "student")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_provisioned_password_is_hashed(self):
        self._stu_upload(self.HEAD, [self._row("STU-PROV2")])
        user = StudentProfile.objects.get(student_id="STU-PROV2").user
        self.assertNotEqual(user.password, "something")
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))

    def test_provisioned_passwords_are_random_and_unpredictable(self):
        self._stu_upload(self.HEAD, [self._row("STU-RAND1"), self._row("STU-RAND2")])
        u1 = StudentProfile.objects.get(student_id="STU-RAND1").user
        u2 = StudentProfile.objects.get(student_id="STU-RAND2").user
        self.assertNotEqual(u1.password, u2.password)
        for user in (u1, u2):
            self.assertNotIn(user.email.split("@")[0], user.password)
            self.assertNotIn(user.email.split("@")[1], user.password)
            self.assertNotIn(user.student_profile.student_id, user.password)

    def test_must_change_password_flag_set(self):
        self._stu_upload(self.HEAD, [self._row("STU-PROV3")])
        user = StudentProfile.objects.get(student_id="STU-PROV3").user
        self.assertTrue(user.must_change_password)

    def test_imported_student_login_forced_change_flow(self):
        from apps.data_import.importers.students import _generate_temporary_password

        temp = "SeedTemp_2026_Ab1!"
        email = "onboard01@test.com"
        with mock.patch(
            "apps.data_import.importers.students._generate_temporary_password",
            return_value=temp,
        ):
            resp = self._stu_upload(self.HEAD, [self._row("STU-OB1", email=email)])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=None)
        login = self.client.post(
            "/api/v1/auth/login/",
            {"email": email, "password": temp},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertIn("access", login.data)
        self.assertTrue(login.data["must_change_password"])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        me = self.client.get("/api/v1/accounts/me/")
        self.assertEqual(me.status_code, status.HTTP_401_UNAUTHORIZED)

        changed = self.client.post(
            "/api/v1/accounts/password/change/",
            {"current_password": temp, "new_password": "NewSecurePass_2026!"},
            format="json",
        )
        self.assertEqual(changed.status_code, status.HTTP_200_OK)

        me2 = self.client.get("/api/v1/accounts/me/")
        self.assertEqual(me2.status_code, status.HTTP_200_OK)

        self.client.credentials()
        old_login = self.client.post(
            "/api/v1/auth/login/", {"email": email, "password": temp}, format="json"
        )
        self.assertEqual(old_login.status_code, status.HTTP_401_UNAUTHORIZED)
        new_login = self.client.post(
            "/api/v1/auth/login/",
            {"email": email, "password": "NewSecurePass_2026!"},
            format="json",
        )
        self.assertEqual(new_login.status_code, status.HTTP_200_OK)
        self.assertFalse(new_login.data["must_change_password"])

        user = User.objects.get(email=email)
        self.assertFalse(user.must_change_password)
        self.assertEqual(user.role, "student")

    def test_password_change_wrong_current_rejected(self):
        from apps.data_import.importers.students import _generate_temporary_password

        temp = "SeedTemp_2026_Ab1!"
        with mock.patch(
            "apps.data_import.importers.students._generate_temporary_password",
            return_value=temp,
        ):
            self._stu_upload(self.HEAD, [self._row("STU-OB2")])
        email = StudentProfile.objects.get(student_id="STU-OB2").user.email
        self.client.force_authenticate(user=None)
        login = self.client.post(
            "/api/v1/auth/login/", {"email": email, "password": temp}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        resp = self.client.post(
            "/api/v1/accounts/password/change/",
            {"current_password": "WrongPass_2026!", "new_password": "NewSecurePass_2026!"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_plaintext_password_in_api_response(self):
        from apps.data_import.importers.students import _generate_temporary_password

        temp = "SeedTemp_2026_Ab1!"
        with mock.patch(
            "apps.data_import.importers.students._generate_temporary_password",
            return_value=temp,
        ):
            resp = self._stu_upload(self.HEAD, [self._row("STU-OB3")])
        body = str(resp.data) + resp.content.decode("utf-8", errors="replace")
        self.assertNotIn(temp, body)

    def test_no_password_in_import_record_and_job_log(self):
        from apps.data_import.importers.students import _generate_temporary_password

        temp = "SeedTemp_2026_Ab1!"
        with mock.patch(
            "apps.data_import.importers.students._generate_temporary_password",
            return_value=temp,
        ):
            resp = self._stu_upload(self.HEAD, [self._row("STU-OB4")])
        job = self._job_from(resp)
        record = job.records.get()
        self.assertNotIn(temp, str(record.data))
        self.assertNotIn(temp, record.error_message)
        self.assertNotIn(temp, str(job.error_log))
        for key in ("password", "temp_password", "default_password"):
            self.assertNotIn(key, record.data)


class StudentTransactionTest(StudentImportApiTest):
    def test_provisioning_failure_rolls_back_entire_row(self):
        with mock.patch.object(
            StudentProfile.objects,
            "create",
            side_effect=RuntimeError("internal failure"),
        ):
            resp = self._stu_upload(self.HEAD, [self._row("STU-TX1")])
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.FAILED)
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertEqual(record.error_message, "The row could not be processed.")
        self.assertNotIn("internal", record.error_message)
        self.assertFalse(User.objects.filter(email="stu-tx1@test.com").exists())
        self.assertEqual(StudentProfile.objects.count(), 0)
        self.assertEqual(Enrollment.objects.count(), 0)

    def test_one_bad_row_does_not_corrupt_another(self):
        rows = [
            self._row("STU-TX2"),
            ["STU-TX3", "Juan", "Dela Cruz", "txbad@test.com", self.dom["grade_name"], "NO-SECTION-9"],
        ]
        resp = self._stu_upload(self.HEAD, rows)
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.PARTIAL)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 1)
        self.assertTrue(StudentProfile.objects.filter(student_id="STU-TX2").exists())
        self.assertFalse(StudentProfile.objects.filter(student_id="STU-TX3").exists())
        self.assertFalse(User.objects.filter(email="txbad@test.com").exists())

    def test_counters_reflect_actual_outcomes(self):
        rows = [
            self._row("STU-TX4"),
            self._row("STU-TX5"),
            ["STU-TX6", "Juan", "Dela Cruz", "txbad2@test.com", self.dom["grade_name"], "NO-SECTION-9"],
        ]
        resp = self._stu_upload(self.HEAD, rows)
        job = self._job_from(resp)
        self.assertEqual(job.total_rows, 3)
        self.assertEqual(job.processed_rows, 2)
        self.assertEqual(job.error_rows, 1)
        self.assertEqual(job.status, JobStatus.PARTIAL)
        self.assertEqual(job.records.filter(status=RecordStatus.ERROR).count(), 1)

    def test_rejected_row_leaves_no_orphans(self):
        resp = self._stu_upload(
            self.HEAD,
            [["STU-TX7", "Juan", "Dela Cruz", "orphan@test.com", self.dom["grade_name"], "NO-SECTION-9"]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.records.get().status, RecordStatus.ERROR)
        self.assertFalse(User.objects.filter(email="orphan@test.com").exists())
        self.assertFalse(StudentProfile.objects.filter(student_id="STU-TX7").exists())


class StudentSecurityTest(StudentImportApiTest):
    def test_duplicate_race_handled_safely(self):
        from apps.data_import.importers.students import StudentImporter

        User.objects.create_user(
            email="race@test.com", password="pass12345",
            first_name="Race", last_name="Holder", role="student",
        )
        with mock.patch.object(StudentImporter, "_resolve_student_profile", return_value=None), mock.patch.object(
            StudentImporter, "_resolve_user_by_email", return_value=None
        ):
            resp = self._stu_upload(
                self.HEAD,
                [["STU-RACE1", "Juan", "Dela Cruz", "race@test.com", self.dom["grade_name"], self.dom["section_name"]]],
            )
        job = self._job_from(resp)
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertEqual(record.error_message, "The row could not be processed.")
        self.assertNotIn("UNIQUE", record.error_message)
        self.assertEqual(
            User.objects.filter(email__iexact="race@test.com").count(), 1
        )
        self.assertFalse(StudentProfile.objects.filter(student_id="STU-RACE1").exists())

    def test_import_never_mutates_existing_account_identity(self):
        dom = self.dom
        sp = StudentProfile.objects.create(
            user=User.objects.create_user(
                email="frozen@test.com", password="pass12345",
                first_name="Frozen", last_name="Identity", role="student",
            ),
            student_id="STU-FROZEN", grade_level=dom["grade"], section=dom["section"],
            enrollment_date="2025-06-01",
        )
        Enrollment.objects.create(student=sp, section=dom["section"], academic_year=dom["ay"], date_enrolled="2025-06-01")
        resp = self._stu_upload(
            self.HEAD,
            [["STU-FROZEN", "Hacker", "Attempt", "frozen@test.com", dom["grade_name"], dom["section_name"]]],
        )
        job = self._job_from(resp)
        self.assertEqual(job.status, JobStatus.COMPLETED)
        user = User.objects.get(email="frozen@test.com")
        self.assertEqual(user.first_name, "Hacker")  # profile fields still refresh
        self.assertEqual(user.check_password("pass12345"), True)
        self.assertEqual(StudentProfile.objects.filter(student_id="STU-FROZEN").count(), 1)

    def test_internal_error_details_never_leak(self):
        with mock.patch.object(
            Enrollment.objects,
            "create",
            side_effect=ValueError("secret: /opt/aegis/db.sqlite3 & user=juan@test.com"),
        ):
            resp = self._stu_upload(self.HEAD, [self._row("STU-SEC1")])
        job = self._job_from(resp)
        record = job.records.get()
        self.assertEqual(record.error_message, "The row could not be processed.")
        for forbidden in ("/opt/", "sqlite3", "juan@test.com", "Traceback"):
            self.assertNotIn(forbidden, record.error_message)
        self.assertFalse(User.objects.filter(email="sec1@test.com").exists())


# ---------------------------------------------------------------------------
# PH11 — TC-ADM-05 (FR-037): the guidance-records import now writes real
# records instead of parsing the file and reporting that nothing was stored.
# ---------------------------------------------------------------------------


class GuidanceRecordsImportTest(DataImportApiBase):
    """TC-ADM-05 — a valid guidance file is stored in the Guidance DB."""

    HEAD = [
        "student_id",
        "session_date",
        "session_time",
        "session_type",
        "concern_categories",
        "session_notes",
        "priority_level",
    ]

    def setUp(self):
        from apps.accounts.models import GuidanceProfile

        super().setUp()
        self.counselor_user = User.objects.create_user(
            email="counselor_gd@test.com",
            password="pass12345",
            first_name="Guide",
            last_name="Ance",
            role="guidance",
        )
        self.counselor = GuidanceProfile.objects.create(
            user=self.counselor_user
        )
        student_user = User.objects.create_user(
            email="stu_gd@test.com",
            password="pass12345",
            first_name="Stu",
            last_name="Guide",
            role="student",
        )
        self.student = StudentProfile.objects.create(
            user=student_user,
            student_id="GDU-001",
            enrollment_date="2026-01-01",
        )

    # -- helpers ----------------------------------------------------------

    def _row(self, **overrides):
        values = {
            "student_id": "GDU-001",
            "session_date": "2026-09-01",
            "session_time": "09:30",
            "session_type": "individual_counseling",
            "concern_categories": "academic|emotional",
            "session_notes": "Discussed workload and study habits.",
            "priority_level": "medium",
        }
        values.update(overrides)
        return values

    def _csv_body(self, rows=None, headers=None):
        headers = headers or self.HEAD
        rows = [self._row()] if rows is None else rows
        return _rows_csv(
            headers, [[row.get(col, "") for col in headers] for row in rows]
        )

    def _upload_rows(self, rows, headers=None, user=None):
        self._auth(user or self.admin_user)
        resp = self._upload(
            self._csv_body(rows, headers), import_type="guidance_records"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        return ImportJob.objects.get(pk=resp.data["id"])

    def _assign_counselor(self):
        from django.utils import timezone

        from apps.guidance.models import RiskAlert

        return RiskAlert.objects.create(
            student=self.student,
            risk_level="moderate",
            assigned_counselor=self.counselor,
            generated_at=timezone.now(),
        )

    def _job_from(self, resp):
        return ImportJob.objects.get(pk=resp.data["id"])

    # -- success path -----------------------------------------------------

    def test_valid_guidance_file_is_stored(self):
        from apps.guidance.models import ConsultationRecord

        self._assign_counselor()
        job = self._upload_rows([self._row()])

        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.total_rows, 1)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 0)

        record = ConsultationRecord.objects.get()
        self.assertEqual(record.student, self.student)
        self.assertEqual(record.counselor, self.counselor)
        self.assertEqual(record.session_date.isoformat(), "2026-09-01")
        self.assertEqual(record.session_time.isoformat()[:5], "09:30")
        self.assertEqual(record.session_type, "individual_counseling")
        self.assertEqual(
            record.concern_categories, ["academic", "emotional"]
        )
        self.assertEqual(record.priority_level, "medium")
        self.assertEqual(record.status, "ongoing")
        self.assertIsNone(record.next_session_date)
        self.assertIsNone(record.recommendations)

        stored = job.records.get()
        self.assertEqual(stored.status, RecordStatus.SUCCESS)
        self.assertEqual(stored.mapped_to_model, "ConsultationRecord")
        self.assertEqual(str(stored.mapped_to_id), str(record.pk))

    def test_optional_columns_are_written_when_present(self):
        from apps.guidance.models import ConsultationRecord

        self._assign_counselor()
        job = self._upload_rows(
            [
                self._row(
                    recommendations="Refer to the reading program.",
                    next_session_date="2026-09-15",
                    status="follow_up",
                )
            ],
            headers=self.HEAD
            + ["recommendations", "next_session_date", "status"],
        )
        self.assertEqual(job.status, JobStatus.COMPLETED)

        record = ConsultationRecord.objects.get()
        self.assertEqual(
            record.recommendations, "Refer to the reading program."
        )
        self.assertEqual(record.next_session_date.isoformat(), "2026-09-15")
        self.assertEqual(record.status, "follow_up")

    def test_counselor_falls_back_to_an_existing_intervention(self):
        from apps.guidance.models import Intervention, RiskAlert

        alert = RiskAlert.objects.filter(student=self.student)
        self.assertFalse(alert.exists())
        Intervention.objects.create(
            student=self.student,
            assigned_counselor=self.counselor,
            plan_start_date="2026-08-01",
        )
        job = self._upload_rows([self._row()])
        self.assertEqual(job.status, JobStatus.COMPLETED)

        from apps.guidance.models import ConsultationRecord

        self.assertEqual(
            ConsultationRecord.objects.get().counselor, self.counselor
        )

    # -- attribution ------------------------------------------------------

    def test_row_is_rejected_when_no_counselor_can_be_attributed(self):
        from apps.guidance.models import ConsultationRecord

        job = self._upload_rows([self._row()])

        # No fabricated counselor: nothing may be stored, and the job must
        # not report a completed import.
        self.assertEqual(ConsultationRecord.objects.count(), 0)
        self.assertEqual(job.processed_rows, 0)
        self.assertIn(
            job.status, (JobStatus.FAILED, JobStatus.PARTIAL)
        )
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertEqual(
            record.error_message,
            "No guidance counselor can be attributed to this record. Assign "
            "the student's counselor before importing.",
        )

    # -- row validation ---------------------------------------------------

    def test_unknown_student_rejected(self):
        job = self._upload_rows([self._row(student_id="NOPE")])
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertIn("No student found with student_id", record.error_message)

    def test_future_session_date_rejected(self):
        job = self._upload_rows([self._row(session_date="2099-01-01")])
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertEqual(
            record.error_message, "session_date cannot be in the future."
        )

    def test_malformed_date_rejected(self):
        job = self._upload_rows([self._row(session_date="next tuesday")])
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertEqual(
            record.error_message, "Dates must use the YYYY-MM-DD format."
        )

    def test_malformed_time_rejected(self):
        job = self._upload_rows([self._row(session_time="half past nine")])
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertIn("24-hour HH:MM", record.error_message)

    def test_unknown_session_type_rejected(self):
        job = self._upload_rows([self._row(session_type="chat")])
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertIn("session_type must be one of", record.error_message)

    def test_unknown_priority_rejected(self):
        job = self._upload_rows([self._row(priority_level="urgent")])
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertIn("priority_level must be one of", record.error_message)

    def test_unknown_concern_category_rejected(self):
        job = self._upload_rows(
            [self._row(concern_categories="academic|weather")]
        )
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertIn("Invalid concern category", record.error_message)

    def test_empty_concern_list_rejected(self):
        job = self._upload_rows([self._row(concern_categories="|;")])
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertIn(
            "at least one valid category", record.error_message
        )

    def test_empty_session_notes_rejected(self):
        job = self._upload_rows([self._row(session_notes="   ")])
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.ERROR)
        self.assertIn("session_notes is required", record.error_message)

    def test_duplicate_row_within_the_file_rejected(self):
        from apps.guidance.models import ConsultationRecord

        self._assign_counselor()
        job = self._upload_rows([self._row(), self._row()])

        self.assertEqual(ConsultationRecord.objects.count(), 1)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(job.error_rows, 1)
        self.assertEqual(job.status, JobStatus.PARTIAL)
        failed = job.records.get(status=RecordStatus.ERROR)
        self.assertIn("duplicates another row", failed.error_message)

    def test_existing_record_is_updated_in_place(self):
        from apps.guidance.models import ConsultationRecord

        self._assign_counselor()
        self._upload_rows([self._row()])
        job = self._upload_rows([self._row(session_notes="Corrected notes.")])

        self.assertEqual(ConsultationRecord.objects.count(), 1)
        record = job.records.get()
        self.assertEqual(record.status, RecordStatus.SUCCESS)
        self.assertEqual(
            ConsultationRecord.objects.get().session_notes, "Corrected notes."
        )

    # -- header validation ------------------------------------------------

    def test_missing_required_column_fails_every_row(self):
        headers = [h for h in self.HEAD if h != "priority_level"]
        self._assign_counselor()
        job = self._upload_rows([self._row()], headers=headers)

        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.processed_rows, 0)
        self.assertEqual(
            job.records.get().error_message,
            "Missing required column(s): priority_level",
        )

    def test_client_supplied_counselor_column_rejected(self):
        # Attribution is server-controlled, exactly like attendance's
        # recorded_by: a client-supplied counselor would be forgery.
        headers = self.HEAD + ["counselor"]
        job = self._upload_rows(
            [self._row(counselor=str(self.counselor.pk))], headers=headers
        )

        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.processed_rows, 0)
        self.assertIn(
            "Unknown column", job.records.get().error_message
        )
        self.assertIn(
            "counselor", job.records.get().error_message
        )

    def test_recorded_by_column_rejected(self):
        job = self._upload_rows(
            [self._row(recorded_by="someone")],
            headers=self.HEAD + ["recorded_by"],
        )
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.processed_rows, 0)

    # -- authority --------------------------------------------------------

    def test_faculty_cannot_import_guidance_records(self):
        self._auth(self.faculty_user)
        resp = self._upload(
            self._csv_body(),
            import_type="guidance_records",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_guidance_role_cannot_import_guidance_records(self):
        # The role matrix (FR-012 / FR-013) is unchanged by PH11: only an
        # admin may submit this import type.
        self._auth(self.counselor_user)
        resp = self._upload(
            self._csv_body(),
            import_type="guidance_records",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_cannot_import_guidance_records(self):
        self._auth(self.student_user)
        resp = self._upload(
            self._csv_body(),
            import_type="guidance_records",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# PH11 — import templates: the header a tester downloads is the header the
# importer validates, so there is no second copy of the schema to drift.
# ---------------------------------------------------------------------------


class BackgroundImportTest(TransactionTestCase):
    """
    A file above ``IMPORT_SYNC_ROW_LIMIT`` is queued, not processed inline.

    ``TransactionTestCase`` on purpose: the worker thread opens its own
    connection, so the job row has to be really committed for it to be seen —
    which is exactly what happens in production.
    """

    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin_bg@test.com", password="pass12345",
            first_name="Ad", last_name="Min", role="admin",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin_user)

    def test_large_upload_is_queued_then_finishes(self):
        from apps.data_import import views as views_module

        dom = _build_grade_domain("bg")
        csv_text = _rows_csv(
            ["student_id", "subject_assignment", "grading_period", "score"],
            [[dom["student_id"], dom["subject_assignment"], dom["grading_period"], 90]],
        )
        with mock.patch.object(views_module, "IMPORT_SYNC_ROW_LIMIT", 0):
            resp = self.client.post(
                "/api/v1/data-import/jobs/",
                {"file": make_csv(csv_text, name="bg.csv"), "import_type": "grades"},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        job_id = resp.json()["id"]
        self.assertEqual(resp.json()["status"], JobStatus.PROCESSING)

        deadline = time.monotonic() + 30
        job = ImportJob.objects.get(pk=job_id)
        while job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
            if time.monotonic() > deadline:
                self.fail(f"job {job_id} never finished (status={job.status})")
            time.sleep(0.25)
            job.refresh_from_db()

        self.assertEqual(job.status, JobStatus.COMPLETED, job.error_log)
        self.assertEqual(job.processed_rows, 1)
        self.assertEqual(Grade.objects.count(), 1)


class BackgroundWorkerTest(TestCase):
    """The worker body itself: success and unexpected failure."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin_bw@test.com", password="pass12345",
            first_name="Ad", last_name="Min", role="admin",
        )

    def test_unexpected_failure_marks_the_job_failed(self):
        from apps.data_import.runner import process_job

        job = ImportJob.objects.create(
            uploaded_by=self.admin_user,
            file="imports/boom.csv",
            file_type=FileType.CSV,
            import_type=ImportType.GRADES,
            status=JobStatus.PROCESSING,
        )
        with mock.patch(
            "apps.data_import.runner.dispatch_domain_processing",
            side_effect=RuntimeError("boom"),
        ):
            process_job(job.pk, ["student_id"])

        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(
            job.error_log[0]["code"], ImportErrorCode.INTERNAL_PIPELINE_ERROR
        )

    def test_missing_job_is_ignored(self):
        from apps.data_import.runner import process_job

        process_job("00000000-0000-0000-0000-000000000000", ["student_id"])


class ImportTemplateApiTest(DataImportApiBase):
    """GET /api/v1/data-import/templates/{import_type}/."""

    def _schema(self):
        from apps.data_import.importers.base import (
            ATTENDANCE_ALLOWED_COLUMNS,
            ATTENDANCE_REQUIRED_COLUMNS,
            GUIDANCE_ALLOWED_COLUMNS,
            GUIDANCE_REQUIRED_COLUMNS,
            GRADE_ALLOWED_COLUMNS,
            GRADE_REQUIRED_COLUMNS,
            STUDENT_ALLOWED_COLUMNS,
            STUDENT_REQUIRED_COLUMNS,
        )

        return {
            "grades": (GRADE_REQUIRED_COLUMNS, GRADE_ALLOWED_COLUMNS),
            "attendance": (
                ATTENDANCE_REQUIRED_COLUMNS,
                ATTENDANCE_ALLOWED_COLUMNS,
            ),
            "students": (STUDENT_REQUIRED_COLUMNS, STUDENT_ALLOWED_COLUMNS),
            "guidance_records": (
                GUIDANCE_REQUIRED_COLUMNS,
                GUIDANCE_ALLOWED_COLUMNS,
            ),
        }

    def _get(self, import_type, user=None):
        self._auth(user or self.admin_user)
        return self.client.get(f"/api/v1/data-import/templates/{import_type}/")

    def test_admin_gets_a_template_for_every_approved_type(self):
        from apps.data_import.constants import ImportType

        for import_type, label in ImportType.CHOICES:
            resp = self._get(import_type)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(resp.data["import_type"], import_type)
            self.assertEqual(resp.data["label"], label)
            names = [c["name"] for c in resp.data["columns"]]
            # The downloadable header matches the documented columns.
            self.assertEqual(resp.data["header"], names)
            self.assertTrue(all(isinstance(c["required"], bool) for c in resp.data["columns"]))
            self.assertTrue(all(c["hint"] for c in resp.data["columns"]))

    def test_template_header_matches_the_importer_schema(self):
        for import_type, (required, allowed) in self._schema().items():
            resp = self._get(import_type)
            header = resp.data["header"]
            marked_required = {
                c["name"] for c in resp.data["columns"] if c["required"]
            }
            self.assertEqual(set(header), set(allowed))
            self.assertEqual(marked_required, set(required))
            # Required columns come first so the template reads in the
            # order the importer reports a missing column.
            self.assertEqual(
                header[: len(required)],
                [c["name"] for c in resp.data["columns"] if c["required"]],
            )

    def test_template_advertises_server_controlled_columns(self):
        resp = self._get("guidance_records")
        self.assertEqual(
            resp.data["forbidden_columns"], ["counselor", "recorded_by"]
        )
        resp = self._get("attendance")
        self.assertEqual(resp.data["forbidden_columns"], ["recorded_by"])

    def test_faculty_may_only_view_templates_they_can_upload(self):
        for import_type in ("grades", "attendance"):
            resp = self._get(import_type, user=self.faculty_user)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for import_type in ("students", "guidance_records"):
            resp = self._get(import_type, user=self.faculty_user)
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_view_templates(self):
        resp = self._get("grades", user=self.student_user)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_parent_cannot_view_templates(self):
        resp = self._get("grades", user=self.parent_user)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unknown_import_type_is_not_found(self):
        resp = self._get("bogus")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_template_requires_authentication(self):
        resp = self.client.get("/api/v1/data-import/templates/grades/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
