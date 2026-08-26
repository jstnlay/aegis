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
