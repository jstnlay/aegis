"""
Test settings for AEGIS Backend.

Uses SQLite so the test suite runs without requiring a live PostgreSQL
connection.  The normal development database (PostgreSQL) is unchanged;
this file is invoked explicitly via:
    python manage.py test --settings=config.settings.test
"""

from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Override database for testing
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# ---------------------------------------------------------------------------
# Speed up password hashing in tests
# ---------------------------------------------------------------------------

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# ---------------------------------------------------------------------------
# Throttling during tests
#
# Throttle classes remain enabled so every request still exercises the real
# throttling code path, but the configured rates are effectively unreachable.
# This keeps the 347+-test suite deterministic: DRF's LocalMemCache throttle
# history persists across tests within a process, and realistic production
# rates (e.g. login 15/min per IP) would trip as tests accumulate anonymous
# requests from the shared test client IP. SEC-002 regression tests install
# tight rates via override_settings() and clear the cache to verify actual
# 429 behavior end-to-end. Production/development rates are unaffected.
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "anon": "1000000/min",
        "user": "1000000/min",
        "login": "1000000/min",
        "token_refresh": "1000000/min",
        "webhook": "1000000/min",
    },
}

DEBUG = False
