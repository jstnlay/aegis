"""
Outgoing mail over a provider's HTTP API.

Why not SMTP
------------
Render's free compute plan blocks outbound traffic on the SMTP ports (25,
465 and 587), so an SMTP connection from this deployment never completes:
the request hangs until the platform's proxy gives up and answers 500. The
HTTP APIs are on 443, which is open.

Two providers are supported, because they solve different problems:

* **Resend** needs a verified *domain* to send to anyone, and until then it
  only delivers to the address on the Resend account.
* **Brevo** needs a verified *email address*, which is enough to send to
  anyone - so a deployment without a domain can still deliver.

A third, **SMTP2GO**, also accepts a single verified email address as a
sender and is in the same shape as the other two.

Which one is used is the ``EMAIL_BACKEND`` setting; the provider's key is
read from the environment. All of them keep Django's contract:
``send_messages`` returns the number of messages the provider accepted, and a
failure raises unless the caller asked for silence. The callers in this
project send mail from a request handler, so the failure is caught and logged
there - a mail that cannot be sent must not turn a password reset into a
server error.
"""

import logging
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.utils.html import escape

logger = logging.getLogger(__name__)

#: The provider's send endpoints. HTTPS, so they are on a port the platform
#: allows and the payload is not in the clear.
RESEND_ENDPOINT = "https://api.resend.com/emails"
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
SMTP2GO_ENDPOINT = "https://api.smtp2go.com/v3/email/send"


class HttpApiEmailBackend(BaseEmailBackend):
    """
    Sends mail through a provider's HTTP API.

    A provider differs in its endpoint, its authentication header and its
    payload shape, so a subclass supplies those three things. Everything else
    - Django's contract, the timeout, the failure behaviour - lives here.
    """

    #: Where the message is posted.
    endpoint = ""

    #: The setting that holds the provider's key.
    key_setting = ""

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
                logger.exception("Mail could not be sent")
                continue
            sent += 1
        return sent

    def _send(self, message):
        api_key = getattr(settings, self.key_setting, "")
        if not api_key:
            raise RuntimeError(
                f"{self.key_setting} is not set, so no mail can be sent."
            )

        response = requests.post(
            self.endpoint,
            json=self.payload(message),
            headers=self.headers(api_key),
            timeout=settings.EMAIL_TIMEOUT,
        )
        response.raise_for_status()
        #: The provider's answer, for a subclass that reads its body.
        self.last_response = response

    def payload(self, message):
        raise NotImplementedError

    def headers(self, api_key):
        raise NotImplementedError


class ResendEmailBackend(HttpApiEmailBackend):
    """Sends mail through the Resend HTTP API."""

    endpoint = RESEND_ENDPOINT
    key_setting = "RESEND_API_KEY"

    def payload(self, message):
        return {
            "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
            "to": list(message.to),
            "subject": message.subject or "",
            "text": message.body or "",
        }

    def headers(self, api_key):
        return {"Authorization": f"Bearer {api_key}"}


class Smtp2GoEmailBackend(HttpApiEmailBackend):
    """Sends mail through the SMTP2GO HTTP API."""

    endpoint = SMTP2GO_ENDPOINT
    key_setting = "SMTP2GO_API_KEY"

    def payload(self, message):
        sender = message.from_email or settings.DEFAULT_FROM_EMAIL
        _, address = parseaddr(sender)
        body = message.body or ""
        return {
            "sender": address,
            "to": list(message.to),
            "subject": message.subject or "",
            "text_body": body,
            "html_body": escape(body).replace("\n", "<br>"),
        }

    def headers(self, api_key):
        return {"X-Smtp2go-Api-Key": api_key}

    def _send(self, message):
        super()._send(message)

        # The provider answers 200 even when it could not deliver to every
        # recipient, reporting the outcome in the body. A send that reached
        # nobody is a failure, and the caller has to hear about it.
        try:
            data = self.last_response.json()
        except Exception:
            return
        outcome = data.get("data") if isinstance(data, dict) else None
        if isinstance(outcome, dict) and outcome.get("succeeded") == 0:
            raise RuntimeError(
                f"The provider delivered no message: {outcome.get('failures')}"
            )


class BrevoEmailBackend(HttpApiEmailBackend):
    """Sends mail through the Brevo HTTP API."""

    endpoint = BREVO_ENDPOINT
    key_setting = "BREVO_API_KEY"

    def payload(self, message):
        sender = message.from_email or settings.DEFAULT_FROM_EMAIL
        name, address = parseaddr(sender)
        body = message.body or ""
        return {
            "sender": {"name": name or address, "email": address},
            "to": [{"email": recipient} for recipient in message.to],
            "subject": message.subject or "",
            "textContent": body,
            # The provider wants a content field, so the plain text is
            # rendered as minimal HTML - the same words, escaped.
            "htmlContent": escape(body).replace("\n", "<br>"),
        }

    def headers(self, api_key):
        return {"api-key": api_key}
