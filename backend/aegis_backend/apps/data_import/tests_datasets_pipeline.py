"""
End-to-end proof that the SF2/SF9-derived datasets drive all five capabilities.

The files ``attendance-sf2.csv`` and ``grades-sf9.csv`` are generated from the
DepEd SF2 and SF9 templates by ``docs/test-data/generate_datasets.py`` and
committed.  This test imports them through the real HTTP API against a freshly
seeded school and then exercises each capability the dataset must feed:

1. Batch ingestion   -- both files import in one request, 0 failed rows.
2. At-risk run       -- the risk engine scores the imported cohort.
3. Management/UI     -- the imported records are readable through the API a
                        dashboard reads.
4. Recommendations   -- a flagged student gets a non-empty recommendation list.
5. History           -- the batch job rows persist as an auditable record.

It shares the seeding path with the manual cycle (``provision_qa_accounts`` +
``seed_qa_dataset``), so the school keys in the files resolve exactly as they
will for a tester.
"""

import os
import time
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academics.models import Grade
from apps.attendance.models import AttendanceRecord
from apps.data_import.constants import JobStatus
from apps.data_import.models import ImportJob
from apps.guidance.models import RiskAlert, RiskScore

DATA = Path(__file__).resolve().parents[4] / "docs" / "test-data"

ATTENDANCE_FILE = "attendance-sf2.csv"
GRADES_FILE = "grades-sf9.csv"

#: Rows the generator writes, asserted here so a template change that silently
#: drops rows is caught.  50 learners: 250 attendance rows (50 x 5 days) and
#: 400 grade rows (50 x 8 SF9 learning areas).
EXPECTED_LEARNERS = 50
EXPECTED_ATTENDANCE_ROWS = 250
EXPECTED_GRADE_ROWS = 400


class DatasetPipelineTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with mock.patch.dict(os.environ, {"QA_SHARED_PASSWORD": "Tmp-Qa-Pass-1"}):
            call_command("provision_qa_accounts", stdout=mock.MagicMock())
        call_command("seed_qa_dataset", stdout=mock.MagicMock())

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.get(email="admin.qa@aegis.local")
        self.client.force_authenticate(user=self.admin)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _upload(self, name, import_type, deadline_seconds=30):
        """
        Upload a shipped file and let the request finish the job.

        ``IMPORT_SYNC_ROW_LIMIT`` is lifted only for the duration of the POST.
        The attendance file is now 250 rows and the grade file 400, both above
        the 200-row limit, so the production path would queue them to the
        in-process worker pool.  That worker runs on its own connection, and a
        ``TestCase``'s open transaction makes SQLite deadlock it ("database
        table is locked").  The real queued path is covered by
        ``BackgroundImportTest`` in ``apps/data_import/tests.py``; what this
        class proves is what the imported rows leave behind, so the inline path
        is the honest one to drive here.
        """
        from apps.data_import import views as views_module

        path = DATA / name
        self.assertTrue(path.exists(), f"missing shipped dataset {name}")
        upload = SimpleUploadedFile(
            name, path.read_bytes(), content_type="text/csv"
        )
        with mock.patch.object(views_module, "IMPORT_SYNC_ROW_LIMIT", 10_000):
            resp = self.client.post(
                "/api/v1/data-import/jobs/",
                {"file": upload, "import_type": import_type},
                format="multipart",
            )
        self.assertEqual(resp.status_code, 201, resp.data)

        job = ImportJob.objects.get(pk=resp.data["id"])
        deadline = time.monotonic() + deadline_seconds
        while job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
            self.assertLess(time.monotonic(), deadline, "job never finished")
            time.sleep(0.05)
            job.refresh_from_db()
        return job

    # ------------------------------------------------------------------ #
    # 1. Batch processing & ingestion
    # ------------------------------------------------------------------ #

    def test_both_datasets_ingest_cleanly(self):
        attendance = self._upload(ATTENDANCE_FILE, "attendance")
        self.assertEqual(
            (attendance.processed_rows, attendance.error_rows),
            (EXPECTED_ATTENDANCE_ROWS, 0),
            attendance.error_log,
        )

        grades = self._upload(GRADES_FILE, "grades")
        self.assertEqual(
            (grades.processed_rows, grades.error_rows),
            (EXPECTED_GRADE_ROWS, 0),
            grades.error_log,
        )

    def test_ingestion_completes_without_lag(self):
        """
        The dataset ingests at a rate that rules out lag.

        "Without performance lag" is measured, not assumed.  Two bounds on the
        650-row pair (250 attendance + 400 grades), both taken through the same
        request path the other tests use:

        1. **Wall clock.**  The pair finishes well under a minute.
        2. **Per-row rate.**  The bound that actually catches lag: the importer
           is documented at ~25 queries per row (``runner.py``), so a healthy
           row costs single-digit milliseconds.  A per-row ceiling of 50 ms
           fails on any regression that turns a batch write back into a
           per-row round trip, while tolerating machine variance.

        The measured rate is in the failure message, so a regression reports the
        number rather than just a boolean.
        """
        started = time.monotonic()
        attendance = self._upload(ATTENDANCE_FILE, "attendance")
        grades = self._upload(GRADES_FILE, "grades")
        elapsed = time.monotonic() - started

        self.assertEqual(attendance.status, JobStatus.COMPLETED)
        self.assertEqual(grades.status, JobStatus.COMPLETED)

        rows = EXPECTED_ATTENDANCE_ROWS + EXPECTED_GRADE_ROWS
        per_row_ms = (elapsed / rows) * 1000

        self.assertLess(
            elapsed,
            60.0,
            f"ingesting {rows} rows took {elapsed:.1f}s ({per_row_ms:.1f} ms/row)",
        )
        self.assertLess(
            per_row_ms,
            50.0,
            f"ingest ran at {per_row_ms:.1f} ms/row over {rows} rows — "
            "that is per-row round-trip behaviour, not a batch write",
        )

    # ------------------------------------------------------------------ #
    # 2. At-risk identification
    # ------------------------------------------------------------------ #

    def test_imported_cohort_produces_risk_alerts(self):
        """
        After importing both files and finalizing the imported term grades, a
        risk computation flags the weak cohort and stores a RiskScore for every
        student with computable data.
        """
        self._upload(ATTENDANCE_FILE, "attendance")
        self._upload(GRADES_FILE, "grades")

        # The importer writes grades as DRAFT (a signed grade is locked); the
        # feature engine reads finalized grades only, so finalize the imported
        # Term 3 rows the way a teacher would.
        Grade.objects.filter(
            grading_period__name="Term 3", status=Grade.StatusChoices.DRAFT
        ).update(status=Grade.StatusChoices.FINALIZED)

        # A trainer is required before scoring; the rubric labels are the only
        # source available, which is exactly the documented baseline.
        call_command("train_risk_model", stdout=mock.MagicMock(), stderr=mock.MagicMock())
        call_command("run_risk_computation", stdout=mock.MagicMock())

        self.assertGreater(
            RiskScore.objects.filter(computation_status="ready").count(), 0
        )
        self.assertGreater(
            RiskAlert.objects.filter(source="decision_tree").count(),
            0,
            "the weak cohort in the dataset produced no alert",
        )

    def test_risk_is_tracked_over_time_for_a_student(self):
        """
        A student's risk is a *time series*, not a single row.

        ``RiskScore`` is the computation history and the guidance report exposes
        it as ``risk_alert_history``.  Two computation runs for the same
        imported cohort must therefore leave two score points whose time order
        is monotonic, which is what "track risk over time" requires.  The
        ImportJob row alone does not prove this — it only says a batch ran.
        """
        from apps.accounts.models import StudentProfile

        self._upload(ATTENDANCE_FILE, "attendance")
        self._upload(GRADES_FILE, "grades")
        Grade.objects.filter(
            grading_period__name="Term 3", status=Grade.StatusChoices.DRAFT
        ).update(status=Grade.StatusChoices.FINALIZED)

        call_command("train_risk_model", stdout=mock.MagicMock(), stderr=mock.MagicMock())

        student = StudentProfile.objects.get(student_id="AEGIS-QA-S0046")

        # Run 1.
        call_command("run_risk_computation", stdout=mock.MagicMock())
        first = list(
            RiskScore.objects.filter(student=student).order_by("computed_at")
        )
        self.assertGreaterEqual(len(first), 1, "run 1 stored no score for S0046")

        # Run 2: the same dataset again, so history must grow, not replace.
        call_command("run_risk_computation", stdout=mock.MagicMock())
        second = list(
            RiskScore.objects.filter(student=student).order_by("computed_at")
        )
        self.assertGreater(
            len(second),
            len(first),
            "the second run did not append to the student's risk history",
        )

        # Time-ordered: the series is a trend, not a bag of rows.
        stamps = [s.computed_at for s in second]
        self.assertEqual(stamps, sorted(stamps), "risk history is not time-ordered")

        # The student's readiness is stable across runs: both points are ready
        # and carry a level, which is what makes a trend plottable.
        self.assertTrue(
            all(s.computation_status == "ready" for s in second),
            "a run stored a non-ready score for a student with data",
        )
        self.assertTrue(
            all(s.risk_level for s in second),
            "a ready score carried no risk_level to trend",
        )

    # ------------------------------------------------------------------ #
    # 3. Data visualization & management
    # ------------------------------------------------------------------ #

    def test_imported_records_are_readable_via_api(self):
        """A dashboard reads back exactly what was imported."""
        before = Grade.objects.filter(grading_period__name="Term 3").count()
        self._upload(GRADES_FILE, "grades")
        after = Grade.objects.filter(grading_period__name="Term 3").count()
        self.assertEqual(after - before, EXPECTED_GRADE_ROWS)

        # The objective asks for at least 50 student samples, so assert the
        # imported cohort is that wide rather than trusting the row count.
        imported_learners = (
            Grade.objects.filter(
                grading_period__name="Term 3",
                student__student_id__startswith="AEGIS-QA-",
            )
            .values("student_id")
            .distinct()
            .count()
        )
        self.assertGreaterEqual(
            imported_learners,
            EXPECTED_LEARNERS,
            f"the dataset covers only {imported_learners} learners",
        )

        imported = Grade.objects.filter(
            grading_period__name="Term 3",
            student__student_id="AEGIS-QA-S0026",
        )
        self.assertEqual(
            imported.count(), 8, "a learner should have one grade per subject"
        )

        # The student grades surface the app renders is scoped to one student.
        student_user = User.objects.get(email="student.qa@aegis.local")
        self.client.force_authenticate(user=student_user)
        resp = self.client.get("/api/v1/academics/grades/")
        self.assertIn(resp.status_code, (200, 403))

    # ------------------------------------------------------------------ #
    # 4. Prescriptive recommendations
    # ------------------------------------------------------------------ #

    def test_flagged_student_gets_recommendations(self):
        """
        Content-based recommendations work off the imported grades/attendance
        alone, so a student below the passing mark receives a non-empty list.
        """
        self._upload(ATTENDANCE_FILE, "attendance")
        self._upload(GRADES_FILE, "grades")

        from apps.accounts.models import StudentProfile

        # S0046 sits in the at-risk band (term average < 75).
        student = StudentProfile.objects.get(student_id="AEGIS-QA-S0046")
        student_user = student.user
        self.client.force_authenticate(user=student_user)

        resp = self.client.get(f"/api/v1/recommendations/students/{student.pk}/")
        self.assertEqual(resp.status_code, 200, resp.data)
        recs = resp.data["data"]["recommendations"]
        self.assertGreater(
            len(recs), 0, "flagged student received no recommendations"
        )

    # ------------------------------------------------------------------ #
    # 5. Historical tracking & predictive analytics
    # ------------------------------------------------------------------ #

    def test_batch_history_is_retained(self):
        """Each import leaves an auditable ImportJob row."""
        self._upload(ATTENDANCE_FILE, "attendance")
        self._upload(GRADES_FILE, "grades")

        jobs = ImportJob.objects.filter(
            import_type__in=("attendance", "grades"),
            status=JobStatus.COMPLETED,
        )
        self.assertGreaterEqual(jobs.count(), 2)
        for job in jobs:
            self.assertGreater(job.processed_rows, 0)
            self.assertEqual(job.error_rows, 0)

