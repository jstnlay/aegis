"""Chatbot URL routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.chatbot import views

router = DefaultRouter()
router.register("admin/keywords", views.KeywordTermViewSet, basename="keyword-term")
router.register(
    "admin/knowledge", views.KnowledgeDocumentViewSet, basename="knowledge-document"
)

urlpatterns = [
    path("message/", views.ChatView.as_view(), name="chatbot-message"),
    path("history/", views.ChatHistoryView.as_view(), name="chatbot-history"),
    path("notice/", views.NoticeView.as_view(), name="chatbot-notice"),
    path(
        "notice/public/",
        views.PublicNoticeView.as_view(),
        name="chatbot-notice-public",
    ),
    path("intents/", views.IntentsView.as_view(), name="chatbot-intents"),
    path("flags/", views.FlagListView.as_view(), name="chatbot-flag-list"),
    path("flags/<uuid:pk>/", views.FlagDetailView.as_view(), name="chatbot-flag-detail"),
    path(
        "flags/<uuid:pk>/acknowledge/",
        views.FlagAcknowledgeView.as_view(),
        name="chatbot-flag-acknowledge",
    ),
    path("flags/<uuid:pk>/notes/", views.FlagNoteView.as_view(), name="chatbot-flag-note"),
    path(
        "flags/<uuid:pk>/resolve/",
        views.FlagResolveView.as_view(),
        name="chatbot-flag-resolve",
    ),
    path(
        "flags/<uuid:pk>/false-positive/",
        views.FlagFalsePositiveView.as_view(),
        name="chatbot-flag-false-positive",
    ),
    path(
        "flags/<uuid:pk>/intervention-suggestions/",
        views.FlagInterventionSuggestionsView.as_view(),
        name="chatbot-flag-interventions",
    ),
    path(
        "flags/<uuid:pk>/assessment-draft/",
        views.FlagAssessmentDraftView.as_view(),
        name="chatbot-flag-assessment-draft",
    ),
    path(
        "admin/dashboard/",
        views.AdminDashboardView.as_view(),
        name="chatbot-admin-dashboard",
    ),
    path(
        "admin/model-status/",
        views.AdminModelStatusView.as_view(),
        name="chatbot-admin-model-status",
    ),
    path(
        "admin/escalate/",
        views.AdminEscalateView.as_view(),
        name="chatbot-admin-escalate",
    ),
    path("", include(router.urls)),
]
