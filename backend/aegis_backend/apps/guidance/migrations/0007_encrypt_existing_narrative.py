"""
Encrypt the guidance narrative that is already stored.

`0006` marked the fields as encrypted. The rows that existed before it still
hold plain text, because enabling encryption does not rewrite history by
itself — so this migration rewrites them.

What it encrypts: a counselor's session notes, a teacher's behavioral
observation, an intervention step, a progress note. The concern categories, the
risk scores and the rest are structured data and stay as they are.

The reverse decrypts, with raw SQL, because the field would encrypt the value
again on the way in.
"""

from django.db import connection
from django.db import migrations

#: (model, fields) pairs to rewrite.
MODELS = (
    ("BehavioralNote", ("note_text",)),
    ("ConsultationRecord", ("session_notes", "recommendations")),
    ("InterventionStep", ("description",)),
    ("ProgressNote", ("note_text",)),
)

#: The tables and columns, for the reverse.
COLUMNS = (
    ("guidance_behavioralnote", "note_text"),
    ("guidance_consultationrecord", "session_notes"),
    ("guidance_consultationrecord", "recommendations"),
    ("guidance_interventionstep", "description"),
    ("guidance_progressnote", "note_text"),
)


def encrypt_existing(apps, schema_editor):
    """Write every existing value back through the encrypted field."""
    for model_name, fields in MODELS:
        model = apps.get_model("guidance", model_name)
        for row in model.objects.all().iterator():
            row.save(update_fields=list(fields))


def decrypt_existing(apps, schema_editor):
    """Put the plain text back, with raw SQL so it is not encrypted again."""
    from core.crypto import decrypt

    with connection.cursor() as cursor:
        for table, column in COLUMNS:
            cursor.execute(
                f"SELECT id, {column} FROM {table} WHERE {column} LIKE 'enc1:%'"
            )
            for pk, ciphertext in cursor.fetchall():
                cursor.execute(
                    f"UPDATE {table} SET {column} = %s WHERE id = %s",
                    [decrypt(ciphertext), pk],
                )


class Migration(migrations.Migration):

    dependencies = [
        ("guidance", "0006_alter_behavioralnote_note_text_and_more"),
    ]

    operations = [
        migrations.RunPython(encrypt_existing, decrypt_existing),
    ]
