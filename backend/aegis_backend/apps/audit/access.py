"""
PH10.8 — Sensitive-data ACCESS event hook.

Records an ``access`` AuditLog event for a *successfully authorized* read
of a sensitive domain object, through the PH10.4 central audit service:

    Request
      |
      v
    authentication
      |
      v
    authorization / queryset scoping
      |
      v
    object successfully accessible
      |
      v
    record_object_access(instance)      (this module)
      |
      v
    record_audit(action="access")       (PH10.4)
      |
      v
    AuditLog

Design constraints
------------------
- ACCESS is a *side effect of a successful read*, never an authorization
  gate.  This helper MUST be called only after authentication,
  authorization, and queryset scoping have all succeeded — typically
  immediately after a view's ``self.get_object()`` returns.  It is never
  called before permission checks and never for hidden/404 targets.
- The audit write is error-isolated (fail-open, the PH10.7 philosophy):
  if ``record_audit`` raises, the failure is logged internally and never
  re-raised, so a successful authorized data response is never converted
  into a failure because of an audit hiccup.
- Exactly ONE AuditLog row is created per call.  Views call this exactly
  once per canonical sensitive-object read, so one successful retrieval
  produces exactly one ACCESS event (no serializer / nested-path / list
  duplication).
- Only target METADATA is stored: ``model_name``, ``object_id`` and a
  PII-free ``object_repr`` (``<ModelName>:<UUID>``) derived by PH10.4.
  The sensitive content being viewed (note text, session notes,
  recommendations, risk factors, assessment answers, tokens, headers) is
  NEVER copied into the audit record.  ``changes`` is always NULL — the
  purpose of ACCESS is "who accessed what", not "what did they read".
- The actor (user), IP address and user-agent come exclusively from the
  PH10.6 request context via ``get_audit_context()``.  No new ContextVar,
  no request-header inspection, no duplicate extraction.  Background /
  non-HTTP reads would legitimately record ``user=None``, but no
  synthetic background ACCESS events are produced here.
"""

import logging

from apps.audit.context import get_audit_context
from apps.audit.services import record_audit

logger = logging.getLogger(__name__)


def record_object_access(instance):
    """Record the authorized read of one sensitive object as one ACCESS event.

    Parameters
    ----------
    instance : Model
        The sensitive domain object whose successful retrieval is being
        audited.  Its model metadata and primary key drive the safe
        ``model_name`` / ``object_id`` / ``object_repr`` values computed
        by the PH10.4 service.  The instance's field *values* are never
        serialized into the audit record.

    Notes
    -----
    Call exactly once per canonical sensitive read, and only after access
    has been authorized.  The write is fail-open: any audit failure is
    logged and swallowed so the already-authorized read still succeeds.
    """
    context = get_audit_context()
    try:
        record_audit(
            action="access",
            instance=instance,
            user=context.user,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        )
    except Exception:
        meta = getattr(instance, "_meta", None)
        label = meta.label if meta is not None else None
        logger.exception(
            "ACCESS audit record failed for %s (read outcome unchanged)",
            label or "unknown",
        )