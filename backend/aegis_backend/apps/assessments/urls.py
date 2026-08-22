"""
Assessments URL configuration.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AssessmentViewSet, AssessmentQuestionViewSet, AssessmentResultViewSet

router = DefaultRouter()
router.register(r'assessments', AssessmentViewSet, basename='assessment')
router.register(r'assessment-questions', AssessmentQuestionViewSet, basename='assessmentquestion')
router.register(r'assessment-results', AssessmentResultViewSet, basename='assessmentresult')

urlpatterns = [
    path('', include(router.urls)),
]
