"""
Phase 4 test suite for AEGIS Notifications.

Covers: model validation, API endpoints, scoped querysets,
role-based permissions, mark-read, preferences, GRADE_POSTED
integration, ATTENDANCE_THRESHOLD integration, deduplication,
and dispatch_event unit tests.
"""

from datetime import date, time, timedelta

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
    Grade,
    GradeLevel,
    GradingPeriod,
    Section,
    Subject,
    SubjectAssignment,
)
from apps.attendance.models import AttendanceRecord
from apps.notifications.events import dispatch_event
from apps.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationType,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class NotificationsTestBase(TestCase):
    """Shared setUp for notification tests."""

    def setUp(self):
        # --- Users ---
        self.admin_user = User.objects.create_user(
            email="admin_notif@test.com", password="pass12345",
            first_name="Admin", last_name="User", role="admin",
        )
        self.faculty_user = User.objects.create_user(
            email="faculty_notif@test.com", password="pass12345",
            first_name="Fac", last_name="ulty", role="faculty",
        )
        self.student_user = User.objects.create_user(
            email="student_notif@test.com", password="pass12345",
            first_name="Stu", last_name="dent", role="student",
        )
        self.student2_user = User.objects.create_user(
            email="student2_notif@test.com", password="pass12345",
            first_name="Stu2", last_name="dent2", role="student",
        )
        self.parent_user = User.objects.create_user(
            email="parent_notif@test.com", password="pass12345",
            first_name="Par", last_name="ent", role="parent",
        )
        self.parent2_user = User.objects.create_user(
            email="parent2_notif@test.com", password="pass12345",
            first_name="Par2", last_name="ent2", role="parent",
        )
        self.guidance_user = User.objects.create_user(
            email="guidance_notif@test.com", password="pass12345",
            first_name="Guid", last_name="ance", role="guidance",
        )

        # --- Profiles ---
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="EMP-NOTIF-001", department="Math",
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user, student_id="STU-NOTIF-001",
            enrollment_date=date(2026, 6, 1),
        )
        self.student2_profile = StudentProfile.objects.create(
            user=self.student2_user, student_id="STU-NOTIF-002",
            enrollment_date=date(2026, 6, 1),
        )
        self.parent_profile = ParentProfile.objects.create(
            user=self.parent_user, relationship_to_student="mother",
        )
        self.parent2_profile = ParentProfile.objects.create(
            user=self.parent2_user, relationship_to_student="father",
        )
        ParentStudentLink.objects.create(
            parent=self.parent_profile, student=self.student_profile, is_primary=True,
        )
        ParentStudentLink.objects.create(
            parent=self.parent2_profile, student=self.student_profile, is_primary=False,
        )

        # --- Academic structure ---
        self.academic_year = AcademicYear.objects.create(
            name="2026-2027", start_date=date(2026, 6, 1),
            end_date=date(2027, 3, 31), is_current=True,
        )
        self.grade_level = GradeLevel.objects.create(name="Grade 7", level_number=7)
        self.section = Section.objects.create(
            name="Einstein", grade_level=self.grade_level,
            academic_year=self.academic_year, adviser=self.faculty_profile,
        )
        self.subject = Subject.objects.create(
            name="Mathematics", code="MATH-7", grade_level=self.grade_level,
        )
        self.subject_assignment = SubjectAssignment.objects.create(
            subject=self.subject, faculty=self.faculty_profile,
            section=self.section, academic_year=self.academic_year,
        )
        self.grading_period = GradingPeriod.objects.create(
            academic_year=self.academic_year, name="1st Quarter",
            order=1, start_date=date(2026, 6, 1), end_date=date(2026, 8, 31),
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student_profile, section=self.section,
            academic_year=self.academic_year, date_enrolled=date(2026, 6, 1),
        )
        self.enrollment2 = Enrollment.objects.create(
            student=self.student2_profile, section=self.section,
            academic_year=self.academic_year, date_enrolled=date(2026, 6, 1),
        )

        # --- Submitted grade (for finalize integration) ---
        self.submitted_grade = Grade.objects.create(
            student=self.student_profile,
            subject_assignment=self.subject_assignment,
            grading_period=self.grading_period,
            score=85.0,
            letter_grade="B",
            encoded_by=self.faculty_profile,
            status=Grade.StatusChoices.SUBMITTED,
        )

        # Second grading period for tests that need a free student/subject/slot
        self.grading_period2 = GradingPeriod.objects.create(
            academic_year=self.academic_year, name="2nd Quarter",
            order=2, start_date=date(2026, 9, 1), end_date=date(2026, 11, 30),
        )

        # --- API client ---
        self.client = APIClient()

    def _auth(self, user):
        """Authenticate as the given user."""
        self.client.force_authenticate(user=user)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class NotificationStrTest(NotificationsTestBase):
    def test_str(self):
        n = Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="Test", message="Body",
        )
        result = str(n)
        self.assertIn("Grade Posted", result)
        self.assertIn(self.student_user.get_full_name(), result)


