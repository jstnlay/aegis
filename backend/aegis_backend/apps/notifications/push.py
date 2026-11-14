"""
Web Push delivery.

Called from ``dispatch_event`` for every recipient whose preference allows
push. One browser is one ``PushSubscription`` row; a user may have several.
Delivery is best-effort: a dead endpoint is deleted, and any other failure is
logged without touching the in-app notification, the email, or the caller's
transaction.

The payload is deliberately small and contains no school record beyond the
notification's own title and message. The service worker opens the app rather
than a cached page, so no student data is stored by the worker.
"""

import json
import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Browsers cap payloads at 4 KB. The title is already capped at 255 chars; the
#: body is cut so a long notification cannot make delivery fail for every
#: subscription of that user.
MAX_BODY_CHARS = 300

#: Where a click lands when the notification's link is a backend API path.
#: The frontend owns the API-path-to-screen mapping; the inbox is the one
#: destination that is always valid for every role.
FALLBACK_CLICK_PATH = "/app/notifications"


def in_quiet_hours(pref, now=None):
    """
    True when ``now`` falls inside the user's quiet window.

    Quiet hours are wall-clock times in ``settings.TIME_ZONE`` (Asia/Manila),
    and a window may cross midnight (`22:00`–`06:00`). Both ends must be set;
    a single supplied end has no interval to test.
    """
    start = pref.quiet_hours_start
    end = pref.quiet_hours_end
    if start is None or end is None or start == end:
        return False

    current = timezone.localtime(now or timezone.now()).time()
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _click_path(link):
    """Only SPA paths are opened; API paths fall back to the inbox."""
    if isinstance(link, str) and link.startswith("/app/"):
        return link
    return FALLBACK_CLICK_PATH


def _vapid_subject():
    contact = (settings.VAPID_ADMIN_EMAIL or "").strip()
    if contact.startswith(("mailto:", "https://")):
        return contact
    return f"mailto:{contact or 'no-reply@localhost'}"


def send_push_to_user(*, user, title, message, link=None, tag=None):
    """
    Send one event to every browser the user registered.

    Returns the number of accepted deliveries. Zero is normal: the user may
    have no subscription, push may be unconfigured, or every endpoint may be
    gone. None of those is an error for the notification itself.
    """
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        return 0

    subscriptions = list(user.push_subscriptions.all())
    if not subscriptions:
        return 0

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:  # pragma: no cover - production installs the package
        logger.error("pywebpush is not installed; push delivery skipped.")
        return 0

    payload = json.dumps(
        {
            "title": title,
            "body": (message or "")[:MAX_BODY_CHARS],
            "url": _click_path(link),
            "tag": tag or "aegis",
        }
    )

    delivered = 0
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {
                        "p256dh": subscription.p256dh,
                        "auth": subscription.auth,
                    },
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": _vapid_subject()},
                ttl=86400,
            )
            delivered += 1
        except WebPushException as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code in (404, 410):
                # The browser unsubscribed or the endpoint expired. Keeping the
                # row would make every later event retry a dead address.
                subscription.delete()
            else:
                logger.warning(
                    "Push delivery failed for subscription %s (status %s).",
                    subscription.pk,
                    status_code,
                )
        except Exception:
            logger.exception(
                "Push delivery failed for subscription %s.", subscription.pk
            )

    return delivered
