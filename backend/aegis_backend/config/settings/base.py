"""
Django base settings for AEGIS Backend.

Environment-agnostic settings. Environment-specific overrides
go in development.py or production.py.
"""

import logging
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY")

DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="", cast=Csv())

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.academics",  # Stub models needed by accounts FK references
    "apps.attendance",
    "apps.guidance",
    "apps.assessments",
    "apps.analytics",  # PH9: role-controlled analytics aggregation API
    # Recommendations: the HTTP surface for ai_engine/recommender.py, which is
    # a pure computation package with no routes of its own.
    "apps.recommendations",
    "apps.cms",  # Phase 7: Strapi integration adapter (webhook + read-through proxy)
    "apps.data_import",  # Phase 8: CSV/XLSX data import + controlled export
    "apps.notifications",
    "apps.chatbot",  # PH9: chatbot service boundary + deterministic layer
    "apps.audit",  # PH10: audit trail domain model
    "apps.portfolio",  # Student-authored showcase entries (text + link, no file storage)
]

# AI Engine: pure computation layer (feature/label/risk/benchmark/recommend).
# Registered as an installed app so its management commands are discoverable.
LOCAL_APPS.append("ai_engine")

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # PH10.6: request-scoped audit context. Runs after AuthenticationMiddleware
    # so the actor cell can safely read request.user lazily (DRF JWT auth is
    # performed inside the view cycle; the ContextVar is reset in a finally
    # block, so placement after session/CSRF/auth middleware is safe while
    # the resolved context always reflects the authenticated DRF user).
    "apps.audit.middleware.AuditContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ---------------------------------------------------------------------------
# URL configuration
# ---------------------------------------------------------------------------

ROOT_URLCONF = "config.urls"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database - PostgreSQL via environment variables
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DATABASE_NAME", default="aegis_db"),
        "USER": config("DATABASE_USER", default="postgres"),
        "PASSWORD": config("DATABASE_PASSWORD", default=""),
        "HOST": config("DATABASE_HOST", default="localhost"),
        "PORT": config("DATABASE_PORT", default="5432"),
        # Persistent connections. Without this, Django opens and closes a
        # PostgreSQL connection per request, which is a handshake on every
        # API call and the first thing that runs out of database
        # connections under load. 60 seconds is inside the lifetime of a
        # typical proxy/pooler idle timeout, and the health check drops a
        # connection the server has already closed instead of failing a
        # request on it.
        "CONN_MAX_AGE": config("DATABASE_CONN_MAX_AGE", default=60, cast=int),
        "CONN_HEALTH_CHECKS": True,
    }
}

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
#
# The default cache is used by DRF throttling, so the rate limits that protect
# login, refresh, import, export, password change and registration are
# enforced through it.
#
# The built-in local-memory cache is per-process: with more than one worker
# or instance the effective limit is multiplied by the number of processes.
# That is acceptable for a single-process deployment and wrong for a scaled
# one.
#
# So the backend is named explicitly here, and a shared cache is one
# environment variable away. With `REDIS_URL` set and `django-redis`
# installed, every worker shares one throttle history and the limits hold
# however many workers there are. Without it, they hold per process.
# ---------------------------------------------------------------------------

REDIS_URL = config("REDIS_URL", default="")


def _default_cache():
    if REDIS_URL:
        try:
            import django_redis  # noqa: F401
        except ImportError:
            logging.getLogger(__name__).warning(
                "REDIS_URL is set but django-redis is not installed. The "
                "throttle limits fall back to the per-process local cache, so "
                "they are multiplied by the number of workers. Install "
                "django-redis, or unset REDIS_URL if this deployment runs a "
                "single worker."
            )
        else:
            return {
                "BACKEND": "django_redis.cache.RedisCache",
                "LOCATION": REDIS_URL,
                "OPTIONS": {
                    "CLIENT_CLASS": "django_redis.client.DefaultClient",
                    # A Redis outage must not take the API down with it. With
                    # this, a cache that cannot be reached is treated as an
                    # empty cache: the request is served, and the rate limit
                    # for that window is not enforced. 500s on every request
                    # would be a worse failure than a briefly unenforced
                    # limit.
                    "IGNORE_EXCEPTIONS": True,
                },
                "TIMEOUT": 300,
            }
    return {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "aegis-default-cache",
        "TIMEOUT": 300,
    }


