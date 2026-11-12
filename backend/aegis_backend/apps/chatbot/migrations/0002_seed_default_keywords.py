"""Seed the default Layer 1 keyword terms.

A fresh install must screen something on Layer 1 even with no API key, so the
default terms ship with the schema. The seed is idempotent and never touches
a term an administrator has already edited.
"""

from django.db import migrations


def seed(apps, schema_editor):
    from apps.chatbot.defaults import seed_keyword_terms

    seed_keyword_terms()


def unseed(apps, schema_editor):
    from apps.chatbot.models import KeywordTerm

    from apps.chatbot.defaults import DEFAULT_KEYWORD_TERMS

    terms = [row[0] for row in DEFAULT_KEYWORD_TERMS]
    KeywordTerm.objects.filter(term__in=terms, created_by__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("chatbot", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
