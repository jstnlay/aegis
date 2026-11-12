"""
Report the security posture of a deployment.

One command that answers the questions an operator actually has before they
put a deployment in front of students:

* Is student free text encrypted at rest, and with which key?
* Which columns are encrypted?
* What is the acknowledgment window, and the retention window?
* Is the model reachable, and if not, why?

It prints facts, not reassurance. A deployment that reports "encryption OFF"
has told the operator what they need to know.

It never prints a key, a key id beyond the active one, or any student data.
"""

from django.core.management.base import BaseCommand

from core.crypto import ALGORITHM, status as encryption_status


class Command(BaseCommand):
    help = (
        "Report the security posture of this deployment: field encryption, "
        "the acknowledgment and retention windows, and the model status."
    )

    def handle(self, *args, **options):
        from apps.cms.settings_registry import get_int_setting, get_setting
        from apps.chatbot import gemini_client, routing

        self.stdout.write(self.style.MIGRATE_HEADING("AEGIS security posture"))

        # --- Field encryption ------------------------------------------
        state = encryption_status()
        self.stdout.write("")
        self.stdout.write("Field encryption (student free text)")
        if state["enabled"]:
            self.stdout.write(
                f"  ON — {state['algorithm']}, "
                f"{state['key_count']} key(s), "
                f"active key id '{state['active_key_id']}'"
            )
        else:
            self.stdout.write(
                self.style.WARNING("  OFF — student messages are stored in plain text.")
            )
            if state.get("error"):
                self.stdout.write(f"  {state['error']}")
        self.stdout.write(f"  Columns: {', '.join(self._encrypted_columns())}")

        required = bool(getattr(self._settings(), "FIELD_ENCRYPTION_REQUIRED", False))
        self.stdout.write(
            "  Required in this environment: "
            + ("yes" if required else "no")
        )

        # --- Windows ----------------------------------------------------
        self.stdout.write("")
        self.stdout.write("Acknowledgment window (minutes)")
        for severity, minutes in routing.severity_windows().items():
            self.stdout.write(f"  {severity:8} {minutes}")

        retention = get_int_setting("chatbot.retention_days", 0)
        self.stdout.write("")
        self.stdout.write("Retention window")
        if retention > 0:
            self.stdout.write(f"  {retention} day(s)")
        else:
            self.stdout.write(
                self.style.WARNING(
                    "  0 — no window is set, so nothing is ever deleted."
                )
            )
        notice_version = get_setting("chatbot.notice_version", "")
        self.stdout.write(f"  Student notice version: {notice_version}")

        # --- Model ------------------------------------------------------
        model = gemini_client.status()
        self.stdout.write("")
        self.stdout.write("Model")
        self.stdout.write(f"  {model['model']} — {'available' if model['available'] else 'NOT available'}")
        self.stdout.write(
            f"  {model['key_count']} key(s) configured, {model['keys_exhausted']} spent"
        )
        if model["last_failure"].get("reason"):
            self.stdout.write(
                self.style.WARNING(f"  Last call failed: {model['last_failure']['reason']}")
            )

        # --- What this does not cover -----------------------------------
        self.stdout.write("")
        self.stdout.write("Not covered by the application (platform's job)")
        self.stdout.write("  - Encryption of the Postgres volume and its backups.")
        self.stdout.write("  - Where the field encryption key is stored and who holds it.")
        self.stdout.write("  - See docs/SECURITY_POSTURE_RUNBOOK.md for the questions to ask.")

    @staticmethod
    def _settings():
        from django.conf import settings

        return settings

    @staticmethod
    def _encrypted_columns():
        """Every model field that is encrypted, by label."""
        from django.apps import apps

        from core.fields import EncryptedJSONField, EncryptedTextField

        found = []
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if isinstance(field, (EncryptedTextField, EncryptedJSONField)):
                    found.append(f"{model._meta.label}.{field.name}")
        return sorted(found)
