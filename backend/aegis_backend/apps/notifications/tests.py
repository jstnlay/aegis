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
    def test_the_notification_types_are_exactly_these(self):
        """
        Asserted as a set, not a count.

        The count alone would pass if a type were renamed or swapped for
        another - it only ever caught additions and removals. Naming the set
        catches both, which is what the enumeration is for: every one of these
        is a string a migration, a serializer or a frontend label map depends
        on staying put.
        """
        self.assertEqual(
            {value for value, _label in NotificationType.choices},
            {
                "GRADE_POSTED",
                "ATTENDANCE_THRESHOLD",
                "BEHAVIORAL_WARNING",
                "BEHAVIORAL_INCIDENT",
                "ASSESSMENT_DEPLOYED",
                "ASSESSMENT_COMPLETED",
                "RISK_ALERT_GENERATED",
                "INTERVENTION_UPDATE",
                "ANNOUNCEMENT_PUBLISHED",
                "CONSULTATION_SCHEDULED",
                # NFR-012 / TC-SYS-08
                "MAINTENANCE_NOTICE",
            },
        )

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
"""
NFR-012 / TC-SYS-08: advance notice of scheduled maintenance.

NFR-012 reads "Users shall be notified at least 24 hours in advance of
scheduled maintenance." The repo has no task scheduler, so that guarantee
cannot be a job that fires later and cannot be tested against a clock that has
advanced. It is a structural property instead: a window cannot be scheduled
inside 24 hours, and its notice goes out with it.

These tests pin the property from both directions, because each half can be
true alone and neither is the requirement:
  - a window that is refused must not exist and must not have notified anyone
  - a window that is allowed must have notified every active user
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.notifications.events import schedule_maintenance_window
from apps.notifications.models import (
    MaintenanceWindow,
    Notification,
    NotificationPreference,
    NotificationType,
)

User = get_user_model()

URL = "/api/v1/notifications/maintenance/"


class MaintenanceTestBase(TestCase):
    """A handful of users across roles, and nothing else."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="maint_admin@test.com", password="pass12345",
            first_name="Ad", last_name="Min", role="admin",
        )
        self.faculty = User.objects.create_user(
            email="maint_faculty@test.com", password="pass12345",
            first_name="Fac", last_name="Ultty", role="faculty",
        )
        self.student = User.objects.create_user(
            email="maint_student@test.com", password="pass12345",
            first_name="Stu", last_name="Dent", role="student",
        )
        self.parent = User.objects.create_user(
            email="maint_parent@test.com", password="pass12345",
            first_name="Par", last_name="Ent", role="parent",
        )
        self.client = APIClient()

    @staticmethod
    def _start(hours_ahead: int):
        return timezone.now() + timedelta(hours=hours_ahead)

    @staticmethod
    def _notices():
        return Notification.objects.filter(
            notification_type=NotificationType.MAINTENANCE_NOTICE
        )