class NotificationTypeChoicesTest(NotificationsTestBase):
    def test_all_ten_types_exist(self):
        self.assertEqual(len(NotificationType.choices), 10)

    def test_grade_posted_value(self):
        self.assertEqual(NotificationType.GRADE_POSTED, "GRADE_POSTED")

    def test_attendance_threshold_value(self):
        self.assertEqual(NotificationType.ATTENDANCE_THRESHOLD, "ATTENDANCE_THRESHOLD")


class NotificationDefaultsTest(NotificationsTestBase):
    def test_is_read_defaults_false(self):
        n = Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="T", message="M",
        )
        self.assertFalse(n.is_read)
        self.assertIsNone(n.read_at)
        self.assertIsNone(n.sender)
        self.assertIsNone(n.link)


class NotificationPreferenceStrTest(NotificationsTestBase):
    def test_str(self):
        pref = NotificationPreference.objects.create(user=self.student_user)
        result = str(pref)
        self.assertIn(self.student_user.get_full_name(), result)


class NotificationPreferenceDefaultsTest(NotificationsTestBase):
    def test_defaults(self):
        pref = NotificationPreference.objects.create(user=self.student_user)
        self.assertTrue(pref.email_enabled)
        self.assertTrue(pref.in_app_enabled)
        self.assertIsNone(pref.quiet_hours_start)
        self.assertIsNone(pref.quiet_hours_end)


class NotificationPreferenceUniqueUserTest(NotificationsTestBase):
    def test_duplicate_user_raises(self):
        NotificationPreference.objects.create(user=self.student_user)
        with self.assertRaises(Exception):
            NotificationPreference.objects.create(user=self.student_user)


# ---------------------------------------------------------------------------
# API tests — List/retrieve
# ---------------------------------------------------------------------------


class UnauthenticatedListTest(NotificationsTestBase):
    def test_list_401(self):
        resp = self.client.get("/api/v1/notifications/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_401(self):
        n = Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="T", message="M",
        )
        resp = self.client.get(f"/api/v1/notifications/{n.id}/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class UserSeesOnlyOwnNotificationsTest(NotificationsTestBase):
    def test_student_sees_only_own(self):
        Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="Student notif", message="M",
        )
        Notification.objects.create(
            recipient=self.parent_user,
            notification_type="GRADE_POSTED",
            title="Parent notif", message="M",
        )
        self._auth(self.student_user)
        resp = self.client.get("/api/v1/notifications/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["title"], "Student notif")


class FilterByReadStatusTest(NotificationsTestBase):
    def test_filter_unread(self):
        n1 = Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="Read", message="M", is_read=True, read_at=timezone.now(),
        )
        n2 = Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="Unread", message="M",
        )
        self._auth(self.student_user)
        resp = self.client.get("/api/v1/notifications/?is_read=false")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["title"], "Unread")


class FilterByTypeTest(NotificationsTestBase):
    def test_filter_by_type(self):
        Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="Grade", message="M",
        )
        Notification.objects.create(
            recipient=self.student_user,
            notification_type="ATTENDANCE_THRESHOLD",
            title="Attend", message="M",
        )
        self._auth(self.student_user)
        resp = self.client.get("/api/v1/notifications/?notification_type=GRADE_POSTED")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["title"], "Grade")


# ---------------------------------------------------------------------------
# API tests — Mark-read
# ---------------------------------------------------------------------------


class MarkOneAsReadTest(NotificationsTestBase):
    def test_mark_read(self):
        n = Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="T", message="M",
        )
        self._auth(self.student_user)
        resp = self.client.post(f"/api/v1/notifications/{n.id}/read/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        n.refresh_from_db()
        self.assertTrue(n.is_read)
        self.assertIsNotNone(n.read_at)


class MarkAlreadyReadTest(NotificationsTestBase):
    def test_already_read(self):
        n = Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="T", message="M",
            is_read=True, read_at=timezone.now(),
        )
        original_read_at = n.read_at
        self._auth(self.student_user)
        resp = self.client.post(f"/api/v1/notifications/{n.id}/read/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        n.refresh_from_db()
        self.assertEqual(n.read_at, original_read_at)


class MarkOtherUserReadTest(NotificationsTestBase):
    def test_cannot_mark_others(self):
        n = Notification.objects.create(
            recipient=self.parent_user,
            notification_type="GRADE_POSTED",
            title="T", message="M",
        )
        self._auth(self.student_user)
        resp = self.client.post(f"/api/v1/notifications/{n.id}/read/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class MarkAllAsReadTest(NotificationsTestBase):
    def test_mark_all(self):
        Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="T1", message="M",
        )
        Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="T2", message="M",
        )
        self._auth(self.student_user)
        resp = self.client.post("/api/v1/notifications/read-all/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.student_user, is_read=True
            ).count(),
            2,
        )


