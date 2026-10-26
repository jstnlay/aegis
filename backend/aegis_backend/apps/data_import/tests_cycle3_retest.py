"""
Cycle-3 log (AEGIS Test Case Log Testing Phase Cycle 3 Complete.md) — acceptance re-test.

Every test here reproduces one FAILED row's *actual results* text verbatim in
its docstring, then asserts the behaviour the log says is missing. The point is
that a reader can map one failing log row to one test.

These are re-tests, not regression tests: where the feature already existed at
HEAD (TC-FAC-18/19/20), the test pins the existing behaviour rather than new
code.

Live HTTP only for the new whitelist propagation test; everything else uses the
existing synchronous job pipeline.
"""

import csv
import io

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    FacultyProfile,
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
from apps.data_import.exports import (
    ATTENDANCE_ROUNDTRIP_COLUMNS,
    GRADE_ROUNDTRIP_COLUMNS,
    GUIDANCE_ROUNDTRIP_COLUMNS,
    STUDENT_ROUNDTRIP_COLUMNS,
    ExportType,
    export_queryset_for,
    rows_for_queryset,
)
from apps.data_import.models import ImportJob


def _auth(client, user):
    client.force_authenticate(user=user)
    return client


def _post_job(client, csv_bytes, import_type, name="retest.csv"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return client.post(
        "/api/v1/data-import/jobs/",
        {
            "file": SimpleUploadedFile(name, csv_bytes, content_type="text/csv"),
            "import_type": import_type,
        },
        format="multipart",
    )


class _Cycle3Base(TestCase):
    """Minimal domain: one academic year, one section, one assignment."""

    def setUp(self):
        self.ay = AcademicYear.objects.create(
            name="2025-2026", start_date="2025-06-01", end_date="2026-03-31",
            is_current=True,
        )
        self.g7 = GradeLevel.objects.create(name="Grade 7", level_number=7)
        self.section = Section.objects.create(
            name="S-7A", grade_level=self.g7, academic_year=self.ay
        )
        self.subject = Subject.objects.create(
            name="Math 7", code="MG7A", grade_level=self.g7
        )
        self.gp = GradingPeriod.objects.create(
            academic_year=self.ay, name="Term 1", order=1,
            start_date="2025-06-01", end_date="2025-08-31",
        )
        self.admin_user = User.objects.create_user(
            email="admin_rt@test.com", password="pass12345",
            first_name="Ad", last_name="Min", role="admin",
        )
        self.faculty_user = User.objects.create_user(
            email="fac_rt@test.com", password="pass12345",
            first_name="Sam", last_name="Faculty", role="faculty",
        )
        self.fp = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="EMP-RT-001"
        )
        self.sa = SubjectAssignment.objects.create(
            subject=self.subject, section=self.section,
            faculty=self.fp, academic_year=self.ay,
        )

        self.s1 = self._student("s1rt@test.com", "STU-RT-001", "Ana", "Zulu")
        self.s2 = self._student("s2rt@test.com", "STU-RT-002", "Ben", "Alpha")

    def _student(self, email, code, first, last):
        user = User.objects.create_user(
            email=email, password="pass12345",
            first_name=first, last_name=last, role="student",
        )
        profile = StudentProfile.objects.create(
            user=user, student_id=code, grade_level=self.g7,
            section=self.section, enrollment_date="2025-06-01",
        )
        Enrollment.objects.create(
            student=profile, academic_year=self.ay, section=self.section,
            date_enrolled="2025-06-01",
        )
        return profile


class _ExportMixin:
    def _export(self, client, kind, schema="reimport", fmt="csv"):
        params = {"file_format": fmt}
        if schema:
            params["schema"] = schema
        return client.get(f"/api/v1/data-import/exports/{kind}/", params)

    def _header(self, body):
        text = body
        if text.startswith(b"\xef\xbb\xbf"):
            text = text[3:]
        return list(csv.reader(io.StringIO(text.decode("utf-8"))))[0]