CACHES = {"default": _default_cache()}

# ---------------------------------------------------------------------------
# Custom User Model
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Media files
# ---------------------------------------------------------------------------

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Upload limits (Phase 8: data import)
#
# Uploaded files are untrusted input. DATA_UPLOAD_MAX_MEMORY_SIZE bounds the
# request body at the server level before any app-level validation. It is
# sized to match apps.data_import.constants.MAX_IMPORT_FILE_SIZE (10 MB) so
# legitimate CSVs/XLSXs are accepted while runaway bodies are rejected (413).
# ---------------------------------------------------------------------------

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Extended SimpleJWT pipeline: identical token semantics, plus the
        # PH8.7 initial-password-change onboarding gate (must_change_password).
        "core.authentication.AegisJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Global ceilings (defense against runaway clients/scanners).
        "anon": "120/min",
        "user": "600/min",
        # Endpoint-specific high-risk caps (core/throttling.py scopes).
        "login": "15/min",
        "token_refresh": "30/min",
        "webhook": "60/min",
        # Data-import uploads are expensive (parsing + row validation).
        # Lower-than-global cap to bound resource use (Phase 8).
        "data_import": "30/min",
        # Controlled-export file downloads (PH8.8).
        "data_export": "60/min",
        # Health and readiness probes. Anonymous and cheap, but the readiness
        # probe opens a database connection, so the cap stops it from being
        # a denial-of-service amplifier.
        "health": "120/min",
        # Self-service password changes. The endpoint checks the current
        # password, so this is the cap on how often a stolen access token may
        # try to guess it.
        "password_change": "10/min",
        # Password recovery. Each request may send an email, so the cap
        # bounds how much mail a stranger can make the school send.
        "password_forgot": "5/min",
        # Reset redemptions are keyed on the token, not the client.
        "password_reset": "10/min",
        # Student registration. Each submission may send a verification
        # email, so an open form must not be usable to flood an inbox.
        "registration": "5/min",
        # Parent nominations. Each one reaches an administrator's queue.
        "parent_invitation": "5/min",
    },
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
}

# ---------------------------------------------------------------------------
# Simple JWT
# ---------------------------------------------------------------------------

from datetime import timedelta

SIMPLE_JWT = {
    # An idle session is short: 15 minutes for the access token.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("JWT_ACCESS_LIFETIME_MINUTES", default=15, cast=int)),
    # "Remember me" is the ceiling: one day. A sign-in that did not ask to be
    # remembered gets the shorter idle lifetime below instead (see
    # accounts/serializers.py).
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("JWT_REFRESH_LIFETIME_DAYS", default=1, cast=int)),
    # The idle session's refresh token. It is not a SimpleJWT setting, so it
    # is read by the login serializer directly; the name keeps it next to the
    # lifetimes it belongs with.
    "SESSION_REFRESH_LIFETIME": timedelta(minutes=config("JWT_SESSION_REFRESH_LIFETIME_MINUTES", default=15, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ---------------------------------------------------------------------------
# Frontend URL and outgoing mail
# ---------------------------------------------------------------------------
#
# The frontend is a separate service, so any link the backend mails out
# (password reset, account invitation) is built from this base URL.
AEGIS_FRONTEND_URL = config("AEGIS_FRONTEND_URL", default="http://127.0.0.1:5173")

#: The address outgoing mail is sent from. Without it, Django uses the
# webserver's own account, which is usually not a deliverable address.
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL", default="no-reply@localhost"
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Strapi CMS integration (Phase 7)
#
# STRAPI_API_TOKEN and STRAPI_WEBHOOK_SECRET are server-side-only
# credentials. In development they are loaded from cms/.env (see
# development.py); in production set them via the environment.
# ---------------------------------------------------------------------------

STRAPI_BASE_URL = config("STRAPI_BASE_URL", default="http://localhost:1337")
STRAPI_API_TOKEN = config("STRAPI_API_TOKEN", default="")
STRAPI_WEBHOOK_SECRET = config("STRAPI_WEBHOOK_SECRET", default="")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
