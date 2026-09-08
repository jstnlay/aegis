"""
PH10.6 — Request / actor context (contextvars.ContextVar).

A tiny, request-scoped context that lets the PH10.5 signal layer and any
other PH10 code learn the *actor* behind an event without coupling to
HTTP, Django middleware, or DRF.

Stored per request (execution context):

- ``user``       : the authenticated actor, or None.
- ``ip_address`` : direct client address from ``REMOTE_ADDR``, or None.
- ``user_agent`` : the raw ``HTTP_USER_AGENT`` string, or None.

NOT stored: the request object, headers, authorization token, cookies,
request/response bodies, or any secret.  The only request-derived value
is the three fields above.

Isolation
---------
A :class:`contextvars.ContextVar` provides full execution-context
isolation: request A can never observe request B's context, nested
requests (e.g. subrequests) get their own token, exceptions cannot leak
context, and async code sees the context its own task created.  The
middleware stores the exact token returned by ``set()`` and ALWAYS
resets it in ``finally``.

No-request behaviour
--------------------
Outside any HTTP request (management commands, AI/background jobs,
tests, signal fixtures) ``get_audit_context()`` returns a fresh empty
context: ``user=None``, ``ip_address=None``, ``user_agent=None``.

Actor resolution
----------------
The middleware seeds ``user`` with a lazy resolver that, on first
demand, reads ``request.user`` and keeps only values whose
``is_authenticated`` is ``True`` (`request.user.is_authenticated`).  DRF
performs authentication *inside* the view cycle, so the resolver is only
ever demanded by model signals that fire after authentication has
populated ``request.user`` — no authentication is forced and no global
mutable state is used.
"""

import contextvars
import weakref


# ---------------------------------------------------------------------------
# Lazy actor resolver (middleware only)
# ---------------------------------------------------------------------------

class _LazyUser:
    """Deferred actor cell: resolves ``request.user`` on first demand.

    Holds only a *weak* reference to the underlying request, so the
    context never keeps a finished request object alive and no request is
    ever stored strongly inside the context.  After the request completes
    (or if it is garbage-collected) the resolver returns ``None``.
    """

    __slots__ = ("_request_ref",)

    def __init__(self, request):
        self._request_ref = weakref.ref(request)

    def __call__(self):
        request = self._request_ref()
        if request is None:
            return None
        return getattr(request, "user", None)


# ---------------------------------------------------------------------------
# AuditContext value object
# ---------------------------------------------------------------------------

class AuditContext:
    """Immutable-by-convention, request-scoped actor metadata.

    Parameters
    ----------
    user : accounts.User or None
        The authenticated actor.  May also be a ``_LazyUser`` resolver
        (currently only the middleware uses this).  Anonymous / not
        authenticated values resolve to ``None``.
    ip_address : str or None
        Direct client address from ``REMOTE_ADDR``.
    user_agent : str or None
        Raw ``HTTP_USER_AGENT`` string.
    """

    __slots__ = ("_user", "ip_address", "user_agent")

    def __init__(self, *, user=None, ip_address=None, user_agent=None):
        self._user = user
        self.ip_address = ip_address
        self.user_agent = user_agent

    @property
    def user(self):
        """The authenticated actor or None.

        Lazy resolvers are demanded here (first access resolves the
        actor); every other value is normalised so that an anonymous or
        non-authenticated user becomes ``None``.  Domain relationships
        (counselor, student, encoded_by, ...) are never consulted — only
        ``request.user`` semantics.
        """
        value = self._user
        if isinstance(value, _LazyUser):
            value = value()
        if value is None:
            return None
        if getattr(value, "is_authenticated", False) is True:
            return value
        return None

    @property
    def user_id(self):
        """Primary key of the authenticated actor, or None."""
        user = self.user
        return getattr(user, "pk", None)

    def __repr__(self):
        return (
            "AuditContext("
            f"user_id={self.user_id!r}, "
            f"ip_address={self.ip_address!r}, "
            f"user_agent={self.user_agent!r})"
        )


# ---------------------------------------------------------------------------
# ContextVar + tiny public accessor API
# ---------------------------------------------------------------------------

_AUDIT_CONTEXT = contextvars.ContextVar(
    "aegis_audit_context",
    default=None,
)
"""The single request-scoped audit context slot.

Internal.  Enforced through :func:`set_audit_context` /
:func:`reset_audit_context`; NEVER mutated in place by signals.
"""


def get_audit_context():
    """Return the current audit context (never None).

    Outside a request (or after a reset) an empty context is returned:
    ``user=None``, ``ip_address=None``, ``user_agent=None``.  This is the
    safe accessor signals and services use; they must never touch
    :data:`_AUDIT_CONTEXT` directly.
    """
    context = _AUDIT_CONTEXT.get()
    if context is None:
        return AuditContext()
    return context


def set_audit_context(context):
    """Bind *context* to the current execution context.

    Returns the token that must be passed to
    :func:`reset_audit_context` (in a ``finally`` block) so the exact
    context set here is always torn down.
    """
    return _AUDIT_CONTEXT.set(context)


def reset_audit_context(token):
    """Reset the exact context token produced by :func:`set_audit_context`."""
    _AUDIT_CONTEXT.reset(token)