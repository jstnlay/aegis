"""
End-to-end proof that the client's Electronic Class Record workbooks are
accepted in full.

The school sends one workbook per class at the repository root
(``GRADE-7-LATEST-SEPTEMBER-4-2026.xlsx`` and its siblings).  Each workbook is
a multi-sheet form: a roster, three term summaries and the teacher's remarks.
It is uploaded *as the form it is* -- no CSV side door -- and translated by
``deped_forms`` into the flat rows the importers validate.

Two things make this dataset different from the QA SF2/SF9 workbooks, and
both are proved here:

* the learner is identified by **LRN**, not by the school's own code, so the
  ECR reader and the legacy SF9 reader are told apart by the workbook's
  sheets;
* one workbook carries **several datasets**, so the import type decides which
  one the upload reads.

The file's own contents are asserted, not assumed: the row counts below are
what the September 2026 workbooks hold, and a school file that changes shape
should fail here rather than import half of itself.
"""

import os
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.accounts.models import StudentProfile, User
from apps.academics.models import Grade, Section
from apps.data_import import deped_forms
from apps.data_import.constants import JobStatus
from apps.data_import.models import ImportJob

REPO_ROOT = Path(__file__).resolve().parents[4]
CLIENT_WORKBOOKS = {
    7: "GRADE-7-LATEST-SEPTEMBER-4-2026.xlsx",
    8: "GRADE-8-LATEST-SEPTEMBER-4-2026.xlsx",
    9: "GRADE-9-LATEST-SEPTEMBER-4-2026.xlsx",
    10: "GRADE-10-LATEST-SEPTEMBER-4-2026.xlsx",
}

#: The workbook the school sends for each class: (section name, learners on
#: the roster, learners carrying grades, grade rows).
CLIENT_CLASSES = (
    (7, "Timothy", 30, 21, 166),
    (8, "Ephesians", 32, 17, 128),
    (9, "Daniel", 17, 5, 40),
    (10, "Daniel", 18, 10, 79),
)

#: Everything the four workbooks hold: 97 learners, 53 of them with grades,
#: 413 grade rows.
TOTAL_ROSTER = 97
TOTAL_GRADE_ROWS = 413

_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _workbook(level):
    return REPO_ROOT / CLIENT_WORKBOOKS[level]


