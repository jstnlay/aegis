"""
PH8.8 — Controlled Export tests.

Covers authorization, role/scope isolation, anonymized student export,
CSV/XLSX format correctness, determinism, CSV-injection neutralization,
row-limit / throttle enforcement, and filename / Content-Disposition safety.
"""

import csv
import io
from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    FacultyProfile,
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
    User,
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
from apps.data_import.constants import (
    ADMIN_ONLY_EXPORT_TYPES,
    ALL_FACULTY_EXPORT_TYPES,
    ExportErrorCode,
    ExportFormat,
    ExportType,
    MAX_EXPORT_ROWS,
)

from apps.data_import.exports import (
    build_content_disposition,
    safe_export_filename,
    sanitize_export_cell,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _domain(suffix=""):
    """Build a minimal academic structure with two students in one section.

    One student (s1) belongs to the section taught by faculty `fp_own` and
    another faculty `fp_other` also teaches the same section (so attendance
    scoping is by section).  A second section `section_other` is taught only
    by `fp_other`, giving faculty scope distinctions.

    Returns a dict with model objects for assertions.
    """
    ay = AcademicYear.objects.create(
        name=f"2025-2026{suffix}", start_date="2025-06-01",
        end_date="2026-03-31", is_current=True,
    )
    g7 = GradeLevel.objects.create(name=f"Grade 7{suffix}", level_number=7)

    fp_own_user = User.objects.create_user(
        email=f"fac_own{suffix}@test.com", password="pass12345",
        first_name="Own", last_name="Teacher", role="faculty",
    )
    fp_own = FacultyProfile.objects.create(user=fp_own_user, employee_id=f"E-OWN{suffix}")

    fp_other_user = User.objects.create_user(
        email=f"fac_other{suffix}@test.com", password="pass12345",
        first_name="Other", last_name="Teacher", role="faculty",
    )
    fp_other = FacultyProfile.objects.create(user=fp_other_user, employee_id=f"E-OT{suffix}")

    section = Section.objects.create(
        name=f"S-7A{suffix}", grade_level=g7, academic_year=ay, adviser=fp_own,
    )
    section_other = Section.objects.create(
        name=f"S-7B{suffix}", grade_level=g7, academic_year=ay, adviser=fp_other,
    )

    subject_a = Subject.objects.create(name=f"Math{suffix}", code=f"MG7A{suffix}", grade_level=g7)
    subject_b = Subject.objects.create(name=f"Sci{suffix}", code=f"SG7B{suffix}", grade_level=g7)
    sa_own = SubjectAssignment.objects.create(
        subject=subject_a, faculty=fp_own, section=section, academic_year=ay,
    )
    sa_other = SubjectAssignment.objects.create(
        subject=subject_b, faculty=fp_other, section=section, academic_year=ay,
    )
    sa_other_only = SubjectAssignment.objects.create(
        subject=subject_b, faculty=fp_other, section=section_other, academic_year=ay,
    )

    gp = GradingPeriod.objects.create(
        academic_year=ay, name=f"Q1{suffix}", order=1,
        start_date="2025-06-01", end_date="2025-08-31",
    )

    # Two students in `section`.
    def _mk_student(email, sid, first, last, section_obj):
        u = User.objects.create_user(
            email=email, password="pass12345", first_name=first, last_name=last, role="student",
        )
        sp = StudentProfile.objects.create(
            user=u, student_id=sid, grade_level=g7, section=section_obj,
            enrollment_date="2025-06-01",
        )
        Enrollment.objects.create(
            student=sp, section=section_obj, academic_year=ay, date_enrolled="2025-06-01",
        )
        return sp

    s1 = _mk_student(f"s1{suffix}@test.com", f"STU-001{suffix}", "Ana", "Zulu", section)
    s2 = _mk_student(f"s2{suffix}@test.com", f"STU-002{suffix}", "Ben", "Alpha", section)

    # A student in the other faculty's section, for foreign-row checks.
    s_foreign = _mk_student(f"sf{suffix}@test.com", f"STU-009{suffix}", "Cid", "Gamma", section_other)

    return {
        "ay": ay,
        "grade": g7,
        "fp_own": fp_own,
        "fp_other": fp_other,
        "section": section,
        "section_other": section_other,
        "sa_own": sa_own,
        "sa_other": sa_other,
        "sa_other_only": sa_other_only,
        "gp": gp,
        "s1": s1,
        "s2": s2,
        "s_foreign": s_foreign,
        "section_name": f"S-7A{suffix}",
        "subject_a_code": f"MG7A{suffix}",
    }


class ExportApiBase(TestCase):
    """Shared users + auth + domain helpers for export tests."""

    def setUp(self):
        self.dom = _domain()
        self.admin_user = User.objects.create_user(
            email="admin_ex@test.com", password="pass12345",
            first_name="Ad", last_name="Min", role="admin",
        )
        self.faculty_user = User.objects.create_user(
            email="fac_ex@test.com", password="pass12345",
            first_name="Fac", last_name="Exporter", role="faculty",
        )
        self.guidance_user = User.objects.create_user(
            email="guide_ex@test.com", password="pass12345",
            first_name="Guide", last_name="Ance", role="guidance",
        )
        self.student_user = User.objects.create_user(
            email="stu_ex@test.com", password="pass12345",
            first_name="Stu", last_name="Dent", role="student",
        )
        self.parent_user = User.objects.create_user(
            email="parent_ex@test.com", password="pass12345",
            first_name="Par", last_name="Ent", role="parent",
        )
        self.client = APIClient()

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _get(self, path, user, **params):
        self._auth(user)
        return self.client.get(path, params)

    def _csv_rows(self, response):
        text = response.content
        if text.startswith(b"\xef\xbb\xbf"):
            text = text[len(b"\xef\xbb\xbf"):]
        decoded = text.decode("utf-8")
        return list(csv.reader(io.StringIO(decoded)))

    def _seed_grade(self, score=90):
        """Create one grade row in the shared domain.

        An authorised-but-empty export now answers 400 EXPORT_EMPTY
        (TC-FAC-19), so any test that asserts on the generated file itself
        must seed at least one row first.
        """
        return Grade.objects.create(
            student=self.dom["s1"], subject_assignment=self.dom["sa_own"],
            grading_period=self.dom["gp"], score=score, letter_grade="A",
            remarks="ok", encoded_by=self.dom["fp_own"], status="finalized",
        )

    def _seed_attendance(self):
        """Create one attendance row in the shared domain (see `_seed_grade`)."""
        return AttendanceRecord.objects.create(
            student=self.dom["s1"], section=self.dom["section"],
            date="2025-07-01", status="present", recorded_by=self.dom["fp_own"],
        )

    def assertExportEmpty(self, resp):
        """Assert the response is the EXPORT_EMPTY envelope, not a file."""
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNone(resp.get("Content-Disposition", None))
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], ExportErrorCode.EXPORT_EMPTY)
        self.assertIn("No data is available", body["error"]["message"])


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


