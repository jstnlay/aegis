"""
Production settings for AEGIS Backend.

Requires PostgreSQL via environment variables.
"""

from django.core.exceptions import ImproperlyConfigured
from decouple import Csv, config as _env_config

from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Production-specific overrides
# ---------------------------------------------------------------------------

DEBUG = False

# Security settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

# Referrers and opener isolation. The API serves JSON only, so a full
# referrer would leak query strings to anything the page links to, and
# window.opener lets a linked page reach back into this one.
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# The deployment sits behind a TLS-terminating proxy, so the scheme has to
# come from the proxy's forwarding header. Without this, every request
# looks like plain HTTP and SECURE_SSL_REDIRECT would loop.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HTTPS
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ---------------------------------------------------------------------------
# Host header allow-list
# ---------------------------------------------------------------------------
#
# The list is read from the environment here rather than reused from base.py,
# so this module can be reloaded (and this check tested) without reloading
# the whole settings chain.
#
# An empty list means every Host header is refused, which is safe but takes
# the API down; "*" means every Host header is accepted, which is how a
# Host-header injection reaches the application. Neither is a deployable
# default, so an unset list is a configuration error and the process refuses
# to start rather than serving on an unknown host.
# ---------------------------------------------------------------------------

PRODUCTION_ALLOWED_HOSTS = _env_config("DJANGO_ALLOWED_HOSTS", default="", cast=Csv())

if not PRODUCTION_ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must list the hostnames this deployment "
        "answers for. Set it in the environment before starting in "
        "production."
    )

ALLOWED_HOSTS = PRODUCTION_ALLOWED_HOSTS

# ---------------------------------------------------------------------------
# Secret key
# ---------------------------------------------------------------------------
#
# The secret key signs the session cookies, the password-reset tokens and
# anything else Django signs. A short or auto-generated one is guessable,
# and a leaked one lets anyone mint a valid signature. Django's own deploy
# check flags the same thing (security.W009), but as a warning: a deployment
# pipeline that only reads warnings still ships a guessable key. Here it is a
# start-up failure.
# ---------------------------------------------------------------------------

PRODUCTION_SECRET_KEY = _env_config("DJANGO_SECRET_KEY", default="")

if (
    len(PRODUCTION_SECRET_KEY) < 50
    or PRODUCTION_SECRET_KEY.startswith("django-insecure-")
    or len(set(PRODUCTION_SECRET_KEY)) < 5
):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be at least 50 characters, drawn from more "
        "than four distinct characters, and must not be an auto-generated "
        "django-insecure- key. Generate one with "
        "`python -c \"import secrets; print(secrets.token_urlsafe(64))\"`."
    )

SECRET_KEY = PRODUCTION_SECRET_KEY

# ---------------------------------------------------------------------------
# Django admin site
# ---------------------------------------------------------------------------
#
# The admin site is a second authority: it authenticates on `is_staff` and
# knows nothing about the five-role model the API enforces, so an account
# that can reach it holds power the role system never granted. AEGIS
# accounts are created with `is_staff=False`, which means the site is
# unusable in production anyway — so it is not published there unless a
# deployment asks for it by name.
# ---------------------------------------------------------------------------

ENABLE_ADMIN_SITE = _env_config("DJANGO_ENABLE_ADMIN_SITE", default=False, cast=bool)

# Only JSON renderer in production
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
]

# Email backend - override with actual provider in deployment
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
