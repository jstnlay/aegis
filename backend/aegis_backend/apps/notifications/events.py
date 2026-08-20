"""
Notification event dispatch.

This module provides a single function for domain modules to create
in-app notifications. Domain modules are responsible for:
  - Deciding when an event fires
  - Resolving recipients using their own domain models
  - Passing pre-computed title, message, and link

This module is responsible for:
  - Creating Notification records
  - Gating on recipient NotificationPreference.in_app_enabled
  - Lazy-initializing NotificationPreference for new recipients
"""


def dispatch_event(
    event_type,
    *,
    recipients,
    sender=None,
    title,
    message,
    link=None,
    deduplication_key=None,
):
    """
    Create Notification objects for each recipient.

    Args:
        event_type: One of NotificationType values.
        recipients: Iterable of User instances.
        sender: User instance or None (system-generated).
        title: Notification title string.
        message: Notification body string.
        link: Optional frontend route string.
        deduplication_key: Optional string. If provided and a Notification
            with this key already exists for ANY recipient, no notifications
            are created for ANY recipient (all-or-nothing dedup).
    """
    from .models import Notification, NotificationPreference, NotificationType

    recipients = list(recipients)
    if not recipients:
        return

    # Deduplication check: if a key is provided and already exists, skip entirely
    if deduplication_key:
        if Notification.objects.filter(deduplication_key=deduplication_key).exists():
            return

    for recipient in recipients:
        pref, _ = NotificationPreference.objects.get_or_create(user=recipient)
        if not pref.in_app_enabled:
            continue
        Notification.objects.create(
            recipient=recipient,
            sender=sender,
            notification_type=event_type,
            title=title,
            message=message,
            link=link,
            deduplication_key=deduplication_key,
        )
