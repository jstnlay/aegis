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

# Email backend: the console default comes from base.py (no mail leaves a
# local dev machine). A deployment that sets EMAIL_BACKEND plus the
# EMAIL_HOST/PORT/USER/PASSWORD/USE_TLS values gets real delivery from the
# same base code — the DEV/QA service deploys these settings, so
# development.py must not hardcode the backend here or the provider config
# would be silently ignored.

# ---------------------------------------------------------------------------
# Strapi CMS integration secrets (Phase 7)
#
# The Strapi bootstrap writes its read-only API token into cms/.env and
# the shared webhook secret lives there too. Load them as a fallback when
# they are not already provided by the environment / backend .env.
# Values are consumed server-side only.
# ---------------------------------------------------------------------------

from pathlib import Path as _Path

from decouple import Config as _Config, RepositoryEnv as _RepositoryEnv

_CMS_ENV_FILE = _Path(__file__).resolve().parents[4] / "cms" / ".env"

if not STRAPI_API_TOKEN or not STRAPI_WEBHOOK_SECRET:  # noqa: F405
    if _CMS_ENV_FILE.exists():
        _cms_env = _Config(_RepositoryEnv(str(_CMS_ENV_FILE)))
        if not STRAPI_API_TOKEN:  # noqa: F405
            STRAPI_API_TOKEN = _cms_env("STRAPI_API_TOKEN", default="")  # noqa: F405
        if not STRAPI_WEBHOOK_SECRET:  # noqa: F405
            STRAPI_WEBHOOK_SECRET = _cms_env(  # noqa: F405
                "AEGIS_WEBHOOK_SECRET", default=""
            )
