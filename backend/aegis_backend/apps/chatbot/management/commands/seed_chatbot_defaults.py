"""Seed the default chatbot screening terms and settings."""

from django.core.management.base import BaseCommand

from apps.chatbot.defaults import seed_keyword_terms


class Command(BaseCommand):
    help = (
        "Create the default Layer 1 keyword terms if they are missing. "
        "Existing terms, including administrator edits, are left alone."
    )

    def handle(self, *args, **options):
        created = seed_keyword_terms()
        self.stdout.write(
            self.style.SUCCESS(f"Created {created} keyword term(s).")
        )
