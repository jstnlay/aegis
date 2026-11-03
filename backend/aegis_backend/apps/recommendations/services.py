"""
Recommendation service.

Both the HTTP view and the chatbot use the same computation. Keeping the
feature/prediction assembly here means a chatbot answer cannot describe a
different recommendation than the recommendations endpoint returns.
"""

from __future__ import annotations

from datetime import date
from typing import Any


def student_signals(student) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Feature dict + prediction for the content-based path.

    Returns `(features, prediction)`. The prediction is empty when the risk
    engine has not run, because a fabricated risk level would let
    `extract_academic_needs` invent a need. `resolve_recommendations` reads
    needs from the feature dict regardless, so content-based still works off
    real grades and attendance alone.
    """
    from apps.academics.models import AcademicYear, GradingPeriod
    from ai_engine.feature_engine import compute_student_features

    year = (
        AcademicYear.objects.filter(is_current=True)
        .order_by("-start_date")
        .first()
    )
    if year is None:
        return {}, {}

    completed = list(
        GradingPeriod.objects.filter(
            academic_year=year, end_date__lte=date.today()
        ).order_by("order")
    )

    features = compute_student_features(student, completed, year)

    # The latest stored RiskScore for this student, if the engine has run.
    # A read-only lookup: nothing here triggers a computation.
    from apps.guidance.models import RiskScore

    latest = (
        RiskScore.objects.filter(student=student)
        .order_by("-computed_at")
        .first()
    )
    if latest is None:
        return features, {}

    return features, {
        "risk_level": latest.risk_level,
        "risk_score": latest.risk_score,
        "explanation": latest.explanation or {},
    }


def recommend_for_student(student, *, limit: int = 5) -> dict[str, Any]:
    """Compute the same recommendations the recommendations endpoint serves."""
    from apps.cms.models import LearningItem, StudentInteraction
    from ai_engine.recommender import recommend

    # Every interaction in the school, not just this student's. CF computes
    # item-item similarity across the whole cohort; scoping the matrix to one
    # student would make every similarity zero by construction.
    interactions = list(StudentInteraction.objects.select_related("learning_item"))

    # Only APPROVED + ACTIVE items are recommendable. `LearningItem
    # .is_recommendation_eligible` is that rule; it is applied here rather
    # than inside the recommender because the recommender is also used by
    # offline benchmark code that supplies its own item list.
    learning_items = [
        item
        for item in LearningItem.objects.all()
        if item.is_recommendation_eligible
    ]

    features, prediction = student_signals(student)

    return recommend(
        student,
        interactions,
        learning_items,
        feature_dict=features,
        prediction=prediction,
        limit=limit,
    )
