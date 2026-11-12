"""
Encrypt the student free text that is already stored.

`0004` marked the fields as encrypted. The rows that existed before it still
hold plain text, because enabling encryption does not rewrite history by
itself — so this migration rewrites them.

What it does: every chatbot message, reply, flag summary and case note is
written back through the encrypted field. What it does not do: touch any other
table, or any field that was never student free text.

With no key configured the write is a no-op — the field stores what it is
given — so this migration is safe to run in a development environment that has
no key yet. In production the key is required (see `apps.chatbot.checks`), and
by then the rows are ciphertext.

The reverse decrypts. It writes with raw SQL because the field would encrypt
the value again on the way in.
"""

from django.db import connection
from django.db import migrations

#: (table, column) pairs, in the order the application reads them.
ENCRYPTED_COLUMNS = (
    ("chatbot_chatmessage", "message"),
    ("chatbot_chatmessage", "reply"),
    ("chatbot_flag", "summary"),
    ("chatbot_flagaction", "note"),
)

#: The models the columns belong to, for the forward pass.
MODELS = (
    ("ChatMessage", ("message", "reply")),
    ("Flag", ("summary",)),
    ("FlagAction", ("note",)),
)


def encrypt_existing(apps, schema_editor):
    """Write every existing value back through the encrypted field."""
    for model_name, fields in MODELS:
        model = apps.get_model("chatbot", model_name)
        for row in model.objects.all().iterator():
            row.save(update_fields=list(fields))


def decrypt_existing(apps, schema_editor):
    """Put the plain text back, with raw SQL so it is not encrypted again."""
    with connection.cursor() as cursor:
        for table, column in ENCRYPTED_COLUMNS:
            cursor.execute(
                f"SELECT id, {column} FROM {table} WHERE {column} LIKE 'enc1:%'"
            )
            rows = cursor.fetchall()
            for pk, ciphertext in rows:
                cursor.execute(
                    f"UPDATE {table} SET {column} = %s WHERE id = %s",
                    [_plain(ciphertext), pk],
                )


def _plain(ciphertext):
    """Decrypt one value. Imported lazily so the migration runs anywhere."""
    from core.crypto import decrypt

    return decrypt(ciphertext)


class Migration(migrations.Migration):

    dependencies = [
        ("chatbot", "0004_alter_chatmessage_message_alter_chatmessage_reply_and_more"),
    ]

    operations = [
        migrations.RunPython(encrypt_existing, decrypt_existing),
    ]
