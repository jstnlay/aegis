"""
Trained intent classifier for the AEGIS assistant.

Where this sits in the request path
-----------------------------------
`policies.classify_intent` runs FIRST and unchanged. This classifier is only
consulted when the regex layer returns UNKNOWN — the stratum regex structurally
cannot reach. Measured on the labeled probe set:

    clean English   regex 90%  -> classifier not consulted
    Taglish         regex 100% -> classifier not consulted
    typos/clipping  regex 20%  -> 80% of rows land on UNKNOWN, so this runs

So the classifier adds capability only where the system currently answers "I
didn't fully understand". It cannot regress the behaviour that already works,
which is the reason it is a fallback rather than a replacement.

What it deliberately does NOT do
--------------------------------
It does not classify urgency, and it never gates escalation. `detect_urgent` and
`detect_urgency` are regex-only and run before this module is reached, because a
model deciding whether a counselor gets paged about a student's words is exactly
the failure mode that should not exist. The URGENT_CONCERN rows in the dataset
exist to keep the label set balanced for evaluation; they are not an inference
path.

Why word + character n-grams
----------------------------
A word-level TF-IDF treats "absnces" and "absences" as unrelated tokens, which
is precisely the stratum this classifier exists for — bag of words discards
exactly the character overlap that carries the signal. `char_wb` n-grams over
3–5 characters capture it: "absnces" shares 3-5 grams with "absences".

    analyzer="word"    -> handles the phrasing ("how many absences")
    analyzer="char_wb" -> handles the misspelling ("how many absnces")

The union keeps both. Word features alone would still miss the typos;
char_wb alone would lose the phrase structure that separates
"my attendance record" from "my grade record".

Why there is no model file
--------------------------
The model is a pure function of `data/intent_dataset.jsonl`, fitted at import.
A 300-row TF-IDF + LogisticRegression fits in well under a second, so there is
no artifact to persist, no artifact to go stale, and no "model file missing"
failure — the class of bug that left `run_risk_computation` unable to execute at
all until it was fixed.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from apps.chatbot.dataset import load_dataset
from apps.chatbot.taxonomy import ChatIntent

logger = logging.getLogger(__name__)

# Deterministic. The intent layer must give the same answer for the same input
# (NFR-007 in spirit) and a seeded solver is what makes that true.
RANDOM_STATE = 42

# Confidence floor, chosen by stratified 5-fold cross-validation on the
# TRAINING set (out-of-fold predictions) — not tuned against the holdout, which
# would contaminate the only honest estimate available.
#
# Measured out-of-fold on 165 samples across 19 intents:
#
#     floor   kept   accuracy_on_kept   overall
#     0.00    165          60.0%          60.0%
#     0.20     63          82.5%          31.5%
#     0.25     47          89.4%          25.5%
#     0.35     13          92.3%           7.3%
#
# 0.25 is the knee: 89.4% precision on the quarter of UNKNOWN rows it rescues,
# with precision falling away above it and coverage collapsing below it.
#
# The top-1 accuracy at zero floor is 60.0% — no better than the regex layer's
# 64.7% on the same holdout. See the status note below before using this.
CONFIDENCE_FLOOR = 0.25

# ---------------------------------------------------------------------------
# STATUS: not wired into `policies.classify_intent`. Measured, not adopted.
# ---------------------------------------------------------------------------
# The pipeline trains correctly and its top-1 predictions are usually the right
# intent ("absense record" -> ask_attendance, "bothered ako" -> express_concern),
# but at 165 samples across 19 classes the model generalises poorly: 60.0%
# out-of-fold against 64.7% for regex alone on the same probes. The character
# branch alone produces 1,110 features from 165 documents, so it is memorising
# rather than generalising.
#
# A confidence floor converts that into precision at the cost of coverage —
# 25.5% of the UNKNOWN stratum at 89.4% precision — which is a real but small
# gain, and only if the floor is honoured.
#
# It is left unwired deliberately. Routing UNKNOWN through a 60%-accurate
# classifier would replace "I didn't fully understand" with a confidently wrong
# answer, which is worse for the student and worse for the escalation path's
# credibility. Revisit only with a materially larger labeled set; the honest
# measurement command is `manage.py evaluate_intent_classifier`.

_lock = threading.Lock()
_model: Pipeline | None = None
_metadata: dict[str, Any] = {}


def build_pipeline() -> Pipeline:
    """
    Construct the un-fitted pipeline.

    Split out from `fit()` so a test can inspect the configured analyzer
    without training anything.
    """
    features = FeatureUnion(
        [
            (
                "word",
                TfidfVectorizer(
                    analyzer="word",
                    ngram_range=(1, 2),
                    lowercase=True,
                    sublinear_tf=True,
                    min_df=1,
                ),
            ),
            (
                "char",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    lowercase=True,
                    sublinear_tf=True,
                    min_df=2,
                ),
            ),
        ]
    )
    return Pipeline(
        [
            ("features", features),
            (
                "clf",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def _fit() -> tuple[Pipeline, dict[str, Any]]:
    dataset = load_dataset()

    texts = [text for text, _ in dataset]
    labels = [intent for _, intent in dataset]

    pipeline = build_pipeline()
    pipeline.fit(texts, labels)

    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1

    return pipeline, {
        "n_samples": len(dataset),
        "n_intents": len(counts),
        "per_intent": counts,
    }


def fit(rows=None) -> tuple[Pipeline, dict[str, Any]]:
    """Fit the pipeline on (text, intent_value) rows. Returns (model, metadata)."""
    if rows is None:
        return _fit()
    texts = [text for text, _ in rows]
    labels = [intent for _, intent in rows]
    pipeline = build_pipeline()
    pipeline.fit(texts, labels)
    return pipeline, {"n_samples": len(rows), "n_intents": len(set(labels))}


def get_model() -> Pipeline | None:
    """
    The fitted pipeline, training it on first use.

    Returns None if the dataset cannot be read or the fit fails. A missing model
    must not take the chatbot down: the regex layer already answers everything it
    can, and UNKNOWN is the correct answer for the rest.
    """
    global _model, _metadata

    if _model is not None:
        return _model

    with _lock:
        if _model is not None:
            return _model
        try:
            pipeline, metadata = fit()
        except Exception:
            logger.exception(
                "Intent classifier unavailable; falling back to regex-only."
            )
            return None
        _model = pipeline
        _metadata = metadata
        logger.info(
            "Intent classifier fitted on %s samples across %s intents",
            metadata["n_samples"],
            metadata["n_intents"],
        )
        return _model


def get_metadata() -> dict[str, Any]:
    """Training metadata. Empty until the model has been fitted."""
    return dict(_metadata)


def predict(text: str) -> tuple[ChatIntent | None, float]:
    """
    Classify `text`.

    Returns (intent, confidence). `intent` is None when the model is
    unavailable or the confidence is below `CONFIDENCE_FLOOR`, which the caller
    must treat as "still unknown" rather than as a weak guess.

    Only the intents a caller may act on are returned. UNKNOWN is excluded from
    the label set: a model trained to recognise nonsense should not be able to
    emit nonsense as a confident answer.
    """
    model = get_model()
    if model is None:
        return None, 0.0

    try:
        probabilities = model.predict_proba([text])[0]
        classes = model.classes_
    except Exception:
        logger.exception("Intent classifier prediction failed.")
        return None, 0.0

    best_index = int(probabilities.argmax())
    confidence = float(probabilities[best_index])
    label = classes[best_index]

    if label == ChatIntent.UNKNOWN.value:
        return None, confidence
    if confidence < CONFIDENCE_FLOOR:
        return None, confidence

    try:
        return ChatIntent(label), confidence
    except ValueError:
        return None, confidence


def evaluate(holdout) -> dict[str, Any]:
    """
    Score the fitted model against a held-out set.

    `holdout` is a list of (text, expected_intent_value). Reported per class so
    a weak intent cannot hide behind overall accuracy.
    """
    model = get_model()
    if model is None:
        return {"available": False}

    correct = 0
    per_class: dict[str, dict[str, int]] = {}

    for text, expected in holdout:
        got, _confidence = predict(text)
        actual = got.value if got is not None else "unknown"
        bucket = per_class.setdefault(expected, {"total": 0, "correct": 0})
        bucket["total"] += 1
        if actual == expected:
            correct += 1
            bucket["correct"] += 1

    total = len(holdout)
    return {
        "available": True,
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "per_class": per_class,
    }