"""
Assessments URL configuration.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AssessmentViewSet,
    AssessmentQuestionViewSet,
    AssessmentResultViewSet,
    QuestionDraftView,
)

router = DefaultRouter()
router.register(r'assessments', AssessmentViewSet, basename='assessment')
router.register(r'assessment-questions', AssessmentQuestionViewSet, basename='assessmentquestion')
router.register(r'assessment-results', AssessmentResultViewSet, basename='assessmentresult')

urlpatterns = [
    # FR-027. Not a ViewSet: it has no resource behind it and no GET.
    path('question-drafts/', QuestionDraftView.as_view(), name='question-drafts'),
    path('', include(router.urls)),
]
