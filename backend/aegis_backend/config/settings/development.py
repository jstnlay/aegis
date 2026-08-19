"""
Development settings for AEGIS Backend.

Database is PostgreSQL, configured entirely via environment variables.
See .env.example for the required variables (DATABASE_NAME, DATABASE_USER,
DATABASE_PASSWORD, DATABASE_HOST, DATABASE_PORT).  Works with a local
PostgreSQL instance or a Supabase-hosted database.
"""

from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Development-specific overrides
# ---------------------------------------------------------------------------

DEBUG = True

# Allow all hosts in development
ALLOWED_HOSTS = ["*"]

# Database: inherits PostgreSQL config from base.py (env-var driven).
# No SQLite fallback — PostgreSQL is the normal development database.

# Browsable API in development
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Email backend for development (console output)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
