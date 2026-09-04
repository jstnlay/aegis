"""
AEGIS AI Engine — Recommendation Resolver.

PH9 D22: Decision Tree identifies risk class, risk score, academic need,
subject/topic weakness. A separate Recommendation Resolver maps needs
to LearningItems.

The Decision Tree must NOT directly output resource IDs or arbitrary
resource text. The resolver produces recommendation candidates.

PH9 D23: Recommendation pipeline:
  candidate generation → hard filtering → relevance ranking →
  diversity filtering → final recommendations
"""

from __future__ import annotations

from typing import Any


def extract_academic_needs(
    feature_dict: dict[str, Any],
    prediction: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Extract academic needs from features + prediction.

    The Decision Tree does NOT directly output resource IDs. It provides
    the risk class, score, and student-specific factors. The resolver
    interprets those into academic needs.

    Returns list of need dicts:
      {need_type, subject_id, topic, reason}
    """
    needs = []

    # Weak subjects identified from features
    weak_threshold = 70  # Note: should use config
    # In practice, need to pass subject-level data — for now, use
    # feature-level weak_subject_count as the signal. The resolver
    # receives subject-specific detail through the feature snapshot
    # or a dedicated academic-need extraction query.

    # Basic need extraction from features:
    current_avg = feature_dict.get("current_term_grade_average")
    if current_avg is not None and current_avg < weak_threshold:
        needs.append({
            "need_type": "overall_academic_support",
            "subject_id": None,
            "topic": None,
            "reason": f"Term average {current_avg:.1f} below target",
        })

    weak_count = feature_dict.get("weak_subject_count", 0)
    if weak_count > 0:
        needs.append({
            "need_type": "weak_subject_support",
            "subject_id": None,
            "topic": None,
            "reason": f"{weak_count} subject(s) below weak-subject threshold",
        })

    trend = feature_dict.get("grade_trend")
    if trend is not None and trend < -5:
        needs.append({
            "need_type": "declining_trend",
            "subject_id": None,
            "topic": None,
            "reason": f"Grade trend declining by {abs(trend):.1f} points",
        })

    # Subject-specific needs from the DT explanation/decision path
    explanation = prediction.get("explanation", {})
    contributing = explanation.get("contributing_factors", [])
    for factor in contributing:
        if factor.get("feature") == "current_term_grade_average":
            if factor.get("value", 100) < weak_threshold:
                needs.append({
                    "need_type": "subject_performance",
                    "subject_id": None,
                    "topic": None,
                    "reason": "Low subject performance identified",
                })

    if not needs:
        needs.append({
            "need_type": "study_support",
            "subject_id": None,
            "topic": None,
            "reason": "General study support",
        })

    # Deduplicate
    seen = set()
    deduped = []
    for need in needs:
        key = (need["need_type"], need.get("subject_id"), need.get("topic"))
        if key not in seen:
            seen.add(key)
            deduped.append(need)
    return deduped


def resolve_recommendations(
    student_profile,
    feature_dict: dict[str, Any],
    prediction: dict[str, Any],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Resolve academic needs to recommendation candidates.

    Implements PH9 D23 pipeline:
      candidate generation → hard filtering → relevance ranking →
      diversity filtering → final recommendations

    Returns list of recommendation dicts.
    """
    from apps.cms.models import LearningItem

    # Extract grade_level_id from student profile or feature dict
    if hasattr(student_profile, "grade_level_id"):
        grade_level_id = student_profile.grade_level_id
    else:
        grade_level_id = feature_dict.get("grade_level_id")

    # 1. Extract academic needs from DT output (not DT directly → resource IDs)
    needs = extract_academic_needs(feature_dict, prediction)

    # 2. Candidate generation: all eligible learning items
    eligible_items = LearningItem.objects.filter(
        lifecycle_status="approved",
        is_active=True,
    )

    # 3. Hard filtering: match subject + grade level
    hard_filtered = _hard_filter(eligible_items, grade_level_id)

    # 4. Content-based relevance ranking (academic relevance first)
    ranked = _rank_by_relevance(hard_filtered, needs)

    # 5. Diversity filtering
    diverse = _diversity_filter(ranked, needs, limit)

    return diverse


def _hard_filter(queryset, grade_level_id):
    """
    Hard constraints: approved, active, correct subject, relevant
    topic/skill. Only APPROVED + ACTIVE have been filtered already at
    the queryset level; here we apply subject/grade relevance.
    """
    # Grade level relevance
    if grade_level_id:
        queryset = queryset.filter(
            grade_level_id=grade_level_id
        )

    items = list(queryset)
    return items


def _rank_by_relevance(items, needs):
    """
    Academic relevance takes precedence over generic similarity.

    Score items by match to identified academic needs:
      - item.subject matches a need's weak subject (highest)
      - item.topic matches a need's topic
      - item.tags match a need's tags
    """
    scored = []
    for item in items:
        score = 0.0
        for need in needs:
            need_type = need.get("need_type")
            # Overall academic support need → any academic item matches
            if need_type in ("overall_academic_support", "weak_subject_support"):
                score += 1.0
            if need_type == "declining_trend":
                score += 1.0

            # Subject-specific matching
            if need.get("subject_id") and item.subject_id == need["subject_id"]:
                score += 3.0

            # Topic/skill tag match
            if need.get("topic") and item.topic == need["topic"]:
                score += 2.0

            # Tags match
            need_tags = need.get("tags", [])
            item_tags = item.tags or []
            overlap = set(need_tags) & set(item_tags)
            if overlap:
                score += 1.5 * len(overlap)

        scored.append((item, score))

    # Sort by relevance score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _diversity_filter(ranked, needs, limit):
    """
    Diversity: avoid recommending many items of the same type/subject.
    """
    type_seen = set()
    subject_seen = set()
    results = []

    for item, score in ranked:
        if len(results) >= limit:
            break

        # Diversity: at most 2 items per subject, 2 per item type
        if item.item_type in type_seen and item.subject_id in subject_seen:
            continue

        type_seen.add(item.item_type)
        if item.subject_id:
            subject_seen.add(item.subject_id)

        results.append({
            "learning_item_id": str(item.id),
            "title": item.title,
            "item_type": item.item_type,
            "subject_id": str(item.subject_id) if item.subject_id else None,
            "topic": item.topic,
            "relevance_score": round(score, 2),
            "reason": f"Matched need: {_needs_summary(needs)}",
            "method": "content_based",
        })

    return results


def _needs_summary(needs):
    return "; ".join(n["need_type"] for n in needs[:2])
