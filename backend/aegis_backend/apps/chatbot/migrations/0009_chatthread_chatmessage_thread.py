import uuid

import core.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def group_existing_messages(apps, schema_editor):
    """
    Put every user's existing turns into one thread so no history is lost.

    The title is the first thing the student said, truncated: a real preview
    of a conversation nobody can rename yet.
    """
    ChatMessage = apps.get_model("chatbot", "ChatMessage")
    ChatThread = apps.get_model("chatbot", "ChatThread")

    user_ids = (
        ChatMessage.objects.filter(thread__isnull=True)
        # Default ordering is `-created_at`; without clearing it, SQLite and
        # PostgreSQL include that column in SELECT DISTINCT, so every message
        # becomes its own "user" and the loop below runs once per message.
        .order_by()
        .values_list("user_id", flat=True)
        .distinct()
    )
    for user_id in list(user_ids):
        rows = ChatMessage.objects.filter(
            user_id=user_id, thread__isnull=True
        ).order_by("created_at")
        first = rows.first()
        if first is None:
            continue
        title = " ".join((first.message or "").split())[:80]
        thread = ChatThread.objects.create(user_id=user_id, title=title)
        rows.update(thread=thread)


def ungroup(apps, schema_editor):
    """Reverse: drop the grouping, keep the messages."""
    apps.get_model("chatbot", "ChatMessage").objects.update(thread=None)


class Migration(migrations.Migration):

    dependencies = [
        ("chatbot", "0008_chatmessage_retrieved_sources_knowledgedocument_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatThread",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", core.fields.EncryptedTextField(blank=True, default="")),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_threads",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="chatthread",
            index=models.Index(
                fields=["user", "deleted_at"], name="chatbot_cha_user_id_e1805d_idx"
            ),
        ),
        migrations.AddField(
            model_name="chatmessage",
            name="thread",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="messages",
                to="chatbot.chatthread",
            ),
        ),
        migrations.RunPython(group_existing_messages, ungroup),
    ]
