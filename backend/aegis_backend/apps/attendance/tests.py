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