class ExportAuthorizationTest(ExportApiBase):
    def test_anonymous_returns_401(self):
        resp = self.client.get("/api/v1/data-import/exports/grades/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthorized_role_returns_403(self):
        # Students export is admin-only -> 403 for non-admin roles.
        resp = self._get("/api/v1/data-import/exports/students/", self.faculty_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_students_export_admin_only_constant(self):
        self.assertEqual(ADMIN_ONLY_EXPORT_TYPES, frozenset({ExportType.STUDENTS}))


# ---------------------------------------------------------------------------
# PH8.9 — Security / integration regression (invalid input, methods, leakage)
# ---------------------------------------------------------------------------


class ExportSecurityRegressionTest(ExportApiBase):
    """Targeted PH8.9 security assertions for the controlled-export surface.

    These lock in behaviors the view already implements but that were not
    covered by the PH8.8 export tests: malformed format rejection, HTTP
    method restriction, raw-exception non-disclosure, and parent/student
    cross-dataset row isolation.
    """

    def test_invalid_file_format_returns_400_with_stable_code(self):
        resp = self._get("/api/v1/data-import/exports/grades/", self.admin_user, file_format="pdf")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], ExportErrorCode.UNSUPPORTED_FORMAT)
        self.assertEqual(resp.get("Content-Disposition", None), None)
        self.assertNotIn("pdf", str(body).lower())

    def test_unknown_export_type_path_is_not_matched(self):
        # Trying to reach an export type that does not exist must not fall
        # through to another dataset or a generic export.
        for path in ("exports/foo/", "exports/grades/x/", "exports/", "exports"):
            resp = self._get(f"/api/v1/data-import/{path}", self.admin_user)
            self.assertIn(resp.status_code, (status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED))

    def test_write_methods_are_rejected(self):
        # Exports are read-only: POST/PUT/DELETE produce 405, not a file.
        for method, url in (
            ("post", "/api/v1/data-import/exports/grades/?file_format=csv"),
            ("put", "/api/v1/data-import/exports/attendance/?file_format=csv"),
            ("delete", "/api/v1/data-import/exports/students/?file_format=csv"),
        ):
            self._auth(self.admin_user)
            resp = getattr(self.client, method)(url)
            self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_internal_error_does_not_leak_exception_details(self):
        # A failure while building rows must surface as a generic envelope,
        # never a traceback, filesystem path, or raw message.
        self._auth(self.admin_user)
        with mock.patch(
            "apps.data_import.views.rows_for_queryset",
            side_effect=RuntimeError("boom /app/secret.py"),
        ):
            resp = self.client.get("/api/v1/data-import/exports/grades/?file_format=csv")
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        body = resp.content.decode("utf-8", "replace")
        for needle in ("Traceback", "secret.py", "C:/", "boom", "RuntimeError"):
            self.assertNotIn(needle, body)
        self.assertIn(ExportErrorCode.INTERNAL_EXPORT_ERROR, body)

    def test_parent_no_link_sees_no_attendance(self):
        # Parent with no linked child has zero attendance rows in scope, so
        # the export answers with the no-data message (TC-FAC-19) instead of
        # a file — and certainly never with someone else's rows.
        ParentProfile.objects.create(user=self.parent_user, relationship_to_student="mother")
        AttendanceRecord.objects.create(
            student=self.dom["s1"], section=self.dom["section"],
            date="2025-07-01", status="present", recorded_by=self.dom["fp_own"],
        )
        resp = self._get(
            "/api/v1/data-import/exports/attendance/", self.parent_user, file_format="csv"
        )
        self.assertExportEmpty(resp)

    def test_student_not_in_section_sees_no_attendance(self):
        # A student gets ONLY their own rows; a foreign-section record is
        # invisible to them, so their (empty) scope gets no file at all.
        AttendanceRecord.objects.create(
            student=self.dom["s_foreign"], section=self.dom["section_other"],
            date="2025-07-02", status="absent", recorded_by=self.dom["fp_other"],
        )
        resp = self._get(
            "/api/v1/data-import/exports/attendance/", self.dom["s1"].user, file_format="csv"
        )
        self.assertExportEmpty(resp)

    def test_empty_scope_returns_export_empty_envelope(self):
        # No grades are seeded here, so the admin's own export answers with
        # the no-data envelope rather than a header-only file.
        resp = self._get(
            "/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv"
        )
        self.assertExportEmpty(resp)


