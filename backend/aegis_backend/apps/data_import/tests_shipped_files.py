"""
The shipped ``docs/test-data`` files import cleanly (manual-QA guard).

The import files handed to a manual tester are part of the deliverable: they
carry the school-key forms a real upload uses ("Grade 8 - Bonifacio", "ENG-8",
"Term 3") and the re-upload cases.  Importing them here against a freshly
seeded QA dataset means a change to the importers cannot quietly invalidate the
files the tester is about to run, and it exercises the same path the manual
steps do — through the HTTP API, not the importer classes directly.

The seeding is what the manual cycle uses, so the names in the files resolve
exactly as they will for the tester.
"""

import os
import time
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academics.models import Grade
from apps.attendance.models import AttendanceRecord
from apps.guidance.models import ConsultationRecord
from apps.data_import.constants import JobStatus
from apps.data_import.models import ImportJob

DATA = Path(__file__).resolve().parents[4] / "docs" / "test-data"


def _file(name):
    path = DATA / name
    return SimpleUploadedFile(
        name, path.read_bytes(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if name.endswith(".xlsx")
        else "text/csv",
    )


class ShippedImportFilesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with mock.patch.dict(os.environ, {"QA_SHARED_PASSWORD": "Tmp-Qa-Pass-1"}):
            call_command("provision_qa_accounts", stdout=mock.MagicMock())
        call_command("seed_qa_dataset", stdout=mock.MagicMock())

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=User.objects.get(email="admin.qa@aegis.local"))

    def _upload(self, name, import_type, sheet=None):
        payload = {"file": _file(name), "import_type": import_type}
        if sheet is not None:
            payload["sheet"] = sheet
        resp = self.client.post("/api/v1/data-import/jobs/", payload, format="multipart")
        self.assertEqual(resp.status_code, 201, resp.data)

        # Small files finish in the request; a larger one would come back
        # pending, so poll the way the page does rather than assume.
        job = ImportJob.objects.get(pk=resp.data["id"])
        deadline = time.monotonic() + 30
        while job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
            self.assertLess(time.monotonic(), deadline, "job never finished")
            time.sleep(0.05)
            job.refresh_from_db()
        return job

    def test_attendance_workbook(self):
        before = AttendanceRecord.objects.count()
        job = self._upload("attendance-import.xlsx", "attendance", "Valid Attendance")
        self.assertEqual((job.processed_rows, job.error_rows), (5, 0), job.error_log)
        self.assertEqual(AttendanceRecord.objects.count(), before + 5)

        # No sheet named -> the rejection lists the sheets it found.
        job = self._upload("attendance-import.xlsx", "attendance")
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_log[0]["code"], "MULTIPLE_WORKSHEETS")

        # Malformed sheet -> every row has its own reason.
        job = self._upload("attendance-import.xlsx", "attendance", "Malformed Attendance")
        self.assertEqual((job.processed_rows, job.error_rows), (0, 5), job.error_log)
        for rec in job.records.all():
            self.assertTrue(rec.error_message, rec.row_number)

        # Re-upload -> updates in place, no duplicates.
        job = self._upload("attendance-import.xlsx", "attendance", "Valid Attendance")
        self.assertEqual((job.processed_rows, job.error_rows), (5, 0), job.error_log)
        self.assertEqual(AttendanceRecord.objects.count(), before + 5)

    def test_attendance_csvs(self):
        before = AttendanceRecord.objects.count()
        job = self._upload("attendance-valid.csv", "attendance")
        self.assertEqual((job.processed_rows, job.error_rows), (5, 0), job.error_log)
        self.assertEqual(AttendanceRecord.objects.count(), before + 5)
        job = self._upload("attendance-malformed.csv", "attendance")
        self.assertEqual((job.processed_rows, job.error_rows), (0, 5), job.error_log)

    def test_grades_workbook_uses_school_keys(self):
        before = Grade.objects.count()
        job = self._upload("grades-import.xlsx", "grades")
        self.assertEqual((job.processed_rows, job.error_rows), (2, 0), job.error_log)
        self.assertEqual(Grade.objects.count(), before + 2)
        new_grades = Grade.objects.filter(grading_period__name="Term 3")
        codes = {g.subject_assignment.subject.code for g in new_grades}
        self.assertEqual(codes, {"ENG-8"}, codes)
        periods = {g.grading_period.name for g in new_grades}
        self.assertEqual(periods, {"Term 3"}, periods)

        # Second run updates the same two grades.
        job = self._upload("grades-import.xlsx", "grades")
        self.assertEqual((job.processed_rows, job.error_rows), (2, 0), job.error_log)
        self.assertEqual(Grade.objects.count(), before + 2)

    def test_guidance_workbook(self):
        before = ConsultationRecord.objects.count()
        job = self._upload("guidance-import.xlsx", "guidance_records")
        self.assertEqual((job.processed_rows, job.error_rows), (3, 0), job.error_log)
        self.assertEqual(ConsultationRecord.objects.count(), before + 3)
        job = self._upload("guidance-import.xlsx", "guidance_records")
        self.assertEqual((job.processed_rows, job.error_rows), (3, 0), job.error_log)
        self.assertEqual(ConsultationRecord.objects.count(), before + 3)
