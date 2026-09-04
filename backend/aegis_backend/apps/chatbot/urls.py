"""Phase 9 chatbot app URL patterns."""

from django.urls import path

from apps.chatbot import views


urlpatterns = [
    path("message/", views.ChatView.as_view(), name="chatbot-message"),
    path("intents/", views.IntentsView.as_view(), name="chatbot-intents"),
]
