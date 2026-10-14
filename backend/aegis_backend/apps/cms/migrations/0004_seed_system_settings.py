"""
Seed the system-wide settings the code reads (FR-034, TC-ADM-11).

Seeding here rather than on first GET means the settings exist from the moment
the migration lands, and no endpoint has to write on a read. A setting added to
the registry in a later release gets its own data migration alongside it -
which is why this reads `SETTING_DEFINITIONS` instead of hard-coding the rows:
one source for what a setting is and what it starts as.
"""

from django.db import migrations

from apps.cms.settings_registry import SETTING_DEFINITIONS


def seed_system_settings(apps, schema_editor):
    """Insert any registered setting that is not already in the table."""
    SystemSetting = apps.get_model("cms", "SystemSetting")

    existing = set(
        SystemSetting.objects.values_list("key", flat=True)
    )
    SystemSetting.objects.bulk_create(
        [
            SystemSetting(
                key=key,
                value=str(definition["default"]),
                description=definition["description"],
            )
            for key, definition in SETTING_DEFINITIONS.items()
            if key not in existing
        ]
    )


def remove_system_settings(apps, schema_editor):
    """Reverse of the seed. Only removes rows that were seeded."""
    SystemSetting = apps.get_model("cms", "SystemSetting")
    SystemSetting.objects.filter(
        key__in=SETTING_DEFINITIONS,
        updated_by__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0003_systemsetting"),
    ]

    operations = [
        migrations.RunPython(
            seed_system_settings,
            remove_system_settings,
        ),
    ]
