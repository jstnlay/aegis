"""
TC-ADM-17 re-test — the Cycle-3 log's actual result was:

    PASSED – *But, Could not verify if explicit consent is given

The row's condition is: "an Admin without explicit consent can only view student
data in aggregated or anonymized form", expected "System restricts the view to
aggregated/anonymized data only and does not expose individually identifiable
student records."

The mechanism exists at HEAD: `ConsentRecord` (accounts/models.py) with its
active() manager, the admin-only `ConsentRecordView` / `ConsentRevokeView`, the
admin screen and the Django admin, and the redaction in
`GradeSerializer.to_representation` driven by `GradeViewSet.get_serializer_context`.

What the log could not verify is the *link*: that granting consent is what
flips the view from withheld to identifiable. The pre-existing tests in
`academics/tests.py::AdminGradesAnonymizationTest` create `ConsentRecord` rows
directly through the ORM, so they prove the redaction reads the table but never
that the consent API - the thing a family actually touches - is wired to it.

This file closes that gap end to end, over HTTP only:

    parent POSTs /consent-records/  ->  admin GET /grades/ now shows a name
    admin PATCHes /consent-records/{id}/revoke/  ->  admin GET /grades/ withholds

It is a re-test, not new behaviour: no production code changed.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    AdminProfile,
    ConsentRecord,
    ParentProfile,
    ParentStudentLink,
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

WITHHELD_NAME = "Name withheld — no family consent"
WITHHELD_ID = "ID withheld — no family consent"


class _Adm17Base(TestCase):
    """One student with an enrolled grade, one linked parent, one admin."""

    def setUp(self):
        self.ay = AcademicYear.objects.create(
            name="2025-2026", start_date="2025-06-01", end_date="2026-03-31",
            is_current=True,
        )
        self.g7 = GradeLevel.objects.create(name="Grade 7", level_number=7)
        self.section = Section.objects.create(
            name="S-ADM17", grade_level=self.g7, academic_year=self.ay
        )
        self.subject = Subject.objects.create(
            name="Math 7", code="M17", grade_level=self.g7
        )
        self.gp = GradingPeriod.objects.create(
            academic_year=self.ay, name="Term 1", order=1,
            start_date="2025-06-01", end_date="2025-08-31",
        )

        self.admin_user = User.objects.create_user(
            email="admin_adm17@test.com", password="pass12345",
            first_name="Ada", last_name="Min", role="admin",
        )
        AdminProfile.objects.create(user=self.admin_user, admin_level="school_admin")
        self.faculty_user = User.objects.create_user(
            email="fac_adm17@test.com", password="pass12345",
            first_name="Fay", last_name="Culty", role="faculty",
        )
        from apps.accounts.models import FacultyProfile

        self.faculty = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="EMP-ADM17-001"
        )
        self.student_user = User.objects.create_user(
            email="stu_adm17@test.com", password="pass12345",
            first_name="Nina", last_name="Reyes", role="student",
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user, student_id="STU-ADM17-001",
            grade_level=self.g7, section=self.section,
            enrollment_date="2025-06-01",
        )
        self.parent_user = User.objects.create_user(
            email="par_adm17@test.com", password="pass12345",
            first_name="Pia", last_name="Reyes", role="parent",
        )
        self.parent = ParentProfile.objects.create(
            user=self.parent_user, relationship_to_student="mother",
        )
        ParentStudentLink.objects.create(
            parent=self.parent, student=self.student, is_primary=True,
        )

        self.sa = SubjectAssignment.objects.create(
            subject=self.subject, section=self.section,
            faculty=self.faculty, academic_year=self.ay,
        )
        # SEC-013: Grade.full_clean() requires an enrollment for the grade's
        # section and academic year, so the fixture must create one.
        Enrollment.objects.create(
            student=self.student, section=self.section, academic_year=self.ay,
            date_enrolled="2025-06-01",
        )
        self.grade = Grade.objects.create(
            student=self.student, subject_assignment=self.sa,
            grading_period=self.gp, score=Decimal("88.50"),
            encoded_by=self.faculty, status="submitted",
        )

    def _row_for_grade(self, client, url):
        resp = client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        rows = resp.data.get("results", [resp.data])
        return next(r for r in rows if r["id"] == str(self.grade.pk))

    def _as(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client


class Adm17ConsentApiDrivesAnonymizationTest(_Adm17Base):
    """
    The end-to-end claim the log could not confirm: explicit consent, granted
    through the consent API, is what decides whether the admin sees identity.
    """

    def test_admin_without_consent_sees_only_anonymized_data(self):
        row = self._row_for_grade(
            self._as(self.admin_user), "/api/v1/academics/grades/"
        )
        self.assertEqual(row["student_name"], WITHHELD_NAME)
        self.assertEqual(row["student_id"], WITHHELD_ID)
        self.assertIsNone(row["student"])
        self.assertFalse(row["family_consent_on_file"])

    def test_parent_granting_consent_flips_the_admin_view(self):
        """The parent POSTs the consent; the admin then reads the name."""
        before = self._row_for_grade(
            self._as(self.admin_user), "/api/v1/academics/grades/"
        )
        self.assertFalse(before["family_consent_on_file"])

        created = self._as(self.parent_user).post(
            "/api/v1/accounts/consents/",
            {"student": str(self.student.id)},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.content)
        # The record names who actually granted it, server-side.
        self.assertEqual(
            created.data["granted_by_email"], self.parent_user.email
        )
        self.assertTrue(created.data["is_active"])

        after = self._row_for_grade(
            self._as(self.admin_user), "/api/v1/academics/grades/"
        )
        self.assertEqual(after["student_name"], "Nina Reyes")
        self.assertEqual(after["student_id"], "STU-ADM17-001")
        self.assertTrue(after["family_consent_on_file"])

    def test_revoking_through_the_api_restores_withholding(self):
        created = self._as(self.parent_user).post(
            "/api/v1/accounts/consents/",
            {"student": str(self.student.id)},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        revoked = self._as(self.parent_user).patch(
            f"/api/v1/accounts/consents/{created.data['id']}/revoke/",
            {},
            format="json",
        )
        self.assertEqual(revoked.status_code, status.HTTP_200_OK, revoked.content)

        row = self._row_for_grade(
            self._as(self.admin_user), "/api/v1/academics/grades/"
        )
        self.assertEqual(row["student_name"], WITHHELD_NAME)
        self.assertFalse(row["family_consent_on_file"])
        # Revocation closes the row rather than deleting it, so the history
        # still answers "who permitted what, when".
        self.assertEqual(ConsentRecord.objects.filter(student=self.student).count(), 1)

    def test_a_parent_cannot_consent_for_a_child_that_is_not_theirs(self):
        """
        The grant must be scoped, or "consent was given" would mean nothing.
        """
        stranger_user = User.objects.create_user(
            email="par_stranger_adm17@test.com", password="pass12345",
            first_name="Not", last_name="Linked", role="parent",
        )
        ParentProfile.objects.create(
            user=stranger_user, relationship_to_student="guardian",
        )

        resp = self._as(stranger_user).post(
            "/api/v1/accounts/consents/",
            {"student": str(self.student.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertFalse(
            ConsentRecord.objects.filter(student=self.student).exists()
        )
        # And the admin still sees nothing.
        row = self._row_for_grade(
            self._as(self.admin_user), "/api/v1/academics/grades/"
        )
        self.assertEqual(row["student_name"], WITHHELD_NAME)

    def test_a_student_cannot_create_a_consent_for_themselves(self):
        """Consent is the family's to give, not the student's."""
        resp = self._as(self.student_user).post(
            "/api/v1/accounts/consents/",
            {"student": str(self.student.id)},
            format="json",
        )
        self.assertIn(
            resp.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED),
            resp.content,
        )
        self.assertFalse(
            ConsentRecord.objects.filter(student=self.student).exists()
        )


class Adm17NonAdminScopeIsUnchangedTest(_Adm17Base):
    """
    NFR-010 names the administrator. A faculty member reading their own class
    keeps their scope, and never learns whether consent is on file.
    """

    def test_faculty_still_reads_their_own_students_identity(self):
        row = self._row_for_grade(
            self._as(self.faculty_user), "/api/v1/academics/grades/"
        )
        self.assertEqual(row["student_name"], "Nina Reyes")
        self.assertNotIn("family_consent_on_file", row)

    def test_anonymized_means_identity_not_the_oversight_itself(self):
        """The admin still sees the grade, score and subject."""
        row = self._row_for_grade(
            self._as(self.admin_user),
            f"/api/v1/academics/grades/{self.grade.pk}/",
        )
        self.assertEqual(row["score"], "88.50")
        self.assertEqual(row["status"], "submitted")
        self.assertTrue(row["subject_name"])
