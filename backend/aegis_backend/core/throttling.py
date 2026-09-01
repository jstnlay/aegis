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