class MarkAllAlreadyReadTest(NotificationsTestBase):
    def test_all_already_read(self):
        Notification.objects.create(
            recipient=self.student_user,
            notification_type="GRADE_POSTED",
            title="T", message="M",
            is_read=True, read_at=timezone.now(),
        )
        self._auth(self.student_user)
        resp = self.client.post("/api/v1/notifications/read-all/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 0)


# ---------------------------------------------------------------------------
# API tests — Preferences
# ---------------------------------------------------------------------------


class GetDefaultPreferencesTest(NotificationsTestBase):
    def test_get_creates_defaults(self):
        self._auth(self.student_user)
        resp = self.client.get("/api/v1/notifications/preferences/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["email_enabled"])
        self.assertTrue(resp.data["in_app_enabled"])
        self.assertIsNone(resp.data["quiet_hours_start"])
        self.assertIsNone(resp.data["quiet_hours_end"])


class UpdatePreferencesTest(NotificationsTestBase):
    def test_update(self):
        self._auth(self.student_user)
        resp = self.client.put(
            "/api/v1/notifications/preferences/",
            {
                "email_enabled": False,
                "in_app_enabled": True,
                "quiet_hours_start": None,
                "quiet_hours_end": None,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["email_enabled"])


class ValidOvernightQuietHoursTest(NotificationsTestBase):
    def test_overnight_valid(self):
        self._auth(self.student_user)
        resp = self.client.put(
            "/api/v1/notifications/preferences/",
            {
                "email_enabled": True,
                "in_app_enabled": True,
                "quiet_hours_start": "22:00:00",
                "quiet_hours_end": "06:00:00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class InvalidSameTimeQuietHoursTest(NotificationsTestBase):
    def test_same_time_invalid(self):
        self._auth(self.student_user)
        resp = self.client.put(
            "/api/v1/notifications/preferences/",
            {
                "email_enabled": True,
                "in_app_enabled": True,
                "quiet_hours_start": "06:00:00",
                "quiet_hours_end": "06:00:00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Integration tests — GRADE_POSTED
# ---------------------------------------------------------------------------


class GradeFinalizeCreatesNotificationsTest(NotificationsTestBase):
    def test_finalize_creates_for_student_and_parents(self):
        self._auth(self.admin_user)
        resp = self.client.post(
            f"/api/v1/academics/grades/{self.submitted_grade.id}/finalize/"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Student + 2 parents = 3 notifications
        self.assertEqual(
            Notification.objects.filter(
                notification_type="GRADE_POSTED",
            ).count(),
            3,
        )
        # Check student received one
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.student_user,
                notification_type="GRADE_POSTED",
            ).exists()
        )
        # Check both parents received one
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.parent_user,
                notification_type="GRADE_POSTED",
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.parent2_user,
                notification_type="GRADE_POSTED",
            ).exists()
        )


class GradeDraftNoNotificationTest(NotificationsTestBase):
    def test_draft_no_notification(self):
        self._auth(self.faculty_user)
        resp = self.client.post(
            "/api/v1/academics/grades/encode/",
            {
                "student": str(self.student_profile.id),
                "subject_assignment": str(self.subject_assignment.id),
                "grading_period": str(self.grading_period2.id),
                "score": 90.0,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertFalse(
            Notification.objects.filter(
                notification_type="GRADE_POSTED",
            ).exists()
        )


class GradeEncodeNoNotificationTest(NotificationsTestBase):
    def test_encode_no_notification(self):
        """Encoding (creating a grade via faculty encode endpoint) does not fire GRADE_POSTED."""
        self._auth(self.faculty_user)
        resp = self.client.post(
            "/api/v1/academics/grades/encode/",
            {
                "student": str(self.student2_profile.id),
                "subject_assignment": str(self.subject_assignment.id),
                "grading_period": str(self.grading_period.id),
                "score": 75.0,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertFalse(
            Notification.objects.filter(
                notification_type="GRADE_POSTED",
            ).exists()
        )


# ---------------------------------------------------------------------------
# Integration tests — ATTENDANCE_THRESHOLD
# ---------------------------------------------------------------------------


class BelowThresholdNoNotificationTest(NotificationsTestBase):
    def test_two_absences_no_notification(self):
        self._auth(self.faculty_user)
        for i in range(2):
            self.client.post(
                "/api/v1/attendance/records/",
                {
                    "student": str(self.student_profile.id),
                    "section": str(self.section.id),
                    "date": (date(2026, 7, 1) + timedelta(days=i)).isoformat(),
                    "status": "absent",
                },
                format="json",
            )
        self.assertFalse(
            Notification.objects.filter(
                notification_type="ATTENDANCE_THRESHOLD",
            ).exists()
        )


class AtThresholdFiresNotificationTest(NotificationsTestBase):
    def test_three_absences_fires(self):
        self._auth(self.faculty_user)
        for i in range(3):
            resp = self.client.post(
                "/api/v1/attendance/records/",
                {
                    "student": str(self.student_profile.id),
                    "section": str(self.section.id),
                    "date": (date(2026, 7, 1) + timedelta(days=i)).isoformat(),
                    "status": "absent",
                },
                format="json",
            )
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # After 3 absences, parents should be notified
        self.assertTrue(
            Notification.objects.filter(
                notification_type="ATTENDANCE_THRESHOLD",
                recipient=self.parent_user,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                notification_type="ATTENDANCE_THRESHOLD",
                recipient=self.parent2_user,
            ).exists()
        )


class DeduplicationPreventsDuplicateTest(NotificationsTestBase):
    def test_fourth_absence_no_duplicate(self):
        self._auth(self.faculty_user)
        for i in range(3):
            self.client.post(
                "/api/v1/attendance/records/",
                {
                    "student": str(self.student_profile.id),
                    "section": str(self.section.id),
                    "date": (date(2026, 7, 1) + timedelta(days=i)).isoformat(),
                    "status": "absent",
                },
                format="json",
            )
        # Count after 3
        count_after_3 = Notification.objects.filter(
            notification_type="ATTENDANCE_THRESHOLD",
        ).count()

        # Record 4th absence
        self.client.post(
            "/api/v1/attendance/records/",
            {
                "student": str(self.student_profile.id),
                "section": str(self.section.id),
                "date": date(2026, 7, 4).isoformat(),
                "status": "absent",
            },
            format="json",
        )
        # Count should not increase (deduplication)
        count_after_4 = Notification.objects.filter(
            notification_type="ATTENDANCE_THRESHOLD",
        ).count()
        self.assertEqual(count_after_3, count_after_4)


class ThresholdDifferentAcademicYearTest(NotificationsTestBase):
    def test_new_year_eligible_for_new_notification(self):
        self._auth(self.faculty_user)
        # Record 3 absences in current year
        for i in range(3):
            self.client.post(
                "/api/v1/attendance/records/",
                {
                    "student": str(self.student_profile.id),
                    "section": str(self.section.id),
                    "date": (date(2026, 7, 1) + timedelta(days=i)).isoformat(),
                    "status": "absent",
                },
                format="json",
            )
        self.assertTrue(
            Notification.objects.filter(
                notification_type="ATTENDANCE_THRESHOLD",
            ).exists()
        )

        # Create a second academic year and section
        ay2 = AcademicYear.objects.create(
            name="2027-2028", start_date=date(2027, 6, 1),
            end_date=date(2028, 3, 31), is_current=False,
        )
        section2 = Section.objects.create(
            name="Newton", grade_level=self.grade_level,
            academic_year=ay2, adviser=self.faculty_profile,
        )
        Enrollment.objects.create(
            student=self.student_profile, section=section2,
            academic_year=ay2, date_enrolled=date(2027, 6, 1),
        )

        # Record 3 absences in new year
        for i in range(3):
            self.client.post(
                "/api/v1/attendance/records/",
                {
                    "student": str(self.student_profile.id),
                    "section": str(section2.id),
                    "date": (date(2027, 7, 1) + timedelta(days=i)).isoformat(),
                    "status": "absent",
                },
                format="json",
            )
        # Should have 2 ATTENDANCE_THRESHOLD notifications total (one per year)
        self.assertEqual(
            Notification.objects.filter(
                notification_type="ATTENDANCE_THRESHOLD",
            ).count(),
            2,
        )


class ThresholdSkipsOptedOutParentTest(NotificationsTestBase):
    def test_opted_out_parent_no_notification(self):
        NotificationPreference.objects.create(
            user=self.parent_user, in_app_enabled=False,
        )
        self._auth(self.faculty_user)
        for i in range(3):
            self.client.post(
                "/api/v1/attendance/records/",
                {
                    "student": str(self.student_profile.id),
                    "section": str(self.section.id),
                    "date": (date(2026, 7, 1) + timedelta(days=i)).isoformat(),
                    "status": "absent",
                },
                format="json",
            )
        # opted-out parent should NOT have notification
        self.assertFalse(
            Notification.objects.filter(
                notification_type="ATTENDANCE_THRESHOLD",
                recipient=self.parent_user,
            ).exists()
        )
        # opted-in parent2 SHOULD have notification
        self.assertTrue(
            Notification.objects.filter(
                notification_type="ATTENDANCE_THRESHOLD",
                recipient=self.parent2_user,
            ).exists()
        )


class PresentLateDoesNotTriggerThresholdTest(NotificationsTestBase):
    def test_present_and_late_do_not_count(self):
        self._auth(self.faculty_user)
        statuses = ["present", "late", "present", "late", "present"]
        for i, st in enumerate(statuses):
            self.client.post(
                "/api/v1/attendance/records/",
                {
                    "student": str(self.student_profile.id),
                    "section": str(self.section.id),
                    "date": (date(2026, 7, 1) + timedelta(days=i)).isoformat(),
                    "status": st,
                },
                format="json",
            )
        self.assertFalse(
            Notification.objects.filter(
                notification_type="ATTENDANCE_THRESHOLD",
            ).exists()
        )


# ---------------------------------------------------------------------------
# dispatch_event unit tests
# ---------------------------------------------------------------------------


class DispatchEventCreatesNotificationsTest(TestCase):
    def test_creates_notifications(self):
        user = User.objects.create_user(
            email="dispatch1@test.com", password="pass12345",
            first_name="D", last_name="1", role="student",
        )
        dispatch_event(
            "GRADE_POSTED",
            recipients=[user],
            title="T", message="M",
        )
        self.assertEqual(Notification.objects.count(), 1)
        n = Notification.objects.first()
        self.assertEqual(n.recipient, user)
        self.assertEqual(n.notification_type, "GRADE_POSTED")


class DispatchEventSkipsOptedOutTest(TestCase):
    def test_skips_opted_out(self):
        user = User.objects.create_user(
            email="dispatch2@test.com", password="pass12345",
            first_name="D", last_name="2", role="student",
        )
        NotificationPreference.objects.create(user=user, in_app_enabled=False)
        dispatch_event(
            "GRADE_POSTED",
            recipients=[user],
            title="T", message="M",
        )
        self.assertEqual(Notification.objects.count(), 0)


class DispatchEventCreatesDefaultPreferenceTest(TestCase):
    def test_creates_preference(self):
        user = User.objects.create_user(
            email="dispatch3@test.com", password="pass12345",
            first_name="D", last_name="3", role="student",
        )
        self.assertFalse(NotificationPreference.objects.filter(user=user).exists())
        dispatch_event(
            "GRADE_POSTED",
            recipients=[user],
            title="T", message="M",
        )
        self.assertTrue(NotificationPreference.objects.filter(user=user).exists())


class DispatchEventDeduplicationTest(TestCase):
    def test_deduplication_key_prevents_duplicate(self):
        user = User.objects.create_user(
            email="dedup1@test.com", password="pass12345",
            first_name="D", last_name="D1", role="student",
        )
        dispatch_event(
            "ATTENDANCE_THRESHOLD",
            recipients=[user],
            title="T", message="M",
            deduplication_key="key123",
        )
        self.assertEqual(Notification.objects.count(), 1)
        # Second dispatch with same key should be skipped
        dispatch_event(
            "ATTENDANCE_THRESHOLD",
            recipients=[user],
            title="T2", message="M2",
            deduplication_key="key123",
        )
        self.assertEqual(Notification.objects.count(), 1)


class DispatchEventEmptyRecipientsTest(TestCase):
    def test_empty_recipients_no_error(self):
        dispatch_event(
            "GRADE_POSTED",
            recipients=[],
            title="T", message="M",
        )
        self.assertEqual(Notification.objects.count(), 0)


class DispatchEventNoSenderTest(TestCase):
    def test_sender_none(self):
        user = User.objects.create_user(
            email="sender1@test.com", password="pass12345",
            first_name="S", last_name="1", role="student",
        )
        dispatch_event(
            "GRADE_POSTED",
            recipients=[user],
            sender=None,
            title="T", message="M",
        )
        n = Notification.objects.first()
        self.assertIsNone(n.sender)
