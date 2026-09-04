"""Phase 9 analytics app URL patterns."""

from django.urls import path

from apps.analytics import views


urlpatterns = [
    path(
        "students/<uuid:student_id>/metrics/",
        views.StudentMetricsView.as_view(),
        name="analytics-student-metrics",
    ),
    path(
        "sections/<uuid:section_id>/performance/",
        views.SectionPerformanceView.as_view(),
        name="analytics-section-performance",
    ),
    path(
        "grade-levels/comparison/",
        views.GradeLevelComparisonView.as_view(),
        name="analytics-grade-level-comparison",
    ),
    path(
        "subjects/trends/",
        views.SubjectTrendsView.as_view(),
        name="analytics-subject-trends",
    ),
    path(
        "school-wide/",
        views.SchoolWideAggregatesView.as_view(),
        name="analytics-school-wide",
    ),
    path(
        "risk-distribution/",
        views.RiskDistributionView.as_view(),
        name="analytics-risk-distribution",
    ),
    path(
        "low-performance/",
        views.LowPerformanceView.as_view(),
        name="analytics-low-performance",
    ),
]
