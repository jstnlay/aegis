"""
Phase 1 test suite for AEGIS accounts.

Covers: user creation, password hashing, role choices, JWT login,
role permission classes, parent/student relationships, SEC-001
self-service privilege escalation, SEC-002 auth throttling, and
SEC-003 logout / refresh-token revocation.
"""

import hashlib
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
    FacultyProfile,
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

    def _refresh_lifetime_seconds(self, refresh_token):
        """Seconds until the refresh token expires, from its own claim."""
        import time

        from rest_framework_simplejwt.tokens import RefreshToken

        payload = RefreshToken(refresh_token).payload
        return int(payload["exp"] - time.time())

    def test_idle_session_ends_after_fifteen_minutes(self):
        """
        Without "remember me" the session is idle-bounded.

        The access token and the refresh token both live 15 minutes, so a
        browser left alone is signed out after a quarter of an hour and
        cannot be replayed afterwards.
        """
        response = self.client.post(
            self.login_url,
            {"email": "jwt@example.com", "password": "jwtpass123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["remember_me"])

        lifetime = self._refresh_lifetime_seconds(response.data["refresh"])
        self.assertLessEqual(lifetime, 15 * 60)
        self.assertGreater(lifetime, 14 * 60)

    def test_remember_me_extends_the_refresh_token_to_one_day(self):
        """
        With "remember me" the refresh token lives a day.

        The access token is untouched: a long session must never mean a
        long-lived access token.
        """
        response = self.client.post(
            self.login_url,
            {
                "email": "jwt@example.com",
                "password": "jwtpass123",
                "remember_me": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["remember_me"])

        lifetime = self._refresh_lifetime_seconds(response.data["refresh"])
        self.assertGreater(lifetime, 23 * 3600)
        self.assertLessEqual(lifetime, 24 * 3600)

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


@mock.patch.dict(
    "core.throttling.PasswordChangeRateThrottle.THROTTLE_RATES",
    {"password_change": "3/min"},
)
class SEC002PasswordChangeThrottlingTest(TestCase):
    """
    Regression tests for the password-change rate limit (SEC-002 family).

    The endpoint verifies the current password, so an unauthenticated
    caller cannot reach it at all. The limit that matters is the one on a
    stolen access token: without it, that token could guess the current
    password as fast as the network allows.

    The bucket is keyed on the account, not the client IP: the threat model
    is one compromised token, and a shared office IP must not lock out every
    account behind it.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.url = "/api/v1/accounts/password/change/"
        self.user = User.objects.create_user(
            email="sec002-password@example.com",
            password="pass12345",
            first_name="Sec",
            last_name="Password",
            role="student",
        )
        self.other = User.objects.create_user(
            email="sec002-other@example.com",
            password="pass12345",
            first_name="Other",
            last_name="Account",
            role="student",
        )

    def tearDown(self):
        cache.clear()

    def _token(self, user):
        login = self.client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "pass12345"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        return login.data["access"]

    def _change(self, token, current_password="wrong-password"):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return self.client.post(
            self.url,
            {
                "current_password": current_password,
                "new_password": "newpass12345",
            },
            format="json",
        )

    def test_password_change_throttled_after_repeated_attempts(self):
        """Three attempts fill the bucket; the fourth is rejected."""
        token = self._token(self.user)

        for _ in range(3):
            response = self._change(token)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        fourth = self._change(token)
        self.assertEqual(fourth.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(fourth.data["error"]["code"], "RATE_LIMIT_EXCEEDED")

    def test_throttle_is_per_account_not_per_client(self):
        """One account exhausting its bucket must not block another."""
        token = self._token(self.user)
        for _ in range(3):
            self._change(token)
        blocked = self._change(token)
        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        other_token = self._token(self.other)
        other = self._change(other_token)
        self.assertEqual(other.status_code, status.HTTP_400_BAD_REQUEST)

    def test_successful_change_below_the_limit_still_works(self):
        token = self._token(self.user)

        response = self._change(token, current_password="pass12345")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpass12345"))


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


# ---------------------------------------------------------------------------
# PH11.10: administrator faculty roster
# ---------------------------------------------------------------------------


class FacultyProfileListTest(TestCase):
    """
    GET /api/v1/accounts/faculty-profiles/ feeds the subject-assignment picker.

    ``SubjectAssignment.faculty`` is a required foreign key. Until PH11.10 no
    administrator-facing route listed ``FacultyProfile``, so that picker could
    not be populated and every create was rejected on a field the form never
    offered. These tests pin the roster, its ordering, its permission boundary
    and the absence of personnel fields.
    """

    URL = "/api/v1/accounts/faculty-profiles/"

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="facultyroster_admin@example.com",
            password="RosterAdmin_2026!",
            first_name="Roster",
            last_name="Admin",
            role="admin",
        )
        # Deliberately created out of surname order so the ordering assertion
        # fails if the view ever falls back to insertion order.
        self.delta = User.objects.create_user(
            email="facultyroster_delta@example.com",
            password="RosterDelta_2026!",
            first_name="Ana",
            last_name="Zulu",
            role="faculty",
        )
        self.bravo = User.objects.create_user(
            email="facultyroster_bravo@example.com",
            password="RosterBravo_2026!",
            first_name="Bea",
            last_name="Alpha",
            role="faculty",
        )
        FacultyProfile.objects.create(user=self.delta, employee_id="FAC-002")
        FacultyProfile.objects.create(user=self.bravo, employee_id="FAC-001")

    def _as(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {_token_for(user)}"
        )

    def test_admin_can_list_faculty_profiles(self):
        self._as(self.admin)
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [row["name"] for row in response.data["results"]]
        self.assertEqual(names, ["Bea Alpha", "Ana Zulu"])

    def test_list_is_ordered_by_surname_then_forename(self):
        """A stable picker order, not primary-key insertion order."""
        self._as(self.admin)
        response = self.client.get(self.URL)

        # Zulu was created first, so insertion order and surname order disagree.
        self.assertEqual(
            [row["name"] for row in response.data["results"]],
            ["Bea Alpha", "Ana Zulu"],
        )

    def test_each_row_carries_the_foreign_key_id_and_employee_id(self):
        """`faculty` on SubjectAssignment takes the profile id, not the user id."""
        self._as(self.admin)
        response = self.client.get(self.URL)

        by_name = {row["name"]: row for row in response.data["results"]}
        self.assertEqual(by_name["Bea Alpha"]["id"], str(self.bravo.faculty_profile.id))
        self.assertEqual(by_name["Bea Alpha"]["employee_id"], "FAC-001")

    def test_empty_roster_returns_an_empty_page_not_an_error(self):
        FacultyProfile.objects.all().delete()
        self._as(self.admin)
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])

    def test_non_faculty_roles_are_excluded(self):
        """Only real faculty profiles appear; a user with no profile has none."""
        from apps.accounts.models import StudentProfile

        student = User.objects.create_user(
            email="facultyroster_student@example.com",
            password="RosterStudent_2026!",
            first_name="Sam",
            last_name="Student",
            role="student",
        )
        StudentProfile.objects.create(
            user=student,
            student_id="2026-0001",
            enrollment_date="2026-06-01",
        )

        self._as(self.admin)
        response = self.client.get(self.URL)

        ids = [row["id"] for row in response.data["results"]]
        self.assertNotIn(str(student.student_profile.id), ids)
        self.assertEqual(len(ids), 2)

    def test_no_personnel_or_contact_fields_are_exposed(self):
        """NFR-010 reasoning applied to staff: a roster is not a personnel file."""
        self._as(self.admin)
        response = self.client.get(self.URL)

        for row in response.data["results"]:
            self.assertEqual(
                set(row.keys()), {"id", "name", "employee_id"}
            )

    def test_every_non_admin_role_is_refused(self):
        """Same authority rule as the user list: role=admin, nothing else."""
        others = [
            User.objects.create_user(
                email=f"facultyroster_{role}@example.com",
                password=f"Roster{role.capitalize()}_2026!",
                first_name="Other",
                last_name=role.capitalize(),
                role=role,
            )
            for role in ("faculty", "guidance", "student", "parent")
        ]
        for user in others:
            with self.subTest(role=user.role):
                self.client.credentials(HTTP_AUTHORIZATION="")
                self._as(user)
                response = self.client.get(self.URL)
                self.assertEqual(
                    response.status_code, status.HTTP_403_FORBIDDEN
                )

    def test_anonymous_is_refused(self):
        self.client.credentials(HTTP_AUTHORIZATION="")
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# PH11 — TC-ADM-10 (FR-036, NFR-011): role-based access is assignable from
# the API, not only through the Django admin site.
# ---------------------------------------------------------------------------


class AdminAccountUpdateTest(TestCase):
    """PATCH /api/v1/accounts/users/{id}/ — administrator account management."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="admupd_admin@example.com",
            password="AdminUpdate_2026!",
            first_name="Ad",
            last_name="Min",
            role="admin",
        )
        self.other_admin = User.objects.create_user(
            email="admupd_other@example.com",
            password="OtherUpdate_2026!",
            first_name="Oth",
            last_name="Adm",
            role="admin",
        )
        self.target = User.objects.create_user(
            email="admupd_target@example.com",
            password="TargetUpdate_2026!",
            first_name="Tar",
            last_name="Get",
            role="student",
        )

    def _url(self, user=None):
        return f"/api/v1/accounts/users/{(user or self.target).id}/"

    def _as(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token_for(user)}")

    # -- the reported gap -------------------------------------------------

    def test_admin_can_assign_a_role(self):
        self._as(self.admin)
        response = self.client.patch(
            self._url(), {"role": "faculty"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "faculty")
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, "faculty")

    def test_assigned_role_takes_effect_for_the_target_account(self):
        """The granted access is usable, not merely stored."""
        self._as(self.target)
        self.assertEqual(
            self.client.get("/api/v1/accounts/users/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self._as(self.admin)
        self.assertEqual(
            self.client.patch(
                self._url(), {"role": "admin"}, format="json"
            ).status_code,
            status.HTTP_200_OK,
        )

        self._as(self.target)
        self.assertEqual(
            self.client.get("/api/v1/accounts/users/").status_code,
            status.HTTP_200_OK,
        )

    def test_admin_can_deactivate_and_reactivate_an_account(self):
        self._as(self.admin)
        response = self.client.patch(
            self._url(), {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

        # A deactivated account can no longer use its token.
        self._as(self.target)
        self.assertEqual(
            self.client.get("/api/v1/accounts/users/").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        self._as(self.admin)
        self.assertEqual(
            self.client.patch(
                self._url(), {"is_active": True}, format="json"
            ).status_code,
            status.HTTP_200_OK,
        )
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_role_and_active_state_can_change_together(self):
        self._as(self.admin)
        response = self.client.patch(
            self._url(),
            {"role": "guidance", "is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, "guidance")
        self.assertFalse(self.target.is_active)

    # -- audit ------------------------------------------------------------

    def test_change_is_recorded_in_the_audit_log(self):
        from apps.audit.models import AuditLog

        self._as(self.admin)
        self.assertEqual(
            self.client.patch(
                self._url(), {"role": "guidance"}, format="json"
            ).status_code,
            status.HTTP_200_OK,
        )

        log = AuditLog.objects.get(action="update", model_name="accounts.User")
        self.assertEqual(log.user, self.admin)
        self.assertEqual(log.object_id, self.target.id)
        self.assertEqual(log.object_repr, f"User:{self.target.id}")
        self.assertEqual(
            log.changes,
            {"old": {"role": "student"}, "new": {"role": "guidance"}},
        )

    def test_identity_and_credentials_never_reach_the_audit_diff(self):
        from apps.audit.models import AuditLog
        from apps.audit.redact import get_allowed_fields

        self.assertEqual(get_allowed_fields("accounts.User"), ("role", "is_active"))

        self._as(self.admin)
        self.client.patch(self._url(), {"role": "faculty"}, format="json")

        changes = AuditLog.objects.get(action="update").changes
        flattened = set(changes["old"]) | set(changes["new"])
        self.assertEqual(flattened, {"role"})
        for forbidden in ("password", "email", "username", "first_name", "last_name"):
            self.assertNotIn(forbidden, flattened)

    # -- guards -----------------------------------------------------------

    def test_non_admin_cannot_change_a_role(self):
        for role in ("student", "faculty", "guidance", "parent"):
            other = User.objects.create_user(
                email=f"admupd_{role}@example.com",
                password="Passw0rd_2026!",
                first_name="No",
                last_name="Admin",
                role=role,
            )
            self._as(other)
            response = self.client.patch(
                self._url(), {"role": "admin"}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.target.refresh_from_db()
            self.assertEqual(self.target.role, "student")

    def test_admin_cannot_change_their_own_role(self):
        self._as(self.admin)
        response = self.client.patch(
            self._url(self.admin), {"role": "student"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "admin")

    def test_admin_cannot_deactivate_their_own_account(self):
        self._as(self.admin)
        response = self.client.patch(
            self._url(self.admin), {"is_active": False}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_acting_on_another_administrator_keeps_an_active_admin(self):
        # Deliberately no "last administrator" guard: an authenticated
        # administrator is always an active one, so acting on any other
        # account can never leave AEGIS without an administrator.
        self._as(self.admin)
        response = self.client.patch(
            self._url(self.other_admin), {"is_active": False}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.other_admin.refresh_from_db()
        self.assertFalse(self.other_admin.is_active)
        self.assertTrue(
            User.objects.filter(role="admin", is_active=True).exists()
        )

    def test_unknown_role_is_rejected(self):
        self._as(self.admin)
        response = self.client.patch(
            self._url(), {"role": "superuser"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, "student")

    def test_profile_fields_are_not_writable_here(self):
        self._as(self.admin)
        response = self.client.patch(
            self._url(), {"first_name": "Renamed"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertEqual(self.target.first_name, "Tar")

    def test_put_and_delete_are_not_offered(self):
        self._as(self.admin)
        self.assertEqual(
            self.client.put(
                self._url(), {"role": "faculty"}, format="json"
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(self._url()).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.patch(self._url(), {"role": "faculty"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_user_is_not_found(self):
        from uuid import uuid4

        self._as(self.admin)
        response = self.client.patch(
            f"/api/v1/accounts/users/{uuid4()}/", {"role": "faculty"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
"""
NFR-010 / TC-ADM-17: family consent records.

NFR-010 reads "Admins shall view student data in aggregated/anonymized form
unless consent is given." These tests pin the "unless": who may grant, what a
grant requires, and that revocation closes the row rather than deleting it.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    ConsentRecord,
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
)

User = get_user_model()

URL = "/api/v1/accounts/consents/"


class ConsentTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="consent_admin@test.com", password="pass12345",
            first_name="Ad", last_name="Min", role="admin",
        )
        self.parent_user = User.objects.create_user(
            email="consent_parent@test.com", password="pass12345",
            first_name="Par", last_name="Ent", role="parent",
        )
        self.other_parent_user = User.objects.create_user(
            email="consent_other@test.com", password="pass12345",
            first_name="Oth", last_name="Er", role="parent",
        )
        self.student_user = User.objects.create_user(
            email="consent_student@test.com", password="pass12345",
            first_name="Stu", last_name="Dent", role="student",
        )
        self.faculty_user = User.objects.create_user(
            email="consent_faculty@test.com", password="pass12345",
            first_name="Fac", last_name="Ulty", role="faculty",
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user, student_id="STU-CONS-1",
            enrollment_date="2025-06-01",
        )
        self.parent = ParentProfile.objects.create(
            user=self.parent_user, relationship_to_student="mother",
        )
        self.other_parent = ParentProfile.objects.create(
            user=self.other_parent_user, relationship_to_student="father",
        )
        ParentStudentLink.objects.create(
            parent=self.parent, student=self.student, is_primary=True,
        )
        # `other_parent` is deliberately NOT linked to the student.


class ConsentPermissionTest(ConsentTestBase):
    def test_anonymous_is_rejected(self):
        self.assertEqual(
            self.client.get(URL).status_code, status.HTTP_401_UNAUTHORIZED
        )
        self.assertEqual(
            self.client.post(URL, {}, format="json").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_faculty_and_students_are_refused(self):
        for user in (self.faculty_user, self.student_user):
            self.client.force_authenticate(user=user)
            self.assertEqual(
                self.client.get(URL).status_code,
                status.HTTP_403_FORBIDDEN,
                f"{user.role} must not list consents",
            )
            response = self.client.post(
                URL, {"student": str(self.student.pk)}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(ConsentRecord.objects.count(), 0)

    def test_parent_lists_only_their_own_childrens_rows(self):
        ConsentRecord.objects.create(
            student=self.student, granted_by=self.parent_user
        )
        other_student_user = User.objects.create_user(
            email="consent_student2@test.com", password="pass12345",
            first_name="Stu2", last_name="Dent2", role="student",
        )
        other_student = StudentProfile.objects.create(
            user=other_student_user, student_id="STU-CONS-2",
            enrollment_date="2025-06-01",
        )
        ConsentRecord.objects.create(
            student=other_student, granted_by=self.admin,
            note="Form SY2026-001 on file.",
        )

        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(str(response.data[0]["student"]), str(self.student.pk))


class ConsentGrantTest(ConsentTestBase):
    def test_parent_grants_for_their_own_child(self):
        self.client.force_authenticate(user=self.parent_user)

        response = self.client.post(
            URL, {"student": str(self.student.pk)}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        record = ConsentRecord.objects.get(student=self.student)
        self.assertEqual(record.granted_by, self.parent_user)
        self.assertTrue(record.is_active)

    def test_parent_cannot_grant_for_an_unlinked_child(self):
        """Consent for a stranger's child is refused, not silently scoped."""
        self.client.force_authenticate(user=self.other_parent_user)

        response = self.client.post(
            URL, {"student": str(self.student.pk)}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("student", response.data["error"]["details"])
        self.assertEqual(ConsentRecord.objects.count(), 0)

    def test_admin_must_name_the_form_on_file(self):
        """Without provenance the row would be an admin permitting themselves."""
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            URL, {"student": str(self.student.pk)}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("note", response.data["error"]["details"])
        self.assertEqual(ConsentRecord.objects.count(), 0)

    def test_admin_records_offline_consent_with_provenance(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            URL,
            {
                "student": str(self.student.pk),
                "note": "Signed form SY2026-034 on file.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        record = ConsentRecord.objects.get(student=self.student)
        self.assertEqual(record.granted_by, self.admin)
        self.assertEqual(record.note, "Signed form SY2026-034 on file.")

    def test_granted_by_comes_from_the_request_never_the_payload(self):
        self.client.force_authenticate(user=self.parent_user)

        response = self.client.post(
            URL,
            {
                "student": str(self.student.pk),
                "granted_by": str(self.admin.pk),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("granted_by", response.data)
        self.assertEqual(
            ConsentRecord.objects.get(student=self.student).granted_by,
            self.parent_user,
        )

    def test_a_second_active_consent_is_refused(self):
        ConsentRecord.objects.create(
            student=self.student, granted_by=self.parent_user
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            URL,
            {
                "student": str(self.student.pk),
                "note": "Second form on file.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            ConsentRecord.objects.filter(student=self.student).count(), 1
        )


class ConsentRevokeTest(ConsentTestBase):
    def setUp(self):
        super().setUp()
        self.record = ConsentRecord.objects.create(
            student=self.student, granted_by=self.parent_user
        )
        self.url = f"{URL}{self.record.pk}/revoke/"

    def test_parent_revokes(self):
        self.client.force_authenticate(user=self.parent_user)

        response = self.client.patch(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record.refresh_from_db()
        self.assertFalse(self.record.is_active)
        self.assertEqual(self.record.revoked_by, self.parent_user)
        self.assertIsNotNone(self.record.revoked_at)

    def test_revocation_closes_the_row_it_does_not_delete_it(self):
        self.client.force_authenticate(user=self.parent_user)
        self.client.patch(self.url, {}, format="json")

        self.assertTrue(
            ConsentRecord.objects.filter(pk=self.record.pk).exists()
        )

    def test_revoking_twice_is_refused_not_silent(self):
        self.client.force_authenticate(user=self.parent_user)
        self.client.patch(self.url, {}, format="json")

        response = self.client.patch(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unlinked_parent_cannot_revoke(self):
        self.client.force_authenticate(user=self.other_parent_user)

        response = self.client.patch(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.record.refresh_from_db()
        self.assertTrue(self.record.is_active)

    def test_admin_can_revoke(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record.refresh_from_db()
        self.assertEqual(self.record.revoked_by, self.admin)

    def test_a_new_consent_may_follow_a_revoked_one(self):
        """History accumulates; only one row is ever live."""
        self.client.force_authenticate(user=self.parent_user)
        self.client.patch(self.url, {}, format="json")

        response = self.client.post(
            URL, {"student": str(self.student.pk)}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            ConsentRecord.objects.filter(student=self.student).count(), 2
        )
        self.assertEqual(
            ConsentRecord.objects.active()
            .filter(student=self.student)
            .count(),
            1,
        )

    def test_delete_is_not_offered(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(self.url)

        self.assertEqual(
            response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )


@mock.patch.dict(
    "core.throttling.PasswordForgotRateThrottle.THROTTLE_RATES",
    {"password_forgot": "5/min"},
)
class PasswordResetFlowTest(TestCase):
    """
    The password recovery flow.

    Three properties matter and are asserted here: the request answer never
    depends on whether the address belongs to an account, the token is single
    use, and a successful reset revokes the sessions it must.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.forgot_url = "/api/v1/accounts/password/forgot/"
        self.reset_url = "/api/v1/accounts/password/reset/"
        self.user = User.objects.create_user(
            email="reset@example.com",
            password="pass12345",
            first_name="Reset",
            last_name="Tester",
            role="student",
        )

    def tearDown(self):
        cache.clear()

    def _forgot(self, email):
        return self.client.post(
            self.forgot_url, {"email": email}, format="json"
        )

    def _token_for(self, user):
        from apps.accounts.password_reset import issue_reset_token

        raw_token, _record = issue_reset_token(user)
        return raw_token

    def test_unknown_address_gets_the_same_answer_as_a_known_one(self):
        """The endpoint must not be usable to find out who has an account."""
        known = self._forgot("reset@example.com")
        unknown = self._forgot("nobody@example.com")

        self.assertEqual(known.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(unknown.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(known.data, unknown.data)

    def test_the_email_carries_the_reset_link(self):
        """The link the recipient follows is the one the token opens."""
        from django.core import mail

        from apps.accounts.models import PasswordResetToken

        self._forgot("reset@example.com")

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["reset@example.com"])

        body = message.body
        self.assertIn("/reset-password?token=", body)

        # The token in the link is the one that was stored.
        raw_token = body.split("/reset-password?token=")[1].split()[0]
        record = PasswordResetToken.objects.get(user=self.user)
        self.assertEqual(
            record.token_hash,
            hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        )

    def test_an_unknown_address_sends_no_mail(self):
        from django.core import mail

        self._forgot("nobody@example.com")

        self.assertEqual(len(mail.outbox), 0)

    def test_request_creates_one_token_and_closes_the_previous_one(self):
        from apps.accounts.models import PasswordResetToken

        self._forgot("reset@example.com")
        self._forgot("reset@example.com")

        tokens = PasswordResetToken.objects.filter(user=self.user)
        self.assertEqual(tokens.count(), 2)
        self.assertEqual(tokens.filter(used_at__isnull=True).count(), 1)

    def test_reset_sets_the_new_password(self):
        from django.contrib.auth import get_user_model

        token = self._token_for(self.user)

        response = self.client.post(
            self.reset_url,
            {
                "token": token,
                "new_password": "brandnewpass1",
                "confirm_password": "brandnewpass1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.assertTrue(self.user.check_password("brandnewpass1"))

    def test_token_cannot_be_used_twice(self):
        token = self._token_for(self.user)
        payload = {
            "token": token,
            "new_password": "brandnewpass1",
            "confirm_password": "brandnewpass1",
        }

        first = self.client.post(self.reset_url, payload, format="json")
        second = self.client.post(self.reset_url, payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expired_token_is_refused(self):
        from django.utils import timezone

        from apps.accounts.models import PasswordResetToken

        token = self._token_for(self.user)
        PasswordResetToken.objects.filter(user=self.user).update(
            expires_at=timezone.now() - timezone.timedelta(minutes=1)
        )

        response = self.client.post(
            self.reset_url,
            {
                "token": token,
                "new_password": "brandnewpass1",
                "confirm_password": "brandnewpass1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_token_is_refused(self):
        response = self.client.post(
            self.reset_url,
            {
                "token": "not-a-real-token",
                "new_password": "brandnewpass1",
                "confirm_password": "brandnewpass1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mismatched_confirmation_is_refused(self):
        token = self._token_for(self.user)

        response = self.client.post(
            self.reset_url,
            {
                "token": token,
                "new_password": "brandnewpass1",
                "confirm_password": "something-else1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_revokes_outstanding_sessions(self):
        """A reset exists because a session may be stolen."""
        from django.utils import timezone
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )
        from rest_framework_simplejwt.tokens import RefreshToken

        token = self._token_for(self.user)
        refresh = RefreshToken.for_user(self.user)
        # Issuing a refresh token already recorded it in the blacklist
        # application's outstanding-token table.
        outstanding = OutstandingToken.objects.get(jti=str(refresh["jti"]))

        response = self.client.post(
            self.reset_url,
            {
                "token": token,
                "new_password": "brandnewpass1",
                "confirm_password": "brandnewpass1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        outstanding.refresh_from_db()
        self.assertTrue(
            BlacklistedToken.objects.filter(token=outstanding).exists(),
            "the outstanding refresh token was not blacklisted by the reset",
        )

    def test_reset_is_written_to_the_audit_trail(self):
        """A password reset is a security event and belongs in the trail."""
        from apps.audit.models import AuditLog

        token = self._token_for(self.user)

        self.client.post(
            self.reset_url,
            {
                "token": token,
                "new_password": "brandnewpass1",
                "confirm_password": "brandnewpass1",
            },
            format="json",
        )

        self.assertTrue(
            AuditLog.objects.filter(
                model_name="accounts.PasswordResetToken"
            ).exists(),
            "no audit row was written for the reset",
        )

    def test_reset_clears_the_initial_password_state(self):
        from django.contrib.auth import get_user_model

        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])
        token = self._token_for(self.user)

        self.client.post(
            self.reset_url,
            {
                "token": token,
                "new_password": "brandnewpass1",
                "confirm_password": "brandnewpass1",
            },
            format="json",
        )

        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.assertFalse(self.user.must_change_password)


@mock.patch.dict(
    "core.throttling.RegistrationRateThrottle.THROTTLE_RATES",
    {"registration": "5/min"},
)
class StudentRegistrationTest(TestCase):
    """
    Student registration.

    The point of the whole flow: a registration request is not an account.
    It carries no role and no permissions, and the only way to an account
    runs through an administrator's approval.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.submit_url = "/api/v1/accounts/registrations/"
        self.verify_url = "/api/v1/accounts/registrations/verify/"
        self.admin_list_url = "/api/v1/accounts/admin/registrations/"
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="pass12345",
            first_name="Admin",
            last_name="Person",
            role="admin",
        )
        self.student = User.objects.create_user(
            email="student@example.com",
            password="pass12345",
            first_name="Student",
            last_name="Person",
            role="student",
        )

    def tearDown(self):
        cache.clear()

    def _submit(self, **overrides):
        payload = {
            "full_name": "Juan Dela Cruz",
            "email": "juan@example.com",
            "student_code": "AEGIS-QA-S0001",
            "password": "brandnewpass1",
            "confirm_password": "brandnewpass1",
        }
        payload.update(overrides)
        return self.client.post(self.submit_url, payload, format="json")

    def _admin_headers(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(self.admin)
        return {"HTTP_AUTHORIZATION": f"Bearer {token.access_token}"}

    def test_request_gets_the_same_answer_whatever_the_address(self):
        fresh = self._submit()
        unknown = self._submit(email="nobody@example.com")
        existing = self._submit(email="student@example.com")

        for response in (fresh, unknown, existing):
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(fresh.data, unknown.data)
        self.assertEqual(fresh.data, existing.data)

    def test_a_request_creates_no_account(self):
        from apps.accounts.models import RegistrationRequest

        self._submit()

        self.assertEqual(RegistrationRequest.objects.count(), 1)
        self.assertFalse(
            User.objects.filter(email="juan@example.com").exists(),
            "a registration request must not create an account",
        )

    def test_the_request_stores_no_plaintext_password(self):
        from apps.accounts.models import RegistrationRequest

        self._submit()

        request_row = RegistrationRequest.objects.get()
        self.assertNotIn("brandnewpass1", request_row.password_hash)
        self.assertTrue(request_row.password_hash.startswith("pbkdf2_sha256$"))

    def test_verification_moves_the_request_to_verified(self):
        from django.core import mail

        from apps.accounts.models import RegistrationRequest

        self._submit()
        request_row = RegistrationRequest.objects.get()

        body = mail.outbox[0].body
        raw_token = body.split("/register?token=")[1].split()[0]

        response = self.client.get(self.verify_url, {"token": raw_token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        request_row.refresh_from_db()
        self.assertEqual(
            request_row.status, RegistrationRequest.Status.VERIFIED
        )

    def test_an_unknown_verification_token_is_refused(self):
        response = self.client.get(self.verify_url, {"token": "not-a-token"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_an_administrator_may_see_the_queue(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(self.student)
        response = self.client.get(
            self.admin_list_url,
            HTTP_AUTHORIZATION=f"Bearer {token.access_token}",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_approval_creates_the_account_and_the_student_profile(self):
        from apps.accounts.models import StudentProfile

        self._submit()
        from apps.accounts.models import RegistrationRequest

        request_row = RegistrationRequest.objects.get()
        request_row.status = RegistrationRequest.Status.VERIFIED
        request_row.save(update_fields=["status"])

        response = self.client.post(
            f"{self.admin_list_url}{request_row.pk}/approve/",
            {},
            format="json",
            **self._admin_headers(),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="juan@example.com")
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertTrue(user.check_password("brandnewpass1"))
        self.assertFalse(user.must_change_password)
        self.assertTrue(StudentProfile.objects.filter(user=user).exists())

        request_row.refresh_from_db()
        self.assertEqual(
            request_row.status, RegistrationRequest.Status.APPROVED
        )
        self.assertEqual(request_row.reviewed_by_id, self.admin.id)

    def test_rejection_creates_no_account(self):
        from apps.accounts.models import RegistrationRequest

        self._submit()
        request_row = RegistrationRequest.objects.get()

        response = self.client.post(
            f"{self.admin_list_url}{request_row.pk}/reject/",
            {"note": "No enrolment on record."},
            format="json",
            **self._admin_headers(),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(User.objects.filter(email="juan@example.com").exists())
        request_row.refresh_from_db()
        self.assertEqual(
            request_row.status, RegistrationRequest.Status.REJECTED
        )
        self.assertEqual(request_row.review_note, "No enrolment on record.")


@mock.patch.dict(
    "core.throttling.ParentInvitationRateThrottle.THROTTLE_RATES",
    {"parent_invitation": "5/min"},
)
class ParentInvitationTest(TestCase):
    """
    Parent invitations.

    The rule: a parent's account shows a child's academic record, so it is
    not something anyone may request from a public form. A nomination is a
    request; an administrator issues the invitation; the parent accepts.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.create_url = "/api/v1/accounts/parent-invitations/"
        self.accept_url = "/api/v1/accounts/parent-invitations/accept/"
        self.admin_list_url = "/api/v1/accounts/admin/parent-invitations/"
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="pass12345",
            first_name="Admin",
            last_name="Person",
            role="admin",
        )
        self.student_user = User.objects.create_user(
            email="student@example.com",
            password="pass12345",
            first_name="Student",
            last_name="Person",
            role="student",
        )
        from apps.academics.models import AcademicYear, GradeLevel, Section

        level = GradeLevel.objects.create(name="Grade 7", level_number=7)
        year = AcademicYear.objects.create(
            name="2026-2027",
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timezone.timedelta(days=365),
            is_current=True,
        )
        self.section = Section.objects.create(
            name="Rizal",
            grade_level=level,
            academic_year=year,
        )
        from apps.accounts.models import StudentProfile

        self.student = StudentProfile.objects.create(
            user=self.student_user,
            student_id="AEGIS-QA-S0001",
            grade_level=level,
            section=self.section,
            enrollment_date=timezone.localdate(),
        )

    def tearDown(self):
        cache.clear()

    def _student_token(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        return str(RefreshToken.for_user(self.student_user).access_token)

    def _admin_token(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        return str(RefreshToken.for_user(self.admin).access_token)

    def test_a_nomination_creates_no_account(self):
        from apps.accounts.models import ParentInvitation, User

        response = self.client.post(
            self.create_url,
            {
                "full_name": "Maria Cruz",
                "email": "maria@example.com",
                "relationship": "mother",
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self._student_token()}",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(ParentInvitation.objects.count(), 1)
        self.assertFalse(User.objects.filter(email="maria@example.com").exists())

    def test_a_nomination_is_scoped_to_the_nominating_student(self):
        from apps.accounts.models import ParentInvitation

        self.client.post(
            self.create_url,
            {
                "full_name": "Maria Cruz",
                "email": "maria@example.com",
                "relationship": "mother",
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self._student_token()}",
        )

        invitation = ParentInvitation.objects.get()
        self.assertEqual(invitation.student_id, self.student.id)
        self.assertEqual(invitation.nominated_by_id, self.student_user.id)

    def test_only_an_administrator_may_issue_the_invitation(self):
        from apps.accounts.models import ParentInvitation

        self.client.post(
            self.create_url,
            {
                "full_name": "Maria Cruz",
                "email": "maria@example.com",
                "relationship": "mother",
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self._student_token()}",
        )
        invitation = ParentInvitation.objects.get()

        response = self.client.post(
            f"{self.admin_list_url}{invitation.pk}/approve/",
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self._student_token()}",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_approval_issues_the_invitation_link(self):
        from django.core import mail

        from apps.accounts.models import ParentInvitation

        self.client.post(
            self.create_url,
            {
                "full_name": "Maria Cruz",
                "email": "maria@example.com",
                "relationship": "mother",
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self._student_token()}",
        )
        invitation = ParentInvitation.objects.get()

        response = self.client.post(
            f"{self.admin_list_url}{invitation.pk}/approve/",
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self._admin_token()}",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invitation.refresh_from_db()
        self.assertEqual(
            invitation.status, ParentInvitation.Status.APPROVED
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accept-invitation?token=", mail.outbox[0].body)

    def test_accepting_creates_the_account_and_the_child_link(self):
        from django.core import mail

        from apps.accounts.models import (
            ParentInvitation,
            ParentProfile,
            ParentStudentLink,
            User,
        )

        self.client.post(
            self.create_url,
            {
                "full_name": "Maria Cruz",
                "email": "maria@example.com",
                "relationship": "mother",
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self._student_token()}",
        )
        invitation = ParentInvitation.objects.get()
        self.client.post(
            f"{self.admin_list_url}{invitation.pk}/approve/",
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self._admin_token()}",
        )
        raw_token = mail.outbox[0].body.split("/accept-invitation?token=")[1].split()[0]

        response = self.client.post(
            self.accept_url,
            {
                "token": raw_token,
                "password": "brandnewpass1",
                "confirm_password": "brandnewpass1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="maria@example.com")
        self.assertEqual(user.role, User.Role.PARENT)
        self.assertTrue(user.check_password("brandnewpass1"))
        profile = ParentProfile.objects.get(user=user)
        self.assertTrue(
            ParentStudentLink.objects.filter(
                parent=profile, student=self.student
            ).exists()
        )

    def test_an_invitation_can_be_used_only_once(self):
        from django.core import mail

        from apps.accounts.models import ParentInvitation

        self.client.post(
            self.create_url,
            {
                "full_name": "Maria Cruz",
                "email": "maria@example.com",
                "relationship": "mother",
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self._student_token()}",
        )
        invitation = ParentInvitation.objects.get()
        self.client.post(
            f"{self.admin_list_url}{invitation.pk}/approve/",
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self._admin_token()}",
        )
        raw_token = mail.outbox[0].body.split("/accept-invitation?token=")[1].split()[0]
        payload = {
            "token": raw_token,
            "password": "brandnewpass1",
            "confirm_password": "brandnewpass1",
        }

        first = self.client.post(self.accept_url, payload, format="json")
        second = self.client.post(self.accept_url, payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_unknown_token_is_refused(self):
        response = self.client.post(
            self.accept_url,
            {
                "token": "not-a-token",
                "password": "brandnewpass1",
                "confirm_password": "brandnewpass1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class StaffSetPasswordLinkTest(TestCase):
    """
    A provisioned staff account sets its own password.

    The administrator creates the account; the person sets the password
    from a one-time link that is emailed to them. No administrator chooses
    a colleague's password, and no password travels by email.
    """

    def setUp(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="staffadmin@example.com",
            password="pass12345",
            first_name="Staff",
            last_name="Admin",
            role="admin",
        )
        self.token = str(
            RefreshToken.for_user(self.admin).access_token
        )

    def _create(self, **overrides):
        payload = {
            "email": "new.teacher@example.com",
            "username": "",
            "first_name": "New",
            "last_name": "Teacher",
            "role": "faculty",
        }
        payload.update(overrides)
        return self.client.post(
            "/api/v1/accounts/users/create/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

    def test_account_created_without_a_password_cannot_sign_in_yet(self):
        response = self._create()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="new.teacher@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.must_change_password)

    def test_the_set_password_link_is_emailed(self):
        from django.core import mail

        self._create()

        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("/set-password?token=", body)
        # No password in the mail: not even the administrator's own.
        self.assertNotIn("password:", body.lower().split("set your password")[0])

    def test_the_link_sets_the_password_and_clears_the_onboarding_flag(self):
        from django.core import mail

        self._create()
        raw_token = mail.outbox[0].body.split("/set-password?token=")[1].split()[0]

        response = self.client.post(
            "/api/v1/accounts/password/reset/",
            {
                "token": raw_token,
                "new_password": "brandnewpass1",
                "confirm_password": "brandnewpass1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="new.teacher@example.com")
        self.assertTrue(user.check_password("brandnewpass1"))
        self.assertFalse(user.must_change_password)

        login = self.client.post(
            "/api/v1/auth/login/",
            {
                "email": "new.teacher@example.com",
                "password": "brandnewpass1",
            },
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_an_account_created_with_a_password_keeps_it_and_sends_no_mail(self):
        from django.core import mail

        response = self._create(password="chosenpass123")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="new.teacher@example.com")
        self.assertTrue(user.check_password("chosenpass123"))
        self.assertEqual(len(mail.outbox), 0)
