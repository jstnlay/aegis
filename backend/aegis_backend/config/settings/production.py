"""
Production settings for AEGIS Backend.

Requires PostgreSQL via environment variables.
"""

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
X_FRAME_OPTIONS = "DENY"

# HTTPS
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Only JSON renderer in production
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
]

# Email backend - override with actual provider in deployment
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