class MaintenancePermissionTest(MaintenanceTestBase):
    """NFR-012 schedules through an administrator, like every other system act."""

    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            self.client.post(URL, {}, format="json").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_every_non_admin_role_is_refused(self):
        starts = self._start(72)
        for user in (self.faculty, self.student, self.parent):
            self.client.force_authenticate(user=user)
            self.assertEqual(
                self.client.get(URL).status_code,
                status.HTTP_403_FORBIDDEN,
                f"{user.role} must not schedule maintenance",
            )
            response = self.client.post(
                URL,
                {"starts_at": starts, "ends_at": starts + timedelta(hours=2)},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(MaintenanceWindow.objects.count(), 0)

    def test_admin_can_list_and_schedule(self):
        self.client.force_authenticate(user=self.admin)
        starts = self._start(72)

        response = self.client.post(
            URL,
            {
                "starts_at": starts,
                "ends_at": starts + timedelta(hours=2),
                "message": "Database upgrade.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MaintenanceWindow.objects.count(), 1)
        listing = self.client.get(URL)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data), 1)


class MaintenanceTwentyFourHourRuleTest(MaintenanceTestBase):
    """The property NFR-012 actually names."""

    def test_a_window_inside_24_hours_is_refused(self):
        self.client.force_authenticate(user=self.admin)
        starts = self._start(3)

        response = self.client.post(
            URL, {"starts_at": starts, "ends_at": starts + timedelta(hours=1)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("starts_at", response.data["error"]["details"])

    def test_a_refused_window_creates_nothing_and_notifies_no_one(self):
        """The half of the property that is easy to leave unstated."""
        self.client.force_authenticate(user=self.admin)
        starts = self._start(1)

        self.client.post(
            URL, {"starts_at": starts, "ends_at": starts + timedelta(hours=1)},
            format="json",
        )

        self.assertEqual(MaintenanceWindow.objects.count(), 0)
        self.assertEqual(self._notices().count(), 0)

    def test_a_window_at_exactly_24_hours_is_refused(self):
        """
        The boundary fails safe, and the reason is worth pinning rather than
        hiding.

        The notice is issued an instant *after* the timestamp the admin picked,
        so a window chosen at exactly T+24h is delivered at T+24h-epsilon.
        Rejecting it is pedantry against a clock, but accepting it would mean
        promising 24 hours and delivering slightly less. Failing safe costs an
        admin one nudge of the clock; failing open costs the requirement.
        """
        starts = timezone.now() + timedelta(hours=24)
        with self.assertRaises(ValidationError):
            schedule_maintenance_window(
                starts_at=starts, ends_at=starts + timedelta(hours=1)
            )

    def test_a_window_with_any_margin_is_allowed(self):
        """The same call with one clear minute of headroom sails through."""
        starts = timezone.now() + timedelta(hours=24, minutes=1)
        window = schedule_maintenance_window(
            starts_at=starts, ends_at=starts + timedelta(hours=1)
        )
        self.assertIsNotNone(window.pk)

    def test_a_window_in_the_past_is_refused(self):
        with self.assertRaises(ValidationError):
            schedule_maintenance_window(
                starts_at=timezone.now() - timedelta(hours=2),
                ends_at=timezone.now(),
            )

    def test_a_window_ending_before_it_starts_is_refused(self):
        starts = self._start(72)
        with self.assertRaises(ValidationError):
            schedule_maintenance_window(
                starts_at=starts, ends_at=starts - timedelta(hours=1)
            )

    def test_the_endpoint_reports_the_real_lead_time(self):
        self.client.force_authenticate(user=self.admin)
        starts = self._start(72)

        response = self.client.post(
            URL, {"starts_at": starts, "ends_at": starts + timedelta(hours=1)},
            format="json",
        )

        # `lead_hours` is measured, not echoed from the request: 72 requested,
        # minus however long validation and the dispatch took.
        self.assertGreaterEqual(response.data["lead_hours"], 71)


class MaintenanceNoticeDeliveryTest(MaintenanceTestBase):
    """What a permitted window actually does."""

    def setUp(self):
        super().setUp()
        self.starts = self._start(48)
        self.window = schedule_maintenance_window(
            starts_at=self.starts,
            ends_at=self.starts + timedelta(hours=2),
            message="Database upgrade.",
            sender=self.admin,
        )

    def test_every_active_user_is_notified(self):
        notified = set(self._notices().values_list("recipient_id", flat=True))
        active = set(User.objects.filter(is_active=True).values_list("id", flat=True))
        self.assertEqual(notified, active)

    def test_the_notice_states_its_own_lead_time(self):
        """NFR-012 is a claim about elapsed time; make it checkable."""
        import re

        match = re.search(r"(\d+) hours in advance", self._notices().first().message)
        self.assertIsNotNone(match, "the notice must state its lead time")
        # Floored to whole hours, and measured from the moment of dispatch, so
        # a 48-hour request reports 47. The property is that it clears the
        # requirement's own number with room to spare.
        self.assertGreaterEqual(int(match.group(1)), 47)
        self.assertGreaterEqual(int(match.group(1)), MaintenanceWindow.MIN_NOTICE.total_seconds() // 3600)

    def test_the_message_body_carries_the_admins_wording(self):
        self.assertIn("Database upgrade.", self._notices().first().message)

    def test_the_window_is_stamped_as_notified(self):
        self.assertIsNotNone(self.window.notified_at)
        self.assertLessEqual(self.window.notified_at, self.window.starts_at)

    def test_an_inactive_user_is_not_notified(self):
        User.objects.filter(email="maint_parent@test.com").update(is_active=False)

        starts = self._start(96)
        second = schedule_maintenance_window(
            starts_at=starts, ends_at=starts + timedelta(hours=1)
        )

        notified = Notification.objects.filter(
            deduplication_key=f"maintenance:{second.id}"
        ).values_list("recipient__email", flat=True)
        self.assertNotIn("maint_parent@test.com", notified)

    def test_an_opted_out_user_is_not_notified(self):
        """dispatch_event honours in_app_enabled, and so does this."""
        NotificationPreference.objects.filter(user=self.student).update(
            in_app_enabled=False
        )

        starts = self._start(96)
        second = schedule_maintenance_window(
            starts_at=starts, ends_at=starts + timedelta(hours=1)
        )

        # Scoped to the new window: setUp already notified the student once,
        # and a test that filters every maintenance notice would be asserting
        # on the fixture rather than on this dispatch.
        notified = Notification.objects.filter(
            deduplication_key=f"maintenance:{second.id}"
        ).values_list("recipient_id", flat=True)
        self.assertNotIn(self.student.id, notified)

    def test_rescheduling_the_same_window_does_not_double_notify(self):
        """The dedup key is per window, so a retry is not a second notice."""
        from apps.notifications.events import dispatch_event

        before = self._notices().count()
        dispatch_event(
            NotificationType.MAINTENANCE_NOTICE,
            recipients=User.objects.filter(is_active=True),
            title="Scheduled maintenance",
            message="retry",
            deduplication_key=f"maintenance:{self.window.id}",
        )
        self.assertEqual(self._notices().count(), before)


class MaintenanceTransactionTest(MaintenanceTestBase):
    """The invariant is only real if a failed notice cannot leave a window."""

    def test_a_failed_dispatch_creates_no_window(self):
        starts = self._start(72)

        with mock.patch(
            "apps.notifications.events.dispatch_event",
            side_effect=RuntimeError("notification backend down"),
        ):
            with self.assertRaises(RuntimeError):
                schedule_maintenance_window(
                    starts_at=starts,
                    ends_at=starts + timedelta(hours=1),
                    sender=self.admin,
                )

        self.assertEqual(
            MaintenanceWindow.objects.count(),
            0,
            "a window whose notice never went out is the state NFR-012 forbids",
        )


class MaintenanceModelTest(MaintenanceTestBase):
    """The rule lives on the model, so every caller is covered by it."""

    def test_clean_enforces_the_rule_without_an_endpoint(self):
        window = MaintenanceWindow(
            starts_at=self._start(2),
            ends_at=self._start(3),
        )
        with self.assertRaises(ValidationError) as ctx:
            window.full_clean()
        self.assertIn("starts_at", ctx.exception.message_dict)

    def test_a_valid_window_passes_clean(self):
        window = MaintenanceWindow(
            starts_at=self._start(30),
            ends_at=self._start(32),
        )
        window.full_clean()  # must not raise

    def test_the_min_notice_constant_is_the_requirements_own_number(self):
        self.assertEqual(MaintenanceWindow.MIN_NOTICE, timedelta(hours=24))
"""
NFR-012 via the Django admin.

The admin schedules through the same service the API uses, and this pins
that: adding a window dispatches exactly one notice, refusing a window
inside 24 hours creates nothing and notifies no one, and windows cannot be
edited or deleted from here.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.client import Client
from django.utils import timezone

from apps.notifications.models import (
    MaintenanceWindow,
    Notification,
    NotificationType,
)

User = get_user_model()

ADD_URL = "/admin/notifications/maintenancewindow/add/"


class MaintenanceAdminTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            email="maint_root@test.com", password="pass12345",
            first_name="Ro", last_name="Ot",
        )
        self.ordinary = User.objects.create_user(
            email="maint_ordinary@test.com", password="pass12345",
            first_name="Or", last_name="Dinary", role="student",
        )
        self.client.force_login(self.superuser)

    @staticmethod
    def _post_data(starts_at, ends_at):
        # The admin's split datetime widget posts date and time separately.
        return {
            "starts_at_0": starts_at.strftime("%Y-%m-%d"),
            "starts_at_1": starts_at.strftime("%H:%M:%S"),
            "ends_at_0": ends_at.strftime("%Y-%m-%d"),
            "ends_at_1": ends_at.strftime("%H:%M:%S"),
            "message": "Database upgrade.",
        }

    def _notices(self):
        return Notification.objects.filter(
            notification_type=NotificationType.MAINTENANCE_NOTICE
        )

    def test_adding_a_window_schedules_and_notifies_once(self):
        starts = timezone.now() + timedelta(hours=72)

        response = self.client.post(
            ADD_URL, self._post_data(starts, starts + timedelta(hours=2))
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(MaintenanceWindow.objects.count(), 1)
        window = MaintenanceWindow.objects.get()
        self.assertIsNotNone(window.notified_at)
        self.assertEqual(window.created_by, self.superuser)
        self.assertEqual(self._notices().count(), 2)

    def test_a_window_inside_24_hours_is_refused_with_nothing_created(self):
        starts = timezone.now() + timedelta(hours=3)

        response = self.client.post(
            ADD_URL, self._post_data(starts, starts + timedelta(hours=1))
        )

        # A re-rendered form (200), not a redirect: the refusal is displayed,
        # not silent.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MaintenanceWindow.objects.count(), 0)
        self.assertEqual(self._notices().count(), 0)

    def test_windows_cannot_be_edited(self):
        starts = timezone.now() + timedelta(hours=72)
        window = MaintenanceWindow.objects.create(
            starts_at=starts, ends_at=starts + timedelta(hours=1),
            notified_at=timezone.now(),
        )
        url = f"/admin/notifications/maintenancewindow/{window.pk}/change/"

        # Viewing is allowed; saving the edit is refused. Editing a notified
        # window would move downtime without re-notifying.
        self.assertEqual(self.client.get(url).status_code, 200)

        new_starts = timezone.now() + timedelta(hours=96)
        response = self.client.post(url, self._post_data(
            new_starts, new_starts + timedelta(hours=1)
        ))

        self.assertEqual(response.status_code, 403)
        window.refresh_from_db()
        self.assertEqual(window.starts_at, starts)
        self.assertEqual(MaintenanceWindow.objects.count(), 1)
        self.assertEqual(self._notices().count(), 0)

    def test_windows_cannot_be_deleted(self):
        starts = timezone.now() + timedelta(hours=72)
        window = MaintenanceWindow.objects.create(
            starts_at=starts, ends_at=starts + timedelta(hours=1),
            notified_at=timezone.now(),
        )

        response = self.client.get(
            f"/admin/notifications/maintenancewindow/{window.pk}/delete/"
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            MaintenanceWindow.objects.filter(pk=window.pk).exists()
        )
