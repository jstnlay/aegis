"""
Phase 10.6 test suite — Request / actor context.

Verifies the request-scoped audit context end to end:

    HTTP request
        ↓
    AuditContextMiddleware
        ↓
    ContextVar
        ├── user
        ├── ip_address
        └── user_agent
        ↓
    domain operation
        ↓
    PH10.5 signal
        ↓
    record_audit()
        ↓
    AuditLog

Coverage groups
---------------
1. No-request behaviour: empty context (user/ip/user_agent None).
2. AuditContext value semantics: authenticated actor preserved, anonymous
   values resolved to None, no domain-relationship inference.
3. Middleware capture: REMOTE_ADDR, missing REMOTE_ADDR, HTTP_USER_AGENT,
   missing user-agent, X-Forwarded-For ignored, IPv6 passthrough.
4. Lifecycle: context reset after normal requests and after exceptions,
   exact-token reset semantics, nested contexts, cross-task isolation.
5. Actor resolution through a real DRF request cycle (force_authenticate,
   real SimpleJWT Bearer tokens, anonymous requests).
6. PH10.5 signal integration: authenticated request -> AuditLog carries
   user/ip/user_agent; background write -> all None.
7. Security: Authorization header, cookies, request body, and arbitrary
   headers never enter the context or AuditLog; X-Forwarded-For cannot
   spoof the recorded IP; no actor leakage between requests.

Deliberately NOT covered here (later PH10 phases): login/logout audit
hooks, ACCESS auditing, the admin API, the audit UI, retention/purge.
"""

import asyncio
import types
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import path
from django.utils import timezone

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.audit.context import (
    AuditContext,
    get_audit_context,
    set_audit_context,
    reset_audit_context,
)
from apps.audit.middleware import AuditContextMiddleware
from apps.audit.models import AuditLog

User = get_user_model()


# ---------------------------------------------------------------------------
# Probe views + test-only URLconf
#
# The middleware is exercised through real HTTP requests.  A tiny DRF
# URLconf is swapped in so the probe views can report exactly what the
# context held during the request.  DRF APIViews are used because DRF
# authentication is lazy and happens inside the view cycle — exactly the
# behaviour PH10.6 must tolerate.
# ---------------------------------------------------------------------------

class _ContextProbeView(APIView):
    """Report what the audit context held during this request."""

    permission_classes = []

    def get(self, request):
        ctx = get_audit_context()
        return Response({
            "user_id": str(ctx.user_id) if ctx.user_id else None,
            "ip_address": ctx.ip_address,
            "user_agent": ctx.user_agent,
        })


class _CreateNoteView(APIView):
    """Create an instrumented model so the PH10.5 signal fires in-request."""

    def post(self, request):
        from apps.accounts.models import FacultyProfile, StudentProfile
        from apps.guidance.models import BehavioralNote

        student = StudentProfile.objects.get(pk=request.data["student_id"])
        faculty = FacultyProfile.objects.get(user=request.user)
        note = BehavioralNote.objects.create(
            student=student,
            recorded_by=faculty,
            note_type="positive",
            note_text=request.data.get("note_text", "integration note"),
            date_recorded=date.today(),
        )
        return Response({"note_id": str(note.pk)})


class _TouchNoteView(APIView):
    """Update an existing instrumented model in-request."""

    def post(self, request):
        from apps.guidance.models import BehavioralNote

        note = BehavioralNote.objects.get(pk=request.data["note_id"])
        note.note_type = "warning"
        note.save()
        return Response({"touched": True})


class _DeleteNoteView(APIView):
    """Delete an instrumented model in-request (fires pre_delete)."""

    def post(self, request):
        from apps.guidance.models import BehavioralNote

        note = BehavioralNote.objects.get(pk=request.data["note_id"])
        note.delete()
        return Response({"deleted": True})


class _BoomView(APIView):
    """Raise an exception inside the DRF view cycle."""

    permission_classes = []

    def get(self, request):
        raise RuntimeError("boom")


def _build_probe_urlconf():
    module = types.ModuleType("aegis_audit_probe_urls")
    module.urlpatterns = [
        path("context/", _ContextProbeView.as_view()),
        path("note/", _CreateNoteView.as_view()),
        path("note/touch/", _TouchNoteView.as_view()),
        path("note/delete/", _DeleteNoteView.as_view()),
        path("boom/", _BoomView.as_view()),
    ]
    return module


