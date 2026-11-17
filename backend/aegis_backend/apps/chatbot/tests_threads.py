"""Conversation history: ownership, scoping and soft delete."""

from datetime import timedelta

from django.utils import timezone
from rest_framework import status

from apps.chatbot.models import ChatMessage, ChatThread, Flag
from apps.chatbot.tests import ChatbotBase


class ChatThreadBase(ChatbotBase):
    def thread(self, user=None, title="Math help", age_minutes=0):
        thread = ChatThread.objects.create(
            user=user or self.student_user, title=title
        )
        if age_minutes:
            ChatThread.objects.filter(pk=thread.pk).update(
                updated_at=timezone.now() - timedelta(minutes=age_minutes)
            )
        return thread

    def message(self, thread, text="hello"):
        return ChatMessage.objects.create(
            user=thread.user, thread=thread, message=text, reply="Hi!"
        )


class ThreadIsCreatedWithFirstMessageTest(ChatThreadBase):
    def test_message_creates_a_thread_and_returns_its_id(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(
            "/api/v1/chatbot/message/", {"message": "Hello there"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        thread_id = response.data["data"]["thread_id"]
        thread = ChatThread.objects.get(id=thread_id)
        self.assertEqual(thread.user, self.student_user)
        self.assertEqual(thread.title, "Hello there")

        row = ChatMessage.objects.get(user=self.student_user)
        self.assertEqual(row.thread_id, thread.id)


class ThreadListScopeTest(ChatThreadBase):
    def test_list_returns_only_the_callers_live_threads(self):
        mine = self.thread(title="Mine")
        self.thread(title="Older", age_minutes=10)
        self.thread(user=self.other_student_user, title="Theirs")

        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/v1/chatbot/threads/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        titles = [row["title"] for row in response.data["results"]]
        self.assertEqual(titles, ["Mine", "Older"])
        self.assertEqual(response.data["results"][0]["id"], str(mine.id))
        self.assertEqual(response.data["results"][0]["message_count"], 0)


class ThreadDetailScopeTest(ChatThreadBase):
    def test_detail_returns_messages_oldest_first(self):
        thread = self.thread()
        first = self.message(thread, "first")
        second = self.message(thread, "second")

        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(f"/api/v1/chatbot/threads/{thread.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["messages"]]
        self.assertEqual(ids, [str(first.id), str(second.id)])

    def test_another_users_thread_is_not_found(self):
        thread = self.thread(user=self.other_student_user)
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(f"/api/v1/chatbot/threads/{thread.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MessageThreadOwnershipTest(ChatThreadBase):
    def test_cannot_post_into_another_users_thread(self):
        thread = self.thread(user=self.other_student_user)
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(
            "/api/v1/chatbot/message/",
            {"message": "Hello", "thread_id": str(thread.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(ChatMessage.objects.filter(thread=thread).count(), 0)

    def test_invalid_thread_id_is_rejected(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(
            "/api/v1/chatbot/message/",
            {"message": "Hello", "thread_id": "not-a-uuid"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_deleted_thread_cannot_receive_new_messages(self):
        thread = self.thread()
        thread.deleted_at = timezone.now()
        thread.save(update_fields=["deleted_at"])

        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(
            "/api/v1/chatbot/message/",
            {"message": "Hello", "thread_id": str(thread.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ThreadDeleteTest(ChatThreadBase):
    def test_delete_hides_the_thread_but_keeps_the_safety_record(self):
        thread = self.thread()
        message = self.message(thread)
        flag = Flag.objects.create(
            student=self.student_profile,
            user=self.student_user,
            chat_message=message,
            severity="high",
            source=Flag.Source.KEYWORD,
        )

        self.client.force_authenticate(user=self.student_user)
        response = self.client.delete(f"/api/v1/chatbot/threads/{thread.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        thread.refresh_from_db()
        self.assertIsNotNone(thread.deleted_at)
        self.assertTrue(ChatMessage.objects.filter(id=message.id).exists())
        self.assertTrue(Flag.objects.filter(id=flag.id).exists())

        listing = self.client.get("/api/v1/chatbot/threads/")
        self.assertEqual(listing.data["results"], [])

        detail = self.client.get(f"/api/v1/chatbot/threads/{thread.id}/")
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_all_history_leaves_other_users_alone(self):
        self.thread(title="Mine")
        theirs = self.thread(user=self.other_student_user, title="Theirs")

        self.client.force_authenticate(user=self.student_user)
        response = self.client.delete("/api/v1/chatbot/history/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted"], 1)

        theirs.refresh_from_db()
        self.assertIsNone(theirs.deleted_at)


class HistoryEndpointScopeTest(ChatThreadBase):
    def test_history_hides_messages_from_deleted_threads(self):
        live = self.thread()
        self.message(live, "visible")

        gone = self.thread(title="Gone")
        self.message(gone, "hidden")
        gone.deleted_at = timezone.now()
        gone.save(update_fields=["deleted_at"])

        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/v1/chatbot/history/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        texts = [row["message"] for row in response.data["results"]]
        self.assertEqual(texts, ["visible"])
