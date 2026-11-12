"""
Model fields whose value is encrypted at rest.

One field, one behaviour: the column holds ciphertext, the application sees
plaintext. Nothing else in the codebase has to know, and a query that compares
an encrypted column still works because the encryption is deterministic
(see ``core.crypto``).
"""

from __future__ import annotations

import json

from django.db import models

from core.crypto import decrypt, encrypt, is_encrypted


class EncryptedTextField(models.TextField):
    """
    A text column encrypted with AES-SIV.

    * Writing encrypts the value.
    * Reading decrypts it.
    * A value that was never encrypted (written before encryption was turned
      on) is returned as it is, so enabling encryption never makes old rows
      unreadable.
    * With no key configured the field stores and returns plain text. The
      production system check refuses to start in that state when
      ``FIELD_ENCRYPTION_REQUIRED`` is on.

    The column is still a text column: no schema change is needed to store
    ciphertext, only to mark the field as one that is encrypted.
    """

    description = "Text encrypted at rest with AES-SIV."

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        if is_encrypted(value):
            # Already encrypted — a row that was read and written back must not
            # be encrypted twice.
            return value
        return encrypt(value)

    def from_db_value(self, value, expression, connection):
        # `Field` has no `from_db_value` of its own — the hook is optional —
        # so there is nothing to call up to. A value that is not one of ours is
        # returned untouched: a row written before encryption was enabled must
        # still be readable.
        if not isinstance(value, str) or not is_encrypted(value):
            return value
        return decrypt(value)


class EncryptedJSONField(models.JSONField):
    """
    A JSON column whose value is encrypted at rest.

    The column type does not change: the ciphertext is stored as a JSON string,
    so the schema is untouched and no ``ALTER TYPE`` is needed. What changes is
    what the column holds — the model's own words about a student's message
    are no longer readable in a dump.

    The application still sees a dict. A value written before encryption was
    enabled is a plain dict and is returned as it is.
    """

    description = "JSON encrypted at rest with AES-SIV."

    def get_prep_value(self, value):
        if value is None:
            return None
        # With no key configured the value is stored as plain JSON, so the
        # column keeps holding a JSON object rather than a JSON string. The
        # application must not be able to tell the difference between "no key"
        # and "a key", except by the fact that the column is readable.
        from core.crypto import key_pairs

        if not key_pairs():
            return value
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        if is_encrypted(text):
            return text
        return encrypt(text)

    def from_db_value(self, value, expression, connection):
        # `JSONField.from_db_value` parses the stored JSON, so what arrives
        # here is the ciphertext string rather than the raw column text.
        parsed = super().from_db_value(value, expression, connection)
        if isinstance(parsed, str) and is_encrypted(parsed):
            try:
                return json.loads(decrypt(parsed))
            except (TypeError, ValueError):
                return {}
        return parsed