class EcrReaderTest(SimpleTestCase):
    """The reader, against the workbooks the school actually sends."""

    def test_the_client_workbooks_are_recognised_as_ecr(self):
        for level in CLIENT_WORKBOOKS:
            workbook = self._open(level)
            self.assertEqual(
                deped_forms.detect(workbook.sheetnames),
                "ecr",
                f"GRADE-{level} is not recognised",
            )

    def test_the_legacy_sf9_template_is_still_an_sf9(self):
        """The ECR rules must not reach the QA workbooks."""
        import openpyxl

        from apps.data_import.tests_deped_forms import DATA, SF9_TEMPLATE

        workbook = openpyxl.load_workbook(
            DATA / SF9_TEMPLATE, read_only=True, data_only=True
        )
        self.assertEqual(deped_forms.detect(workbook.sheetnames), "sf9")

    def test_grade_rows_carry_the_lrn_not_the_name(self):
        for level, section, _roster, _graded, grade_rows in CLIENT_CLASSES:
            workbook = self._open(level)
            _headers, rows = deped_forms.read(workbook, "grades")
            workbook.close()

            self.assertEqual(len(rows), grade_rows, f"GRADE-{level} row count")

            for row in rows:
                self.assertTrue(
                    row["student_id"].isdigit(),
                    f"the learner key must be the LRN: {row['student_id']!r}",
                )
                self.assertEqual(row["section"], f"Grade {level} - {section}")
                self.assertEqual(row["grading_period"], "Term 1")
                self.assertRegex(row["subject_code"], r"^[A-Z]+-\d+$")

    def test_a_learner_without_an_area_has_no_row_for_it(self):
        """Galvez has no Filipino and no English; those rows simply are not there."""
        workbook = self._open(7)
        _headers, rows = deped_forms.read(workbook, "grades")
        workbook.close()

        galvez = [row for row in rows if row["student_id"] == "107718180080"]
        subjects = {row["subject_code"] for row in galvez}
        self.assertNotIn("FIL-7", subjects)
        self.assertNotIn("ENG-7", subjects)
        self.assertIn("SCI-7", subjects)

    def test_a_learner_with_no_grade_at_all_has_no_row(self):
        """Buban is on the Grade 8 roster with no mark in any area."""
        workbook = self._open(8)
        _headers, rows = deped_forms.read(workbook, "grades")
        workbook.close()

        self.assertFalse(
            [row for row in rows if row["student_id"] == "107718170032"],
            "a learner with no mark must not import a row",
        )

    def test_the_roster_carries_every_learner(self):
        for level, section, roster, _graded, _grade_rows in CLIENT_CLASSES:
            workbook = self._open(level)
            _headers, rows = deped_forms.read(workbook, "students")
            workbook.close()

            self.assertEqual(len(rows), roster, f"GRADE-{level} roster size")
            for row in rows:
                self.assertTrue(row["student_id"].isdigit())
                self.assertEqual(row["grade_level"], str(level))
                self.assertEqual(row["section"], section)
                self.assertEqual(row["academic_year"], "2026-2027")
                self.assertTrue(row["first_name"])
                self.assertTrue(row["last_name"])
                self.assertEqual(
                    row["email"], f"{row['student_id']}@students.aegis.local"
                )

    def test_a_name_without_a_comma_is_still_a_learner(self):
        """The Grade 8 roster carries 'Garate. Denisse Maxine D.'."""
        workbook = self._open(8)
        _headers, rows = deped_forms.read(workbook, "students")
        workbook.close()

        garate = [row for row in rows if row["last_name"] == "Garate"]
        self.assertEqual(len(garate), 1, "the learner is on the roster")
        self.assertEqual(garate[0]["first_name"], "Denisse Maxine D.")

    def test_a_name_with_a_stray_comma_keeps_one_name(self):
        """The Grade 8 roster carries 'Mendoza, Marcjoey C,'."""
        workbook = self._open(8)
        _headers, rows = deped_forms.read(workbook, "students")
        workbook.close()

        mendoza = [row for row in rows if row["last_name"] == "Mendoza"]
        self.assertEqual(len(mendoza), 1)
        self.assertEqual(mendoza[0]["first_name"], "Marcjoey C")

    def test_the_teachers_remarks_ride_with_the_grade(self):
        """Grade 7's COMMENT sheet reaches the grade rows of that term."""
        workbook = self._open(7)
        _headers, rows = deped_forms.read(workbook, "grades")
        workbook.close()

        remarked = [row for row in rows if row.get("remarks")]
        self.assertEqual(len(remarked), 166)
        self.assertIn("Nagpapakita", remarked[0]["remarks"])

    def test_a_workbook_with_no_marks_is_not_read_as_an_attendance_file(self):
        """The ECR carries no daily attendance marks; saying so beats 0 rows."""
        for level in CLIENT_WORKBOOKS:
            workbook = self._open(level)
            with self.assertRaises(deped_forms.DepedFormError) as caught:
                deped_forms.read(workbook, "attendance")
            workbook.close()
            self.assertIn("attendance", caught.exception.message)

    def test_a_workbook_with_no_sessions_is_not_read_as_guidance(self):
        for level in CLIENT_WORKBOOKS:
            workbook = self._open(level)
            with self.assertRaises(deped_forms.DepedFormError) as caught:
                deped_forms.read(workbook, "guidance_records")
            workbook.close()
            self.assertIn("guidance", caught.exception.message)

    # ------------------------------------------------------------------ #

    def _open(self, level):
        import openpyxl

        return openpyxl.load_workbook(_workbook(level), data_only=True)