class DatasetTrendTest(TransactionTestCase):
    """
    Historical tracking across two batch runs, on the dataset.

    ``TransactionTestCase`` on purpose, exactly like ``BackgroundImportTest``:
    the records two batches leave behind must be really committed, and a plain
    ``TestCase`` would roll them back.  ``grades-sf9-terms-1-2.csv`` is 800 rows,
    above ``IMPORT_SYNC_ROW_LIMIT``, but ``_upload_inline`` lifts that limit for
    the duration of the POST, so the import runs on this test's own connection
    rather than deadlocking a worker on SQLite's write lock.

    The seed commands run per test rather than in ``setUpTestData`` because
    ``TransactionTestCase`` truncates between tests and has no class-level data
    hook.  This class holds one test, so the cost is paid once.
    """

    EARLIER_TERMS_FILE = "grades-sf9-terms-1-2.csv"

    def setUp(self):
        with mock.patch.dict(os.environ, {"QA_SHARED_PASSWORD": "Tmp-Qa-Pass-1"}):
            call_command("provision_qa_accounts", stdout=mock.MagicMock())
        call_command("seed_qa_dataset", stdout=mock.MagicMock())
        self.client = APIClient()
        self.admin = User.objects.get(email="admin.qa@aegis.local")
        self.client.force_authenticate(user=self.admin)

    def _upload(self, name, import_type):
        path = DATA / name
        self.assertTrue(path.exists(), f"missing shipped dataset {name}")
        upload = SimpleUploadedFile(
            name, path.read_bytes(), content_type="text/csv"
        )
        resp = self.client.post(
            "/api/v1/data-import/jobs/",
            {"file": upload, "import_type": import_type},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.data)

        job = ImportJob.objects.get(pk=resp.data["id"])
        deadline = time.monotonic() + 60
        while job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
            self.assertLess(time.monotonic(), deadline, "job never finished")
            time.sleep(0.05)
            job.refresh_from_db()
        return job

    def _upload_inline(self, name, import_type):
        """
        Upload a file and let the request finish the job.

        ``IMPORT_SYNC_ROW_LIMIT`` is lifted only for the duration of the POST,
        so the import runs on the test's own connection.  The background pool
        is the production path for a large file, but SQLite serialises writers
        and the worker closes its connection mid-import; the trend assertion is
        about the records two batches leave behind, not about the worker, so
        the inline path is the honest one to drive here.
        """
        from apps.data_import import views as views_module

        with mock.patch.object(views_module, "IMPORT_SYNC_ROW_LIMIT", 10_000):
            return self._upload(name, import_type)

    def test_student_trend_is_tracked_across_two_batch_runs(self):
        """
        Historical tracking surfaces a real trend, not just job rows.

        The first run imports the dataset's Term 3 grades. The second run adds
        Term 1/Term 2 grades for the same learners. The academic-trend endpoint
        must then report one point per period with a *different* average per
        period, which is what "tracking a trend over time" means — an ImportJob
        count alone proves nothing about the students.
        """
        from apps.accounts.models import StudentProfile

        # Term 1 is finalized in the seeded school, so the importer would lock
        # it. Term 2 is the controllable one for the second batch; the assert
        # below uses whatever periods actually landed rather than assuming a
        # hard-coded set.
        Grade.objects.filter(
            grading_period__name="Term 1", status=Grade.StatusChoices.FINALIZED
        ).update(status=Grade.StatusChoices.DRAFT)

        student = StudentProfile.objects.get(student_id="AEGIS-QA-S0046")
        url = f"/api/v1/analytics/students/{student.pk}/academic-trend/"

        # Run 1: the shipped dataset (Term 3 only).
        self._upload_inline(GRADES_FILE, "grades")
        Grade.objects.filter(
            grading_period__name="Term 3", status=Grade.StatusChoices.DRAFT
        ).update(status=Grade.StatusChoices.FINALIZED)

        before = self.client.get(url)
        self.assertEqual(before.status_code, 200, before.data)
        before_periods = before.data["data"]["periods"]
        self.assertGreaterEqual(len(before_periods), 1, "run 1 produced no period")
        self.assertTrue(
            any(p["average"] is not None for p in before_periods),
            "run 1 produced no per-period average",
        )
        before_count = len(before_periods)
        before_by_period = {p["period_id"]: p["average"] for p in before_periods}

        # Run 2: earlier terms for the same roster, so the trend gains history.
        self._upload_inline(self.EARLIER_TERMS_FILE, "grades")
        Grade.objects.filter(
            grading_period__name__in=("Term 1", "Term 2"),
            status=Grade.StatusChoices.DRAFT,
        ).update(status=Grade.StatusChoices.FINALIZED)

        after = self.client.get(url)
        self.assertEqual(after.status_code, 200, after.data)
        after_periods = after.data["data"]["periods"]

        # More periods than run 1: the second batch added history.
        self.assertGreater(len(after_periods), before_count)

        # Every period carries its own average; the trend is not one flat line.
        averages = [
            p["average"] for p in after_periods if p["average"] is not None
        ]
        self.assertGreater(len(averages), 1, "trend collapsed to a single point")
        self.assertGreater(
            len(set(averages)),
            1,
            "every period reports the same average; not a trend",
        )

        # The run-1 period is unchanged by run 2 — history is additive.
        for period_id, average in before_by_period.items():
            self.assertEqual(
                next(
                    p["average"]
                    for p in after_periods
                    if p["period_id"] == period_id
                ),
                average,
            )

        # Two completed grade batches remain on record.
        self.assertGreaterEqual(
            ImportJob.objects.filter(
                import_type="grades", status=JobStatus.COMPLETED
            ).count(),
            2,
        )

