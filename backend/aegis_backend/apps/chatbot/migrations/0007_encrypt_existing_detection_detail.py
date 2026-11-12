"""
Encrypt the model rationale that is already stored.

`0006` marked `detection_detail` as encrypted. The column type did not change
— the ciphertext is a JSON string — so what is left is rewriting the rows
that hold a plain JSON object.

The reverse decrypts, with raw SQL, because the field would encrypt the value
again on the way in.
"""

from django.db import connection
from django.db import migrations


def encrypt_existing(apps, schema_editor):
    """Write every existing value back through the encrypted field."""
    ChatMessage = apps.get_model("chatbot", "ChatMessage")
    for row in ChatMessage.objects.all().iterator():
        row.save(update_fields=["detection_detail"])


def decrypt_existing(apps, schema_editor):
    """Put the plain JSON back, with raw SQL so it is not encrypted again."""
    import json

    from core.crypto import decrypt

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, detection_detail FROM chatbot_chatmessage "
            "WHERE detection_detail LIKE 'enc1:%'"
        )
        for pk, ciphertext in cursor.fetchall():
            plaintext = decrypt(ciphertext)
            cursor.execute(
                "UPDATE chatbot_chatmessage SET detection_detail = %s WHERE id = %s",
                [json.dumps(json.loads(plaintext)), pk],
            )


class Migration(migrations.Migration):

    dependencies = [
        ("chatbot", "0006_alter_chatmessage_detection_detail"),
    ]

    operations = [
        migrations.RunPython(encrypt_existing, decrypt_existing),
    ]
