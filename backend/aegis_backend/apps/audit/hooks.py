"""
PH10.7 — Authentication event hooks, PH11 account-administration hook.

Thin integration points that connect existing AEGIS flows to the PH10.4
central audit service.  Three functions, three call-sites:

- ``audit_successful_login(user)``  — called from
  ``AegisTokenObtainPairSerializer.validate()`` after token issuance.
- ``audit_successful_logout()``     — called from
  ``LogoutView.post()`` after refresh-token blacklisting succeeds.
- ``audit_account_access_change(old, new)`` — called from
  ``UserDetailView.patch()`` after an administrator changes an account's
  role or active state (PH11 / TC-ADM-10).

Design constraints
------------------
- Each successful event produces EXACTLY ONE AuditLog row.
- The audit side-effect is fire-and-forget: success is not conditional
  on the audit write, and audit failure does not prevent the operation
  from succeeding.  Any exception raised by the audit write is caught,
  logged internally (without tokens, passwords, or credentials), and not
  re-raised.
- No tokens, passwords, credentials, or request/response bodies are
  stored in AuditLog.  The account-update diff is limited to the
  PH10.2 allowlist for ``accounts.User``, which holds only ``role`` and
  ``is_active`` — never identity or credential fields.
- PH10.6 ``get_audit_context()`` supplies the actor, IP and user-agent.
  For LOGIN the authenticated user is passed explicitly because the
  PH10.6 context still holds an anonymous actor at the point of
  token issuance (DRF authentication has not run yet on a login POST).
"""

import logging

from apps.audit.context import get_audit_context
from apps.audit.services import record_audit, AUTH_EVENT_MODEL_NAME

logger = logging.getLogger(__name__)


def audit_successful_login(user):
    """Record a LOGIN audit event after successful token issuance.

    Parameters
    ----------
    user : accounts.User
        The authenticated user whose credentials just succeeded.  Passed
        explicitly because the PH10.6 request context still holds the
        anonymous actor at this point in the SimpleJWT pipeline.

    The audit write is isolated: if it raises, the failure is logged
    internally and NOT re-raised, so successful token issuance always
    completes.  Only the audit side-effect is guarded — the caller's
    authentication exception path is untouched.
    """
    context = get_audit_context()
    try:
        record_audit(
            action="login",
            user=user,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            model_name=AUTH_EVENT_MODEL_NAME,
            object_repr="Login",
        )
    except Exception:
        logger.exception("LOGIN audit record failed (authentication outcome unchanged)")


def audit_successful_logout():
    """Record a LOGOUT audit event after refresh-token blacklisting.

    Called from LogoutView.post() after token.blacklist() succeeds.
    The PH10.6 context holds the correct authenticated actor, IP, and
    user-agent because the request passed through DRF authentication
    before reaching the logout view.

    Token revocation is authoritative and performed by the caller BEFORE
    this hook.  The audit write here is isolated: if it raises, the
    failure is logged internally and NOT re-raised, so the successful
    logout response is still returned and the blacklisting is not undone.
    """
    context = get_audit_context()
    try:
        record_audit(
            action="logout",
            user=context.user,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            model_name=AUTH_EVENT_MODEL_NAME,
            object_repr="Logout",
        )
    except Exception:
        logger.exception("LOGOUT audit record failed (revocation outcome unchanged)")


def audit_account_access_change(old_instance, new_instance):
    """Record an UPDATE event after an administrator changes an account.

    Called from ``UserDetailView.patch()`` once the write has succeeded and
    only when ``role`` or ``is_active`` actually moved, so a PATCH that
    changes nothing produces no audit row.

    Parameters
    ----------
    old_instance : accounts.User
        Pre-change snapshot taken before the write.
    new_instance : accounts.User
        The account as saved.

    The audit write is isolated: if it raises, the failure is logged
    internally and NOT re-raised, so account administration still
    completes.  The stored diff is limited by the PH10.2 allowlist for
    ``accounts.User`` — ``role`` and ``is_active`` only; identity and
    credential fields are never serialized into ``AuditLog.changes``.
    """
    context = get_audit_context()
    try:
        record_audit(
            action="update",
            old_instance=old_instance,
            new_instance=new_instance,
            user=context.user,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        )
    except Exception:
        logger.exception(
            "ACCOUNT UPDATE audit record failed (account change unchanged)"
        )