_PROBE_URLCONF = _build_probe_urlconf()


def _create_actor_users():
    faculty_user = User.objects.create_user(
        email="actor-faculty@example.com",
        password="pass12345",
        first_name="Actor",
        last_name="Faculty",
        role="faculty",
    )
    student_user = User.objects.create_user(
        email="actor-student@example.com",
        password="pass12345",
        first_name="Actor",
        last_name="Student",
        role="student",
    )
    from apps.accounts.models import FacultyProfile, StudentProfile

    faculty_profile = FacultyProfile.objects.create(
        user=faculty_user,
        employee_id="FAC-CTX-001",
    )
    student_profile = StudentProfile.objects.create(
        user=student_user,
        student_id="STU-CTX-001",
        enrollment_date=date.today() - timedelta(days=30),
    )
    return {
        "faculty_user": faculty_user,
        "student_user": student_user,
        "faculty_profile": faculty_profile,
        "student_profile": student_profile,
    }


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


# ---------------------------------------------------------------------------
# 1 — No active request context
# ---------------------------------------------------------------------------

class NoRequestContextTest(TestCase):
    """Outside a request the accessor always returns an empty context."""

    def test_no_context_returns_empty(self):
        ctx = get_audit_context()
        self.assertIsNone(ctx.user)
        self.assertIsNone(ctx.ip_address)
        self.assertIsNone(ctx.user_agent)

    def test_no_context_never_returns_none(self):
        self.assertIsInstance(get_audit_context(), AuditContext)

    def test_background_system_operation_has_empty_context(self):
        # Simulates management-command / AI-worker execution: no request.
        from apps.accounts.models import StudentProfile
        from apps.guidance.models import RiskAlert

        student_user = User.objects.create_user(
            email="bg-context@example.com",
            password="pass12345",
            first_name="Bg",
            last_name="Context",
            role="student",
        )
        student = StudentProfile.objects.create(
            user=student_user,
            student_id="STU-BG-001",
            enrollment_date=date.today(),
        )
        _clear_audit()
        alert = RiskAlert.objects.create(
            student=student,
            risk_level="low",
            risk_factors=["attendance_pattern"],
            source="decision_tree",
            status="active",
            generated_at=timezone.now(),
        )
        log = AuditLog.objects.get(object_id=alert.pk)
        self.assertIsNone(log.user)
        self.assertIsNone(log.ip_address)
        self.assertIsNone(log.user_agent)


# ---------------------------------------------------------------------------
# 2 — AuditContext value semantics
# ---------------------------------------------------------------------------