class ClientEcrImportTest(TestCase):
    """The workbooks uploaded through the API, into a freshly seeded school."""

    @classmethod
    def setUpTestData(cls):
        with mock.patch.dict(os.environ, {"QA_SHARED_PASSWORD": "Tmp-Qa-Pass-1"}):
            call_command("provision_qa_accounts", stdout=mock.MagicMock())
            call_command("provision_client_school", stdout=mock.MagicMock())
        call_command("seed_qa_dataset", stdout=mock.MagicMock())

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.get(email="admin.qa@aegis.local")
        self.client.force_authenticate(user=self.admin)

    # ------------------------------------------------------------------ #

    def _upload(self, level, import_type):
        """Upload one client workbook and let the request finish the job."""
        from apps.data_import import views as views_module

        name = CLIENT_WORKBOOKS[level]
        upload = SimpleUploadedFile(
            name, _workbook(level).read_bytes(), content_type=_XLSX_CONTENT_TYPE
        )
        # A class's grade workbook is over the 200-row sync limit, and the
        # in-process worker deadlocks a TestCase's transaction.  The queued
        # path is covered by BackgroundImportTest in apps/data_import/tests.py.
        with mock.patch.object(views_module, "IMPORT_SYNC_ROW_LIMIT", 10_000):
            response = self.client.post(
                "/api/v1/data-import/jobs/",
                {"file": upload, "import_type": import_type},
                format="multipart",
            )
        self.assertEqual(response.status_code, 201, response.data)
        job = ImportJob.objects.get(pk=response.data["id"])
        job.refresh_from_db()
        return job

    def _upload_all(self, import_type):
        return [self._upload(level, import_type) for level in CLIENT_WORKBOOKS]

    # ------------------------------------------------------------------ #

    def test_the_roster_imports_cleanly(self):
        jobs = self._upload_all("students")

        self.assertEqual(
            [(job.processed_rows, job.error_rows) for job in jobs],
            [(30, 0), (32, 0), (17, 0), (18, 0)],
        )
        self.assertEqual(StudentProfile.objects.filter(section__name="Timothy").count(), 30)

    def test_the_grades_import_cleanly(self):
        """The roster first: a grade resolves its learner through an enrollment."""
        self._upload_all("students")
        jobs = self._upload_all("grades")

        self.assertEqual(
            [(job.processed_rows, job.error_rows) for job in jobs],
            [(166, 0), (128, 0), (40, 0), (79, 0)],
        )
        self.assertEqual(
            Grade.objects.filter(
                subject_assignment__section__name="Timothy"
            ).count(),
            166,
        )

    def test_the_remarks_reach_the_imported_grade(self):
        """The COMMENT sheet is read on the upload path, not only in the reader."""
        self._upload_all("students")
        self._upload_all("grades")

        grade = Grade.objects.get(
            student__student_id="136884180155",
            subject_assignment__subject__code="FIL-7",
        )
        self.assertIn("Nagpapakita", grade.remarks)
        self.assertEqual(grade.score, 87)

    def test_a_learner_is_keyed_by_their_lrn(self):
        self._upload_all("students")
        self._upload_all("grades")

        profile = StudentProfile.objects.get(student_id="136884180155")
        self.assertEqual(profile.user.get_full_name(), "Gabriel Andaya")
        self.assertEqual(profile.section.name, "Timothy")
        self.assertEqual(profile.grade_level.level_number, 7)

    def test_re_uploading_updates_the_record_in_place(self):
        self._upload_all("students")
        self._upload_all("grades")
        before = Grade.objects.count()

        jobs = self._upload_all("grades")

        self.assertEqual(
            [(job.processed_rows, job.error_rows) for job in jobs],
            [(166, 0), (128, 0), (40, 0), (79, 0)],
        )
        self.assertEqual(Grade.objects.count(), before)

    def test_the_client_sections_are_readable_by_the_api(self):
        self._upload_all("students")
        self._upload_all("grades")

        response = self.client.get("/api/v1/academics/sections/")
        self.assertEqual(response.status_code, 200)
        names = {row["name"] for row in response.data["results"]}
        self.assertIn("Timothy", names)
        self.assertIn("Ephesians", names)
        self.assertIn("Daniel", names)

    def test_the_adviser_sees_the_advisees_grades(self):
        """The adviser of a client section reads that section's grades."""
        self._upload_all("students")
        self._upload_all("grades")

        adviser = User.objects.get(email="gerald.gutierrez@hccsi.aegis.local")
        self.client.force_authenticate(user=adviser)

        response = self.client.get("/api/v1/academics/grades/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["results"])

    def test_the_risk_features_read_the_client_grades(self):
        """The risk engine's features are computed from the client's marks."""
        from datetime import date

        from ai_engine.feature_engine import compute_student_features

        from apps.academics.models import AcademicYear, GradingPeriod

        self._upload_all("students")
        self._upload_all("grades")

        # An imported grade is draft; finalizing is an administrator action.
        Grade.objects.filter(
            subject_assignment__section__name="Timothy"
        ).update(status="finalized")

        academic_year = AcademicYear.objects.get(name="2026-2027")
        # The engine reads the periods that have closed, as the scheduled run does.
        periods = list(
            GradingPeriod.objects.filter(
                academic_year=academic_year, end_date__lte=date.today()
            ).order_by("order")
        )
        profile = StudentProfile.objects.get(student_id="136884180155")

        features = compute_student_features(profile, periods, academic_year)

        self.assertEqual(features["computation_status"], "ready")
        self.assertEqual(float(features["current_term_grade_average"]), 87.0)
        self.assertEqual(float(features["lowest_subject_grade"]), 82.0)
        self.assertEqual(features["weak_subject_count"], 0)

    def test_the_client_grades_export_round_trip(self):
        """The re-importable export of a client class uploads back unchanged."""
        self._upload_all("students")
        self._upload_all("grades")
        section = Section.objects.get(name="Timothy", grade_level__level_number=7)

        response = self.client.get(
            "/api/v1/data-import/exports/grades/",
            {"file_format": "csv", "schema": "reimport", "section": str(section.pk)},
        )
        self.assertEqual(response.status_code, 200)

        lines = [
            line for line in response.content.decode().splitlines() if line.strip()
        ]
        self.assertEqual(len(lines) - 1, 166, "one row per grade")
        self.assertIn("student_id", lines[0])
        self.assertTrue(
            any("136884180155" in line for line in lines[1:]),
            "the learner's own grade is in the export",
        )

        upload = SimpleUploadedFile(
            "timothy-grades.csv",
            response.content,
            content_type="text/csv",
        )
        reimport = self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": upload, "import_type": "grades"},
            format="multipart",
        )
        self.assertEqual(reimport.status_code, 201, reimport.data)
        job = ImportJob.objects.get(pk=reimport.data["id"])
        self.assertEqual(job.error_rows, 0)
        self.assertEqual(job.processed_rows, 166)
        self.assertEqual(
            Grade.objects.filter(
                subject_assignment__section__name="Timothy"
            ).count(),
            166,
            "the round trip updates the same records",
        )

    def test_an_attendance_upload_of_the_workbook_is_refused(self):
        """The workbook carries no attendance; the job says so."""
        response = self.client.post(
            "/api/v1/data-import/jobs/",
            {
                "file": SimpleUploadedFile(
                    CLIENT_WORKBOOKS[7],
                    _workbook(7).read_bytes(),
                    content_type=_XLSX_CONTENT_TYPE,
                ),
                "import_type": "attendance",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        job = ImportJob.objects.get(pk=response.data["id"])
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertIn("attendance", job.error_log[0]["message"])