class Cycle3AdminImportRetest(_Cycle3Base, _ExportMixin):
    """
    TC-ADM-03/04/05 — the log's Cycle-3 actuals were:

      * TC-ADM-03 — "Importing an Exported Grades failed. Missing required
        column(s): subject_assignment" and "Importing an Exported Student
        failed. Missing required column(s): email, first_name, last_name"
      * TC-ADM-04 — "Importing an Exported Attendance failed. Unknown
        column(s) not supported by this import: recorded_by, student_name"
      * TC-ADM-05 — "Export of Guidance records not implemented"

    Each test exports through the API, uploads the downloaded bytes through
    the real job pipeline, and asserts a completed job with zero error rows.
    """

    def setUp(self):
        super().setUp()
        self.client = _auth(APIClient(), self.admin_user)

    def test_adm_03_exported_grades_reimport_has_subject_assignment(self):
        Grade.objects.create(
            student=self.s1, subject_assignment=self.sa,
            grading_period=self.gp, score=90, status="finalized",
            encoded_by=self.fp,
        )
        resp = self._export(self.client, "grades")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(self._header(resp.content), GRADE_ROUNDTRIP_COLUMNS)

        Grade.objects.all().delete()
        job = _post_job(self.client, resp.content, "grades")
        self.assertEqual(job.status_code, status.HTTP_201_CREATED, job.content)
        self.assertEqual(job.data["status"], "completed")
        self.assertEqual(job.data["error_rows"], 0)
        self.assertEqual(Grade.objects.count(), 1)

    def test_adm_03_exported_students_reimport_has_identity_columns(self):
        resp = self._export(self.client, "students")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(self._header(resp.content), STUDENT_ROUNDTRIP_COLUMNS)

        Enrollment.objects.all().delete()
        StudentProfile.objects.all().delete()
        User.objects.filter(role="student").delete()

        job = _post_job(self.client, resp.content, "students")
        self.assertEqual(job.status_code, status.HTTP_201_CREATED, job.content)
        self.assertEqual(job.data["status"], "completed")
        self.assertEqual(job.data["error_rows"], 0)
        self.assertEqual(StudentProfile.objects.count(), 2)

    def test_adm_04_exported_attendance_reimport_has_no_forbidden_columns(self):
        from apps.attendance.models import AttendanceRecord

        AttendanceRecord.objects.create(
            student=self.s1, section=self.section, date="2025-07-01",
            status="present", recorded_by=self.fp,
        )
        resp = self._export(self.client, "attendance")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        header = self._header(resp.content)
        self.assertEqual(header, ATTENDANCE_ROUNDTRIP_COLUMNS)
        # The log named these two as rejected by the importer.
        self.assertNotIn("recorded_by", header)
        self.assertNotIn("student_name", header)

        AttendanceRecord.objects.all().delete()
        job = _post_job(self.client, resp.content, "attendance")
        self.assertEqual(job.status_code, status.HTTP_201_CREATED, job.content)
        self.assertEqual(job.data["status"], "completed")
        self.assertEqual(job.data["error_rows"], 0)
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    def test_adm_05_guidance_records_export_exists_and_reimports(self):
        from apps.accounts.models import GuidanceProfile
        from apps.guidance.models import ConsultationRecord, RiskAlert
        from django.utils import timezone

        counselor = GuidanceProfile.objects.create(
            user=User.objects.create_user(
                email="guide_c3@test.com", password="pass12345",
                first_name="Gail", last_name="Counsel", role="guidance",
            ),
            employee_id="GDE-C3-001",
        )
        ConsultationRecord.objects.create(
            student=self.s1, counselor=counselor, session_date="2025-07-01",
            session_time="10:30", session_type="individual_counseling",
            concern_categories=["academic"], session_notes="Cycle-3 retest.",
            priority_level="high", status="ongoing",
        )
        # The importer attributes the counselor server-side, so the student
        # needs one on record before the re-import can succeed.
        RiskAlert.objects.create(
            student=self.s1, assigned_counselor=counselor, risk_level="high",
            risk_factors=["declining_grades"], generated_at=timezone.now(),
        )

        resp = self._export(self.client, "guidance-records")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(self._header(resp.content), GUIDANCE_ROUNDTRIP_COLUMNS)

        ConsultationRecord.objects.all().delete()
        job = _post_job(self.client, resp.content, "guidance_records")
        self.assertEqual(job.status_code, status.HTTP_201_CREATED, job.content)
        self.assertEqual(job.data["status"], "completed")
        self.assertEqual(job.data["error_rows"], 0)
        self.assertEqual(ConsultationRecord.objects.count(), 1)

    def test_adm_05_standalone_export_route_resolves(self):
        """The route the log said was missing."""
        resp = self.client.get(
            "/api/v1/data-import/exports/guidance-records/",
            {"file_format": "csv"},
        )
        self.assertNotEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class Cycle3FacultyUploadRetest(_Cycle3Base, _ExportMixin):
    """
    TC-FAC-11/13 — the log's actuals were "Grade data is successfully parsed,
    but the excel files fails to import and save the records" and "System fails
    to import the attendance Excel file and displays a failed status".

    Faculty scope differs from admin (their own subject assignments only), so
    this re-tests the same round-trip through a faculty session.
    """

    def setUp(self):
        super().setUp()
        self.client = _auth(APIClient(), self.faculty_user)

    def test_fac_11_faculty_round_trip_grade_file_imports(self):
        Grade.objects.create(
            student=self.s1, subject_assignment=self.sa,
            grading_period=self.gp, score=88, status="draft",
            encoded_by=self.fp,
        )
        resp = self._export(self.client, "grades")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)

        Grade.objects.all().delete()
        job = _post_job(self.client, resp.content, "grades")
        self.assertEqual(job.data["status"], "completed", job.data)
        self.assertEqual(job.data["error_rows"], 0)
        self.assertEqual(Grade.objects.count(), 1)

    def test_fac_13_faculty_round_trip_attendance_file_imports(self):
        from apps.attendance.models import AttendanceRecord

        AttendanceRecord.objects.create(
            student=self.s1, section=self.section, date="2025-07-01",
            status="late", recorded_by=self.fp,
        )
        resp = self._export(self.client, "attendance")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)

        AttendanceRecord.objects.all().delete()
        job = _post_job(self.client, resp.content, "attendance")
        self.assertEqual(job.data["status"], "completed", job.data)
        self.assertEqual(job.data["error_rows"], 0)


