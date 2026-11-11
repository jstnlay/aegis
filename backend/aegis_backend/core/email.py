"""
Outgoing mail through the Resend HTTP API.

Why not SMTP
------------
Render's free compute plan blocks outbound traffic on the SMTP ports (25,
465 and 587), so an SMTP connection from this deployment never completes:
the request hangs until the platform's proxy gives up and answers 500. The
HTTP API is on 443, which is open.

The backend keeps Django's contract: ``send_messages`` returns the number of
messages handed to the provider, and a failure raises unless the caller asked
for silence. The callers in this project send mail from a request handler,
so the failure is caught and logged there - a mail that cannot be sent must
not turn a password reset into a server error.

A paid plan may still use Django's SMTP backend; the choice is the
``EMAIL_BACKEND`` setting, and this backend is one value of it.
"""

import logging

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

#: The provider's send endpoint. HTTPS, so it is on a port the platform
#: allows and the payload is not in the clear.
RESEND_ENDPOINT = "https://api.resend.com/emails"


class ResendEmailBackend(BaseEmailBackend):
    """Sends mail through the Resend HTTP API."""

    def send_messages(self, email_messages):
        """Send each message; return how many the provider accepted."""
        if not email_messages:
            return 0

        sent = 0
        for message in email_messages:
            try:
                self._send(message)
            except Exception:
                if not self.fail_silently:
                    raise
                logger.exception("Resend email could not be sent")
                continue
            sent += 1
        return sent

    def _send(self, message):
        api_key = getattr(settings, "RESEND_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "RESEND_API_KEY is not set, so no mail can be sent."
            )

        payload = {
            "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
            "to": list(message.to),
            "subject": message.subject or "",
            "text": message.body or "",
        }

        response = requests.post(
            RESEND_ENDPOINT,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=settings.EMAIL_TIMEOUT,
        )
        response.raise_for_status()
