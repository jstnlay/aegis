"""Escalate chatbot flags that passed their acknowledgment timer."""

from django.core.management.base import BaseCommand

from apps.chatbot.routing import escalate_stale_flags


class Command(BaseCommand):
    help = (
        "Escalate open, unacknowledged chatbot flags whose timer expired. "
        "Safe to run repeatedly: an escalated flag is not escalated twice."
    )

    def handle(self, *args, **options):
        rows = escalate_stale_flags()
        self.stdout.write(
            self.style.SUCCESS(f"Escalated {len(rows)} flag(s).")
        )
        for row in rows:
            self.stdout.write(f"  {row.id} {row.severity} status={row.status}")
