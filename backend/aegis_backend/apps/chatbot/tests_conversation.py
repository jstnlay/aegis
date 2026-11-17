"""
Free conversation, bounded memory, and the record boundary.

The assistant now answers ordinary questions with Gemini. What must not change
is that a grade, an attendance count or an escalation is answered by the code
that computed it: those are the facts a student acts on, and a model reply is a
chance to change them. These tests pin both halves.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings

from apps.chatbot.models import ChatMessage, ChatThread
from apps.chatbot.pipeline import MEMORY_TURNS, _recent_turns, process_message
from apps.chatbot.tests import ChatbotBase


def detection(**overrides):
    """A non-sensitive detection result, so the pipeline reaches the reply path."""
    values = {
        "sensitive": False,
        "severity": "low",
        "categories": [],
        "manual_review": False,
        "source": "none",
        "layer1": SimpleNamespace(sensitive=False, matches=[]),
        "layer2": None,
    }
    values.update(overrides)
    values["to_dict"] = lambda: {}
    return SimpleNamespace(**values)


def thread_with_turn(user, message, reply, *, sensitive=False):
    thread = ChatThread.objects.create(user=user, title=message[:40])
    ChatMessage.objects.create(
        user=user,
        thread=thread,
        message=message,
        reply=reply,
        sensitive=sensitive,
    )
    return thread


@override_settings(GEMINI_API_KEY="test-key")
class FreeConversationTest(ChatbotBase):
    def test_a_general_question_is_answered_by_the_model(self):
        with (
            patch("apps.chatbot.pipeline.detect", return_value=detection()),
            patch(
                "apps.chatbot.pipeline.gemini_client.chat",
                return_value="Paris is the capital of France.",
            ) as chat,
        ):
            response = process_message(
                self.student_user, "What is the capital of France?"
            )

        self.assertEqual(response.reply, "Paris is the capital of France.")
        self.assertTrue(chat.called)

    def test_the_model_sees_only_this_threads_turns(self):
        thread = thread_with_turn(
            self.student_user,
            "My favourite colour is green.",
            "Noted.",
        )
        thread_with_turn(
            self.student_user,
            "A different chat.",
            "Noted.",
        )

        with (
            patch("apps.chatbot.pipeline.detect", return_value=detection()),
            patch(
                "apps.chatbot.pipeline.gemini_client.chat",
                return_value="Green is a calm colour.",
            ) as chat,
        ):
            process_message(
                self.student_user, "What do you think of it?", thread=thread
            )

        self.assertEqual(
            chat.call_args.kwargs["history"],
            [{"message": "My favourite colour is green.", "reply": "Noted."}],
        )

    def test_memory_is_capped_and_ordered_oldest_first(self):
        thread = ChatThread.objects.create(user=self.student_user, title="Chat")
        for index in range(MEMORY_TURNS + 4):
            ChatMessage.objects.create(
                user=self.student_user,
                thread=thread,
                message=f"message {index}",
                reply=f"reply {index}",
            )

        turns = _recent_turns(thread)

        self.assertEqual(len(turns), MEMORY_TURNS)
        self.assertEqual(turns[-1]["message"], f"message {MEMORY_TURNS + 3}")

    def test_a_sensitive_turn_is_not_replayed_to_the_model(self):
        thread = thread_with_turn(
            self.student_user,
            "I am being bullied every day.",
            "Thank you for telling me.",
            sensitive=True,
        )

        with (
            patch("apps.chatbot.pipeline.detect", return_value=detection()),
            patch(
                "apps.chatbot.pipeline.gemini_client.chat",
                return_value="Here is a joke.",
            ) as chat,
        ):
            process_message(self.student_user, "Tell me a joke.", thread=thread)

        self.assertNotIn("bullied", str(chat.call_args.kwargs["history"]))


@override_settings(GEMINI_API_KEY="test-key")
class DefinitionQuestionTest(ChatbotBase):
    """A definition is general knowledge, even when it names a school word."""

    def test_a_definition_does_not_become_a_resource_request(self):
        with (
            patch("apps.chatbot.pipeline.detect", return_value=detection()),
            patch(
                "apps.chatbot.pipeline.gemini_client.chat",
                return_value="Study is the act of learning something.",
            ) as chat,
        ):
            response = process_message(
                self.student_user, "What is the meaning of study?"
            )

        self.assertTrue(chat.called)
        self.assertEqual(response.intent.value, "unknown")
        self.assertEqual(response.reply, "Study is the act of learning something.")
        self.assertNotIn("approved learning resources", response.reply)

    def test_a_resource_request_still_names_the_documents(self):
        with (
            patch("apps.chatbot.pipeline.detect", return_value=detection()),
            patch("apps.chatbot.pipeline.gemini_client.chat") as chat,
        ):
            response = process_message(
                self.student_user, "Do you have study materials for Science?"
            )

        chat.assert_not_called()
        self.assertEqual(response.intent.value, "ask_learning_resource")


@override_settings(GEMINI_API_KEY="test-key")
class RecordBoundaryTest(ChatbotBase):
    def test_a_grade_question_never_reaches_the_model(self):
        with (
            patch("apps.chatbot.pipeline.detect", return_value=detection()),
            patch("apps.chatbot.pipeline.gemini_client.chat") as chat,
        ):
            response = process_message(
                self.student_user, "What is my grade in Math?"
            )

        chat.assert_not_called()
        self.assertEqual(response.intent.value, "ask_grade")

    def test_an_attendance_question_never_reaches_the_model(self):
        with (
            patch("apps.chatbot.pipeline.detect", return_value=detection()),
            patch("apps.chatbot.pipeline.gemini_client.chat") as chat,
        ):
            response = process_message(self.student_user, "What is my attendance?")

        chat.assert_not_called()
        self.assertEqual(response.intent.value, "ask_attendance")

    def test_an_escalation_never_reaches_the_model(self):
        """The reply must not imply more happened than the escalation did."""
        with (
            patch("apps.chatbot.pipeline.detect", return_value=detection()),
            patch("apps.chatbot.pipeline.gemini_client.chat") as chat,
        ):
            response = process_message(
                self.student_user, "I want to talk to a counselor."
            )

        chat.assert_not_called()
        self.assertTrue(response.escalated)
