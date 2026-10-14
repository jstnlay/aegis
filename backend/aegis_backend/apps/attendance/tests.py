"""
Phase 3 test suite for AEGIS Attendance.

Covers: model validation, API endpoints, scoped querysets,
role-based permissions, filtering, summary, and batch import placeholder.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    FacultyProfile,
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
)
from apps.academics.models import (
    AcademicYear,
    Enrollment,
    GradeLevel,
    Section,
    Subject,
    SubjectAssignment,
)
from apps.attendance.models import AttendanceRecord

User = get_user_model()


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class AttendanceTestBase(TestCase):
    """Shared setUp for attendance tests."""

    def setUp(self):
        # --- Users ---
        self.admin_user = User.objects.create_user(
            email="admin_att@test.com", password="pass12345",
            first_name="Admin", last_name="User", role="admin",
        )
        self.faculty_user = User.objects.create_user(
            email="faculty_att@test.com", password="pass12345",
            first_name="Fac", last_name="ulty", role="faculty",
        )
        self.faculty2_user = User.objects.create_user(
            email="faculty2_att@test.com", password="pass12345",
            first_name="Fac2", last_name="ulty2", role="faculty",
        )
        self.student_user = User.objects.create_user(
            email="student_att@test.com", password="pass12345",
            first_name="Stu", last_name="dent", role="student",
        )
        self.student2_user = User.objects.create_user(
            email="student2_att@test.com", password="pass12345",
            first_name="Stu2", last_name="dent2", role="student",
        )
        self.parent_user = User.objects.create_user(
            email="parent_att@test.com", password="pass12345",
            first_name="Par", last_name="ent", role="parent",
        )
        self.guidance_user = User.objects.create_user(
            email="guidance_att@test.com", password="pass12345",
            first_name="Guid", last_name="ance", role="guidance",
        )

        # --- Profiles ---
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="EMP-ATT-001", department="Math",
        )
        self.faculty2_profile = FacultyProfile.objects.create(
            user=self.faculty2_user, employee_id="EMP-ATT-002", department="Science",
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user, student_id="STU-ATT-001", enrollment_date="2025-06-01",
        )
        self.student2_profile = StudentProfile.objects.create(
            user=self.student2_user, student_id="STU-ATT-002", enrollment_date="2025-06-01",
        )
        self.parent_profile = ParentProfile.objects.create(
            user=self.parent_user, relationship_to_student="mother",
        )
        ParentStudentLink.objects.create(
            parent=self.parent_profile, student=self.student_profile, is_primary=True,
        )

        # --- Academic structure ---
        self.ay = AcademicYear.objects.create(
            name="2025-2026", start_date="2025-06-01",
            end_date="2026-03-31", is_current=True,
        )
        self.g7 = GradeLevel.objects.create(name="Grade 7", level_number=7)

        self.section_a = Section.objects.create(
            name="Einstein", grade_level=self.g7, academic_year=self.ay,
            adviser=self.faculty_profile,
        )
        self.section_b = Section.objects.create(
            name="Newton", grade_level=self.g7, academic_year=self.ay,
        )

        self.math = Subject.objects.create(name="Mathematics", code="MATH-ATT-7", grade_level=self.g7)

        self.sa_math = SubjectAssignment.objects.create(
            subject=self.math, faculty=self.faculty_profile,
            section=self.section_a, academic_year=self.ay,
        )

        self.enrollment1 = Enrollment.objects.create(
            student=self.student_profile, section=self.section_a,
            academic_year=self.ay, date_enrolled="2025-06-01",
        )
        self.enrollment2 = Enrollment.objects.create(
            student=self.student2_profile, section=self.section_b,
            academic_year=self.ay, date_enrolled="2025-06-01",
        )

        # Update student profiles to reflect section assignment
        self.student_profile.section = self.section_a
        self.student_profile.grade_level = self.g7
        self.student_profile.save()
        self.student2_profile.section = self.section_b
        self.student2_profile.grade_level = self.g7
        self.student2_profile.save()

        # --- Dates ---
        self.today = timezone.localdate()
        self.yesterday = self.today - timedelta(days=1)
        self.two_days_ago = self.today - timedelta(days=2)

        # --- Attendance records ---
        self.record1 = AttendanceRecord.objects.create(
            student=self.student_profile, section=self.section_a,
            date=self.yesterday, status=AttendanceRecord.Status.PRESENT,
            recorded_by=self.faculty_profile,
        )
        self.record2 = AttendanceRecord.objects.create(
            student=self.student_profile, section=self.section_a,
            date=self.two_days_ago, status=AttendanceRecord.Status.ABSENT,
            recorded_by=self.faculty_profile,
        )
        self.record3 = AttendanceRecord.objects.create(
            student=self.student2_profile, section=self.section_b,
            date=self.yesterday, status=AttendanceRecord.Status.LATE,
            recorded_by=self.faculty2_profile,
        )
        # Record in section_a created by faculty2 — visible to faculty_user
        # but they did NOT create it, so update/delete should be 403.
        self.record4 = AttendanceRecord.objects.create(
            student=self.student_profile, section=self.section_a,
            date=self.today - timedelta(days=3), status=AttendanceRecord.Status.LATE,
            recorded_by=self.faculty2_profile,
        )

        self.client = APIClient()

    @staticmethod
    def _get_token(user):
        from rest_framework_simplejwt.tokens import RefreshToken

        return str(RefreshToken.for_user(user).access_token)


# ===========================================================================
# Model tests
# ===========================================================================


class AttendanceRecordModelTest(AttendanceTestBase):
    def test_str(self):
        s = str(self.record1)
        self.assertIn("dent", s)
        self.assertIn("Present", s)

    def test_str_absent(self):
        s = str(self.record2)
        self.assertIn("Absent", s)

    def test_unique_together_student_date(self):
        with self.assertRaises(ValidationError):
            AttendanceRecord.objects.create(
                student=self.student_profile, section=self.section_a,
                date=self.yesterday, status=AttendanceRecord.Status.LATE,
                recorded_by=self.faculty_profile,
            )

    def test_status_choices(self):
        expected = {"present", "late", "absent"}
        actual = {choice[0] for choice in AttendanceRecord.Status.choices}
        self.assertEqual(actual, expected)

    def test_future_date_rejected(self):
        record = AttendanceRecord(
            student=self.student_profile, section=self.section_a,
            date=self.today + timedelta(days=1),
            status=AttendanceRecord.Status.PRESENT,
            recorded_by=self.faculty_profile,
        )
        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_today_date_allowed(self):
        record = AttendanceRecord(
            student=self.student_profile, section=self.section_a,
            date=self.today,
            status=AttendanceRecord.Status.PRESENT,
            recorded_by=self.faculty_profile,
        )
        record.full_clean()

    def test_historical_date_allowed(self):
        record = AttendanceRecord(
            student=self.student_profile, section=self.section_a,
            date=date(2025, 6, 15),
            status=AttendanceRecord.Status.PRESENT,
            recorded_by=self.faculty_profile,
        )
        record.full_clean()


# ===========================================================================
# API tests — Authentication required
# ===========================================================================


class AttendanceUnauthenticatedTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_list_records_unauthenticated(self):
        response = self.client.get("/api/v1/attendance/records/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_summary_unauthenticated(self):
        response = self.client.get("/api/v1/attendance/summary/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ===========================================================================
# API tests — Admin read-only on attendance records
# ===========================================================================


class AdminReadOnlyTest(AttendanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.admin_user)}"
        )

    def test_admin_list_all_records(self):
        response = self.client.get("/api/v1/attendance/records/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 4)

    def test_admin_retrieve_record(self):
        response = self.client.get(f"/api/v1/attendance/records/{self.record1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_cannot_create_record(self):
        response = self.client.post(
            "/api/v1/attendance/records/",
            {
                "student": str(self.student_profile.id),
                "section": str(self.section_a.id),
                "date": str(self.two_days_ago),
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_update_record(self):
        response = self.client.patch(
            f"/api/v1/attendance/records/{self.record1.id}/",
            {"status": "absent"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_delete_record(self):
        response = self.client.delete(f"/api/v1/attendance/records/{self.record1.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ===========================================================================
# API tests — Faculty CRUD within scoped sections
# ===========================================================================


class FacultyRecordTest(AttendanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )

    def test_faculty_create_record_success(self):
        response = self.client.post(
            "/api/v1/attendance/records/",
            {
                "student": str(self.student_profile.id),
                "section": str(self.section_a.id),
                "date": str(self.today),
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(AttendanceRecord.objects.count(), 5)

    def test_faculty_create_record_sets_recorded_by(self):
        response = self.client.post(
            "/api/v1/attendance/records/",
            {
                "student": str(self.student_profile.id),
                "section": str(self.section_a.id),
                "date": str(self.today),
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        rec = AttendanceRecord.objects.get(id=response.data["id"])
        self.assertEqual(rec.recorded_by, self.faculty_profile)

    def test_faculty_create_duplicate_returns_409(self):
        response = self.client.post(
            "/api/v1/attendance/records/",
            {
                "student": str(self.student_profile.id),
                "section": str(self.section_a.id),
                "date": str(self.yesterday),
                "status": "absent",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_faculty_create_future_date_returns_400(self):
        response = self.client.post(
            "/api/v1/attendance/records/",
            {
                "student": str(self.student_profile.id),
                "section": str(self.section_a.id),
                "date": str(self.today + timedelta(days=5)),
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_faculty_create_student_not_enrolled_returns_400(self):
        response = self.client.post(
            "/api/v1/attendance/records/",
            {
                "student": str(self.student_profile.id),
                "section": str(self.section_b.id),
                "date": str(self.two_days_ago),
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_faculty_update_own_record(self):
        response = self.client.patch(
            f"/api/v1/attendance/records/{self.record1.id}/",
            {"status": "absent"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record1.refresh_from_db()
        self.assertEqual(self.record1.status, AttendanceRecord.Status.ABSENT)

    def test_faculty_cannot_update_other_record(self):
        response = self.client.patch(
            f"/api/v1/attendance/records/{self.record4.id}/",
            {"status": "absent"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_faculty_delete_own_record(self):
        response = self.client.delete(f"/api/v1/attendance/records/{self.record1.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_faculty_cannot_delete_other_record(self):
        response = self.client.delete(f"/api/v1/attendance/records/{self.record4.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_faculty_list_own_section_records(self):
        response = self.client.get("/api/v1/attendance/records/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in response.data["results"]]
        self.assertIn(str(self.record1.id), ids)
        self.assertIn(str(self.record2.id), ids)
        self.assertIn(str(self.record4.id), ids)
        self.assertNotIn(str(self.record3.id), ids)


# ===========================================================================
# API tests — Student scoped read
# ===========================================================================


class StudentScopedReadTest(AttendanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.student_user)}"
        )

    def test_student_sees_own_records(self):
        response = self.client.get("/api/v1/attendance/records/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)

    def test_student_cannot_create(self):
        response = self.client.post(
            "/api/v1/attendance/records/",
            {
                "student": str(self.student_profile.id),
                "section": str(self.section_a.id),
                "date": str(self.two_days_ago),
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_retrieve_own_record(self):
        response = self.client.get(f"/api/v1/attendance/records/{self.record1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_student_cannot_see_other_record(self):
        response = self.client.get(f"/api/v1/attendance/records/{self.record3.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ===========================================================================
# API tests — Parent scoped read
# ===========================================================================


class ParentScopedReadTest(AttendanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.parent_user)}"
        )

    def test_parent_sees_linked_child_records(self):
        response = self.client.get("/api/v1/attendance/records/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)

    def test_parent_cannot_create(self):
        response = self.client.post(
            "/api/v1/attendance/records/",
            {
                "student": str(self.student_profile.id),
                "section": str(self.section_a.id),
                "date": str(self.two_days_ago),
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_parent_does_not_see_unlinked_student(self):
        response = self.client.get("/api/v1/attendance/records/")
        ids = [r["id"] for r in response.data["results"]]
        self.assertNotIn(str(self.record3.id), ids)


# ===========================================================================
# API tests — Guidance read-only
# ===========================================================================


class GuidanceReadOnlyTest(AttendanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.guidance_user)}"
        )

    def test_guidance_sees_all_records(self):
        response = self.client.get("/api/v1/attendance/records/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 4)

    def test_guidance_cannot_create(self):
        response = self.client.post(
            "/api/v1/attendance/records/",
            {
                "student": str(self.student_profile.id),
                "section": str(self.section_a.id),
                "date": str(self.two_days_ago),
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_guidance_retrieve_record(self):
        response = self.client.get(f"/api/v1/attendance/records/{self.record1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ===========================================================================
# API tests — Query parameter filtering
# ===========================================================================


class AttendanceFilteringTest(AttendanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.admin_user)}"
        )

    def test_filter_by_student(self):
        response = self.client.get(
            f"/api/v1/attendance/records/?student={self.student_profile.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)

    def test_filter_by_section(self):
        response = self.client.get(
            f"/api/v1/attendance/records/?section={self.section_a.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)

    def test_filter_by_status(self):
        response = self.client.get("/api/v1/attendance/records/?status=present")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_filter_by_date_range(self):
        response = self.client.get(
            f"/api/v1/attendance/records/?date_from={self.two_days_ago}&date_to={self.yesterday}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)


# ===========================================================================
# API tests — Attendance summary
# ===========================================================================


class AttendanceSummaryTest(AttendanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.admin_user)}"
        )

    def test_summary_returns_all_students(self):
        response = self.client.get("/api/v1/attendance/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_summary_student_present_count(self):
        response = self.client.get(
            f"/api/v1/attendance/summary/?student={self.student_profile.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = next(e for e in response.data if str(e["student"]) == str(self.student_profile.id))
        self.assertEqual(entry["present_count"], 1)

    def test_summary_student_absent_count(self):
        response = self.client.get(
            f"/api/v1/attendance/summary/?student={self.student_profile.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = next(e for e in response.data if str(e["student"]) == str(self.student_profile.id))
        self.assertEqual(entry["absent_count"], 1)

    def test_summary_student2_late_count(self):
        response = self.client.get(
            f"/api/v1/attendance/summary/?student={self.student2_profile.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = next(e for e in response.data if str(e["student"]) == str(self.student2_profile.id))
        self.assertEqual(entry["late_count"], 1)

    def test_summary_filter_by_section(self):
        response = self.client.get(
            f"/api/v1/attendance/summary/?section={self.section_a.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_summary_filter_by_student(self):
        response = self.client.get(
            f"/api/v1/attendance/summary/?student={self.student_profile.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


# ===========================================================================
# API tests — Batch import placeholder
# ===========================================================================


class AttendanceBatchImportTest(AttendanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )

    def test_batch_import_delegates_to_data_import(self):
        """
        The attendance batch-import route now delegates to the data_import app
        pinned to import_type="attendance". It used to return 501.

        This asserts the delegation contract only; the attendance parsing and
        row-scoring pipeline is covered by apps/data_import/tests.py.
        """
        response = self.client.post(
            "/api/v1/attendance/records/batch-import/",
            format="multipart",
        )
        self.assertNotEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data["error"]["details"])

    def test_batch_import_forces_attendance_import_type(self):
        """The recorded job type is attendance regardless of the request body."""
        from io import BytesIO

        from apps.data_import.constants import JobStatus
        from apps.data_import.models import ImportJob

        self.client.post(
            "/api/v1/attendance/records/batch-import/",
            {
                "import_type": "students",
                "file": BytesIO(b"student_id,first_name\nS1,Ana\n"),
            },
            format="multipart",
        )

        job = ImportJob.objects.latest("created_at")
        self.assertEqual(job.import_type, "attendance")
        self.assertEqual(job.uploaded_by, self.faculty_user)
        # Student columns cannot satisfy the attendance column contract.
        self.assertEqual(job.status, JobStatus.FAILED)


# ===========================================================================
# API tests — Faculty cannot access unrelated sections
# ===========================================================================


class FacultyCannotAccessUnrelatedSectionTest(AttendanceTestBase):
    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )

    def test_faculty_cannot_create_for_unrelated_section(self):
        response = self.client.post(
            "/api/v1/attendance/records/",
            {
                "student": str(self.student2_profile.id),
                "section": str(self.section_b.id),
                "date": str(self.two_days_ago),
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ===========================================================================
# TC-FAC-17: faculty summary counts must not be multiplied by joins
# ===========================================================================


class FacultySummaryCountTest(AttendanceTestBase):
    """
    `GET /attendance/summary/` groups by student and section.

    The faculty scope used to be expressed as a join through
    `section__subject_assignments__faculty`, a multi-valued relation. A
    `.values().annotate()` over that filter groups on the wrong key, so the
    endpoint returned one group per attendance record, each counting every
    subject assignment in the section: a class with 3 records reported 24
    (3 records x 8 assignments). The advisory class summary reads this
    endpoint, so the page showed the same inflated numbers.
    """

    def setUp(self):
        super().setUp()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty_user)}"
        )
        # Other faculty teaching the same section: the relation the old filter
        # joined through, and what made the counts multiply.
        for index in range(3):
            Subject.objects.create(
                name=f"Extra {index}", code=f"EXT-ATT-{index}",
                grade_level=self.g7,
            )
        for index, subject in enumerate(
            Subject.objects.filter(code__startswith="EXT-ATT-")
        ):
            SubjectAssignment.objects.create(
                subject=subject, faculty=self.faculty2_profile,
                section=self.section_a, academic_year=self.ay,
            )

    def test_summary_returns_one_row_per_student_with_real_counts(self):
        response = self.client.get("/api/v1/attendance/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        rows = [
            entry for entry in response.data
            if str(entry["student"]) == str(self.student_profile.id)
        ]
        # One row for the student in this section, not one row per record.
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # The three real records: 1 present, 1 absent, 1 late.
        self.assertEqual(row["present_count"], 1)
        self.assertEqual(row["absent_count"], 1)
        self.assertEqual(row["late_count"], 1)
        self.assertEqual(row["total_records"], 3)

    def test_summary_scope_is_unchanged_for_other_faculty(self):
        # The section scoping must still hide another faculty's section.
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self._get_token(self.faculty2_user)}"
        )
        response = self.client.get("/api/v1/attendance/summary/")
        rows = [
            entry for entry in response.data
            if str(entry["student"]) == str(self.student_profile.id)
        ]
        # faculty2 teaches section_a too now, so they still see the student,
        # but only the records belonging to their visible sections.
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total_records"], 3)
"""
TC-ADM-11 / FR-034: the attendance threshold is configured at runtime.

