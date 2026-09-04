"""
AEGIS AI Engine — rule-based initial labeling.

PH9 D4: Hybrid labeling:
  rule-based initial labels
  → human / Guidance refinement
  → final reviewed labels
  → Decision Tree training target

IMPORTANT:
  Do not pretend rule-generated labels are historical truth.
  They are initial labels. Human/refined labels may replace/augment.
"""

from __future__ import annotations

from ai_engine.config import PASSING_GRADE, WEAK_SUBJECT_THRESHOLD

# Risk-model config knobs (D14, OPEN/configurable)
CRITICAL_GRADE_THRESHOLD = 62   # below this = critically low average
HIGH_WEAK_THRESHOLD = 4         # at least this many weak subjects = critical


def rule_based_label(features: dict) -> str:
    """
    Compute an initial rule-based risk label from features.

    Scoring rubric (initial, configurable):
      - current_term_grade_average below passing grade: +1
      - current_term_grade_average critically low (< critical): +2
      - weak_subject_count >= HIGH_WEAK: +3, >= 3: +2, >= 1: +1
      - declining grade trend (< -5): +1
      - attendance_rate < 0.75: +1
      - consultation_count >= 3: +1
      - behavioral_count >= 2: +1

    Interpretation:
      - insufficient_data → "insufficient_data"
      - score 0 → "low"
      - score 1-4 → "moderate"
      - score >= 5 → "high"

    Severe signals (critically low average or many weak subjects) push
    toward HIGH even at the same raw point count as a MODERATE profile.
    """
    if features.get("computation_status") == "insufficient_data":
        return "insufficient_data"

    score = 0
    avg = features.get("current_term_grade_average")
    if avg is not None:
        if avg < CRITICAL_GRADE_THRESHOLD:
            score += 2
        elif avg < PASSING_GRADE:
            score += 1

    weak = features.get("weak_subject_count", 0)
    if weak >= HIGH_WEAK_THRESHOLD:
        score += 3
    elif weak >= 3:
        score += 2
    elif weak >= 1:
        score += 1

    trend = features.get("grade_trend")
    if trend is not None and trend < -5:
        score += 1

    attendance = features.get("attendance_rate")
    if attendance is not None and attendance < 0.75:
        score += 1

    consultation = features.get("consultation_count", 0)
    if consultation >= 3:
        score += 1

    behavioral = features.get("behavioral_count", 0)
    if behavioral >= 2:
        score += 1

    if score == 0:
        return "low"
    if score <= 4:
        return "moderate"
    return "high"


def reviewed_label(features: dict, manual_label: str | None) -> str:
    """
    Produce the training target label.

    If a human-reviewed label exists, it takes precedence over the
    rule-based initial label. Otherwise the rule-based label is used
    as the initial training target.
    """
    if manual_label in ("low", "moderate", "high"):
        return manual_label
    return rule_based_label(features)
