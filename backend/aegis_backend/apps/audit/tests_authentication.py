"""
Phase 10.7 test suite — Authentication event integration.

Verifies that existing AEGIS authentication flows write LOGIN / LOGOUT
audit events through the PH10.4 central audit service:

    Authentication flow
        ↓
    PH10.7 hook
        ↓
    audit context (PH10.6) where applicable
        ↓
    record_audit()
        ↓
    AuditLog

Coverage groups
---------------
LOGIN:
  1. Successful login creates exactly one AuditLog.
  2. Audit action = login.
  3. model_name = accounts.Authentication.
  4. object_id = NULL.
  5. object_repr = Login.
  6. changes = NULL.
  7. correct authenticated user recorded.
  8. PH10.6 IP recorded.
  9. PH10.6 user-agent recorded.
 10. password not stored.
 11. access token not stored.
 12. refresh token not stored.
 13. Authorization header not stored.
 14. failed login creates no LOGIN audit event.
 15. repeated ordinary authenticated requests do not create LOGIN events.

LOGOUT:
 16. Successful logout creates exactly one AuditLog.
 17. Audit action = logout.
 18. model_name = accounts.Authentication.
 19. object_id = NULL.
 20. object_repr = Logout.
 21. changes = NULL.
 22. correct authenticated actor recorded.
 23. PH10.6 IP recorded.
 24. PH10.6 user-agent recorded.
 25. failed logout/revocation creates no LOGOUT event.
 26. repeated logout does not create duplicate successful events.

CONTEXT:
 27. LOGIN uses the correct request context.
 28. LOGOUT uses the correct request context.
 29. request A context cannot leak into authentication request B.

SECURITY:
 30. No token/credential information reaches AuditLog fields.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from unittest import mock

from apps.audit.models import AuditLog

User = get_user_model()


def _clear_audit():
    AuditLog.objects.all().delete()


def _serialize_log(log):
    """Flatten every saved AuditLog field into one searchable string."""
    chunks = [
        str(getattr(log, field, "") or "")
        for field in (
            "user_id",
            "action",
            "model_name",
            "object_id",
            "object_repr",
            "ip_address",
            "user_agent",
        )
    ]
    if log.changes:
        chunks.append(str(log.changes))
    return "\n".join(chunks)


class AuthenticationTestBase(TestCase):
    URL_LOGIN = "/api/v1/auth/login/"
    URL_LOGOUT = "/api/v1/auth/logout/"
    URL_ME = "/api/v1/accounts/me/"

    def setUp(self):
        self.client = APIClient()
        self.password = "authpass123"
        self.user = User.objects.create_user(
            email="auth@example.com",
            password=self.password,
            first_name="Auth",
            last_name="User",
            role="student",
        )
        _clear_audit()

    def _login(self, email=None, password=None, ip="203.0.113.10", ua="AuthUA/1.0"):
        return self.client.post(
            self.URL_LOGIN,
            {"email": email or self.user.email, "password": password or self.password},
            format="json",
            REMOTE_ADDR=ip,
            HTTP_USER_AGENT=ua,
        )

    def _login_and_credentials(self, ip="203.0.113.20", ua="LogoutUA/1.0"):
        response = self._login(ip=ip, ua=ua)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["access"], response.data["refresh"]


# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------


class SuccessfulLoginTest(AuthenticationTestBase):
    """A single correct login creates exactly one LOGIN audit record."""

    def test_successful_login_creates_exactly_one_auditlog(self):
        self._login()
        logs = AuditLog.objects.filter(action="login")
        self.assertEqual(logs.count(), 1)

    def test_audit_action_is_login(self):
        self._login()
        log = AuditLog.objects.get(action="login")
        self.assertEqual(log.action, "login")

    def test_model_name_is_accounts_authentication(self):
        self._login()
        log = AuditLog.objects.get(action="login")
        self.assertEqual(log.model_name, "accounts.Authentication")

    def test_object_id_is_null(self):
        self._login()
        log = AuditLog.objects.get(action="login")
        self.assertIsNone(log.object_id)

    def test_object_repr_is_login(self):
        self._login()
        log = AuditLog.objects.get(action="login")
        self.assertEqual(log.object_repr, "Login")

    def test_changes_is_null(self):
        self._login()
        log = AuditLog.objects.get(action="login")
        self.assertIsNone(log.changes)

    def test_correct_authenticated_user_recorded(self):
        self._login()
        log = AuditLog.objects.get(action="login")
        self.assertEqual(log.user_id, self.user.pk)

    def test_ph106_ip_recorded(self):
        self._login(ip="203.0.113.44")
        log = AuditLog.objects.get(action="login")
        self.assertEqual(log.ip_address, "203.0.113.44")

    def test_ph106_user_agent_recorded(self):
        self._login(ua="LoginSpec-UA/9.9")
        log = AuditLog.objects.get(action="login")
        self.assertEqual(log.user_agent, "LoginSpec-UA/9.9")


class LoginTokenPrivacyTest(AuthenticationTestBase):
    """Credentials and tokens never reach the LOGIN audit record."""

    def test_password_not_stored(self):
        self._login()
        log = AuditLog.objects.get(action="login")
        self.assertNotIn(self.password, _serialize_log(log))

    def test_access_token_not_stored(self):
        access, _ = self._login_and_credentials()
        log = AuditLog.objects.get(action="login")
        self.assertNotIn(access, _serialize_log(log))

    def test_refresh_token_not_stored(self):
        _, refresh = self._login_and_credentials()
        log = AuditLog.objects.get(action="login")
        self.assertNotIn(refresh, _serialize_log(log))

    def test_authorization_header_not_stored(self):
        access, _ = self._login_and_credentials()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self._login()
        log = AuditLog.objects.filter(action="login").last()
        self.assertNotIn("Bearer", _serialize_log(log))
        self.assertNotIn(access, _serialize_log(log))


class FailedAndRepeatedLoginTest(AuthenticationTestBase):
    """Only an actual token-issuance event produces a LOGIN record."""

    def test_failed_login_creates_no_successful_login_event(self):
        response = self._login(password="totally-wrong-password")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(AuditLog.objects.filter(action="login").count(), 0)

    def test_nonexistent_user_creates_no_login_event(self):
        response = self._login(email="nobody@example.com")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(AuditLog.objects.filter(action="login").count(), 0)

    def test_repeated_authenticated_requests_do_not_create_login_events(self):
        access, _ = self._login_and_credentials()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        for _ in range(3):
            response = self.client.get(self.URL_ME, REMOTE_ADDR="203.0.113.50")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.filter(action="login").count(), 1)


# ---------------------------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------------------------


class SuccessfulLogoutTest(AuthenticationTestBase):
    """A successful refresh-token revocation creates exactly one LOGOUT."""

    def _logout(self, access, refresh, ip="203.0.113.30", ua="LogoutSpecUA/2.0"):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return self.client.post(
            self.URL_LOGOUT,
            {"refresh": refresh},
            format="json",
            REMOTE_ADDR=ip,
            HTTP_USER_AGENT=ua,
        )

    def test_successful_logout_creates_exactly_one_auditlog(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        response = self._logout(access, refresh)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.filter(action="logout").count(), 1)

    def test_audit_action_is_logout(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self._logout(access, refresh)
        log = AuditLog.objects.get(action="logout")
        self.assertEqual(log.action, "logout")

    def test_model_name_is_accounts_authentication(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self._logout(access, refresh)
        log = AuditLog.objects.get(action="logout")
        self.assertEqual(log.model_name, "accounts.Authentication")

    def test_object_id_is_null(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self._logout(access, refresh)
        log = AuditLog.objects.get(action="logout")
        self.assertIsNone(log.object_id)

    def test_object_repr_is_logout(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self._logout(access, refresh)
        log = AuditLog.objects.get(action="logout")
        self.assertEqual(log.object_repr, "Logout")

    def test_changes_is_null(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self._logout(access, refresh)
        log = AuditLog.objects.get(action="logout")
        self.assertIsNone(log.changes)

    def test_correct_authenticated_actor_recorded(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self._logout(access, refresh)
        log = AuditLog.objects.get(action="logout")
        self.assertEqual(log.user_id, self.user.pk)

    def test_ph106_ip_recorded(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self._logout(access, refresh, ip="203.0.113.66")
        log = AuditLog.objects.get(action="logout")
        self.assertEqual(log.ip_address, "203.0.113.66")

    def test_ph106_user_agent_recorded(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self._logout(access, refresh, ua="LogoutUA-77")
        log = AuditLog.objects.get(action="logout")
        self.assertEqual(log.user_agent, "LogoutUA-77")


class FailedAndRepeatedLogoutTest(AuthenticationTestBase):
    """No LOGOUT event without a successful revocation."""

    def test_failed_logout_creates_no_logout_event(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = self.client.post(
            self.URL_LOGOUT,
            {"refresh": "not-a-real-token"},
            format="json",
            REMOTE_ADDR="203.0.113.31",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AuditLog.objects.filter(action="logout").count(), 0)

    def test_other_users_token_creates_no_logout_event(self):
        access, refresh = self._login_and_credentials()
        attacker = User.objects.create_user(
            email="attacker@example.com",
            password="authpass123",
            first_name="At",
            last_name="Tacker",
            role="student",
        )
        attacker_login = self.client.post(
            self.URL_LOGIN,
            {"email": attacker.email, "password": "authpass123"},
            format="json",
        )
        _clear_audit()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {attacker_login.data['access']}")
        response = self.client.post(
            self.URL_LOGOUT,
            {"refresh": refresh},
            format="json",
            REMOTE_ADDR="203.0.113.32",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AuditLog.objects.filter(action="logout").count(), 0)

    def test_repeated_logout_does_not_create_duplicate_successful_events(self):
        access, refresh = self._login_and_credentials()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        first = self.client.post(
            self.URL_LOGOUT, {"refresh": refresh}, format="json",
            REMOTE_ADDR="203.0.113.33",
        )
        _clear_audit()
        second = self.client.post(
            self.URL_LOGOUT, {"refresh": refresh}, format="json",
            REMOTE_ADDR="203.0.113.33",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AuditLog.objects.filter(action="logout").count(), 0)


# ---------------------------------------------------------------------------
# CONTEXT
# ---------------------------------------------------------------------------


class AuthContextIsolationTest(AuthenticationTestBase):
    """Each authentication event uses its own request context."""

    def test_login_uses_correct_request_context(self):
        self._login(ip="203.0.113.70", ua="CtxLoginUA-1")
        log = AuditLog.objects.get(action="login")
        self.assertEqual(log.ip_address, "203.0.113.70")
        self.assertEqual(log.user_agent, "CtxLoginUA-1")

    def test_logout_uses_correct_request_context(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.client.post(
            self.URL_LOGOUT, {"refresh": refresh}, format="json",
            REMOTE_ADDR="203.0.113.71", HTTP_USER_AGENT="CtxLogoutUA-2",
        )
        log = AuditLog.objects.get(action="logout")
        self.assertEqual(log.ip_address, "203.0.113.71")
        self.assertEqual(log.user_agent, "CtxLogoutUA-2")

    def test_request_a_context_does_not_leak_into_request_b(self):
        # First request: a real login from IP A with UA A.
        self._login(ip="203.0.113.80", ua="LeakUA-A")
        first = AuditLog.objects.get(action="login")
        self.assertEqual(first.ip_address, "203.0.113.80")
        self.assertEqual(first.user_agent, "LeakUA-A")

        # Second request: fresh login from IP B with UA B.
        self._login(ip="203.0.113.81", ua="LeakUA-B")
        second = AuditLog.objects.filter(action="login").order_by("timestamp").last()
        self.assertEqual(second.ip_address, "203.0.113.81")
        self.assertEqual(second.user_agent, "LeakUA-B")
        self.assertNotEqual(second.ip_address, first.ip_address)
        self.assertNotEqual(second.user_agent, first.user_agent)


# ---------------------------------------------------------------------------
# SECURITY
# ---------------------------------------------------------------------------


class AuthSecurityTest(AuthenticationTestBase):
    """No token/credential/header material reaches any AuditLog field."""

    def test_no_token_or_credential_information_reaches_auditlog(self):
        access, refresh = self._login_and_credentials()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.client.post(
            self.URL_LOGOUT, {"refresh": refresh}, format="json",
            REMOTE_ADDR="203.0.113.90", HTTP_USER_AGENT="SecUA-9",
        )
        all_blob = "\n".join(_serialize_log(log) for log in AuditLog.objects.all())
        self.assertNotIn(access, all_blob)
        self.assertNotIn(refresh, all_blob)
        self.assertNotIn(self.password, all_blob)


# ---------------------------------------------------------------------------
# FAILURE ISOLATION
#
# The audit side-effect is fire-and-forget: an audit write failure must
# never alter the authentication outcome.  record_audit() is patched via
# apps.audit.hooks.record_audit (the name bound inside the hooks module).
# ---------------------------------------------------------------------------


class AuditFailureIsolationTest(AuthenticationTestBase):
    """A failing audit write never breaks successful authentication."""

    def test_login_returns_200_when_audit_record_raises(self):
        with mock.patch(
            "apps.audit.hooks.record_audit", side_effect=RuntimeError("db down")
        ):
            response = self._login(
                ip="203.0.113.100", ua="FailLoginUA-1"
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_audit_failure_does_not_suppress_token_issuance(self):
        with mock.patch("apps.audit.hooks.record_audit", side_effect=ValueError("boom")):
            response = self._login()
        # Tokens are still issued despite the audit failure.
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["access"])
        self.assertTrue(response.data["refresh"])

    def test_logout_returns_200_when_audit_record_raises_after_blacklist(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        with mock.patch(
            "apps.audit.hooks.record_audit", side_effect=RuntimeError("db down")
        ):
            response = self.client.post(
                self.URL_LOGOUT,
                {"refresh": refresh},
                format="json",
                REMOTE_ADDR="203.0.113.101",
                HTTP_USER_AGENT="FailLogoutUA-1",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logout_audit_failure_does_not_undo_token_blacklisting(self):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

        access, refresh = self._login_and_credentials()
        _clear_audit()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        with mock.patch(
            "apps.audit.hooks.record_audit", side_effect=RuntimeError("db down")
        ):
            response = self.client.post(
                self.URL_LOGOUT, {"refresh": refresh}, format="json",
                REMOTE_ADDR="203.0.113.102",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Revocation remains authoritative: the token is still blacklisted.
        self.assertTrue(BlacklistedToken.objects.exists())
        refresh_used = self.client.post(
            "/api/v1/auth/token/refresh/",
            {"refresh": refresh},
            format="json",
        )
        self.assertEqual(refresh_used.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_failed_login_does_not_call_audit_hook(self):
        with mock.patch(
            "apps.audit.hooks.audit_successful_login"
        ) as mocked:
            response = self._login(password="wrong-password")
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            mocked.assert_not_called()

    def test_failed_logout_does_not_create_successful_logout_event(self):
        access, refresh = self._login_and_credentials()
        _clear_audit()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        with mock.patch(
            "apps.audit.hooks.audit_successful_logout"
        ) as mocked:
            response = self.client.post(
                self.URL_LOGOUT, {"refresh": "not-a-valid-token"}, format="json",
                REMOTE_ADDR="203.0.113.103",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            mocked.assert_not_called()
        self.assertEqual(AuditLog.objects.filter(action="logout").count(), 0)


class AuditFailurePrivacyTest(AuthenticationTestBase):
    """An audit failure logs safely — no sensitive authentication payload."""

    def test_audit_failure_logs_no_credentials_or_tokens(self):
        from django.test import override_settings
        import logging

        access, refresh = self._login_and_credentials()

        records = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = _Capture()
        logger = logging.getLogger("apps.audit.hooks")
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)
        try:
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
            with mock.patch(
                "apps.audit.hooks.record_audit", side_effect=RuntimeError("db down")
            ):
                self.client.post(
                    self.URL_LOGOUT, {"refresh": refresh}, format="json",
                    REMOTE_ADDR="203.0.113.104",
                )
        finally:
            logger.removeHandler(handler)

        blob = "\n".join(records)
        self.assertTrue(blob)  # the failure was logged
        self.assertNotIn(access, blob)
        self.assertNotIn(refresh, blob)
        self.assertNotIn(self.password, blob)
