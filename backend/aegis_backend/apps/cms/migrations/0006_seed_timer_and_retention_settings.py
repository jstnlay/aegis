"""
Seed the chatbot settings registered after `0005`.

The per-severity acknowledgment windows and the retention window were added to
the registry after `0005` ran, so on an existing database they have no row.
They still work — `get_setting` falls back to the registered default — but an
administrator cannot see or change a setting that has no row.

This migration inserts exactly these keys, and only the ones that are missing.
"""

from django.db import migrations

from apps.cms.settings_registry import SETTING_DEFINITIONS

NEW_KEYS = (
    "chatbot.acknowledgment_timer_minutes.critical",
    "chatbot.acknowledgment_timer_minutes.high",
    "chatbot.acknowledgment_timer_minutes.medium",
    "chatbot.acknowledgment_timer_minutes.low",
    "chatbot.retention_days",
)


def seed(apps, schema_editor):
    SystemSetting = apps.get_model("cms", "SystemSetting")

    existing = set(SystemSetting.objects.values_list("key", flat=True))
    SystemSetting.objects.bulk_create(
        [
            SystemSetting(
                key=key,
                value=str(SETTING_DEFINITIONS[key]["default"]),
                description=SETTING_DEFINITIONS[key]["description"],
            )
            for key in NEW_KEYS
            if key not in existing
        ]
    )


def unseed(apps, schema_editor):
    SystemSetting = apps.get_model("cms", "SystemSetting")
    SystemSetting.objects.filter(
        key__in=NEW_KEYS, updated_by__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0005_seed_chatbot_settings"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
