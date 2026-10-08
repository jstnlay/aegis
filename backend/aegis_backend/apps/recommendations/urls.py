"""Recommendation URL routes."""

from django.urls import path

from .views import RecommendationsView, StudentInteractionView

app_name = "recommendations"

urlpatterns = [
    path(
        "students/<uuid:student_id>/",
        RecommendationsView.as_view(),
        name="recommendations-student",
    ),
    path(
        "interactions/",
        StudentInteractionView.as_view(),
        name="recommendations-interaction",
    ),
]