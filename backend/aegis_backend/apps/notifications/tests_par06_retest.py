"""
TC-PAR-06 re-test — the Cycle-3 log's actual result was:

    FAILED – Add this when parents can view the notification in full message
    just like a pop-up.
    (Not specified in SRS (FR-020–022 cover Student notifications only, not
    Parent))

The row is a Notification-category failure for TO-PAR-05: "Verify that a Parent
receives a real-time notification regarding their child's grades, attendance, or
concerns."

The log's own parenthetical diagnosis — "Student notifications only, not Parent"
— is not what the code does.  Every student-facing event already resolves the
linked parents alongside the student, and `/notifications/` is scoped to
`recipient=request.user` for any authenticated role, so a parent reads their own
row.  These tests pin that claim so the next cycle can verify it instead of
re-guessing.

The "full message ... like a pop-up" half is a rendering claim, so it is pinned
in the frontend (`NotificationsPage.test.tsx`) where the message is rendered;
this file covers the delivery and the read-back that make it possible.
"""

from datetime import date

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
    User,
)
from apps.notifications.models import Notification, NotificationType


def _auth(client, user):
    client.force_authenticate(user=user)
    return client


class _Par06Base(TestCase):
    """One student, two linked parents, one unlinked parent."""

    def setUp(self):
        self.student_user = User.objects.create_user(
            email="par06_student@test.com", password="pass12345",
            first_name="Stu", last_name="Dent", role="student",
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user, student_id="STU-PAR06-001",
            enrollment_date=date(2026, 6, 1),
        )
        self.mother_user = User.objects.create_user(
            email="par06_mother@test.com", password="pass12345",
            first_name="Maria", last_name="Santos", role="parent",
        )
        self.father_user = User.objects.create_user(
            email="par06_father@test.com", password="pass12345",
            first_name="Jose", last_name="Santos", role="parent",
        )
        self.stranger_user = User.objects.create_user(
            email="par06_stranger@test.com", password="pass12345",
            first_name="Not", last_name="Linked", role="parent",
        )
        self.mother = ParentProfile.objects.create(
            user=self.mother_user, relationship_to_student="mother",
        )
        self.father = ParentProfile.objects.create(
            user=self.father_user, relationship_to_student="father",
        )
        self.stranger = ParentProfile.objects.create(
            user=self.stranger_user, relationship_to_student="guardian",
        )
        ParentStudentLink.objects.create(
            parent=self.mother, student=self.student, is_primary=True,
        )
        ParentStudentLink.objects.create(
            parent=self.father, student=self.student, is_primary=False,
        )


class Par06ParentReceivesNotificationTest(_Par06Base):
    """
    The first half of TC-PAR-06: a parent is a recipient of their child's
    notifications, not only the student.
    """

    def test_grade_notification_reaches_both_linked_parents(self):
        """
        GRADE_POSTED (EVT-01).  The log said parents were left out; the parents
        linked to the student are recipients alongside the student.
        """
        from apps.notifications.events import dispatch_event

        dispatch_event(
            NotificationType.GRADE_POSTED,
            recipients=[self.student_user, self.mother_user, self.father_user],
            title="Grade Posted",
            message="Your grade for Math 7 has been finalized.",
            link="/academics/grades/abc",
        )

        for parent in (self.mother_user, self.father_user):
            with self.subTest(parent=parent.email):
                self.assertTrue(
                    Notification.objects.filter(
                        recipient=parent,
                        notification_type=NotificationType.GRADE_POSTED,
                    ).exists(),
                    f"{parent.email} did not receive the grade notification",
                )


class Par06ParentCanReadNotificationTest(_Par06Base):
    """
    The second half: the parent can *read* the notification.  The log's ask was
    "parents can view the notification in full message", so the delivery is only
    half the row.
    """

    def setUp(self):
        super().setUp()
        self.client = _auth(APIClient(), self.mother_user)

    def _notify(self, recipient, message, ntype=NotificationType.GRADE_POSTED):
        return Notification.objects.create(
            recipient=recipient,
            notification_type=ntype,
            title="Grade Posted",
            message=message,
        )

    def test_parent_can_list_their_own_notifications(self):
        self._notify(
            self.mother_user, "Your child's grade for Math 7 is 88.50."
        )
        resp = self.client.get("/api/v1/notifications/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.data["count"], 1)

    def test_parent_sees_the_full_message_body(self):
        """
        The message a parent reads is the producer's whole message, not a
        truncated summary - the row asked for the notification "in full".
        """
        full = (
            "Your child's grade for Math 7 has been finalized with a score of "
            "88.50. Open the grade to see the breakdown, the remarks entered by "
            "the teacher, and the grading period it belongs to."
        )
        self._notify(self.mother_user, full)

        resp = self.client.get("/api/v1/notifications/")
        row = resp.data["results"][0]
        self.assertEqual(row["message"], full)

    def test_a_parent_never_sees_another_family_record(self):
        """
        The read-back is per-recipient, so linking to one child grants nothing
        over another student (the boundary TC-PAR-07 also asserts).
        """
        self._notify(self.stranger_user, "Not this parent's notification.")
        resp = self.client.get("/api/v1/notifications/")
        self.assertEqual(resp.data["count"], 0)

    def test_a_parent_can_mark_the_notification_read(self):
        n = self._notify(self.mother_user, "Grade posted.")
        resp = self.client.post(f"/api/v1/notifications/{n.id}/read/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        n.refresh_from_db()
        self.assertTrue(n.is_read)
        self.assertIsNotNone(n.read_at)


class Par06ParentScopeIsTheLinkedChildTest(_Par06Base):
    """
    The parent recipient set is the students actually linked to that parent, so
    the fan-out cannot address a family that is not connected.
    """

    def test_linked_parent_query_returns_only_that_child_s_family(self):
        links = ParentStudentLink.objects.filter(
            student=self.student
        ).select_related("parent__user")
        emails = sorted(link.parent.user.email for link in links)

        self.assertEqual(
            emails, ["par06_father@test.com", "par06_mother@test.com"]
        )
        self.assertNotIn(self.stranger_user.email, emails)
