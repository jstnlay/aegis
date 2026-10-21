"""
Test settings for AEGIS Backend.

Uses SQLite so the test suite runs without requiring a live PostgreSQL
connection.  The normal development database (PostgreSQL) is unchanged;
this file is invoked explicitly via:
    python manage.py test --settings=config.settings.test
"""

from .base import *  # noqa: F401, F403

from django.contrib.auth.hashers import PBKDF2PasswordHasher

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
#
# Test-only: see ``TestPBKDF2PasswordHasher`` below for why this cannot be the
# stock hasher.  This list is referenced ONLY by this module; base.py,
# development.py and production.py are untouched and keep Django's default
# PBKDF2PasswordHasher at its full 1,500,000 iterations.
PASSWORD_HASHERS = [
    "config.settings.test.TestPBKDF2PasswordHasher",
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
        "data_import": "1000000/min",
        "data_export": "1000000/min",
        "password_change": "1000000/min",
        "password_forgot": "1000000/min",
        "password_reset": "1000000/min",
        "registration": "1000000/min",
        "parent_invitation": "1000000/min",
        "health": "1000000/min",
    },
}

DEBUG = False


# ---------------------------------------------------------------------------
# Test-only password hasher
# ---------------------------------------------------------------------------
#
# Why this exists
# ---------------
# The suite creates its fixture users inside ``setUp()``, so Django rebuilds
# them for every individual test method rather than once per class. Nearly
# every app test file does this (for example ``GuidanceTestBase.setUp``
# creates eight users and 21 of 22 classes in apps/guidance/tests.py inherit
# it). Each ``create_user(password=...)`` is one PBKDF2-SHA256 hash at
# Django's default 1,500,000 iterations, measured at roughly 1.76 s per hash
# on the development machine. Across ~1,400 tests that fixture construction,
# not the test logic and not SQLite, dominated the wall clock and pushed a
# full run past two hours.
#
# Why it is a subclass rather than MD5PasswordHasher
# -------------------------------------------------
# ``PBKDF2PasswordHasher`` takes its iteration count as a constructor
# argument, and Django settings may only reference a hasher by dotted path, so
# the cost cannot be lowered from settings alone. Subclassing is the
# documented way to do it. Substituting ``MD5PasswordHasher`` would be faster
# still but would change the stored prefix to ``md5$``, breaking the existing
# regression test in apps/accounts/tests.py that asserts a stored password
# begins with ``pbkdf2_sha256$``. Keeping the algorithm and lowering only the
# iteration count preserves that expectation, so no test has to be weakened.
#
# Why 10,000
# ----------
# Measured on the development machine:
#     1,500,000 iterations -> ~1.76 s per hash (Django's production default)
#        360,000 iterations -> ~0.40 s per hash
#         10,000 iterations -> ~0.010 s per hash
# 10,000 removes ~99.4% of the hashing cost while leaving PBKDF2-SHA256 - the
# same KDF family, salt handling and algorithm identifier as production - so
# every test still exercises real hash/verify/upgrade code paths.
#
# Scope
# -----
# Tests never assert an iteration count, and no security behaviour depends on
# KDF strength: SEC-002 covers login/token throttling, SEC-008 covers result
# immutability, and the password tests cover verification, hashing, the
# ``must_change_password`` onboarding flag and the validators. None of them
# becomes vacuous at a lower cost. The reduced cost never reaches production.
class TestPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    """PBKDF2-SHA256 with a reduced iteration count. Tests only."""

    iterations = 10_000