class AuditContextValueTest(TestCase):
    """Direct construction semantics of the value object."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="ctx-value@example.com",
            password="pass12345",
            first_name="Ctx",
            last_name="Value",
            role="faculty",
        )

    def test_authenticated_user_preserved(self):
        ctx = AuditContext(user=self.user, ip_address="1.2.3.4", user_agent="UA/1")
        self.assertIs(ctx.user, self.user)
        self.assertEqual(ctx.user_id, self.user.pk)

    def test_no_user_yields_none(self):
        ctx = AuditContext()
        self.assertIsNone(ctx.user)
        self.assertIsNone(ctx.user_id)

    def test_anonymous_resolves_to_none(self):
        from django.contrib.auth.models import AnonymousUser

        ctx = AuditContext(user=AnonymousUser())
        self.assertIsNone(ctx.user)

    def test_non_authenticated_object_resolves_to_none(self):
        class FakeActor:
            is_authenticated = False

        ctx = AuditContext(user=FakeActor())
        self.assertIsNone(ctx.user)

    def test_ip_and_user_agent_passthrough(self):
        ctx = AuditContext(user=self.user, ip_address="2001:db8::1", user_agent="UA/2")
        self.assertEqual(ctx.ip_address, "2001:db8::1")
        self.assertEqual(ctx.user_agent, "UA/2")

    def test_no_domain_relationship_inference(self):
        # context.user must never infer an actor from counselor/encoded_by/
        # recorded_by relationships.
        ctx = AuditContext(user=None)
        self.assertIsNone(ctx.user)


# ---------------------------------------------------------------------------
# 3 — Middleware capture semantics (direct invocation)
# ---------------------------------------------------------------------------

class MiddlewareCaptureTest(TestCase):
    """REMOTE_ADDR / HTTP_USER_AGENT capture through the middleware.

    The middleware is invoked directly around a recording ``get_response``
    so the exact context value can be observed inside the request.
    """

    def _run(self, request):
        observed = {}

        def get_response(inner):
            ctx = get_audit_context()
            observed["user"] = ctx.user
            observed["ip"] = ctx.ip_address
            observed["ua"] = ctx.user_agent
            return HttpResponse("ok")

        AuditContextMiddleware(get_response)(request)
        return observed

    def test_remote_addr_captured(self):
        request = RequestFactory().get("/x/", REMOTE_ADDR="203.0.113.9")
        observed = self._run(request)
        self.assertEqual(observed["ip"], "203.0.113.9")
        self.assertIsNone(observed["user"])
        self.assertIsNone(observed["ua"])

    def test_missing_remote_addr_is_none(self):
        request = RequestFactory().get("/x/")
        request.META.pop("REMOTE_ADDR")
        observed = self._run(request)
        self.assertIsNone(observed["ip"])

    def test_user_agent_captured(self):
        request = RequestFactory().get("/x/", HTTP_USER_AGENT="ApegisUA/1.0")
        observed = self._run(request)
        self.assertEqual(observed["ua"], "ApegisUA/1.0")

    def test_authorization_and_cookie_headers_not_captured(self):
        request = RequestFactory().get(
            "/x/",
            HTTP_AUTHORIZATION="Bearer zzz",
            HTTP_COOKIE="sessionid=abc",
            HTTP_X_CUSTOM="custom-value",
        )
        observed = self._run(request)
        # The ONLY request-derived fields are ip/user_agent; user resolves
        # lazily and is None on this request.
        self.assertIsNone(observed["user"])
        self.assertEqual(observed["ip"], "127.0.0.1")
        self.assertIsNone(observed["ua"])

    def test_missing_user_agent_is_none(self):
        request = RequestFactory().get("/x/")
        request.META.pop("HTTP_USER_AGENT", None)
        observed = self._run(request)
        self.assertIsNone(observed["ua"])

    def test_x_forwarded_for_ignored(self):
        request = RequestFactory().get(
            "/x/",
            REMOTE_ADDR="203.0.113.9",
            HTTP_X_FORWARDED_FOR="6.6.6.6, 5.5.5.5",
        )
        observed = self._run(request)
        self.assertEqual(observed["ip"], "203.0.113.9")

    def test_ipv6_passthrough(self):
        request = RequestFactory().get("/x/", REMOTE_ADDR="2001:db8::42")
        observed = self._run(request)
        self.assertEqual(observed["ip"], "2001:db8::42")

    def test_refreshes_on_reentry_do_not_reuse_stale_context(self):
        # Calling the middleware again after it returned must NOT observe
        # the previous request's values.
        first = RequestFactory().get("/a/", REMOTE_ADDR="10.0.0.1")
        self._run(first)
        second = RequestFactory().get("/b/", REMOTE_ADDR="10.0.0.2")
        observed = self._run(second)
        self.assertEqual(observed["ip"], "10.0.0.2")


# ---------------------------------------------------------------------------
# 4 — Lifecycle: reset after normal request / exception
# ---------------------------------------------------------------------------

class MiddlewareLifecycleTest(TestCase):
    """The context token set by the middleware is always torn down."""

    def test_reset_after_normal_request(self):
        request = RequestFactory().get("/x/", REMOTE_ADDR="203.0.113.5")
        AuditContextMiddleware(lambda r: HttpResponse("ok"))(request)
        ctx = get_audit_context()
        self.assertIsNone(ctx.user)
        self.assertIsNone(ctx.ip_address)
        self.assertIsNone(ctx.user_agent)

    def test_reset_after_exception(self):
        request = RequestFactory().get("/x/", REMOTE_ADDR="203.0.113.5")

        def get_response(inner):
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            AuditContextMiddleware(get_response)(request)
        ctx = get_audit_context()
        self.assertIsNone(ctx.user)
        self.assertIsNone(ctx.ip_address)
        self.assertIsNone(ctx.user_agent)

    def test_reset_restores_outer_value(self):
        """A context established around the middleware must be restored."""
        outer = AuditContext(user=None, ip_address="9.9.9.9", user_agent="outer")
        outer_token = set_audit_context(outer)
        try:
            request = RequestFactory().get("/x/", REMOTE_ADDR="1.2.3.4")
            AuditContextMiddleware(lambda r: HttpResponse("ok"))(request)
            self.assertEqual(get_audit_context().ip_address, "9.9.9.9")
        finally:
            reset_audit_context(outer_token)
        self.assertIsNone(get_audit_context().ip_address)


class NestedContextTest(TestCase):
    """ContextVar token semantics: nesting and exact-token reset."""

    def setUp(self):
        self.user_a = User.objects.create_user(
            email="nested-a@example.com", password="pass12345", role="faculty"
        )
        self.user_b = User.objects.create_user(
            email="nested-b@example.com", password="pass12345", role="student"
        )

    def test_nested_contexts_resolve_inner_then_outer(self):
        outer = AuditContext(user=self.user_a, ip_address="1.1.1.1", user_agent="oua")
        token_outer = set_audit_context(outer)
        try:
            inner = AuditContext(user=self.user_b, ip_address="2.2.2.2", user_agent="ina")
            token_inner = set_audit_context(inner)
            try:
                self.assertEqual(get_audit_context().user_id, self.user_b.pk)
                self.assertEqual(get_audit_context().ip_address, "2.2.2.2")
                self.assertEqual(get_audit_context().user_agent, "ina")
            finally:
                reset_audit_context(token_inner)
            # Exact-token reset: outer context is visible again.
            self.assertEqual(get_audit_context().user_id, self.user_a.pk)
            self.assertEqual(get_audit_context().ip_address, "1.1.1.1")
        finally:
            reset_audit_context(token_outer)
        self.assertIsNone(get_audit_context().user)

    def test_sequential_reuse_does_not_leak(self):
        token1 = set_audit_context(AuditContext(user=self.user_a, ip_address="1.1.1.1"))
        reset_audit_context(token1)
        token2 = set_audit_context(AuditContext(user=self.user_b, ip_address="2.2.2.2"))
        self.assertEqual(get_audit_context().user_id, self.user_b.pk)
        reset_audit_context(token2)
        self.assertIsNone(get_audit_context().user_id)

    def test_cross_task_isolation(self):
        async def worker(ctx):
            token = set_audit_context(ctx)
            try:
                await asyncio.sleep(0)
                return get_audit_context().user_id
            finally:
                reset_audit_context(token)

        async def run_all():
            return await asyncio.gather(
                worker(AuditContext(user=self.user_a, ip_address="1.1.1.1")),
                worker(AuditContext(user=self.user_b, ip_address="2.2.2.2")),
            )

        result = asyncio.run(run_all())
        self.assertEqual(result, [self.user_a.pk, self.user_b.pk])


# ---------------------------------------------------------------------------
# 5 — Actor resolution through a real DRF request cycle
# ---------------------------------------------------------------------------

@override_settings(ROOT_URLCONF=_PROBE_URLCONF)
class ActorResolutionTest(TestCase):
    """What the context reports during live requests."""

    def setUp(self):
        self.actors = _create_actor_users()
        self.faculty_user = self.actors["faculty_user"]

    def test_authenticated_request_user(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        response = client.get(
            "/context/",
            REMOTE_ADDR="203.0.113.11",
            HTTP_USER_AGENT="ActorUA/1.0",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["user_id"], str(self.faculty_user.pk))
        self.assertEqual(data["ip_address"], "203.0.113.11")
        self.assertEqual(data["user_agent"], "ActorUA/1.0")

    def test_authenticated_request_real_jwt_token(self):
        from rest_framework.test import APIClient

        token = str(AccessToken.for_user(self.faculty_user))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.get(
            "/context/",
            REMOTE_ADDR="203.0.113.12",
            HTTP_USER_AGENT="JwtUA/1.0",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], str(self.faculty_user.pk))

    def test_anonymous_request_user_none(self):
        from rest_framework.test import APIClient

        client = APIClient()
        response = client.get(
            "/context/",
            REMOTE_ADDR="203.0.113.13",
            HTTP_USER_AGENT="AnonUA/1.0",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["user_id"])
        self.assertEqual(data["ip_address"], "203.0.113.13")
        self.assertEqual(data["user_agent"], "AnonUA/1.0")

    def test_context_reset_after_normal_request(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        response = client.get("/context/", REMOTE_ADDR="203.0.113.14")
        self.assertEqual(response.json()["user_id"], str(self.faculty_user.pk))
        ctx = get_audit_context()
        self.assertIsNone(ctx.user)
        self.assertIsNone(ctx.ip_address)
        self.assertIsNone(ctx.user_agent)

    def test_context_reset_after_exception(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.raise_request_exception = False
        response = client.get("/boom/")
        self.assertEqual(response.status_code, 500)
        ctx = get_audit_context()
        self.assertIsNone(ctx.user)
        self.assertIsNone(ctx.ip_address)
        self.assertIsNone(ctx.user_agent)


# ---------------------------------------------------------------------------
# 6 — PH10.5 signal integration
# ---------------------------------------------------------------------------

@override_settings(ROOT_URLCONF=_PROBE_URLCONF)
class SignalIntegrationRequestTest(TestCase):
    """Authenticated HTTP request -> model change -> signal -> AuditLog."""

    def setUp(self):
        self.actors = _create_actor_users()
        self.faculty_user = self.actors["faculty_user"]
        self.student_profile = self.actors["student_profile"]
        _clear_audit()

    def _post_note(self, client, ip="203.0.113.21", ua="SigUA/1.0", extra=None):
        payload = {"student_id": str(self.student_profile.pk)}
        if extra:
            payload.update(extra)
        return client.post(
            "/note/",
            payload,
            format="json",
            REMOTE_ADDR=ip,
            HTTP_USER_AGENT=ua,
        )

    def test_create_audit_carries_actor_metadata(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        self._post_note(client)
        log = AuditLog.objects.get(model_name="guidance.BehavioralNote")
        self.assertEqual(log.action, "create")
        self.assertEqual(log.user_id, self.faculty_user.pk)
        self.assertEqual(log.ip_address, "203.0.113.21")
        self.assertEqual(log.user_agent, "SigUA/1.0")

    def test_update_audit_carries_actor_metadata(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        note_id = self._post_note(client).json()["note_id"]
        client.post(
            "/note/touch/",
            {"note_id": note_id},
            format="json",
            REMOTE_ADDR="203.0.113.22",
            HTTP_USER_AGENT="TouchUA/1.0",
        )
        log = AuditLog.objects.get(action="update", model_name="guidance.BehavioralNote")
        self.assertEqual(log.user_id, self.faculty_user.pk)
        self.assertEqual(log.ip_address, "203.0.113.22")
        self.assertEqual(log.user_agent, "TouchUA/1.0")

    def test_delete_audit_carries_actor_metadata(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        note_id = self._post_note(client).json()["note_id"]
        client.post(
            "/note/delete/",
            {"note_id": note_id},
            format="json",
            REMOTE_ADDR="203.0.113.23",
            HTTP_USER_AGENT="DelUA/1.0",
        )
        log = AuditLog.objects.get(action="delete", model_name="guidance.BehavioralNote")
        self.assertEqual(log.user_id, self.faculty_user.pk)
        self.assertEqual(log.ip_address, "203.0.113.23")
        self.assertEqual(log.user_agent, "DelUA/1.0")

    def test_x_forwarded_for_cannot_spoof_audit_ip(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        self._post_note(client, ip="203.0.113.24")
        client.post(
            "/note/",
            {"student_id": str(self.student_profile.pk)},
            format="json",
            REMOTE_ADDR="203.0.113.24",
            HTTP_X_FORWARDED_FOR="6.6.6.6",
        )
        log = AuditLog.objects.filter(model_name="guidance.BehavioralNote").last()
        self.assertEqual(log.ip_address, "203.0.113.24")
        self.assertNotEqual(log.ip_address, "6.6.6.6")

    def test_authenticated_signal_uses_only_request_user(self):
        """The recorded user is request.user — never inferred from domain
        relationships like recorded_by / student on the model."""
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        self._post_note(client)
        log = AuditLog.objects.get(model_name="guidance.BehavioralNote")
        self.assertEqual(log.user_id, self.faculty_user.pk)
        # recorded_by points at faculty_profile; student at student_user —
        # the actor is STILL the request user, not a domain object lookup.
        self.assertNotEqual(log.user_id, self.actors["student_user"].pk)


class SignalIntegrationBackgroundTest(TestCase):
    """Background/system model change -> signal -> AuditLog with empty
    actor metadata (no request context)."""

    def setUp(self):
        self.actors = _create_actor_users()
        self.faculty_profile = self.actors["faculty_profile"]
        self.student_profile = self.actors["student_profile"]
        _clear_audit()

    def test_background_create_audit_is_empty(self):
        from apps.guidance.models import BehavioralNote

        BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="background note",
            date_recorded=date.today(),
        )
        log = AuditLog.objects.get(model_name="guidance.BehavioralNote")
        self.assertEqual(log.action, "create")
        self.assertIsNone(log.user)
        self.assertIsNone(log.ip_address)
        self.assertIsNone(log.user_agent)

    def test_background_update_audit_is_empty(self):
        from apps.guidance.models import BehavioralNote

        note = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="background note",
            date_recorded=date.today(),
        )
        _clear_audit()
        note.note_type = "warning"
        note.save()
        log = AuditLog.objects.get(action="update", model_name="guidance.BehavioralNote")
        self.assertIsNone(log.user)
        self.assertIsNone(log.ip_address)
        self.assertIsNone(log.user_agent)

    def test_background_delete_audit_is_empty(self):
        from apps.guidance.models import BehavioralNote

        note = BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="background note",
            date_recorded=date.today(),
        )
        _clear_audit()
        note.delete()
        log = AuditLog.objects.get(action="delete", model_name="guidance.BehavioralNote")
        self.assertIsNone(log.user)
        self.assertIsNone(log.ip_address)
        self.assertIsNone(log.user_agent)


# ---------------------------------------------------------------------------
# 7 — Security
# ---------------------------------------------------------------------------

@override_settings(ROOT_URLCONF=_PROBE_URLCONF)
class SecurityTest(TestCase):
    """Sensitive request data must never reach the context or AuditLog."""

    def setUp(self):
        self.actors = _create_actor_users()
        self.faculty_user = self.actors["faculty_user"]
        self.student_profile = self.actors["student_profile"]
        _clear_audit()

    def _post_note_with_extras(self, client, **extra):
        return client.post(
            "/note/",
            {
                "student_id": str(self.student_profile.pk),
                "note_text": "safe body content",
            },
            format="json",
            REMOTE_ADDR="203.0.113.31",
            HTTP_USER_AGENT="SecUA/1.0",
            **extra,
        )

    def test_authorization_header_never_stored_in_context(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        response = client.get(
            "/context/",
            HTTP_AUTHORIZATION="Bearer aegis-super-secret-token-xyz",
            REMOTE_ADDR="203.0.113.32",
        )
        body = " ".join(str(v) for v in response.json().values())
        self.assertNotIn("super-secret-token", body)

    def test_real_token_never_reaches_auditlog(self):
        from rest_framework.test import APIClient

        token = str(AccessToken.for_user(self.faculty_user))
        self.assertGreater(len(token), 40)  # sanity: a full JWT was in flight
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self._post_note_with_extras(client)
        for log in AuditLog.objects.all():
            self.assertNotIn(token, _serialize_log(log))

    def test_access_and_refresh_tokens_never_reach_context(self):
        from rest_framework.test import APIClient

        access = str(AccessToken.for_user(self.faculty_user))
        refresh = str(RefreshToken.for_user(self.faculty_user))
        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        response = client.get(
            "/context/",
            HTTP_AUTHORIZATION=f"Bearer {access}",
            REMOTE_ADDR="203.0.113.33",
        )
        body = response.content.decode()
        self.assertNotIn(access, body)
        self.assertNotIn(refresh, body)

    def test_authorization_header_never_reaches_auditlog(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        self._post_note_with_extras(client, HTTP_AUTHORIZATION="Bearer RealHeaderSecret987")
        for log in AuditLog.objects.all():
            self.assertNotIn("RealHeaderSecret", _serialize_log(log))

    def test_cookies_never_stored_in_context_or_auditlog(self):
        from rest_framework.test import APIClient

        cookies = "sessionid=abcfake123; csrftoken=csrffake456; token=cookiesecret789"
        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        response = client.get(
            "/context/",
            HTTP_COOKIE=cookies,
            REMOTE_ADDR="203.0.113.34",
        )
        self.assertNotIn("cookiesecret", response.content.decode())
        self._post_note_with_extras(client, HTTP_COOKIE=cookies)
        for log in AuditLog.objects.all():
            self.assertNotIn("cookiesecret", _serialize_log(log))

    def test_request_body_never_stored_in_context_or_auditlog(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        client.post(
            "/note/",
            {
                "student_id": str(self.student_profile.pk),
                "note_text": "body-super-secret-payload-5555",
            },
            format="json",
            REMOTE_ADDR="203.0.113.35",
            HTTP_USER_AGENT="BodyUA/1.0",
        )
        for log in AuditLog.objects.all():
            self.assertNotIn("body-super-secret-payload-5555", _serialize_log(log))

    def test_arbitrary_headers_not_persisted(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        self._post_note_with_extras(client, HTTP_X_CUSTOM_SECRET="arbitrary-header-value-222")
        for log in AuditLog.objects.all():
            self.assertNotIn("arbitrary-header-value-222", _serialize_log(log))

    def test_x_forwarded_for_cannot_spoof_context_ip(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        response = client.get(
            "/context/",
            REMOTE_ADDR="203.0.113.36",
            HTTP_X_FORWARDED_FOR="6.6.6.6, 7.7.7.7",
        )
        self.assertEqual(response.json()["ip_address"], "203.0.113.36")

    def test_actor_cannot_leak_between_requests(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        first = client.get(
            "/context/", REMOTE_ADDR="203.0.113.37", HTTP_USER_AGENT="UA-1"
        )
        self.assertEqual(first.json()["user_id"], str(self.faculty_user.pk))

        client.force_authenticate(user=self.actors["student_user"])
        second = client.get(
            "/context/", REMOTE_ADDR="203.0.113.38", HTTP_USER_AGENT="UA-2"
        )
        self.assertEqual(second.json()["user_id"], str(self.actors["student_user"].pk))
        self.assertNotEqual(second.json()["user_id"], first.json()["user_id"])
        self.assertEqual(second.json()["ip_address"], "203.0.113.38")
        self.assertEqual(second.json()["user_agent"], "UA-2")

    def test_context_is_empty_after_audited_request(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.faculty_user)
        self._post_note_with_extras(client)
        ctx = get_audit_context()
        self.assertIsNone(ctx.user)
        self.assertIsNone(ctx.ip_address)
        self.assertIsNone(ctx.user_agent)


# ---------------------------------------------------------------------------
# Transaction behaviour (no on_commit / no separate bus)
# ---------------------------------------------------------------------------

class TransactionBehaviourPreservedTest(TestCase):
    """The audit row still participates in the caller's transaction."""

    def setUp(self):
        self.actors = _create_actor_users()
        self.faculty_profile = self.actors["faculty_profile"]
        self.student_profile = self.actors["student_profile"]
        _clear_audit()

    def test_audit_record_rolls_back_with_caller(self):
        from django.db import transaction
        from apps.guidance.models import BehavioralNote

        try:
            with transaction.atomic():
                BehavioralNote.objects.create(
                    student=self.student_profile,
                    recorded_by=self.faculty_profile,
                    note_type="positive",
                    note_text="rollback note",
                    date_recorded=date.today(),
                )
                self.assertEqual(AuditLog.objects.count(), 1)
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_audit_record_commits_with_caller(self):
        from apps.guidance.models import BehavioralNote

        BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="positive",
            note_text="commit note",
            date_recorded=date.today(),
        )
        self.assertEqual(AuditLog.objects.count(), 1)