# ---------------------------------------------------------------------------
# Role / scope
# ---------------------------------------------------------------------------


class ExportRoleScopeTest(ExportApiBase):
    def _grade(self, student, sa, score=90):
        return Grade.objects.create(
            student=student, subject_assignment=sa, grading_period=self.dom["gp"],
            score=score, letter_grade="A", remarks="Excellent", encoded_by=self.dom["fp_own"],
            status="finalized",
        )

    def _attendance(self, student, section, date, status_="present"):
        return AttendanceRecord.objects.create(
            student=student, section=section, date=date, status=status_,
            recorded_by=self.dom["fp_own"],
        )

    def setUp(self):
        super().setUp()
        self.dom["grade_own"] = self._grade(self.dom["s1"], self.dom["sa_own"])       # fp_own subject
        self.dom["grade_other"] = self._grade(self.dom["s1"], self.dom["sa_other"])   # fp_other subject
        self.dom["grade_other_only"] = self._grade(
            self.dom["s_foreign"], self.dom["sa_other_only"]
        )  # fp_other only, foreign section
        self.dom["att_own"] = self._attendance(self.dom["s1"], self.dom["section"], "2025-07-01")
        self.dom["att_other"] = self._attendance(
            self.dom["s_foreign"], self.dom["section_other"], "2025-07-02"
        )

    def test_admin_sees_all_grade_rows(self):
        resp = self._get("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = self._csv_rows(resp)[1:]
        self.assertEqual(len(rows), 3)  # all grades

    def test_faculty_grades_only_own_subject(self):
        resp = self._get(
            "/api/v1/data-import/exports/grades/", self.dom["fp_own"].user, file_format="csv"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = self._csv_rows(resp)[1:]
        ids = {r[0] for r in rows}
        codes = {r[4] for r in rows}
        self.assertEqual(len(rows), 1)
        # fp_own only owns the Math subject on the shared section.
        self.assertIn(self.dom["s1"].student_id, ids)
        self.assertNotIn(self.dom["s_foreign"].student_id, ids)
        self.assertEqual(codes, {self.dom["subject_a_code"]})

    def test_faculty_attendance_only_permitted_sections(self):
        resp = self._get(
            "/api/v1/data-import/exports/attendance/",
            self.dom["fp_own"].user, file_format="csv",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = self._csv_rows(resp)[1:]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], self.dom["s1"].student_id)

    def test_guidance_sees_all_rows(self):
        resp = self._get(
            "/api/v1/data-import/exports/grades/", self.guidance_user, file_format="csv"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = self._csv_rows(resp)[1:]
        self.assertEqual(len(rows), 3)

    def test_student_sees_only_own_grade_rows(self):
        resp = self._get(
            "/api/v1/data-import/exports/grades/", self.dom["s1"].user, file_format="csv"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = self._csv_rows(resp)[1:]
        self.assertEqual(len(rows), 2)  # s1 has 2 grades
        for row in rows:
            self.assertEqual(row[0], self.dom["s1"].student_id)

    def test_student_sees_only_own_attendance_rows(self):
        resp = self._get(
            "/api/v1/data-import/exports/attendance/", self.dom["s1"].user, file_format="csv"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = self._csv_rows(resp)[1:]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], self.dom["s1"].student_id)

    def test_parent_sees_only_linked_child_rows(self):
        ParentProfile.objects.create(user=self.parent_user, relationship_to_student="mother")
        ParentStudentLink.objects.create(parent=self.parent_user.parent_profile, student=self.dom["s1"])
        resp = self._get(
            "/api/v1/data-import/exports/grades/", self.parent_user, file_format="csv"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = self._csv_rows(resp)[1:]
        for row in rows:
            self.assertEqual(row[0], self.dom["s1"].student_id)

    def test_parent_with_no_link_sees_nothing(self):
        ParentProfile.objects.create(user=self.parent_user, relationship_to_student="mother")
        resp = self._get(
            "/api/v1/data-import/exports/grades/", self.parent_user, file_format="csv"
        )
        # Grades exist for other people, but none in this parent's scope:
        # the export refuses with the no-data message (TC-FAC-19) rather
        # than handing back an empty file.
        self.assertExportEmpty(resp)

    def test_no_foreign_row_is_ever_present(self):
        # Faculty sees only own; foreign student's data must never leak.
        for path in ("grades", "attendance"):
            resp = self._get(
                f"/api/v1/data-import/exports/{path}/",
                self.dom["fp_own"].user, file_format="csv",
            )
            rows = self._csv_rows(resp)[1:]
            for row in rows:
                self.assertNotEqual(row[0], self.dom["s_foreign"].student_id)


# ---------------------------------------------------------------------------
# Student export (admin-only, anonymized)
# ---------------------------------------------------------------------------


class ExportStudentTest(ExportApiBase):
    def _student_row(self):
        return self._get(
            "/api/v1/data-import/exports/students/", self.admin_user, file_format="csv"
        )

    def test_student_export_admin_only(self):
        for role_user in (self.faculty_user, self.guidance_user, self.student_user, self.parent_user):
            resp = self._get("/api/v1/data-import/exports/students/", role_user, file_format="csv")
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_export_anonymized_by_default(self):
        # Set private fields so we can prove they are never exported.
        for sp in StudentProfile.objects.all():
            sp.date_of_birth = "2000-01-01"
            sp.guardian_contact = "0917-000-0000"
            sp.user.email = f"secret_{sp.student_id}@test.com"
            sp.user.save()
            sp.save()
        resp = self._student_row()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = self._csv_rows(resp)
        header = rows[0]
        lower = [h.lower() for h in header]
        for forbidden in ("email", "date_of_birth", "guardian_contact", "password"):
            self.assertNotIn(forbidden, lower, f"column {forbidden} leaked")

        body = resp.content.decode("utf-8", "replace").lower()
        self.assertNotIn("date_of_birth", body)
        self.assertNotIn("guardian_contact", body)
        self.assertNotIn("@test.com", body)
        self.assertNotIn("pbkdf2_sha256", body)
        self.assertNotIn("must_change_password", body)
        # Keys that ARE present
        self.assertIn("student_id", header)
        self.assertIn("student_name", header)
        self.assertIn("enrollment_date", header)

    def test_credentials_never_exported(self):
        for u in User.objects.all():
            u.set_password("SuperSecret99!")
            u.must_change_password = True
            u.save()
        resp = self._student_row()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.content.decode("utf-8", "replace")
        self.assertNotIn("SuperSecret99", body)
        self.assertNotIn("pbkdf2_sha256", body)
        self.assertNotIn("must_change_password", body)


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------


class ExportFormatTest(ExportApiBase):
    def setUp(self):
        super().setUp()
        # Format assertions inspect a real generated file; an empty scope now
        # answers 400 EXPORT_EMPTY (TC-FAC-19), so seed one row of each kind.
        self._seed_grade()
        self._seed_attendance()

    def test_csv_content_type_correct(self):
        resp = self._get("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", resp["Content-Type"])

    def test_csv_utf8_bom(self):
        resp = self._get("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self.assertTrue(resp.content.startswith(b"\xef\xbb\xbf"))

    def test_xlsx_opens_with_openpyxl(self):
        resp = self._get("/api/v1/data-import/exports/grades/", self.admin_user, file_format="xlsx")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("spreadsheet", resp["Content-Type"])
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(resp.content), data_only=True)
        ws = wb.active
        header = [c.value for c in ws[1]]
        self.assertEqual(
            header,
            [
                "student_id", "student_name", "grade_level", "section",
                "subject_code", "subject_name", "grading_period", "score",
                "letter_grade", "remarks", "status", "encoded_by",
            ],
        )

    def test_stable_expected_headers_grades(self):
        resp = self._get("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        rows = self._csv_rows(resp)
        self.assertEqual(
            rows[0],
            [
                "student_id", "student_name", "grade_level", "section",
                "subject_code", "subject_name", "grading_period", "score",
                "letter_grade", "remarks", "status", "encoded_by",
            ],
        )

    def test_stable_expected_headers_attendance(self):
        resp = self._get("/api/v1/data-import/exports/attendance/", self.admin_user, file_format="csv")
        rows = self._csv_rows(resp)
        self.assertEqual(
            rows[0],
            ["student_id", "student_name", "section", "date", "status", "recorded_by"],
        )

    def test_stable_expected_headers_students(self):
        resp = self._get("/api/v1/data-import/exports/students/", self.admin_user, file_format="csv")
        rows = self._csv_rows(resp)
        self.assertEqual(
            rows[0],
            ["student_id", "student_name", "grade_level", "section", "enrollment_date", "is_active"],
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class ExportDeterminismTest(ExportApiBase):
    def _mk_grades(self):
        Grade.objects.create(
            student=self.dom["s1"], subject_assignment=self.dom["sa_own"],
            grading_period=self.dom["gp"], score=95, letter_grade="A",
            remarks="Good", encoded_by=self.dom["fp_own"], status="finalized",
        )
        Grade.objects.create(
            student=self.dom["s2"], subject_assignment=self.dom["sa_other"],
            grading_period=self.dom["gp"], score=88, letter_grade="B",
            remarks="Fair", encoded_by=self.dom["fp_other"], status="submitted",
        )

    def test_identical_state_produces_identical_ordered_csv(self):
        self._mk_grades()
        r1 = self._get("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        r2 = self._get("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self.assertEqual(r1.content, r2.content)


# ---------------------------------------------------------------------------
# CSV security (injection neutralization)
# ---------------------------------------------------------------------------


class ExportCsvSecurityTest(ExportApiBase):
    def test_sanitize_cell_neutralizes_formula_prefixes(self):
        for dangerous in ("=cmd", "+1", "-1", "@foo"):
            self.assertTrue(sanitize_export_cell(dangerous).startswith("'"))
        # safe values unchanged
        self.assertEqual(sanitize_export_cell("Ana"), "Ana")
        self.assertIsNone(sanitize_export_cell(None))

    def test_injection_in_name_and_remarks_neutralized(self):
        self.dom["s1"].user.first_name = '=HYPERLINK("http://evil")'
        self.dom["s1"].user.save()
        Grade.objects.create(
            student=self.dom["s1"], subject_assignment=self.dom["sa_own"],
            grading_period=self.dom["gp"], score=90, letter_grade="A",
            remarks="+SUM(1,2)", encoded_by=self.dom["fp_own"], status="finalized",
        )
        resp = self._get("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        rows = self._csv_rows(resp)
        name_col = rows[0].index("student_name")
        remarks_col = rows[0].index("remarks")
        data = [r for r in rows[1:] if r[name_col]]
        self.assertTrue(data)
        self.assertTrue(data[0][name_col].startswith("'="))
        self.assertTrue(data[0][remarks_col].startswith("'+"))


# ---------------------------------------------------------------------------
# Limits / throttle
# ---------------------------------------------------------------------------


class ExportLimitThrottleTest(ExportApiBase):
    @mock.patch("apps.data_import.exports.MAX_EXPORT_ROWS", 0)
    def test_over_limit_returns_400_export_too_large(self):
        Grade.objects.create(
            student=self.dom["s1"], subject_assignment=self.dom["sa_own"],
            grading_period=self.dom["gp"], score=90, letter_grade="A",
            remarks="x", encoded_by=self.dom["fp_own"], status="finalized",
        )
        resp = self._get("/api/v1/data-import/exports/grades/", self.admin_user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(ExportErrorCode.EXPORT_TOO_LARGE, resp.content.decode("utf-8"))

    def test_throttle_returns_429(self):
        from django.core.cache import cache

        cache.clear()
        self._seed_grade()  # a real file, so the first request succeeds (200)
        self._auth(self.admin_user)
        with mock.patch.dict(
            "core.throttling.ExportRateThrottle.THROTTLE_RATES",
            {"data_export": "1/min"},
        ):
            first = self.client.get(
                "/api/v1/data-import/exports/grades/?file_format=csv",
                REMOTE_ADDR="192.0.2.60",
            )
            self.assertEqual(first.status_code, status.HTTP_200_OK)
            second = self.client.get(
                "/api/v1/data-import/exports/grades/?file_format=csv",
                REMOTE_ADDR="192.0.2.60",
            )
            self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        cache.clear()


# ---------------------------------------------------------------------------
# Filename / download
# ---------------------------------------------------------------------------


class ExportFilenameTest(TestCase):
    def test_safe_export_filename(self):
        self.assertEqual(safe_export_filename("grades", "csv"), "aegis_grades_export.csv")
        self.assertEqual(safe_export_filename("students", "xlsx"), "aegis_students_export.xlsx")

    def test_filename_sanitized_no_crlf(self):
        name = safe_export_filename("grades\r\nInjected", "csv")
        self.assertNotIn("\r", name)
        self.assertNotIn("\n", name)

    def test_content_disposition_no_injection(self):
        cd = build_content_disposition("grades\r\nx.csv")
        self.assertNotIn("\r", cd)
        self.assertNotIn("\n", cd)
        self.assertIn("attachment", cd)
        self.assertIn("filename=", cd)

    def test_download_headers_present(self):
        dom = _domain()
        admin = User.objects.create_user(
            email="admin_fn@test.com", password="pass12345",
            first_name="A", last_name="D", role="admin",
        )
        client = APIClient()
        client.force_authenticate(user=admin)
        resp = client.get("/api/v1/data-import/exports/students/?file_format=csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("Content-Disposition", resp)
        cd = resp["Content-Disposition"]
        self.assertIn("attachment", cd)
        self.assertNotIn("\r\n", cd)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class ExportConstantsTest(TestCase):
    def test_export_formats(self):
        self.assertEqual(ExportFormat.CSV, "csv")
        self.assertEqual(ExportFormat.XLSX, "xlsx")
        self.assertEqual(ExportFormat.ALL, frozenset({"csv", "xlsx"}))

    def test_export_types(self):
        self.assertEqual(
            ExportType.ALL, frozenset({"grades", "attendance", "students"})
        )

    def test_max_export_rows(self):
        self.assertEqual(MAX_EXPORT_ROWS, 5000)


# ---------------------------------------------------------------------------
# FR-016 / TC-FAC-20 — advisory class summary export
# ---------------------------------------------------------------------------


class AdvisoryExportTest(ExportApiBase):
    """GET /api/v1/data-import/exports/advisory/."""

    URL = "/api/v1/data-import/exports/advisory/"

    def test_faculty_gets_one_row_per_student_in_their_class(self):
        # The class has records already (grade + attendance seeded by the
        # fixtures above); seed the attendance row for a full aggregate row.
        AttendanceRecord.objects.create(
            student=self.dom["s1"], section=self.dom["section"],
            date="2025-07-02", status="absent", recorded_by=self.dom["fp_own"],
        )
        self._seed_attendance()
        self._seed_grade(score=90)

        resp = self._get(self.URL, self.dom["fp_own"].user, file_format="csv")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = self._csv_rows(resp)
        self.assertEqual(
            rows[0],
            [
                "student_id", "student_name", "grade_level", "section",
                "attendance_present", "attendance_late", "attendance_absent",
                "attendance_total", "grades_recorded", "grade_average",
            ],
        )
        # Only the two students enrolled in the faculty's own section; the
        # foreign student never appears.
        body = [row[0] for row in rows[1:]]
        self.assertIn(self.dom["s1"].student_id, body)
        self.assertIn(self.dom["s2"].student_id, body)
        self.assertNotIn(self.dom["s_foreign"].student_id, body)

        # Deterministic ordering by last name: Alpha (Ben) before Zulu (Ana).
        self.assertEqual(rows[1][0], self.dom["s2"].student_id)
        self.assertEqual(rows[2][0], self.dom["s1"].student_id)

        # Ana: one present, one absent, one finalized grade of 90.
        ana = rows[2]
        self.assertEqual(ana[4], "1")   # present
        self.assertEqual(ana[5], "0")   # late
        self.assertEqual(ana[6], "1")   # absent
        self.assertEqual(ana[7], "2")   # total
        self.assertEqual(ana[8], "1")   # grades recorded
        self.assertEqual(ana[9], "90.00")

        # Ben has no attendance and no grades at all: real zero counts and a
        # blank average, never a fabricated 0.00.
        ben = rows[1]
        self.assertEqual(ben[4], "0")
        self.assertEqual(ben[7], "0")
        self.assertEqual(ben[8], "0")
        self.assertEqual(ben[9], "")

    def test_grade_average_is_blank_when_nothing_is_scored(self):
        resp = self._get(self.URL, self.dom["fp_own"].user, file_format="csv")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = self._csv_rows(resp)
        self.assertEqual(rows[1][9], "")
        self.assertEqual(rows[2][9], "")

    def test_faculty_with_no_sections_gets_the_empty_export_envelope(self):
        other = User.objects.create_user(
            email="fac_noclass@test.com", password="pass12345", role="faculty",
        )
        FacultyProfile.objects.create(user=other, employee_id="E-NONE")
        self.assertExportEmpty(self._get(self.URL, other, file_format="csv"))

    def test_other_roles_are_outside_the_surface(self):
        for user in (
            self.admin_user,
            self.guidance_user,
            self.student_user,
            self.parent_user,
        ):
            resp = self._get(self.URL, user, file_format="csv")
            self.assertEqual(
                resp.status_code, status.HTTP_403_FORBIDDEN, user.email
            )
            body = resp.json()
            self.assertEqual(
                body["error"]["code"], ExportErrorCode.PERMISSION_DENIED
            )

    def test_faculty_export_matrix_includes_the_advisory_summary(self):
        self.assertEqual(
            ALL_FACULTY_EXPORT_TYPES,
            frozenset(
                {
                    ExportType.GRADES,
                    ExportType.ATTENDANCE,
                    ExportType.ADVISORY,
                }
            ),
        )
        # The administrator authority set is unchanged: "advisory class" is
        # not a concept an administrator exports.
        self.assertNotIn(ExportType.ADVISORY, ExportType.ALL)

    def test_unknown_export_type_stays_unsupported(self):
        resp = self._get(
            "/api/v1/data-import/exports/advisory-v2/",
            self.dom["fp_own"].user,
            file_format="csv",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
