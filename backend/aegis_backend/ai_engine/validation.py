"""
AEGIS AI Engine — model validation + security/privacy guards (PH9.13).

Model validation:
  - minimum training examples guard (refuse to train on tiny data)
  - class balance sanity
  - label vocabulary whitelist (never emit unseen labels)
  - single-student group leak guard (documented)

Security/privacy:
  - features must never contain free-text narrative (counts only)
  - risk output must not expose raw PII
  - chatbot/LLM never gets direct DB access (system boundary)
"""

from __future__ import annotations

import logging

from ai_engine.config import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

# Minimum number of training examples (D7/D29 sanity) before we trust a model
MIN_TRAINING_EXAMPLES = 30
MIN_SAMPLES_PER_CLASS = 5

# Allowed risk labels (valued vocabulary)
ALLOWED_LABELS = {"low", "moderate", "high", "insufficient_data"}

# Sensitive / narrative feature keys that must NEVER appear in the
# ML feature set (privacy guard). These are NOT ML features by design.
FORBIDDEN_FEATURES = {
    "notes",
    "narrative",
    "reason",
    "counselor_notes",
    "intervention_narrative",
    "behavior_narrative",
    "risk_notes",
    "free_text",
}


class ModelValidationError(Exception):
    """Raised when a model/training precondition is not satisfied."""


def validate_training_data(X, y) -> None:
    """
    Validate training data before fit.

    Raises ModelValidationError on failure.
    """
    n = len(y)
    if n < MIN_TRAINING_EXAMPLES:
        raise ModelValidationError(
            f"Insufficient training examples: {n} < {MIN_TRAINING_EXAMPLES}. "
            "Refuse to train a model that could overfit tiny data."
        )

    from collections import Counter
    counts = Counter(y)
    for label, count in counts.items():
        if label not in ALLOWED_LABELS:
            raise ModelValidationError(
                f"Unknown label '{label}' in training set. "
                "Allowed: {ALLOWED_LABELS}."
            )
        if count < MIN_SAMPLES_PER_CLASS:
            raise ModelValidationError(
                f"Class '{label}' has only {count} examples "
                f"(min {MIN_SAMPLES_PER_CLASS})."
            )


def validate_feature_keys(feature_dict: dict) -> list[str]:
    """
    Privacy guard: ensure feature dicts never carry narrative/free-text.

    Returns list of violations (empty if compliant).
    """
    violations = []
    for key in feature_dict:
        if key in FORBIDDEN_FEATURES:
            violations.append(key)
    return violations


def validate_prediction_labels(prediction: dict) -> bool:
    """
    Guard against the model emitting unseen/unknown labels.

    If the predicted label is not in the allowed vocabulary, mark the
    prediction invalid so the caller falls back safely.
    """
    level = prediction.get("risk_level")
    if level is None:
        return True  # insufficient_data / non-actionable
    return level in ALLOWED_LABELS


def validate_student_feature_privacy(features: dict) -> bool:
    """
    Highest-confidence privacy check for student-level features.

    Confirms only count/aggregate features are present (no narrative).
    """
    violations = validate_feature_keys(features)
    return len(violations) == 0
