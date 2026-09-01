"""
AEGIS JWT authentication (PH8.7 onboarding gate).

The default SimpleJWT authentication is extended with a single, additive
onboarding check: a user who was provisioned with temporary credentials
(``User.must_change_password = True``) may authenticate and obtain tokens,
but every protected endpoint except the password-change / logout routes
returns 401 (PASSWORD_CHANGE_REQUIRED) until the initial password change
clears the flag.

This reuses the existing SimpleJWT pipeline exactly — no token format,
claim, or refresh semantics are changed.  Users with the flag unset (the
default) are completely unaffected.
"""

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


#: Onboarding routes a must-change-password user may still reach.
#: Everything else is gated until the initial password change completes.
_ONBOARDING_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/accounts/password/change/",
        "/api/v1/auth/logout/",
    }
)

#: Safe, hand-picked message. Never echoes account or token internals.
_PASSWORD_CHANGE_REQUIRED_DETAIL = "Password change required."


class AegisJWTAuthentication(JWTAuthentication):
    """JWT auth plus the initial-password-change onboarding gate."""

    def authenticate(self, request):
        # None -> anonymous request (login/refresh/logout with no header).
        result = super().authenticate(request)
        if result is None:
            return None

        user, token = result
        if user.must_change_password and request.path not in _ONBOARDING_EXEMPT_PATHS:
            raise AuthenticationFailed(
                {"detail": _PASSWORD_CHANGE_REQUIRED_DETAIL}
            )
        return result