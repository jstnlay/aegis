"""
Centralized DRF throttle classes for AEGIS security-sensitive endpoints.

Rates are configured once in settings via REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
keyed by each class's ``scope``. Throttling is an additional defense-in-depth
layer on top of authentication/authorization, never a replacement.

Login throttling keys on client IP (AnonRateThrottle.get_ident), NOT on the
submitted email, so attackers cannot rotate usernames to evade the limit.
Throttle responses never reveal whether an account exists.
"""

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle

import hashlib


class LoginRateThrottle(AnonRateThrottle):
    """Per-client-IP cap on login attempts (scope: "login")."""

    scope = "login"


class TokenRefreshRateThrottle(AnonRateThrottle):
    """Per-client-IP cap on JWT refresh requests (scope: "token_refresh")."""

    scope = "token_refresh"


class WebhookRateThrottle(SimpleRateThrottle):
    """
    Per-source-IP request cap on the Strapi webhook receiver
    (scope: "webhook").

    SimpleRateThrottle is used instead of AnonRateThrottle so the cap
    applies regardless of authentication state, keyed by client IP.
    This bounds the notification fan-out amplification of forged/replayed
    deliveries as defense-in-depth behind the shared-secret check.
    """

    scope = "webhook"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class DataImportRateThrottle(SimpleRateThrottle):
    """
    Per-client-IP cap on data-import job uploads (scope: "data_import").

    Import workflows parse untrusted files row-by-row, so they are more
    expensive than typical API calls. A dedicated, lower-than-global cap
    bounds resource use against runaway/scanner clients as defense-in-depth
    behind authentication and role authorization.

    SimpleRateThrottle is used (like WebhookRateThrottle) so the cap applies
    regardless of authentication state, keyed by client IP. An
    AnonRateThrottle would never fire here because every import upload is
    authenticated.
    """

    scope = "data_import"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class ExportRateThrottle(SimpleRateThrottle):
    """
    Per-client-IP cap on controlled-export file downloads (scope: "data_export").

    Export endpoints generate complete file responses (CSV/XLSX) that can be
    computationally expensive for large datasets. A dedicated, lower-than-global
    cap bounds resource use as defense-in-depth behind authentication and
    role authorization.

    SimpleRateThrottle is used so the cap applies regardless of authentication
    state, keyed by client IP.
    """

    scope = "data_export"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class PasswordChangeRateThrottle(SimpleRateThrottle):
    """
    Per-account cap on self-service password changes (scope: "password_change").

    The endpoint verifies the *current* password before accepting a new one,
    so an unauthenticated attacker cannot use it. It is not the only door
    though: anyone holding a stolen access token can call it as often as the
    network allows and brute-force the current password, which is the one
    secret the token does not carry. A per-account cap bounds that to a
    handful of guesses a minute.

    The key is the account, not the client IP: the threat model is one
    compromised token, and a shared office IP must not lock out every
    account behind it. An anonymous request falls back to the client IP.
    """

    scope = "password_change"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            ident = f"user:{user.pk}"
        else:
            ident = f"ip:{self.get_ident(request)}"
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


class PasswordForgotRateThrottle(SimpleRateThrottle):
    """
    Per-client-IP cap on password reset requests (scope: "password_forgot").

    Each request may send an email, so the cap bounds how much mail a
    stranger can make the school send. It is keyed on the client IP because
    the request is anonymous by definition.
    """

    scope = "password_forgot"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class PasswordResetRateThrottle(SimpleRateThrottle):
    """
    Per-token cap on password reset redemptions (scope: "password_reset").

    The token is the credential, so the cap is keyed on the token rather than
    on the client: guessing is pointless without a token, and a legitimate
    recipient mistyping their new password is not an attack. An unknown token
    falls back to the client IP so that a flood of random tokens is still
    bounded.
    """

    scope = "password_reset"

    def get_cache_key(self, request, view):
        raw_token = ""
        data = getattr(request, "data", None) or {}
        if isinstance(data, dict):
            raw_token = str(data.get("token") or "")
        if raw_token:
            ident = f"token:{hashlib.sha256(raw_token.encode('utf-8')).hexdigest()}"
        else:
            ident = f"ip:{self.get_ident(request)}"
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


class RegistrationRateThrottle(SimpleRateThrottle):
    """
    Per-client-IP cap on registration submissions (scope: "registration").

    Each submission may send a verification email, and an open form is an
    invitation to flood the school's inbox. The cap is keyed on the client
    IP because the request is anonymous.
    """

    scope = "registration"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class ParentInvitationRateThrottle(SimpleRateThrottle):
    """
    Per-client-IP cap on parent nominations (scope: "parent_invitation").

    A nomination is a request that reaches an administrator's queue, so the
    cap bounds how much of the school's attention one client can ask for.
    """

    scope = "parent_invitation"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
