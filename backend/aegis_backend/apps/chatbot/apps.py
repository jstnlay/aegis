from django.apps import AppConfig


class ChatbotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chatbot"
    verbose_name = "Chatbot (PH9)"

    def ready(self):
        # Django does not import an app's checks module for you — the
        # registration has to be explicit. Without this, the deployment check
        # that refuses to start a production deployment without a field
        # encryption key would never run.
        from apps.chatbot import checks  # noqa: F401
