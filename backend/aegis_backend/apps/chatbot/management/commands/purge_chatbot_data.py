"""
Delete chatbot messages and closed flags older than the retention window.

Retention is a school decision, so nothing is deleted until one is recorded:
`chatbot.retention_days` (0 means keep everything) or `--days` on the command.
The default of 0 is the safe one — a job that deletes on a default is a job
that surprises somebody.

What is deleted:

* chat messages older than the window **that are not attached to a flag**. A
  message with a flag is part of a case file, and deleting it would cascade
  the flag away with it.
* flags older than the window that are **closed** — resolved or marked a false
  positive. Their actions and recipients go with them (cascade).

What is never deleted:

* an open, under-review, or unacknowledged flag, whatever its age. An open
  case is live work, not expired data.
* a student record, a grade, an attendance record or anything outside the
  chatbot tables.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.chatbot.models import ChatMessage, Flag


class Command(BaseCommand):
    help = "Delete chatbot messages and closed flags older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help=(
                "Override chatbot.retention_days. 0 or less refuses to run, "
                "because a job that deletes on a default is a job that "
                "surprises somebody."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted and delete nothing.",
        )

    def handle(self, *args, **options):
        from apps.cms.settings_registry import get_int_setting

        days = options.get("days")
        if days is None:
            days = get_int_setting("chatbot.retention_days", 0)
        if days <= 0:
            raise CommandError(
                "No retention window. Set chatbot.retention_days or pass "
                "--days N. Nothing was deleted."
            )

        cutoff = timezone.now() - timedelta(days=days)
        dry_run = options.get("dry_run", False)

        closed = Flag.Status.RESOLVED, Flag.Status.FALSE_POSITIVE
        flags = Flag.objects.filter(created_at__lt=cutoff, status__in=closed)
        # A message attached to a flag is part of that flag's case file.
        messages = ChatMessage.objects.filter(created_at__lt=cutoff, flag__isnull=True)

        flag_count = flags.count()
        message_count = messages.count()

        self.stdout.write(
            f"Window: {days} day(s). Cutoff: {cutoff:%Y-%m-%d %H:%M}."
        )
        self.stdout.write(
            f"Closed flags past the window: {flag_count}. "
            f"Messages with no flag: {message_count}."
        )

        open_flags = Flag.objects.filter(created_at__lt=cutoff).exclude(
            status__in=closed
        )
        self.stdout.write(
            f"Open flags kept regardless of age: {open_flags.count()}."
        )

        if dry_run:
            self.stdout.write("Dry run: nothing was deleted.")
            return

        # Flags first. Deleting a flag does not delete its message — the
        # cascade runs the other way — so closing a case first and deleting
        # messages second means a closed old case loses both its flag and its
        # message, and a message that still belongs to an open flag is kept.
        deleted_flags = flags.count()
        flags.delete()
        deleted_messages = messages.count()
        messages.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_flags} closed flag(s) and "
                f"{deleted_messages} message(s)."
            )
        )
