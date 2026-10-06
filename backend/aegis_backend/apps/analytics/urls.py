"""Phase 9 analytics app URL patterns."""

from django.urls import path

from apps.analytics import views


urlpatterns = [
    path(
        "students/<uuid:student_id>/metrics/",
        views.StudentMetricsView.as_view(),
        name="analytics-student-metrics",
    ),
    # PH11.10: real per-period academic and per-day attendance trends. The
    # metrics endpoint cannot supply either — its latest_period_average is the
    # overall average restated, and the attendance summary has no date axis.
    path(
        "students/<uuid:student_id>/academic-trend/",
        views.StudentAcademicTrendView.as_view(),
        name="analytics-student-academic-trend",
    ),
    path(
        "students/<uuid:student_id>/attendance-trend/",
        views.StudentAttendanceTrendView.as_view(),
        name="analytics-student-attendance-trend",
    ),
    path(
        "academic-trend/",
        views.SchoolWideAcademicTrendView.as_view(),
        name="analytics-school-wide-academic-trend",
    ),
    path(
        "attendance-trend/",
        views.SchoolWideAttendanceTrendView.as_view(),
        name="analytics-school-wide-attendance-trend",
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
