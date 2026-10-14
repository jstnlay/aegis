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


def schedule_maintenance_window(*, starts_at, ends_at, message="", sender=None):
    """
    Create a maintenance window and issue its NFR-012 advance notice.

    The window and its notice are written in one transaction, so the class
    docstring's invariant is not a hope: if the dispatch fails, there is no
    window either. A half-scheduled window whose notice never went out is
    exactly the state NFR-012 forbids, and leaving it behind to be noticed
    later would be leaving it behind.

    The notice states its own lead time in hours. That is not decoration -
    NFR-012 is a claim about elapsed time, and putting the measured number in
    the artifact is what makes the claim checkable from the recipient's side
    rather than only from a test's.
    """
    from django.contrib.auth import get_user_model
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.utils import timezone

    from .models import MaintenanceWindow, NotificationType

    with transaction.atomic():
        window = MaintenanceWindow(
            starts_at=starts_at,
            ends_at=ends_at,
            message=message,
            created_by=sender,
        )
        # Raises for a window inside the 24-hour rule, or one that ends before
        # it starts. Validating here rather than in the view keeps the rule
        # true for every caller, the API and the Django admin alike.
        window.full_clean()
        window.save()

        lead_hours = int(
            (window.starts_at - timezone.now()).total_seconds() // 3600
        )

        body = (
            f"Maintenance runs from {window.starts_at:%B %d, %Y at %H:%M} to "
            f"{window.ends_at:%B %d, %Y at %H:%M}. This notice was issued "
            f"{lead_hours} hours in advance."
        )
        if message:
            body = f"{body}\n\n{message}"

        dispatch_event(
            NotificationType.MAINTENANCE_NOTICE,
            recipients=get_user_model().objects.filter(is_active=True),
            sender=sender,
            title="Scheduled maintenance",
            message=body,
            link="/app/notifications",
            deduplication_key=f"maintenance:{window.id}",
        )

        window.notified_at = timezone.now()
        window.save(update_fields=["notified_at"])

    return window
