"""
PH10.7 — Authentication event hooks.

Thin integration points that connect existing AEGIS authentication flows
to the PH10.4 central audit service.  Two functions, two call-sites:

- ``audit_successful_login(user)``  — called from
  ``AegisTokenObtainPairSerializer.validate()`` after token issuance.
- ``audit_successful_logout()``     — called from
  ``LogoutView.post()`` after refresh-token blacklisting succeeds.

Design constraints
------------------
- Each successful authentication event produces EXACTLY ONE AuditLog row.
- The audit side-effect is fire-and-forget: success is not conditional
  on the audit write, and audit failure does not prevent authentication
  from succeeding.  Any exception raised by the audit write is caught,
  logged internally (without tokens, passwords, or credentials), and not
  re-raised.
- No tokens, passwords, credentials, or request/response bodies are
  stored in AuditLog.
- PH10.6 ``get_audit_context()`` supplies IP and user-agent for both
  hooks.  For LOGIN the authenticated user is passed explicitly because
  the PH10.6 context still holds an anonymous actor at the point of
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
