"""
Phase 1 test suite for AEGIS accounts.

Covers: user creation, password hashing, role choices, JWT login,
role permission classes, and parent/student relationships.
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

User = get_user_model()


# ---------------------------------------------------------------------------
# User model tests
# ---------------------------------------------------------------------------


class UserCreationTest(TestCase):
    """Test that users can be created with the correct fields."""

    def test_create_user_with_email(self):
        user = User.objects.create_user(
            email="test@example.com",
            password="securepass123",
            first_name="Jane",
            last_name="Doe",
            role="student",
        )
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "Jane")
        self.assertEqual(user.role, "student")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)

    def test_create_superuser(self):
        admin = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
            role="admin",
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_user_str_representation(self):
        user = User.objects.create_user(
            email="str@example.com",
            password="pass12345",
            first_name="Juan",
            last_name="Dela Cruz",
            role="faculty",
        )
        self.assertIn("Juan Dela Cruz", str(user))
        self.assertIn("Faculty", str(user))

    def test_uuid_primary_key(self):
        user = User.objects.create_user(
            email="uuid@example.com",
            password="pass12345",
            first_name="UUID",
            last_name="Test",
            role="student",
        )
        self.assertIsNotNone(user.id)
        self.assertEqual(len(str(user.id)), 36)  # UUID format


class PasswordHashingTest(TestCase):
    """Verify passwords are never stored in plaintext."""

    def test_password_is_hashed(self):
        user = User.objects.create_user(
            email="hash@example.com",
            password="mypassword123",
            first_name="Hash",
            last_name="Test",
            role="student",
        )
        self.assertNotEqual(user.password, "mypassword123")
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))

    def test_password_check_works(self):
        user = User.objects.create_user(
            email="check@example.com",
            password="correcthorse",
            first_name="Check",
            last_name="Test",
            role="student",
        )
        self.assertTrue(user.check_password("correcthorse"))
        self.assertFalse(user.check_password("wrongpassword"))


class RoleChoicesTest(TestCase):
    """Verify all expected roles are defined."""

    def test_all_roles_exist(self):
        expected_roles = {"student", "parent", "faculty", "guidance", "admin"}
        actual_roles = {choice[0] for choice in User.Role.choices}
        self.assertEqual(actual_roles, expected_roles)

    def test_role_max_length(self):
        field = User._meta.get_field("role")
        self.assertEqual(field.max_length, 20)

    def test_role_field_has_choices(self):
        field = User._meta.get_field("role")
        self.assertEqual(len(field.choices), 5)


# ---------------------------------------------------------------------------
# JWT authentication tests
# ---------------------------------------------------------------------------


class JWTLoginTest(TestCase):
    """Test JWT token obtain and refresh endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="jwt@example.com",
            password="jwtpass123",
            first_name="JWT",
            last_name="Test",
            role="student",
        )
        self.login_url = "/api/v1/auth/login/"
        self.refresh_url = "/api/v1/auth/token/refresh/"

    def test_login_returns_tokens(self):
        response = self.client.post(
            self.login_url,
            {"email": "jwt@example.com", "password": "jwtpass123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_with_wrong_password(self):
        response = self.client.post(
            self.login_url,
            {"email": "jwt@example.com", "password": "wrongpassword"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_with_nonexistent_user(self):
        response = self.client.post(
            self.login_url,
            {"email": "nobody@example.com", "password": "pass12345"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_refresh(self):
        login_response = self.client.post(
            self.login_url,
            {"email": "jwt@example.com", "password": "jwtpass123"},
            format="json",
        )
        refresh_token = login_response.data["refresh"]

        response = self.client.post(
            self.refresh_url,
            {"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_access_protected_endpoint_with_token(self):
        login_response = self.client.post(
            self.login_url,
            {"email": "jwt@example.com", "password": "jwtpass123"},
            format="json",
        )
        access_token = login_response.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = self.client.get("/api/v1/accounts/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "jwt@example.com")

    def test_access_protected_endpoint_without_token(self):
        response = self.client.get("/api/v1/accounts/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Permission class tests
# ---------------------------------------------------------------------------


class PermissionClassesTest(TestCase):
    """Test role-based permission classes."""

    def setUp(self):
        self.student = User.objects.create_user(
            email="perm_student@example.com",
            password="pass12345",
            first_name="Perm",
            last_name="Student",
            role="student",
        )
        self.faculty = User.objects.create_user(
            email="perm_faculty@example.com",
            password="pass12345",
            first_name="Perm",
            last_name="Faculty",
            role="faculty",
        )
        self.admin = User.objects.create_user(
            email="perm_admin@example.com",
            password="pass12345",
            first_name="Perm",
            last_name="Admin",
            role="admin",
        )

    @staticmethod
    def _mock_request(user):
        class MockRequest:
            def __init__(self, u):
                self.user = u
        return MockRequest(user)

    def test_is_student_user(self):
        from core.permissions import IsStudentUser

        perm = IsStudentUser()
        self.assertTrue(perm.has_permission(self._mock_request(self.student), None))
        self.assertFalse(perm.has_permission(self._mock_request(self.faculty), None))

    def test_is_faculty_user(self):
        from core.permissions import IsFacultyUser

        perm = IsFacultyUser()
        self.assertTrue(perm.has_permission(self._mock_request(self.faculty), None))
        self.assertFalse(perm.has_permission(self._mock_request(self.student), None))

    def test_is_admin_user(self):
        from core.permissions import IsAdminUser

        perm = IsAdminUser()
        self.assertTrue(perm.has_permission(self._mock_request(self.admin), None))
        self.assertFalse(perm.has_permission(self._mock_request(self.student), None))

    def test_is_parent_user(self):
        from core.permissions import IsParentUser

        perm = IsParentUser()
        parent = User.objects.create_user(
            email="perm_parent@example.com",
            password="pass12345",
            first_name="Perm",
            last_name="Parent",
            role="parent",
        )
        self.assertTrue(perm.has_permission(self._mock_request(parent), None))
        self.assertFalse(perm.has_permission(self._mock_request(self.student), None))

    def test_is_guidance_user(self):
        from core.permissions import IsGuidanceUser

        perm = IsGuidanceUser()
        guidance = User.objects.create_user(
            email="perm_guidance@example.com",
            password="pass12345",
            first_name="Perm",
            last_name="Guidance",
            role="guidance",
        )
        self.assertTrue(perm.has_permission(self._mock_request(guidance), None))
        self.assertFalse(perm.has_permission(self._mock_request(self.student), None))

    def test_is_staff_or_admin(self):
        from core.permissions import IsStaffOrAdmin

        perm = IsStaffOrAdmin()
        self.assertTrue(perm.has_permission(self._mock_request(self.faculty), None))
        self.assertTrue(perm.has_permission(self._mock_request(self.admin), None))
        self.assertFalse(perm.has_permission(self._mock_request(self.student), None))

    def test_unauthenticated_user_denied(self):
        from core.permissions import IsAdminUser, IsStudentUser

        class AnonymousRequest:
            user = type("AnonymousUser", (), {"is_authenticated": False})()

        perm = IsAdminUser()
        self.assertFalse(perm.has_permission(AnonymousRequest(), None))
        perm = IsStudentUser()
        self.assertFalse(perm.has_permission(AnonymousRequest(), None))


# ---------------------------------------------------------------------------
# Parent / Student relationship tests
# ---------------------------------------------------------------------------


class ParentStudentRelationshipTest(TestCase):
    """Test parent-student profile creation and linking."""

    def setUp(self):
        self.parent_user = User.objects.create_user(
            email="parent_rel@example.com",
            password="pass12345",
            first_name="Parent",
            last_name="RelTest",
            role="parent",
        )
        self.student_user = User.objects.create_user(
            email="student_rel@example.com",
            password="pass12345",
            first_name="Student",
            last_name="RelTest",
            role="student",
        )

    def test_create_parent_profile(self):
        profile = ParentProfile.objects.create(
            user=self.parent_user,
            relationship_to_student="mother",
        )
        self.assertEqual(profile.user, self.parent_user)
        self.assertEqual(profile.relationship_to_student, "mother")

    def test_create_student_profile(self):
        profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="STU-001",
            enrollment_date="2025-06-01",
        )
        self.assertEqual(profile.user, self.student_user)
        self.assertEqual(profile.student_id, "STU-001")
        self.assertTrue(profile.is_active)

    def test_parent_student_link(self):
        parent_profile = ParentProfile.objects.create(
            user=self.parent_user,
            relationship_to_student="father",
        )
        student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="STU-002",
            enrollment_date="2025-06-01",
        )
        link = ParentStudentLink.objects.create(
            parent=parent_profile,
            student=student_profile,
            is_primary=True,
        )
        self.assertTrue(link.is_primary)
        self.assertEqual(link.parent, parent_profile)
        self.assertEqual(link.student, student_profile)

    def test_parent_student_link_str(self):
        parent_profile = ParentProfile.objects.create(
            user=self.parent_user,
            relationship_to_student="guardian",
        )
        student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="STU-003",
            enrollment_date="2025-06-01",
        )
        link = ParentStudentLink.objects.create(
            parent=parent_profile,
            student=student_profile,
        )
        self.assertIn("->", str(link))

    def test_unique_parent_student_constraint(self):
        parent_profile = ParentProfile.objects.create(
            user=self.parent_user,
            relationship_to_student="mother",
        )
        student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="STU-004",
            enrollment_date="2025-06-01",
        )
        ParentStudentLink.objects.create(
            parent=parent_profile,
            student=student_profile,
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            ParentStudentLink.objects.create(
                parent=parent_profile,
                student=student_profile,
            )

    def test_parent_profile_relationship_choices(self):
        expected = {"mother", "father", "guardian", "other"}
        actual = {c[0] for c in ParentProfile.RelationshipType.choices}
        self.assertEqual(actual, expected)
