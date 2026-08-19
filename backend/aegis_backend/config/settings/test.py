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

DEBUG = False
