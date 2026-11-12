"""
Deployment checks for the field encryption of student free text.

One check, and it is the important one: a deployment that is supposed to
encrypt student text and is not doing so must not start.

The check is an **error**, not a warning, and not a start-up exception in
``production.py``: a warning is something a deployment pipeline reads past,
and the whole point is that a production deployment without a key would store
a student's disclosure in plain text.
"""

from django.conf import settings
from django.core.checks import Error, register

from core.crypto import status as encryption_status


@register()
def check_field_encryption(app_configs, **kwargs):
    """Refuse a deployment that should encrypt student text and does not."""
    if not getattr(settings, "FIELD_ENCRYPTION_REQUIRED", False):
        return []

    state = encryption_status()
    if state["enabled"]:
        return []

    return [
        Error(
            "FIELD_ENCRYPTION_REQUIRED is on but no field encryption key is "
            "configured. Student chat messages, replies, flag summaries and "
            "private case notes would be stored in plain text. Generate a key "
            "with 'manage.py generate_encryption_key' and set "
            "FIELD_ENCRYPTION_KEYS (or FIELD_ENCRYPTION_KEY) in the "
            "environment.",
            hint="Set FIELD_ENCRYPTION_KEYS=key_id:base64key",
            id="chatbot.E001",
        )
    ]
