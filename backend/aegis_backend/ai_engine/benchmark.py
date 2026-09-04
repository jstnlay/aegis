"""
AEGIS AI Engine — D29 model benchmark harness.

D29: On a future external dataset (if/when provided), the school and
AEGIS will benchmark candidate models for the Decision Tree classifier.

This harness compares the baseline DecisionTreeClassifier (D7) against
candidate models (RandomForest, LogisticRegression) using grouped
(GroupKFold) validation so that different terms of the same student are
NOT split across train/test (PH9 D18 student-level grouping).

Usage:
    from ai_engine.benchmark import benchmark_models
    results = benchmark_models(X, y, groups)

Results: dict of model_name → {accuracy, macro_f1, per-class f1}.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold
from sklearn.tree import DecisionTreeClassifier

from ai_engine.config import (
    DT_CRITERION,
    DT_MAX_DEPTH,
    DT_MIN_SAMPLES_LEAF,
    DT_MIN_SAMPLES_SPLIT,
    DT_RANDOM_STATE,
)

logger = logging.getLogger(__name__)


def get_candidate_models() -> dict[str, Any]:
    """Define the candidate models to benchmark (D29)."""
    return {
        "decision_tree_baseline": DecisionTreeClassifier(
            criterion=DT_CRITERION,
            splitter="best",
            max_depth=DT_MAX_DEPTH,
            min_samples_split=DT_MIN_SAMPLES_SPLIT,
            min_samples_leaf=DT_MIN_SAMPLES_LEAF,
            random_state=DT_RANDOM_STATE,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=100,
            max_depth=DT_MAX_DEPTH,
            min_samples_leaf=DT_MIN_SAMPLES_LEAF,
            random_state=DT_RANDOM_STATE,
            n_jobs=-1,
        ),
        "logistic_regression": LogisticRegression(
            max_iter=1000,
            random_state=DT_RANDOM_STATE,
        ),
    }


def grouped_cross_validate(
    model,
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    n_splits: int = 5,
) -> dict[str, Any]:
    """
    GroupKFold validation (respects student grouping).

    IMPORTANT (PH9 D18): Terms from the same student stay in the same
    fold, preventing within-student leakage.
    """
    labels = sorted(set(y))
    gkf = GroupKFold(n_splits=min(n_splits, len(set(groups))))

    all_y = []
    all_pred = []

    for train_idx, test_idx in gkf.split(X, y, groups):
        Xtr, Xte = X[train_idx], X[test_idx]
        ytr, yte = y[train_idx], y[test_idx]

        model_clone = (
            type(model)(**model.get_params())
            if hasattr(model, "get_params")
            else model
        )
        if hasattr(model_clone, "n_jobs"):
            try:
                model_clone.set_params(n_jobs=1)
            except Exception:
                pass

        model_clone.fit(Xtr, ytr)
        pred = model_clone.predict(Xte)

        all_y.extend(yte)
        all_pred.extend(pred)

    y_true = np.array(all_y)
    y_pred = np.array(all_pred)

    accuracy = float(np.mean(y_true == y_pred))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro",
                              labels=labels, zero_division=0))
    per_class = f1_score(y_true, y_pred, average=None,
                         labels=labels, zero_division=0)

    return {
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "per_class_f1": {
            str(label): round(float(f), 4)
            for label, f in zip(labels, per_class)
        },
        "n_samples": int(len(y_true)),
    }


def benchmark_models(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
) -> dict[str, Any]:
    """
    Run the D29 benchmark across candidate models.

    Args:
        X: feature matrix (n_samples × n_features)
        y: label vector (strings)
        groups: student grouping vector (one per sample)

    Returns:
        dict mapping model_name → grouped_cross_validate result.
    """
    results = {}
    for name, model in get_candidate_models().items():
        try:
            results[name] = grouped_cross_validate(model, X, y, groups)
            logger.info("Benchmarked %s: %s", name, results[name])
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Benchmark %s failed: %s", name, exc)
            results[name] = {"error": str(exc)}
    return results


def select_best_model(results: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """
    Select the best-performing model by macro-F1 (tie-break: accuracy).

    Ranking is over benchmark results; preference is reported but the
    decision to switch models is a conscious, documented choice.
    """
    scored = []
    for name, res in results.items():
        if "error" in res:
            continue
        scored.append((name, res.get("macro_f1", 0.0), res.get("accuracy", 0.0)))

    if not scored:
        return "none", {}

    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
    best_name, best_f1, best_acc = scored[0]

    # Do NOT switch automatically — D29 requires documented decision
    baseline_f1 = next(
        (f1 for n, f1, _ in scored if n == "decision_tree_baseline"), None
    )
    recommendation = "keep_baseline"
    if best_name != "decision_tree_baseline" and (
        baseline_f1 is None or best_f1 > baseline_f1 + 0.02
    ):
        recommendation = "evaluate_switch"

    return best_name, {
        "best_model": best_name,
        "best_macro_f1": best_f1,
        "best_accuracy": best_acc,
        "recommendation": recommendation,
        "note": (
            "D29: switching models requires documented decision and "
            "validation on the external dataset; not automatic."
        ),
    }
