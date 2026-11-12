"""
Binary at-risk Decision Tree.

The existing three-class scorer (``risk_scorer.py``) predicts low / moderate /
high. This module answers a narrower operational question: is this student
currently at risk, using four features a school can explain to a family:

    attendance_rate
    current_term_grade_average
    weak_subject_count
    grade_trend

The label is a documented rubric, not ground truth. Until counselors confirm
labels, the tree reproduces the rubric. Its value is a consistent, inspectable
trigger and a decision path that names the factors, not a claim of predictive
accuracy.

Alerts created here are actionable ``RiskAlert`` rows with
``source="decision_tree"``. A repeated run does not create a duplicate while an
at-risk alert for the same student is still active.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

import numpy as np
from sklearn.tree import DecisionTreeClassifier

logger = logging.getLogger(__name__)

MODEL_VERSION = "at_risk_v1"
FEATURE_COLUMNS = (
    "attendance_rate",
    "current_term_grade_average",
    "weak_subject_count",
    "grade_trend",
)
MODEL_DIR = Path(__file__).resolve().parent / "saved_models"
MODEL_PATH = MODEL_DIR / "at_risk_v1.pkl"
MIN_SAMPLES = 20


def build_model() -> DecisionTreeClassifier:
    return DecisionTreeClassifier(
        criterion="gini",
        splitter="best",
        max_depth=4,
        min_samples_split=10,
        min_samples_leaf=5,
        class_weight="balanced",
        random_state=42,
    )


def rule_label(features: dict) -> int:
    """Documented rubric used as the training label."""
    average = features.get("current_term_grade_average")
    attendance = features.get("attendance_rate")
    weak = features.get("weak_subject_count") or 0
    trend = features.get("grade_trend")
    if average is not None and average < 75:
        return 1
    if attendance is not None and attendance < 0.85:
        return 1
    if weak >= 2:
        return 1
    if trend is not None and trend <= -3:
        return 1
    return 0


def _row(features: dict) -> list[float]:
    return [
        float(features.get(column)) if features.get(column) is not None else 0.0
        for column in FEATURE_COLUMNS
    ]


def train(feature_dicts: list[dict]) -> tuple[DecisionTreeClassifier | None, dict]:
    """Train on feature dicts that carry ``at_risk_label``."""
    valid = [
        item
        for item in feature_dicts
        if item.get("computation_status") != "insufficient_data"
        and item.get("at_risk_label") is not None
    ]
    if len(valid) < MIN_SAMPLES:
        return None, {"error": "insufficient_training_data", "n_samples": len(valid)}

    labels = [int(item["at_risk_label"]) for item in valid]
    if len(set(labels)) < 2:
        return None, {"error": "single_class_training_data", "n_samples": len(valid)}

    X = np.array([_row(item) for item in valid], dtype=np.float64)
    y = np.array(labels)
    model = build_model()
    model.fit(X, y)

    metadata = {
        "model_version": MODEL_VERSION,
        "n_samples": len(valid),
        "n_features": X.shape[1],
        "feature_columns": list(FEATURE_COLUMNS),
        "classes": [int(value) for value in model.classes_],
        "feature_importances_": {
            column: round(float(value), 4)
            for column, value in zip(FEATURE_COLUMNS, model.feature_importances_)
        },
        "label_source": "documented rubric",
        "label_caveat": (
            "Labels come from the at-risk rubric in at_risk.rule_label, not "
            "from counselor-confirmed outcomes. Accuracy against these labels "
            "is circular."
        ),
    }
    return model, metadata


def predict(model: DecisionTreeClassifier, features: dict) -> dict:
    """Predict one student and return the decision path as named factors."""
    X = np.array([_row(features)], dtype=np.float64)
    prediction = int(model.predict(X)[0])
    probabilities = model.predict_proba(X)[0]
    class_index = list(model.classes_).index(1) if 1 in model.classes_ else None
    probability = (
        float(probabilities[class_index]) if class_index is not None else 0.0
    )
    return {
        "at_risk": bool(prediction),
        "probability": round(probability, 4),
        "risk_level": "high" if prediction else "low",
        "risk_score": round(probability * 100, 2),
        "explanation": {
            "model": MODEL_VERSION,
            "contributing_factors": _decision_path(model, X[0], features),
        },
    }


def _decision_path(model, row, features) -> list[dict]:
    tree = model.tree_
    node_indicator = model.decision_path(np.array([row]))
    node_indices = node_indicator.indices[
        node_indicator.indptr[0] : node_indicator.indptr[1]
    ]
    factors = []
    for node_id in node_indices:
        if tree.children_left[node_id] == tree.children_right[node_id]:
            continue
        feature_index = tree.feature[node_id]
        feature_name = FEATURE_COLUMNS[feature_index]
        factors.append(
            {
                "feature": feature_name,
                "value": features.get(feature_name),
                "threshold": round(float(tree.threshold[node_id]), 4),
                "direction": (
                    "below"
                    if row[feature_index] <= tree.threshold[node_id]
                    else "above"
                ),
                "model": MODEL_VERSION,
            }
        )
    return factors


def has_active_at_risk_alert(student) -> bool:
    """
    Does this student already have an open alert from this model?

    A repeated run must not stack a second alert on a student Guidance is
    already working. The check is in Python rather than a JSON query because
    `risk_factors` is a JSONField and a containment query is not portable to
    the SQLite test database.
    """
    from apps.guidance.models import RiskAlert

    existing = RiskAlert.objects.filter(
        student=student,
        status__in=[RiskAlert.Status.ACTIVE, RiskAlert.Status.UNDER_MONITORING],
    )
    return any(
        any(
            isinstance(factor, dict) and factor.get("model") == MODEL_VERSION
            for factor in (alert.risk_factors or [])
        )
        for alert in existing
    )


def save_stored_model(model, metadata: dict, *, academic_year=None):
    from apps.guidance.models import RiskModelArtifact

    RiskModelArtifact.objects.filter(
        version=MODEL_VERSION, is_active=True
    ).update(is_active=False)
    artifact = RiskModelArtifact(
        version=MODEL_VERSION,
        payload=pickle.dumps({"model": model, "metadata": metadata}),
        metadata=dict(metadata),
        academic_year=academic_year,
        n_samples=metadata.get("n_samples", 0),
        is_active=True,
    )
    artifact.save()
    return artifact


def load_stored_model():
    from apps.guidance.models import RiskModelArtifact

    artifact = (
        RiskModelArtifact.objects.filter(version=MODEL_VERSION, is_active=True)
        .order_by("-created_at")
        .first()
    )
    if artifact is None:
        return None
    try:
        payload = pickle.loads(bytes(artifact.payload))
    except Exception:
        logger.exception("At-risk model could not be unpickled; treating as absent.")
        return None
    model = payload.get("model")
    if model is None:
        return None
    return model, payload.get("metadata") or {}
