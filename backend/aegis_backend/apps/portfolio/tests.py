"""
Portfolio entry tests.

Students own their rows; linked parents, staff and administrators read
them. Nothing here invents file storage: entries are text plus an optional
link URL, because this host has no persistent disk.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
)
from apps.portfolio.models import PortfolioEntry

User = get_user_model()

BASE = "/api/v1/portfolio/entries/"


def make_user(email, role):
    return User.objects.create_user(
        email=email,
        password="pass12345",
        first_name="Test",
        last_name=role.capitalize(),
        role=role,
    )


class PortfolioEntryTest(TestCase):
    def setUp(self):
        self.student_user = make_user("pf-student@test.com", "student")
        self.other_student_user = make_user("pf-other@test.com", "student")
        self.parent_user = make_user("pf-parent@test.com", "parent")
        self.faculty_user = make_user("pf-faculty@test.com", "faculty")
        self.admin_user = make_user("pf-admin@test.com", "admin")

        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="STU-PF-001",
            enrollment_date="2025-06-01",
        )
        self.other_profile = StudentProfile.objects.create(
            user=self.other_student_user,
            student_id="STU-PF-002",
            enrollment_date="2025-06-01",
        )
        parent_profile = ParentProfile.objects.create(
            user=self.parent_user, relationship_to_student="mother"
        )
        ParentStudentLink.objects.create(
            parent=parent_profile, student=self.student_profile, is_primary=True
        )

    def _client(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def test_anonymous_is_refused(self):
        response = self._client().get(BASE)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_student_creates_entry_on_own_profile(self):
        response = self._client(self.student_user).post(
            BASE,
            {
                "title": "Science investigatory project",
                "activity_type": "project",
                "description": "Water filtration prototype.",
                "link_url": "https://example.com/work",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        entry = PortfolioEntry.objects.get()
        self.assertEqual(entry.student, self.student_profile)
        self.assertEqual(entry.title, "Science investigatory project")

    def test_student_cannot_claim_another_profile(self):
        # `student` is read-only: even a forged id lands on the caller's row.
        response = self._client(self.student_user).post(
            BASE,
            {"title": "My work", "student": str(self.other_profile.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        entry = PortfolioEntry.objects.get()
        self.assertEqual(entry.student, self.student_profile)

    def test_blank_title_is_rejected(self):
        response = self._client(self.student_user).post(
            BASE, {"title": "   "}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_student_sees_nothing_and_cannot_edit(self):
        entry = PortfolioEntry.objects.create(
            student=self.student_profile, title="My work"
        )
        other = self._client(self.other_student_user)
        response = other.get(BASE)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"], [])
        # Outside the caller's queryset, so the row is not addressable.
        self.assertEqual(
            other.patch(f"{BASE}{entry.id}/", {"title": "Taken"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            other.delete(f"{BASE}{entry.id}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_owning_student_can_edit_and_delete(self):
        entry = PortfolioEntry.objects.create(
            student=self.student_profile, title="Draft title"
        )
        mine = self._client(self.student_user)
        response = mine.patch(
            f"{BASE}{entry.id}/", {"title": "Final title"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry.refresh_from_db()
        self.assertEqual(entry.title, "Final title")
        self.assertEqual(
            mine.delete(f"{BASE}{entry.id}/").status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertEqual(PortfolioEntry.objects.count(), 0)

    def test_linked_parent_reads_but_cannot_write(self):
        PortfolioEntry.objects.create(
            student=self.student_profile, title="My work"
        )
        parent = self._client(self.parent_user)
        response = parent.get(BASE)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(
            parent.post(BASE, {"title": "Parent post"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_faculty_and_admin_read_but_cannot_write(self):
        entry = PortfolioEntry.objects.create(
            student=self.student_profile, title="My work"
        )
        for user in (self.faculty_user, self.admin_user):
            client = self._client(user)
            response = client.get(BASE)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data["results"]), 1)
            self.assertEqual(
                client.post(BASE, {"title": "Staff post"}, format="json").status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                client.patch(
                    f"{BASE}{entry.id}/", {"title": "Staff edit"}, format="json"
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                client.delete(f"{BASE}{entry.id}/").status_code,
                status.HTTP_403_FORBIDDEN,
            )

    def test_student_filter_by_student_id(self):
        PortfolioEntry.objects.create(
            student=self.student_profile, title="Mine"
        )
        PortfolioEntry.objects.create(
            student=self.other_profile, title="Theirs"
        )
        response = self._client(self.faculty_user).get(
            f"{BASE}?student={self.student_profile.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["title"] for item in response.data["results"]], ["Mine"]
        )
