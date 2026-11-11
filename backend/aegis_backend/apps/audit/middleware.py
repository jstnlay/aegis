"""
PH10.6 — Audit context middleware.

Establishes the request-scoped audit ContextVar for every HTTP request:

    HTTP request
        |
        v
    AuditContextMiddleware       (this module)
        |
        v
    Domain operation -> PH10.5 signal -> record_audit()
        |
        v
    AuditLog

Placement
---------
Registered immediately after ``django.contrib.auth.middleware.
AuthenticationMiddleware``.  It deliberately does NOT resolve the actor
eagerly: DRF authentication is lazy (``AegisJWTAuthentication`` runs
inside the view cycle via ``request.user``), so the user is resolved
only when a PH10.5 signal demands ``get_audit_context().user`` — by then
DRF has already populated ``request.user``.  No duplicate authentication
is forced and no middleware runs before the CSRF / session machinery it
must tolerate.

Guarantees
----------
- The context token returned by ``ContextVar.set()`` is reset in a
  ``finally`` block, so normal responses, exceptions, and downstream
  middleware failures all tear the context down.
- Only the client address is recorded for the IP, and never a value the
  client chose. ``X-Forwarded-For`` is ignored: it is a header the client
  writes. The CDN's own client-IP header is used when it is present,
  because the CDN overwrites it on every request it forwards - without it
  the recorded address would be the CDN's edge, which is the same for every
  request and identifies nobody.
- The request object is not stored: only a weak reference feeds the lazy
  actor cell, and IP / user-agent are captured as plain values.
"""

from apps.audit.context import AuditContext, _LazyUser, set_audit_context, reset_audit_context
from core.client_ip import client_address


class AuditContextMiddleware:
    """Populate and tear down the request-scoped PH10.6 audit context."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        context = AuditContext(
            user=_LazyUser(request),
            ip_address=_ip_address(request),
            user_agent=_user_agent(request),
        )
        token = set_audit_context(context)
        try:
            return self.get_response(request)
        finally:
            reset_audit_context(token)


def _ip_address(request):
    """The client address. Proxy headers written by the client are never trusted."""
    return client_address(request) or None


def _user_agent(request):
    """Raw user-agent string, or None when the client sent none."""
    user_agent = request.META.get("HTTP_USER_AGENT")
    if not user_agent:
        return None
    return user_agent