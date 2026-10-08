"""
AEGIS AI Engine — Decision Tree risk scorer.

PH9 D6/D7/D11/D12: Decision Tree predicts LOW / MODERATE / HIGH.

Risk Index:
  P(LOW) × 0 + P(MODERATE) × 50 + P(HIGH) × 100

Baseline config (D7):
  DecisionTreeClassifier
  criterion = gini
  splitter = best
  max_depth = 4
  min_samples_split = 10
  min_samples_leaf = 5
  random_state = 42

Student-level grouped validation:
  Do NOT split different terms of the same student across train/test.

PH9.5 correction:
  feature_importances_ is model-level, NOT student-specific.
  For student explanations, use the actual decision path / rule path.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.tree import DecisionTreeClassifier

from ai_engine.config import (
    DT_CRITERION,
    DT_MAX_DEPTH,
    DT_MIN_SAMPLES_LEAF,
    DT_MIN_SAMPLES_SPLIT,
    DT_RANDOM_STATE,
    DT_SPLITTER,
    FEATURE_COLUMNS,
    RISK_INDEX_ANCHORS,
)

logger = logging.getLogger(__name__)

RISK_CLASSES = ["low", "moderate", "high"]

# Model persistence path
MODEL_DIR = Path(__file__).resolve().parent / "saved_models"
MODEL_PATH = MODEL_DIR / "decision_tree_v1.pkl"


def build_model() -> DecisionTreeClassifier:
    """Create a DecisionTreeClassifier with D7 baseline config."""
    return DecisionTreeClassifier(
        criterion=DT_CRITERION,
        splitter=DT_SPLITTER,
        max_depth=DT_MAX_DEPTH,
        min_samples_split=DT_MIN_SAMPLES_SPLIT,
        min_samples_leaf=DT_MIN_SAMPLES_LEAF,
        random_state=DT_RANDOM_STATE,
    )


def features_to_matrix(
    feature_dicts: list[dict[str, Any]],
) -> tuple[np.ndarray, list[str]]:
    """
    Convert feature dicts to numpy array for sklearn.

    Missing values are filled with column median (or 0 if all missing).
    Returns (X, student_ids).
    """
    student_ids = [f["student_id"] for f in feature_dicts]
    X = []
    for f in feature_dicts:
        row = []
        for col in FEATURE_COLUMNS:
            val = f.get(col)
            if val is None:
                row.append(0.0)
            else:
                row.append(float(val))
        X.append(row)
    return np.array(X, dtype=np.float64), student_ids


def labels_to_array(label_dicts: list[dict[str, Any]]) -> np.ndarray:
    """Extract label array from feature+label dicts."""
    return np.array([d.get("label", "low") for d in label_dicts])


def train(
    feature_label_dicts: list[dict[str, Any]],
    model_version: str = "v1",
) -> tuple[DecisionTreeClassifier, dict[str, Any]]:
    """
    Train the Decision Tree on labeled feature data.

    Args:
        feature_label_dicts: list of dicts with features + 'label' key
        model_version: version identifier for this model

    Returns:
        (trained_model, metadata_dict)
    """
    # Filter out insufficient_data entries
    valid = [
        d for d in feature_label_dicts
        if d.get("label") not in ("insufficient_data", "error", None)
    ]

    if len(valid) < DT_MIN_SAMPLES_SPLIT:
        logger.warning(
            "Insufficient labeled data for training: %d samples "
            "(need at least %d)",
            len(valid),
            DT_MIN_SAMPLES_SPLIT,
        )
        return None, {"error": "insufficient_training_data"}

    X, student_ids = features_to_matrix(valid)
    y = labels_to_array(valid)

    model = build_model()
    model.fit(X, y)

    metadata = {
        "model_version": model_version,
        "n_samples": len(valid),
        "n_features": X.shape[1],
        "feature_columns": FEATURE_COLUMNS,
        "classes": list(model.classes_),
        "feature_importances_": {
            col: round(float(imp), 4)
            for col, imp in zip(FEATURE_COLUMNS, model.feature_importances_)
        },
    }

    return model, metadata


def predict_single(
    model: DecisionTreeClassifier,
    feature_dict: dict[str, Any],
    model_version: str = "v1",
) -> dict[str, Any]:
    """
    Predict risk for a single student using the Decision Tree.

    Returns dict with:
      - risk_level: LOW / MODERATE / HIGH
      - risk_score: 0-100 index
      - class_probabilities: {low: P, moderate: P, high: P}
      - explanation: student-specific decision path factors
      - model_version: identifier
    """
    if feature_dict.get("computation_status") == "insufficient_data":
        return {
            "computation_status": "insufficient_data",
            "risk_score": None,
            "risk_level": None,
            "class_probabilities": {},
            "explanation": {},
            "model_version": model_version,
        }

    # Build feature row
    row = []
    for col in FEATURE_COLUMNS:
        val = feature_dict.get(col)
        row.append(float(val) if val is not None else 0.0)
    X = np.array([row], dtype=np.float64)

    # Predict class and probabilities
    predicted_class = model.predict(X)[0]
    probabilities = model.predict_proba(X)[0]
    class_probs = {
        cls: round(float(prob), 4)
        for cls, prob in zip(model.classes_, probabilities)
    }

    # Risk Index: P(LOW) × 0 + P(MODERATE) × 50 + P(HIGH) × 100
    risk_score = sum(
        class_probs.get(cls, 0) * anchor
        for cls, anchor in RISK_INDEX_ANCHORS.items()
    )
    risk_score = round(min(100, max(0, risk_score)), 2)

    # Extract student-specific decision path explanation
    explanation = _extract_decision_path(model, X[0], feature_dict)

    return {
        "computation_status": "ready",
        "risk_level": predicted_class,
        "risk_score": risk_score,
        "class_probabilities": class_probs,
        "explanation": explanation,
        "model_version": model_version,
    }


def _extract_decision_path(
    model: DecisionTreeClassifier,
    x_row: np.ndarray,
    feature_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Extract student-specific decision path from the Decision Tree.

    PH9.5 correction: Do NOT use feature_importances_ as student explanation.
    Use the actual decision path / rule path for individual students.
    """
    from sklearn.tree import _tree

    tree = model.tree_
    feature_names = FEATURE_COLUMNS

    # Traverse the decision path
    node_indicator = model.decision_path(np.array([x_row]))
    node_indices = node_indicator.indices[node_indicator.indptr[0]:node_indicator.indptr[1]]

    contributing_factors = []
    for node_id in node_indices:
        if tree.children_left[node_id] == tree.children_right[node_id]:
            # Leaf node — this is the final decision
            continue
        feature_idx = tree.feature[node_id]
        threshold = tree.threshold[node_id]
        feature_name = feature_names[feature_idx] if feature_idx < len(feature_names) else f"feature_{feature_idx}"
        feature_value = float(x_row[feature_idx])

        direction = "below" if feature_value <= threshold else "above"
        contributing_factors.append({
            "feature": feature_name,
            "threshold": round(float(threshold), 4),
            "value": round(feature_value, 4),
            "direction": direction,
        })

    return {
        "contributing_factors": contributing_factors,
        "path_length": len(contributing_factors),
    }