The point of the feature is that changing the setting changes the very next
alert, with no restart. These tests pin exactly that, plus the direction that
matters most operationally - raising the threshold must stop alerts that used
to fire, and a mistyped setting must not cost an attendance record its write.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.attendance.models import AttendanceRecord
from apps.attendance.tests import AttendanceTestBase
from apps.notifications.models import Notification, NotificationType

User = get_user_model()

SETTINGS_URL = "/api/v1/cms/settings/"
ABSENCE_URL = "/api/v1/cms/settings/attendance.absence_threshold/"
ATTENDANCE_URL = "/api/v1/attendance/records/"


def absent_count() -> int:
    return AttendanceRecord.objects.filter(
        status=AttendanceRecord.Status.ABSENT
    ).count()


def attendance_alert_count() -> int:
    return Notification.objects.filter(
        notification_type=NotificationType.ATTENDANCE_THRESHOLD,
    ).count()


class AttendanceThresholdTestBase(AttendanceTestBase):
    def setUp(self):
        super().setUp()
        # Reset the setting to its registered default so a previously-run test
        # cannot leak a saved value into this one.
        from apps.cms.models import SystemSetting

        SystemSetting.objects.filter(
            key="attendance.absence_threshold"
        ).update(value="3")

    @staticmethod
    def _client_for(user) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _record_absence(self, client, days_ago=20):
        """Record one absence for student_profile through the real endpoint."""
        return client.post(
            ATTENDANCE_URL,
            {
                "student": str(self.student_profile.id),
                "section": str(self.section_a.id),
                "date": (timezone.localdate() - timedelta(days=days_ago)).isoformat(),
                "status": "absent",
            },
            format="json",
        )


