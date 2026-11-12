"""Generate a field encryption key for student free text."""

import base64
import secrets

from django.core.management.base import BaseCommand

from core.crypto import KEY_BYTES


class Command(BaseCommand):
    help = (
        "Generate a field encryption key. Put it in the environment as "
        "FIELD_ENCRYPTION_KEYS=key_id:<value> (or FIELD_ENCRYPTION_KEY=<value>)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--key-id",
            default="k1",
            help="The id of this key. It is stored with every ciphertext so a "
            "later key can still read what this one wrote.",
        )

    def handle(self, *args, **options):
        key_id = options["key_id"]
        raw = secrets.token_bytes(KEY_BYTES)
        encoded = base64.b64encode(raw).decode("ascii")

        self.stdout.write(
            self.style.SUCCESS(
                f"Field encryption key '{key_id}' generated "
                f"({KEY_BYTES * 8} bits, AES-SIV)."
            )
        )
        self.stdout.write("")
        self.stdout.write("Add this to the environment (never to a file in the repo):")
        self.stdout.write("")
        self.stdout.write(f"FIELD_ENCRYPTION_KEYS={key_id}:{encoded}")
        self.stdout.write("")
        self.stdout.write(
            "To rotate: add the new key first, deploy, and drop the old one "
            "once nothing is encrypted with it any more. The first key in the "
            "list encrypts; every key in the list decrypts."
        )