def predict_batch(
    model: DecisionTreeClassifier,
    feature_dicts: list[dict[str, Any]],
    model_version: str = "v1",
) -> list[dict[str, Any]]:
    """Predict risk for a batch of students."""
    return [
        predict_single(model, f, model_version)
        for f in feature_dicts
    ]


def save_model(
    model: DecisionTreeClassifier,
    metadata: dict[str, Any],
    path: Path | None = None,
) -> Path:
    """Persist trained model to disk."""
    save_path = path or MODEL_PATH
    save_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"model": model, "metadata": metadata}
    with open(save_path, "wb") as f:
        pickle.dump(payload, f)
    logger.info("Model saved to %s", save_path)
    return save_path


def load_model(path: Path | None = None) -> tuple[DecisionTreeClassifier, dict[str, Any]]:
    """Load persisted model from disk."""
    load_path = path or MODEL_PATH
    with open(load_path, "rb") as f:
        payload = pickle.load(f)
    return payload["model"], payload["metadata"]


def save_stored_model(
    model: DecisionTreeClassifier,
    metadata: dict[str, Any],
    *,
    version: str = "v1",
    academic_year=None,
) -> Any:
    """
    Persist a trained model as a `RiskModelArtifact` row.

    The database is the store because the deployment host has no persistent
    disk: a model written to MODEL_PATH is lost on every deploy, and
    `run_risk_computation` then refuses to score anyone. Persisting here means a
    retrain is the only thing that changes the model, and it is auditable.

    Returns the saved artifact. The new artifact activates immediately and any
    previously active artifact of the same version is superseded, so a stale
    tree cannot be picked up afterwards.
    """
    from apps.guidance.models import RiskModelArtifact

    # Supersede first. A partial unique index allows only one active row per
    # version, so inserting before deactivating would violate it.
    RiskModelArtifact.objects.filter(
        version=version, is_active=True
    ).update(is_active=False)

    artifact = RiskModelArtifact(
        version=version,
        payload=pickle.dumps({"model": model, "metadata": metadata}),
        metadata=dict(metadata),
        academic_year=academic_year,
        n_samples=metadata.get("n_samples", 0),
        is_active=True,
    )
    artifact.save()
    return artifact


def load_stored_model(version: str = "v1") -> tuple[DecisionTreeClassifier, dict[str, Any]] | None:
    """
    Load the active stored artifact for `version`.

    Returns (model, metadata), or None when no active artifact exists or the
    stored bytes cannot be read. Returning None rather than raising is what lets
    `run_risk_computation` print an instruction and stop instead of raising a
    traceback at the operator.

    A corrupt or incompatible artifact is treated as absent: an unreadable
    estimator cannot be scored with, and silently substituting a fallback would
    fabricate a risk level.
    """
    from apps.guidance.models import RiskModelArtifact

    artifact = (
        RiskModelArtifact.objects.filter(version=version, is_active=True)
        .order_by("-created_at")
        .first()
    )
    if artifact is None:
        return None

    try:
        payload = pickle.loads(bytes(artifact.payload))
    except Exception:
        logger.exception(
            "Stored risk model for version %s could not be unpickled; "
            "treating it as absent.",
            version,
        )
        return None

    model = payload.get("model")
    if model is None:
        return None

    return model, payload.get("metadata") or {}
