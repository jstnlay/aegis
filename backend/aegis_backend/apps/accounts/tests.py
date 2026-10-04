"""
Phase 1 test suite for AEGIS accounts.

Covers: user creation, password hashing, role choices, JWT login,
role permission classes, parent/student relationships, SEC-001
self-service privilege escalation, SEC-002 auth throttling, and
SEC-003 logout / refresh-token revocation.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from pathlib import Path
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from unittest import mock
import os
import re
import subprocess
import sys

from apps.accounts.models import (
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
)
from core.throttling import LoginRateThrottle, TokenRefreshRateThrottle

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


# ---------------------------------------------------------------------------
# SEC-001 regression tests: self-service privilege escalation
# ---------------------------------------------------------------------------


class SEC001SelfServicePrivilegeEscalationTest(TestCase):
    """
    Regression tests for SEC-001.

    PATCH /api/v1/accounts/me/ must accept only legitimate profile fields.
    role, is_active, email and username are server-controlled and must be
    ignored (and never persisted) when submitted by any authenticated user.
    """

    def setUp(self):
        self.client = APIClient()
        self.me_url = "/api/v1/accounts/me/"
        self.login_url = "/api/v1/auth/login/"
        self.users = {}
        for role in ("student", "parent", "faculty", "guidance"):
            self.users[role] = User.objects.create_user(
                email=f"sec001_{role}@example.com",
                password="pass12345",
                first_name="Sec",
                last_name=role.title(),
                role=role,
            )

    def _authenticate(self, user, password="pass12345"):
        """Log in through the real JWT endpoint to prove end-to-end behavior."""
        response = self.client.post(
            self.login_url,
            {"email": user.email, "password": password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    # A-D: no non-admin role can escalate to admin via PATCH /me/

    def test_student_cannot_self_assign_admin_role(self):
        user = self.users["student"]
        self._authenticate(user)
        response = self.client.patch(self.me_url, {"role": "admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.role, "student")
        self.assertEqual(response.data["role"], "student")

    def test_parent_cannot_self_assign_admin_role(self):
        user = self.users["parent"]
        self._authenticate(user)
        response = self.client.patch(self.me_url, {"role": "admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.role, "parent")
        self.assertEqual(response.data["role"], "parent")

    def test_faculty_cannot_self_assign_admin_role(self):
        user = self.users["faculty"]
        self._authenticate(user)
        response = self.client.patch(self.me_url, {"role": "admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.role, "faculty")
        self.assertEqual(response.data["role"], "faculty")

    def test_guidance_cannot_self_assign_admin_role(self):
        user = self.users["guidance"]
        self._authenticate(user)
        response = self.client.patch(self.me_url, {"role": "admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.role, "guidance")
        self.assertEqual(response.data["role"], "guidance")

    # E: account-state fields cannot be modified by self-service

    def test_cannot_deactivate_own_account_via_me(self):
        user = self.users["student"]
        self._authenticate(user)
        response = self.client.patch(
            self.me_url, {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(response.data["is_active"])

    def test_combined_escalation_payload_is_rejected(self):
        user = self.users["student"]
        self._authenticate(user)
        response = self.client.patch(
            self.me_url,
            {"role": "admin", "is_active": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.role, "student")
        self.assertNotEqual(response.data["role"], "admin")

    def test_cannot_change_login_email_via_me(self):
        user = self.users["student"]
        self._authenticate(user)
        response = self.client.patch(
            self.me_url,
            {
                "email": "hijacked@example.com",
                "first_name": "Still",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.email, "sec001_student@example.com")
        self.assertEqual(user.first_name, "Still")
        self.assertEqual(response.data["email"], "sec001_student@example.com")

    def test_privilege_fields_still_visible_on_get(self):
        """Users may SEE their role/status; they just cannot change them."""
        user = self.users["student"]
        self._authenticate(user)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], user.email)
        self.assertEqual(response.data["role"], "student")
        self.assertIn("is_active", response.data)

    def test_anonymous_patch_denied(self):
        response = self.client.patch(self.me_url, {"role": "admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # F: legitimate self-service profile editing still works

    def test_legitimate_profile_fields_update(self):
        user = self.users["student"]
        self._authenticate(user)
        payload = {
            "first_name": "UpdatedFirst",
            "last_name": "UpdatedLast",
            "phone_number": "+63 917 000 0000",
            "address": "123 Remediation St., Quezon City",
            "language_preference": "en",
        }
        response = self.client.patch(self.me_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        for field, expected in payload.items():
            self.assertEqual(getattr(user, field), expected)
            self.assertEqual(response.data[field], expected)

    def test_profile_edit_survives_with_malicious_fields_present(self):
        """Profile fields persist even when the same request smuggles
        privilege/account-state fields."""
        user = self.users["faculty"]
        self._authenticate(user)
        response = self.client.patch(
            self.me_url,
            {
                "phone_number": "+63 918 111 2222",
                "role": "admin",
                "is_active": False,
                "email": "evil@example.com",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.phone_number, "+63 918 111 2222")
        self.assertEqual(user.role, "faculty")
        self.assertTrue(user.is_active)
        self.assertEqual(user.email, "sec001_faculty@example.com")

    # G: existing administrator paths still work

    def test_admin_can_create_user_with_role_via_api(self):
        admin = User.objects.create_superuser(
            email="sec001_admin@example.com",
            password="adminpass123",
            first_name="Sec",
            last_name="Admin",
        )
        self._authenticate(admin, password="adminpass123")
        response = self.client.post(
            "/api/v1/accounts/users/create/",
            {
                "email": "new_faculty@example.com",
                "username": "",
                "first_name": "New",
                "last_name": "Faculty",
                "role": "faculty",
                "password": "securepass123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(email="new_faculty@example.com")
        self.assertEqual(created.role, "faculty")

    def test_admin_user_list_and_detail_still_work(self):
        admin = User.objects.create_superuser(
            email="sec001_admin2@example.com",
            password="adminpass123",
            first_name="Sec",
            last_name="Admin",
        )
        self._authenticate(admin, password="adminpass123")
        list_response = self.client.get("/api/v1/accounts/users/")
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)

        target = self.users["student"]
        detail_response = self.client.get(f"/api/v1/accounts/users/{target.id}/")
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["role"], "student")


# ---------------------------------------------------------------------------
# SEC-002 regression tests: authentication throttling
# ---------------------------------------------------------------------------


@mock.patch.dict("core.throttling.LoginRateThrottle.THROTTLE_RATES", {"login": "3/min"})
class SEC002AuthThrottlingTest(TestCase):
    """
    Regression tests for SEC-002.

    Login and token refresh are rate-limited per client IP. DRF throttle
    classes bind their rate dicts at import time, so tests tighten them
    via mock.patch.dict on the class attributes; throttle state lives in
    the default cache, which each test clears for determinism.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.login_url = "/api/v1/auth/login/"
        self.refresh_url = "/api/v1/auth/token/refresh/"
        self.user = User.objects.create_user(
            email="sec002@example.com",
            password="pass12345",
            first_name="Sec",
            last_name="Two",
            role="student",
        )

    def tearDown(self):
        cache.clear()

    def _login(self, password, ip="192.0.2.10"):
        return self.client.post(
            self.login_url,
            {"email": self.user.email, "password": password},
            format="json",
            REMOTE_ADDR=ip,
        )

    def test_login_throttled_after_repeated_attempts(self):
        """Three attempts fill the 3/min bucket; the fourth is rejected."""
        for _ in range(3):
            response = self._login("wrong-password")
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        fourth = self._login("wrong-password")
        self.assertEqual(fourth.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_throttled_login_returns_rate_limit_code_and_retry_after(self):
        for _ in range(3):
            self._login("wrong-password")

        blocked = self._login("wrong-password")
        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("Retry-After", blocked)
        self.assertEqual(
            blocked.data["error"]["code"], "RATE_LIMIT_EXCEEDED"
        )

    def test_successful_login_not_blocked_by_other_ips_attempts(self):
        """Bucket exhaustion from one IP must not lock the account itself:
        correct credentials from a different IP still succeed."""
        for _ in range(3):
            self._login("wrong-password", ip="192.0.2.10")
        exhausted = self._login("wrong-password", ip="192.0.2.10")
        self.assertEqual(exhausted.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        response = self._login("pass12345", ip="203.0.113.77")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_legitimate_logins_below_threshold_succeed(self):
        first = self._login("pass12345")
        second = self._login("pass12345")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)

    def test_token_refresh_throttled(self):
        """Each attempt uses a fresh, valid refresh token (rotation
        blacklists used ones, which would 401 before the throttle).
        The bucket is per client IP, so three valid refreshes from one
        IP trip the 2/min cap."""
        refresh_tokens = []
        for _ in range(3):
            login_response = self._login("pass12345")
            self.assertEqual(login_response.status_code, status.HTTP_200_OK)
            refresh_tokens.append(login_response.data["refresh"])

        with mock.patch.dict(
            TokenRefreshRateThrottle.THROTTLE_RATES, {"token_refresh": "2/min"}
        ):
            cache.clear()
            first = self.client.post(
                self.refresh_url,
                {"refresh": refresh_tokens[0]},
                format="json",
                REMOTE_ADDR="192.0.2.10",
            )
            second = self.client.post(
                self.refresh_url,
                {"refresh": refresh_tokens[1]},
                format="json",
                REMOTE_ADDR="192.0.2.10",
            )
            third = self.client.post(
                self.refresh_url,
                {"refresh": refresh_tokens[2]},
                format="json",
                REMOTE_ADDR="192.0.2.10",
            )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(third.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


# ---------------------------------------------------------------------------
# SEC-003 regression tests: logout / refresh-token revocation
# ---------------------------------------------------------------------------


class SEC003LogoutTest(TestCase):
    """
    Regression tests for SEC-003 (logout / refresh-token revocation).

    POST /api/v1/auth/logout/ requires an authenticated user and
    blacklists the caller's own refresh token via the existing
    SimpleJWT blacklist infrastructure. After logout the token can no
    longer be used or rotated; every failure mode returns a generic
    400 without token reflection.
    """

    def setUp(self):
        self.client = APIClient()
        self.login_url = "/api/v1/auth/login/"
        self.logout_url = "/api/v1/auth/logout/"
        self.refresh_url = "/api/v1/auth/token/refresh/"
        self.user = User.objects.create_user(
            email="logout@example.com",
            password="logoutpass123",
            first_name="Log",
            last_name="Out",
            role="student",
        )
        response = self.client.post(
            self.login_url,
            {"email": "logout@example.com", "password": "logoutpass123"},
            format="json",
        )
        self.refresh_token = response.data["refresh"]
        self.access_token = response.data["access"]

    def _authenticate(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")

    def _login(self, email):
        return self.client.post(
            self.login_url,
            {"email": email, "password": "logoutpass123"},
            format="json",
        )

    def test_logout_with_valid_refresh_token_succeeds(self):
        """A. Authenticated user can logout with a valid refresh token."""
        self._authenticate()
        response = self.client.post(
            self.logout_url,
            {"refresh": self.refresh_token},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(BlacklistedToken.objects.exists())

    def test_logout_response_does_not_reflect_token(self):
        """The response must never echo token material back."""
        self._authenticate()
        response = self.client.post(
            self.logout_url,
            {"refresh": self.refresh_token},
            format="json",
        )
        self.assertNotIn(self.refresh_token, str(response.content))
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_refresh_rejected_after_logout(self):
        """B. The logged-out refresh token can no longer be used."""
        self._authenticate()
        logout_response = self.client.post(
            self.logout_url,
            {"refresh": self.refresh_token},
            format="json",
        )
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            self.refresh_url,
            {"refresh": self.refresh_token},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_post_logout_refresh_reports_token_not_valid(self):
        """C. Blacklisted token yields SimpleJWT's standard auth error."""
        self._authenticate()
        self.client.post(self.logout_url, {"refresh": self.refresh_token}, format="json")

        response = self.client.post(
            self.refresh_url,
            {"refresh": self.refresh_token},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        # Project-wide error envelope wraps SimpleJWT's code (see
        # core/exceptions.custom_exception_handler).
        details = response.data["error"]["details"]
        self.assertEqual(details.get("code"), "token_not_valid")

    def test_invalid_signature_token_handled_safely(self):
        """D. A structurally valid but tampered token is rejected safely."""
        self._authenticate()
        tampered = self.refresh_token[:-4] + "AAAA"
        response = self.client.post(
            self.logout_url,
            {"refresh": tampered},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_malformed_tokens_handled_safely(self):
        """E. Malformed payloads never produce a server error."""
        self._authenticate()
        for payload in (
            {},
            {"refresh": ""},
            {"refresh": "not-a-jwt"},
            {"refresh": "a.b.c"},
        ):
            response = self.client.post(self.logout_url, payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_already_blacklisted_token_no_server_error(self):
        """F. Logging out twice with the same token stays safe (no 500),
        and cannot resurrect or duplicate blacklist state."""
        self._authenticate()
        first = self.client.post(
            self.logout_url,
            {"refresh": self.refresh_token},
            format="json",
        )
        second = self.client.post(
            self.logout_url,
            {"refresh": self.refresh_token},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(BlacklistedToken.objects.count(), 1)

    def test_anonymous_logout_rejected_and_revokes_nothing(self):
        """G. Unauthenticated requests are rejected and revoke nothing."""
        response = self.client.post(
            self.logout_url,
            {"refresh": self.refresh_token},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(BlacklistedToken.objects.exists())

        # The token was untouched by the rejected request.
        still_works = self.client.post(
            self.refresh_url,
            {"refresh": self.refresh_token},
            format="json",
        )
        self.assertEqual(still_works.status_code, status.HTTP_200_OK)

    def test_newer_refresh_token_still_works_after_logout(self):
        """H. A newly issued refresh token for the same account survives
        revocation of an older one."""
        other_session = self._login("logout@example.com")
        newer_refresh = other_session.data["refresh"]

        self._authenticate()
        self.client.post(
            self.logout_url,
            {"refresh": self.refresh_token},
            format="json",
        )

        response = self.client.post(
            self.refresh_url,
            {"refresh": newer_refresh},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_other_users_token_cannot_be_revoked(self):
        """Another authenticated user gets the generic rejection for a
        token they do not own, and the target token keeps working."""
        attacker = User.objects.create_user(
            email="attacker@example.com",
            password="logoutpass123",
            first_name="At",
            last_name="Tacker",
            role="student",
        )
        self.assertIsNotNone(attacker)

        attack_response = self._login("attacker@example.com")
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {attack_response.data['access']}"
        )
        response = self.client.post(
            self.logout_url,
            {"refresh": self.refresh_token},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(BlacklistedToken.objects.exists())

        # Victim's session is intact.
        self.client.credentials()
        victim_refresh = self.client.post(
            self.refresh_url,
            {"refresh": self.refresh_token},
            format="json",
        )
        self.assertEqual(victim_refresh.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# SEC-012 regression tests: hardcoded seed password in tracked source
# ---------------------------------------------------------------------------

_SEED_SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts" / "seed_phase7_e2e.py"
)
_ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"
_ROOT_GITIGNORE = Path(__file__).resolve().parents[4] / ".gitignore"
_HARDcoded_PATTERNS = re.compile(
    r'PASSWORD\s*=\s*["\'][^"\']{4,}["\']', re.IGNORECASE
)


class SEC012HardcodedSeedPasswordTest(TestCase):
    """
    Regression tests for SEC-012.

    The Phase 7 E2E seed script must never contain a hardcoded password
    in tracked source code.  The password is read from the
    PHASE7_E2E_PASSWORD environment variable; if absent the script exits
    non-zero without creating any accounts.
    """

    # A — seed script source contains no hardcoded password assignment
    def test_A_seed_script_has_no_hardcoded_password(self):
        source = _SEED_SCRIPT.read_text(encoding="utf-8")
        matches = _HARDcoded_PATTERNS.findall(source)
        self.assertEqual(
            matches, [], f"Hardcoded password patterns found: {matches}"
        )

    # B — missing PHASE7_E2E_PASSWORD fails clearly
    def test_B_missing_env_var_fails(self):
        env = {**os.environ}
        env.pop("PHASE7_E2E_PASSWORD", None)
        env.pop("DJANGO_SETTINGS_MODULE", None)
        result = subprocess.run(
            [sys.executable, str(_SEED_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(_SEED_SCRIPT.parent.parent),
            env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PHASE7_E2E_PASSWORD", result.stdout + result.stderr)

    # C — missing password does not create or partially mutate E2E accounts
    def test_C_missing_password_no_db_mutation(self):
        from apps.accounts.models import StudentProfile

        before = set(
            User.objects.filter(email__startswith="e2e.").values_list(
                "email", flat=True
            )
        )
        env = {**os.environ}
        env.pop("PHASE7_E2E_PASSWORD", None)
        env.pop("DJANGO_SETTINGS_MODULE", None)
        subprocess.run(
            [sys.executable, str(_SEED_SCRIPT)],
            capture_output=True,
            timeout=15,
            cwd=str(_SEED_SCRIPT.parent.parent),
            env=env,
        )
        after = set(
            User.objects.filter(email__startswith="e2e.").values_list(
                "email", flat=True
            )
        )
        self.assertEqual(before, after)

    # D — supplied environment variable is used successfully
    def test_D_supplied_env_var_succeeds(self):
        test_password = "SEC012_Test_Pass_2026!"
        env = {**os.environ}
        env["PHASE7_E2E_PASSWORD"] = test_password
        env.pop("DJANGO_SETTINGS_MODULE", None)
        result = subprocess.run(
            [sys.executable, str(_SEED_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(_SEED_SCRIPT.parent.parent),
            env=env,
        )
        self.assertEqual(
            result.returncode, 0, f"Script failed: {result.stdout} {result.stderr}"
        )
        self.assertIn("SEEDED", result.stdout)

    # E — supplied password is never printed
    def test_E_password_never_printed(self):
        test_password = "SEC012_Secret_NotPrinted!"
        env = {**os.environ}
        env["PHASE7_E2E_PASSWORD"] = test_password
        env.pop("DJANGO_SETTINGS_MODULE", None)
        result = subprocess.run(
            [sys.executable, str(_SEED_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(_SEED_SCRIPT.parent.parent),
            env=env,
        )
        combined = result.stdout + result.stderr
        self.assertNotIn(test_password, combined)

    # F — .env.example contains only a placeholder/non-secret
    def test_F_env_example_has_placeholder_only(self):
        content = _ENV_EXAMPLE.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("PHASE7_E2E_PASSWORD="):
                value = line.split("=", 1)[1]
                self.assertTrue(
                    value.startswith("your-") or value == "",
                    f".env.example value looks like a real secret: {value[:8]}...",
                )
                return
        self.fail("PHASE7_E2E_PASSWORD not found in .env.example")

    # G — real .env remains ignored by Git
    def test_G_env_ignored_by_git(self):
        content = _ROOT_GITIGNORE.read_text(encoding="utf-8")
        self.assertIn(".env", content)

    # H — seed script works end-to-end with env var (subprocess)
    def test_H_seed_script_end_to_end_with_env(self):
        test_password = "SEC012_E2E_EndToEnd!"
        env = {**os.environ}
        env["PHASE7_E2E_PASSWORD"] = test_password
        env.pop("DJANGO_SETTINGS_MODULE", None)
        result = subprocess.run(
            [sys.executable, str(_SEED_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(_SEED_SCRIPT.parent.parent),
            env=env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("e2e.admin@aegis.dev", result.stdout)
        self.assertIn("e2e.student@aegis.dev", result.stdout)

    # I — existing account/authentication behaviour remains intact
    def test_I_account_auth_smoke_test(self):
        from django.test import Client

        client = Client()
        user = User.objects.create_user(
            email="sec012_smoke@example.com",
            password="smokepass123",
            first_name="Smoke",
            last_name="Test",
            role="student",
        )
        self.assertTrue(user.check_password("smokepass123"))
        self.assertFalse(user.check_password("wrong"))
        self.assertEqual(user.role, "student")


# ---------------------------------------------------------------------------
# PH8.7 — Account provisioning onboarding (initial password change)
# ---------------------------------------------------------------------------


class PH87OnboardingTest(TestCase):
    """Tests the PH8.7 provisioned-account onboarding lifecycle.

    A provisioned account authenticates with the temporary credential via
    the existing JWT flow, but every protected route except the
    password-change / logout endpoints is gated until the initial password
    change clears ``must_change_password``.
    """

    def setUp(self):
        self.client = APIClient()
        self.email = "onboarding@example.com"
        self.temp_password = "SeedTemp_2026_Ab1!"
        self.new_password = "NewSecurePass_2026!"
        self.user = User.objects.create_user(
            email=self.email,
            password=self.temp_password,
            first_name="On", last_name="Board", role="student",
        )
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])

    def _login(self, password):
        return self.client.post(
            "/api/v1/auth/login/",
            {"email": self.email, "password": password},
            format="json",
        )

    def test_login_response_includes_must_change_password_flag(self):
        resp = self._login(self.temp_password)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("must_change_password", resp.data)
        self.assertTrue(resp.data["must_change_password"])

    def test_login_flag_false_for_normal_account(self):
        self.user.must_change_password = False
        self.user.save(update_fields=["must_change_password"])
        resp = self._login(self.temp_password)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["must_change_password"])

    def test_flagged_user_is_gated_outside_onboarding_route(self):
        login = self._login(self.temp_password)
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        me = self.client.get("/api/v1/accounts/me/")
        self.assertEqual(me.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_change_correct_flow_clears_flag(self):
        login = self._login(self.temp_password)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        changed = self.client.post(
            "/api/v1/accounts/password/change/",
            {"current_password": self.temp_password, "new_password": self.new_password},
            format="json",
        )
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.temp_password))
        self.assertEqual(self.user.role, "student")

    def test_password_change_wrong_current_rejected(self):
        login = self._login(self.temp_password)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        resp = self.client.post(
            "/api/v1/accounts/password/change/",
            {"current_password": "WrongPass_2026!", "new_password": self.new_password},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)
        self.assertTrue(self.user.check_password(self.temp_password))

    def test_password_change_enforces_validators(self):
        login = self._login(self.temp_password)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        resp = self.client.post(
            "/api/v1/accounts/password/change/",
            {"current_password": self.temp_password, "new_password": "short"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)

    def test_password_change_works_for_normal_account(self):
        self.user.must_change_password = False
        self.user.save(update_fields=["must_change_password"])
        login = self._login(self.temp_password)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        resp = self.client.post(
            "/api/v1/accounts/password/change/",
            {"current_password": self.temp_password, "new_password": self.new_password},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password(self.new_password))

    def test_temporary_credential_never_echoed(self):
        login = self._login(self.temp_password)
        body = str(login.data)
        self.assertNotIn(self.temp_password, body)


# ---------------------------------------------------------------------------
# Administrator authority is role-based, not is_staff-based
# ---------------------------------------------------------------------------
#
# The user-administration endpoints previously used DRF's stock
# ``IsAdminUser``, which gates on ``is_staff``. Every other administrator area
# gates on ``core.permissions.IsAdminUser`` (``role == "admin"``) per NFR-011.
# An account created by ``provision_qa_accounts`` - or by any plain
# ``create_user`` call - has ``is_staff=False``, so the QA administrator was
# rejected with HTTP 403 on the endpoints it is meant to administer.
#
# These tests pin the reconciled contract: authority follows ``role``, the
# ``is_staff``/``is_superuser`` state does not grant or revoke API access, and
# non-administrator roles stay blocked.


def _token_for(user):
    from rest_framework_simplejwt.tokens import RefreshToken

    return str(RefreshToken.for_user(user).access_token)


class AdminRoleAuthorityTest(TestCase):
    """Administrator authority follows ``role``, independent of staff flags."""

    USERS_URL = "/api/v1/accounts/users/"

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="admrole_admin@example.com",
            password="AdminRole_2026!",
            first_name="Role",
            last_name="Admin",
            role="admin",
        )
        self.target = User.objects.create_user(
            email="admrole_target@example.com",
            password="TargetRole_2026!",
            first_name="Role",
            last_name="Target",
            role="student",
        )
        self.faculty = User.objects.create_user(
            email="admrole_faculty@example.com",
            password="FacultyRole_2026!",
            first_name="Role",
            last_name="Faculty",
            role="faculty",
        )
        self.guidance = User.objects.create_user(
            email="admrole_guidance@example.com",
            password="GuidRole_2026!",
            first_name="Role",
            last_name="Guidance",
            role="guidance",
        )
        self.parent = User.objects.create_user(
            email="admrole_parent@example.com",
            password="ParentRole_2026!",
            first_name="Role",
            last_name="Parent",
            role="parent",
        )

    def _as(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token_for(user)}")
        return user

    # -- the reported mismatch ------------------------------------------

    def test_admin_role_without_is_staff_can_list_users(self):
        """The reported defect: role=admin + is_staff=False was HTTP 403."""
        self.assertEqual(self.admin.role, "admin")
        self.assertFalse(self.admin.is_staff)
        self.assertFalse(self.admin.is_superuser)

        self._as(self.admin)
        response = self.client.get(self.USERS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_role_without_is_staff_can_retrieve_a_user(self):
        self._as(self.admin)
        response = self.client.get(f"{self.USERS_URL}{self.target.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "student")

    def test_admin_role_without_is_staff_can_create_a_user(self):
        self._as(self.admin)
        response = self.client.post(
            "/api/v1/accounts/users/create/",
            {
                "email": "admrole_created@example.com",
                "username": "",
                "first_name": "Created",
                "last_name": "Faculty",
                "role": "faculty",
                "password": "CreatedRole_2026!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(email="admrole_created@example.com")
        self.assertEqual(created.role, "faculty")

    # -- the staff-state direction that must NOT grant access ------------

    def test_is_staff_without_admin_role_is_refused(self):
        """is_staff alone must never grant API administrator authority."""
        impostor = User.objects.create_user(
            email="admrole_impostor@example.com",
            password="ImpostorRole_2026!",
            first_name="Im",
            last_name="Postor",
            role="faculty",
        )
        impostor.is_staff = True
        impostor.save(update_fields=["is_staff"])

        self._as(impostor)
        response = self.client.get(self.USERS_URL)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_is_superuser_without_admin_role_is_refused(self):
        """is_superuser is a Django-admin flag, not API authority."""
        impostor = User.objects.create_user(
            email="admrole_super@example.com",
            password="SuperRole_2026!",
            first_name="Sup",
            last_name="Erus",
            role="guidance",
        )
        impostor.is_superuser = True
        impostor.save(update_fields=["is_superuser"])

        self._as(impostor)
        response = self.client.get(self.USERS_URL)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_created_by_manager_is_still_authorized(self):
        """
        ``create_superuser`` sets both is_staff and role='admin'.

        The SEC-001 tests already rely on this shape, so this guards the
        existing administrator path against the permission-class change.
        """
        superuser = User.objects.create_superuser(
            email="admrole_superuser@example.com",
            password="SuperUsrRole_2026!",
            first_name="Super",
            last_name="Admin",
        )
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        self.assertEqual(superuser.role, "admin")

        self._as(superuser)
        response = self.client.get(self.USERS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # -- every other role stays blocked ---------------------------------

    def test_every_non_admin_role_is_refused(self):
        for user in (self.faculty, self.guidance, self.target, self.parent):
            with self.subTest(role=user.role):
                self.client.credentials(
                    HTTP_AUTHORIZATION=f"Bearer {_token_for(user)}"
                )
                response = self.client.get(self.USERS_URL)
                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                    msg=f"{user.role} must not reach {self.USERS_URL}",
                )

    def test_every_non_admin_role_is_refused_on_create(self):
        for user in (self.faculty, self.guidance, self.target, self.parent):
            with self.subTest(role=user.role):
                self.client.credentials(
                    HTTP_AUTHORIZATION=f"Bearer {_token_for(user)}"
                )
                response = self.client.post(
                    "/api/v1/accounts/users/create/",
                    {
                        "email": f"admrole_forbidden_{user.role}@example.com",
                        "username": "",
                        "first_name": "No",
                        "last_name": "Way",
                        "role": "admin",
                        "password": "ForbiddenRole_2026!",
                    },
                    format="json",
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                    msg=f"{user.role} must not create users",
                )
        self.assertFalse(User.objects.filter(role="admin").exclude(pk=self.admin.pk).exists())

    def test_anonymous_is_unauthenticated(self):
        self.client.credentials()
        response = self.client.get(self.USERS_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # -- consistency with the other administrator areas -----------------

    def test_same_admin_passes_the_other_role_gated_areas(self):
        """
        One administrator identity must satisfy every administrator gate.

        ``core.permissions.IsAdminUser`` is what the academics, analytics and
        audit areas use, so both gates must agree on the same account.
        """
        from core.permissions import IsAdminUser as RoleIsAdminUser

        class MockRequest:
            def __init__(self, user):
                self.user = user

        self.assertTrue(
            RoleIsAdminUser().has_permission(MockRequest(self.admin), None)
        )

        # A non-admin must fail that same class, so the agreement above is
        # real authority rather than a permissive no-op.
        for user in (self.faculty, self.guidance, self.target, self.parent):
            with self.subTest(role=user.role):
                self.assertFalse(
                    RoleIsAdminUser().has_permission(MockRequest(user), None)
                )

    def test_inactive_admin_is_refused_by_the_authentication_layer(self):
        """is_active is enforced by AegisJWTAuthentication, not by this gate."""
        self.admin.is_active = False
        self.admin.save(update_fields=["is_active"])

        token = _token_for(self.admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(self.USERS_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