class AttendanceThresholdChangeTest(AttendanceThresholdTestBase):
    """An administrator's change takes effect on the next recorded absence."""

    def test_the_registered_default_alerts_on_the_third_absence(self):
        # The shared fixture already made one absence.
        self.assertEqual(absent_count(), 1)
        faculty = self._client_for(self.faculty_user)

        self.assertEqual(
            self._record_absence(faculty, days_ago=21).status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(absent_count(), 2)
        self.assertEqual(attendance_alert_count(), 0, "two absences is not three")

        response = self._record_absence(faculty, days_ago=22)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(attendance_alert_count(), 1, "the third absence alerts")
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.parent_user,
                notification_type=NotificationType.ATTENDANCE_THRESHOLD,
            ).exists(),
            "the alert goes to the parent of the absent student",
        )

    def test_raising_the_threshold_stops_an_alert_that_used_to_fire(self):
        admin = self._client_for(self.admin_user)
        self.assertEqual(
            admin.patch(ABSENCE_URL, {"value": "10"}, format="json").status_code,
            status.HTTP_200_OK,
        )

        faculty = self._client_for(self.faculty_user)
        for days_ago in (21, 22, 23):
            self.assertEqual(
                self._record_absence(faculty, days_ago=days_ago).status_code,
                status.HTTP_201_CREATED,
            )

        self.assertEqual(attendance_alert_count(), 0, "4 < 10, so no alert")

    def test_lowering_the_threshold_alerts_earlier(self):
        admin = self._client_for(self.admin_user)
        self.assertEqual(
            admin.patch(ABSENCE_URL, {"value": "2"}, format="json").status_code,
            status.HTTP_200_OK,
        )

        faculty = self._client_for(self.faculty_user)
        self.assertEqual(
            self._record_absence(faculty, days_ago=21).status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            attendance_alert_count(),
            1,
            "the second absence reaches a threshold of 2",
        )

    def test_the_change_applies_to_an_already_open_client(self):
        """
        Read at the moment of the write, not cached at import time: the same
        client that saw the old value sees the new one without a reconnect.
        """
        faculty = self._client_for(self.faculty_user)
        for days_ago in (21, 22):
            self._record_absence(faculty, days_ago=days_ago)
        self.assertEqual(attendance_alert_count(), 1)

        admin = self._client_for(self.admin_user)
        admin.patch(ABSENCE_URL, {"value": "99"}, format="json")

        self._record_absence(faculty, days_ago=23)
        self._record_absence(faculty, days_ago=24)

        self.assertEqual(
            attendance_alert_count(),
            1,
            "a threshold of 99 adds no further alert",
        )

    def test_a_mistyped_setting_falls_back_to_the_registered_default(self):
        """
        The serializer refuses a non-integer, but if one ever reached the row,
        writing an absence must still succeed - and must still use the default
        of 3. A fallback to 0 would alert on the very first absence, which is
        the opposite of what a mistyped value should cause.
        """
        from apps.cms.models import SystemSetting

        SystemSetting.objects.filter(
            key="attendance.absence_threshold"
        ).update(value="not-a-number")

        faculty = self._client_for(self.faculty_user)
        self.assertEqual(
            self._record_absence(faculty, days_ago=21).status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            attendance_alert_count(),
            0,
            "two absences is still below the default of three",
        )

        response = self._record_absence(faculty, days_ago=22)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            attendance_alert_count(),
            1,
            "the fallback is the registered default of 3, not 0",
        )