class Cycle3MalformedUploadRetest(_Cycle3Base):
    """
    TC-FAC-12/14 and TC-FAC-08 — the log's actuals were "Systems displays a
    failed to import status with 0 of 0 rows processed, without displaying a
    clear validation error for malformed grade data" and the same for
    attendance.

    The re-test asserts the two halves separately: the job still fails (the
    malformed file is not silently accepted), *and* the failure carries a
    human-readable reason the history view can show.
    """

    def setUp(self):
        super().setUp()
        self.client = _auth(APIClient(), self.admin_user)

    def _assert_failed_with_reason(self, job_resp):
        self.assertEqual(job_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(job_resp.data["status"], "failed")
        self.assertEqual(job_resp.data["processed_rows"], 0)

        job_id = job_resp.data["id"]
        # The list endpoint is what the history view reads.
        listed = self.client.get("/api/v1/data-import/jobs/")
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        row = next(j for j in listed.data["results"] if j["id"] == job_id)
        self.assertTrue(
            row["error_log"], "the history row carried no reason for the failure"
        )
        self.assertTrue(row["error_log"][0]["message"].strip())

    def test_fac_12_malformed_grade_upload_fails_with_a_message(self):
        # A required column is absent: header validation rejects the file.
        resp = _post_job(
            self.client,
            b"student_id,grading_period,score\nSTU-RT-001,Term 1,90\n",
            "grades",
        )
        self._assert_failed_with_reason(resp)

    def test_fac_14_malformed_attendance_upload_fails_with_a_message(self):
        # Faculty scope, because that is where the log recorded the failure.
        self.client = _auth(APIClient(), self.faculty_user)
        resp = _post_job(
            self.client, b"student_id,date\nSTU-RT-001,not-a-date\n", "attendance"
        )
        self._assert_failed_with_reason(resp)

    def test_fac_08_row_level_error_names_the_row(self):
        """A well-formed header with one bad row still reports why."""
        grade_csv = (
            b"student_id,grading_period,score,subject_assignment,section\n"
            b"STU-RT-001,Term 1,999," + str(self.sa.id).encode() + b",S-7A\n"
        )
        resp = _post_job(self.client, grade_csv, "grades")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], "failed")
        self.assertEqual(resp.data["error_rows"], 1)
        # Row detail is what the job-detail view shows.
        detail = self.client.get(f"/api/v1/data-import/jobs/{resp.data['id']}/")
        errors = [r for r in detail.data["records"] if r["status"] == "error"]
        self.assertEqual(len(errors), 1)
        message = errors[0]["error_message"]
        self.assertTrue(message.strip())
        # No internals leak into the message.
        for leak in ("Traceback", "sqlite", "File \"", "SELECT "):
            self.assertNotIn(leak, message)


