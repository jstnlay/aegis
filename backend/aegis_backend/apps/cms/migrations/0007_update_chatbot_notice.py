"""
The assistant now answers with Gemini, not only classifies with it.

The old notice said the message text was sent "for classification". A reply is
a second purpose and, with thread memory, a wider payload: recent turns in the
same chat. Students must accept a notice that says so, so the version is bumped
and every acceptance of the old version stops counting.

Only rows still holding the previous shipped values are rewritten. If an
administrator edited either setting, that copy is theirs to update; the version
still moves if it is the old default, because the disclosure it names is no
longer accurate.
"""

from django.db import migrations

OLD_VERSION = "2026-11-01"
NEW_VERSION = "2026-11-17"

OLD_TEXT = (
    "AEGIS stores chatbot messages so a guidance counselor can review a safety "
    "concern. Messages are screened by an automated keyword layer and may be "
    "classified by Gemini, a third-party AI service. Only the message text is "
    "sent for classification; your name, student number and school records are "
    "not. You can ask a counselor what was stored about you."
)

NEW_TEXT = (
    "AEGIS stores chatbot messages so a guidance counselor can review a safety "
    "concern. Messages are screened by an automated keyword layer. To answer a "
    "question, the message text and recent turns in the same chat may be sent "
    "to Gemini, a third-party AI service. Your name, student number and school "
    "records are not sent. You can ask a counselor what was stored about you."
)


def update_notice(apps, schema_editor):
    SystemSetting = apps.get_model("cms", "SystemSetting")
    SystemSetting.objects.filter(
        key="chatbot.notice_version", value=OLD_VERSION
    ).update(value=NEW_VERSION)
    SystemSetting.objects.filter(
        key="chatbot.notice_text", value=OLD_TEXT
    ).update(value=NEW_TEXT)


def restore_notice(apps, schema_editor):
    SystemSetting = apps.get_model("cms", "SystemSetting")
    SystemSetting.objects.filter(
        key="chatbot.notice_version", value=NEW_VERSION
    ).update(value=OLD_VERSION)
    SystemSetting.objects.filter(
        key="chatbot.notice_text", value=NEW_TEXT
    ).update(value=OLD_TEXT)


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0006_seed_timer_and_retention_settings"),
    ]

    operations = [
        migrations.RunPython(update_notice, restore_notice),
    ]
