"""
Seed the chatbot settings added after `0004_seed_system_settings`.

`0004` seeded whatever was registered at the time it ran. The chatbot
settings — the acknowledgment timer, the student notice and its version, and
the faculty-notice switch — were registered later, so on an existing database
they are not in the table.

They still work: `get_setting` falls back to the registered default when a row
is absent. But an administrator cannot see or change a setting that has no
row, so the settings page would not show them. This migration adds the rows.
"""

from django.db import migrations

from apps.cms.settings_registry import SETTING_DEFINITIONS

CHATBOT_KEYS = (
    "chatbot.acknowledgment_timer_minutes",
    "chatbot.notice_version",
    "chatbot.notice_text",
    "chatbot.faculty_notifications_enabled",
)


def seed_chatbot_settings(apps, schema_editor):
    SystemSetting = apps.get_model("cms", "SystemSetting")

    existing = set(SystemSetting.objects.values_list("key", flat=True))
    SystemSetting.objects.bulk_create(
        [
            SystemSetting(
                key=key,
                value=str(SETTING_DEFINITIONS[key]["default"]),
                description=SETTING_DEFINITIONS[key]["description"],
            )
            for key in CHATBOT_KEYS
            if key not in existing
        ]
    )


def remove_chatbot_settings(apps, schema_editor):
    SystemSetting = apps.get_model("cms", "SystemSetting")
    SystemSetting.objects.filter(
        key__in=CHATBOT_KEYS, updated_by__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0004_seed_system_settings"),
    ]

    operations = [
        migrations.RunPython(seed_chatbot_settings, remove_chatbot_settings),
    ]
