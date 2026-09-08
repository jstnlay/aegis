from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    verbose_name = "Audit"

    def ready(self):
        """Register the PH10.5 model audit signals exactly once."""
        from apps.audit.signals import connect_signals

        connect_signals()