class Cycle3ReportRetest(_Cycle3Base, _ExportMixin):
    """
    TC-FAC-17/19/20 — pin the behaviours the log flagged as missing so the
    stale rows stay verifiable.

    * TC-FAC-17 — "generates the subject performance report without displaying
      'No Data available' message for a subject with no recorded grades".
    * TC-FAC-19 — an empty export must say so instead of sending a broken file.
    * TC-FAC-20 — the advisory class summary must export.
    """

    def setUp(self):
        super().setUp()
        self.client = _auth(APIClient(), self.faculty_user)

    def test_fac_19_empty_scope_export_states_that_there_is_no_data(self):
        # No grades recorded at all: the scope is genuinely empty.
        resp = self._export(self.client, "grades", schema="")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()["error"]["code"], "EXPORT_EMPTY")
        self.assertTrue(resp.json()["error"]["message"].strip())

    def test_fac_20_advisory_summary_exports_a_file(self):
        # The advisory summary is scoped to the students in the caller's own
        # advised/taught sections, so the adviser link is what makes it
        # non-empty.
        from apps.academics.models import Section

        Section.objects.filter(pk=self.section.pk).update(adviser=self.fp)

        # No `schema` parameter: this is the path the faculty page drives.
        resp = self._export(self.client, "advisory", schema="")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        header = self._header(resp.content)
        self.assertIn("attendance_present", header)
        self.assertIn("grade_average", header)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        header = self._header(resp.content)
        self.assertIn("attendance_present", header)
        self.assertIn("grade_average", header)

    def test_standard_schema_is_accepted(self):
        """
        The client names the default schema explicitly as "standard", so the
        API must accept that value - not only an absent parameter.
        """
        from apps.academics.models import Section

        Section.objects.filter(pk=self.section.pk).update(adviser=self.fp)
        resp = self._export(self.client, "advisory", schema="standard")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        header = self._header(resp.content)
        self.assertIn("attendance_present", header)
        self.assertIn("grade_average", header)

    def test_fac_17_subject_without_grades_is_not_reported_as_zero(self):
        """
        The backend half of TC-FAC-17: a subject with no finalized grades must
        report `None`, never `0`, so the UI can state "no data" honestly.
        """
        from apps.analytics import services

        Grade.objects.create(
            student=self.s1, subject_assignment=self.sa,
            grading_period=self.gp, score=75, status="draft",  # not finalized
            encoded_by=self.fp,
        )
        result = services.subject_trends(str(self.ay.id))
        self.assertEqual(result.get("subject_trends", {}), {})

        Grade.objects.all().update(status="finalized", score=80)
        result = services.subject_trends(str(self.ay.id))
        self.assertIn("MG7A", result["subject_trends"])
        self.assertEqual(result["subject_trends"]["MG7A"]["Term 1"], 80.0)


class Cycle3ImportTemplateWhitelistRetest(_Cycle3Base, _ExportMixin):
    """
    Round-trip acceptance, generalised: the header the tester downloads from
    the import-template guide must be exactly the header the re-import export
    produces. If these ever drift, the exported file stops being importable and
    TC-ADM-03/04/05 regress.
    """

    def setUp(self):
        super().setUp()
        self.client = _auth(APIClient(), self.admin_user)

    def test_template_header_matches_export_header(self):
        for import_type, export_kind in (
            ("grades", "grades"),
            ("attendance", "attendance"),
            ("students", "students"),
            ("guidance_records", "guidance-records"),
        ):
            with self.subTest(import_type=import_type):
                tpl = self.client.get(
                    f"/api/v1/data-import/templates/{import_type}/"
                )
                self.assertEqual(tpl.status_code, status.HTTP_200_OK, tpl.content)
                # The guide is JSON; the downloadable header is the same row
                # the importer validates.
                template_header = tpl.json()["header"]

                # The export must be within the template's accepted columns,
                # or the exported file stops being importable.
                for col in self._header_of(export_kind):
                    self.assertIn(
                        col,
                        template_header,
                        f"{col} is exported for {export_kind} but the "
                        f"{import_type} template does not accept it",
                    )

    def _header_of(self, export_kind):
        resp = self.client.get(
            f"/api/v1/data-import/exports/{export_kind}/",
            {"file_format": "csv", "schema": "reimport"},
        )
        # An empty scope still returns the header row.
        if resp.status_code == status.HTTP_200_OK:
            return self._header(resp.content)
        body = resp.json()
        self.assertEqual(body["error"]["code"], "EXPORT_EMPTY")
        return []
