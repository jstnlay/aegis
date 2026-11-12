"""
Retire the broad single-word screening terms.

`0002` seeded a first version of the default terms that included bare words
such as "gun", "abuse", "threaten", "bully", "depressed" and "hopeless".
Those fire on ordinary school sentences — a history project about gun
violence, a seminar on drug abuse — and a screening channel that cries wolf
is one staff learn to ignore, which makes a real disclosure less likely to be
read.

The replacements are phrases ("with a gun", "abused at home", "feeling
depressed"). This migration removes the retired terms and seeds the current
list, so a database that ran `0002` early ends up with the same state as a
fresh one.

Only seeded rows are touched: a term an administrator wrote or edited has
`created_by` set and is left alone.
"""

from django.db import migrations

RETIRED_TERMS = (
    "abuse",
    "threaten",
    "gun",
    "bully",
    "depressed",
    "hopeless",
)


def retire(apps, schema_editor):
    from apps.chatbot.defaults import DEFAULT_KEYWORD_TERMS

    KeywordTerm = apps.get_model("chatbot", "KeywordTerm")
    KeywordTerm.objects.filter(
        term__in=RETIRED_TERMS, created_by__isnull=True
    ).delete()

    existing = set(KeywordTerm.objects.values_list("term", "match_type"))
    KeywordTerm.objects.bulk_create(
        [
            KeywordTerm(
                term=term,
                match_type=match_type,
                severity=severity,
                category=category,
                notes=notes,
                is_active=True,
            )
            for term, match_type, severity, category, notes in DEFAULT_KEYWORD_TERMS
            if (term, match_type) not in existing
        ]
    )


def restore(apps, schema_editor):
    KeywordTerm = apps.get_model("chatbot", "KeywordTerm")
    KeywordTerm.objects.filter(
        term__in=RETIRED_TERMS, created_by__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("chatbot", "0002_seed_default_keywords"),
    ]

    operations = [
        migrations.RunPython(retire, restore),
    ]
