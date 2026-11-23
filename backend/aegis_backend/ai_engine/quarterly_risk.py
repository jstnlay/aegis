"""
Quarterly student support computation (pilot, scoring version ``quarterly_v1``).

This follows AEGIS_Developer_Implementation_Guide.md: one record per student,
school year and quarter, built from the completed quarter's records:

    general_average, weak_subjects, grade_trend, absences, consultations,
    adviser_concerns, lowest_subject_grade, late_rate

The first six produce the rule score and label.  The last two are model inputs
only and never change the point total.  The rule label is the training target
for the quarterly Decision Tree; the model category and Risk Index are stored
separately and never overwritten by the rule result.

Data model limits that the guide assumes but this schema does not carry:

* There is no imported per-student "official average" column.  The official
  record here is the adviser's finalized subject grades, so the general average
  is the mean of those grades for the quarter.
* Violations are not modelled.  One completed initial consultation per day and
  concern set stands in for "one per distinct violation".
* Adviser notes have no event id.  Repeated warning/incident notes on the same
  date and type are merged as one concern.

Those limits are recorded in ``DATA_LIMITS`` and in each result's explanation so
a reviewer can see them next to the numbers.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from math import ceil

import numpy as np
from sklearn.model_selection import GroupShuffleSplit
from sklearn.tree import DecisionTreeClassifier

from ai_engine.config import (
    DT_CRITERION,
    DT_MAX_DEPTH,
    DT_MIN_SAMPLES_LEAF,
    DT_MIN_SAMPLES_SPLIT,
    DT_RANDOM_STATE,
    DT_SPLITTER,
    RISK_INDEX_ANCHORS,
)

SCORING_VERSION = "quarterly_v1"
RULE_MODEL_VERSION = "quarterly_rule_v1"
MODEL_VERSION = "quarterly_v1"
MIN_SAMPLES = DT_MIN_SAMPLES_SPLIT
LABELS = ("low", "moderate", "high")

#: Guide values, kept in one versioned pilot configuration.
PILOT_SCORING = {
    "version": SCORING_VERSION,
    "general_average": {
        "critical_below": 62,
        "passing_below": 75,
        "critical_points": 2,
        "below_passing_points": 1,
    },
    "weak_subjects": {
        # 0 -> 0; 1-2 -> 1; exactly 3 -> 2; 4+ -> 3
        "one_to_two_points": 1,
        "three_points": 2,
        "four_or_more_points": 3,
    },
    "grade_trend": {"decline_below": -5, "points": 1},
    "absences": {"cutoff_divisor": 10, "points": 1},
    "consultations": {"threshold": 3, "points": 1},
    "adviser_concerns": {"threshold": 2, "points": 1},
    "labels": {"moderate_min": 1, "high_min": 5},
}

#: Fixed model input order from the guide's input table.
FEATURE_COLUMNS = (
    "general_average",
    "weak_subjects",
    "grade_trend",
    "absences",
    "consultations",
    "adviser_concerns",
    "lowest_subject_grade",
    "late_rate",
)
#: The six rule-score inputs, used by the six-input pilot tree.
RULE_FEATURE_COLUMNS = FEATURE_COLUMNS[:6]
Q1_FEATURE_COLUMNS = tuple(
    column for column in FEATURE_COLUMNS if column != "grade_trend"
)

DATA_LIMITS = {
    "general_average": (
        "Mean of the adviser-imported finalized subject grades for the quarter; "
        "the schema has no separate official-average column."
    ),
    "consultations": (
        "Violations are not modelled. One completed non-follow-up session per "
        "day and concern set is counted."
    ),
    "adviser_concerns": (
        "Repeated warning/incident notes on the same date and type are merged "
        "as one concern."
    ),
    "required_school_days": (
        "Distinct days the student's enrolled section has an attendance record "
        "in the quarter."
    ),
    "source_revision": (
        "Digest of the measured values used for this computation. The schema "
        "has no import/release revision identifier, so a correction is visible "
        "only through changed inputs."
    ),
}


def _source_revision(inputs: dict) -> str:
    """Stable digest of the measured values, standing in for a release id."""
    payload = {
        key: inputs.get(key)
        for key in (
            "student_id",
            "period_id",
            "quarter",
            "general_average",
            "weak_subjects",
            "grade_trend",
            "absences",
            "required_days",
            "consultations",
            "adviser_concerns",
            "lowest_subject_grade",
            "late_rate",
        )
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return digest[:16]


def features_for_quarter(quarter: int) -> tuple[str, ...]:
    return Q1_FEATURE_COLUMNS if quarter == 1 else FEATURE_COLUMNS


def resolve_quarter(academic_year, *, quarter_id=None, order=None):
    """Pick the quarter to process: explicit id/order, else latest completed."""
    from datetime import date

    from apps.academics.models import GradingPeriod

    periods = GradingPeriod.objects.filter(academic_year=academic_year)
    if quarter_id:
        return periods.get(id=quarter_id)
    if order:
        return periods.filter(order=order).order_by("end_date").last()
    return periods.filter(end_date__lte=date.today()).order_by(
        "end_date", "order"
    ).last()


def model_version_for_quarter(quarter: int) -> str:
    return f"{MODEL_VERSION}_q{quarter}"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def compute_quarter_inputs(student_profile, period) -> dict:
    """Compute the guide's measured inputs for one student and one quarter."""
    from apps.academics.models import Enrollment, Grade, GradingPeriod
    from apps.attendance.models import AttendanceRecord
    from apps.guidance.models import BehavioralNote, ConsultationRecord

    if period is None:
        raise ValueError("A completed grading period is required.")

    inputs = {
        "student_id": str(student_profile.id),
        "quarter": period.order,
        "quarter_name": period.name,
        "period_id": str(period.id),
        "scoring_version": SCORING_VERSION,
        "general_average": None,
        "weak_subjects": 0,
        "grade_trend": None,
        "absences": 0,
        "required_days": 0,
        "consultations": 0,
        "adviser_concerns": 0,
        "lowest_subject_grade": None,
        "late_rate": None,
        "computation_status": "insufficient_data",
        "missing": [],
        "model_inputs_missing": [],
        "data_limits": DATA_LIMITS,
    }

    quarter = period.order
    grades = Grade.objects.filter(
        student=student_profile,
        grading_period=period,
        status="finalized",
        score__isnull=False,
    )
    scores = list(grades.values_list("score", flat=True))
    if not scores:
        inputs["missing"].append("general_average")
        inputs["source_revision"] = _source_revision(inputs)
        return inputs

    inputs["general_average"] = float(sum(scores, Decimal("0")) / len(scores))
    inputs["weak_subjects"] = (
        grades.filter(score__lt=Decimal("80"))
        .values("subject_assignment__subject_id")
        .distinct()
        .count()
    )
    inputs["lowest_subject_grade"] = float(min(scores))

    # Previous quarter's official average: same school year, previous order.
    if quarter > 1:
        previous = (
            GradingPeriod.objects.filter(
                academic_year=period.academic_year, order=quarter - 1
            )
            .order_by("start_date")
            .first()
        )
        previous_scores = (
            Grade.objects.filter(
                student=student_profile,
                grading_period=previous,
                status="finalized",
                score__isnull=False,
            ).values_list("score", flat=True)
            if previous is not None
            else []
        )
        previous_scores = list(previous_scores)
        if previous_scores:
            previous_average = float(
                sum(previous_scores, Decimal("0")) / len(previous_scores)
            )
            inputs["grade_trend"] = round(
                inputs["general_average"] - previous_average, 2
            )
        else:
            inputs["missing"].append("grade_trend")

    # Attendance: required days come from the section's records, absences from
    # the student's explicit absent days. A blank cell is neither.
    section_ids = list(
        Enrollment.objects.filter(
            student=student_profile,
            academic_year=period.academic_year,
            is_active=True,
        ).values_list("section_id", flat=True)
    )
    if not section_ids and student_profile.section_id:
        section_ids = [student_profile.section_id]

    required_days = (
        AttendanceRecord.objects.filter(
            section_id__in=section_ids,
            date__gte=period.start_date,
            date__lte=period.end_date,
        )
        .values("date")
        .distinct()
        .count()
    )
    attendance = AttendanceRecord.objects.filter(
        student=student_profile,
        date__gte=period.start_date,
        date__lte=period.end_date,
    )
    inputs["required_days"] = required_days
    inputs["absences"] = (
        attendance.filter(status="absent").values("date").distinct().count()
    )

    present_dates = set()
    late_dates = set()
    for day, status in attendance.values_list("date", "status"):
        if status in ("present", "late"):
            present_dates.add(day)
        if status == "late":
            late_dates.add(day)
    if present_dates:
        inputs["late_rate"] = 100.0 * len(late_dates) / len(present_dates)

    # Consultations: completed, non-follow-up, in the quarter. One per day +
    # concern set stands in for one per distinct violation.
    consultation_keys = set()
    for record in ConsultationRecord.objects.filter(
        student=student_profile,
        session_date__gte=period.start_date,
        session_date__lte=period.end_date,
        status="completed",
    ).exclude(session_type="follow_up"):
        concern_key = tuple(sorted(record.concern_categories or []))
        consultation_keys.add((record.session_date, concern_key))
    inputs["consultations"] = len(consultation_keys)

    # Adviser concerns: warning/incident only, repeated notes on one date and
    # type merged.
    concern_keys = set()
    for note in BehavioralNote.objects.filter(
        student=student_profile,
        date_recorded__gte=period.start_date,
        date_recorded__lte=period.end_date,
        note_type__in=("warning", "incident"),
    ):
        concern_keys.add((note.date_recorded, note.note_type))
    inputs["adviser_concerns"] = len(concern_keys)

    if required_days <= 0:
        inputs["missing"].append("required_school_days")

    inputs["model_inputs_missing"] = [
        column
        for column in features_for_quarter(quarter)
        if inputs.get(column) is None
    ]
    if not inputs["missing"]:
        inputs["computation_status"] = "ready"
    inputs["source_revision"] = _source_revision(inputs)
    return inputs


# ---------------------------------------------------------------------------
# Rule score
# ---------------------------------------------------------------------------


def absence_cutoff(required_days: int) -> int:
    """ceil(D / 10); D must be a positive verified count."""
    return ceil(required_days / PILOT_SCORING["absences"]["cutoff_divisor"])


def score_rule(inputs: dict) -> dict | None:
    """Apply the six point components and return score plus label."""
    if inputs.get("computation_status") != "ready":
        return None

    config = PILOT_SCORING
    average = inputs["general_average"]
    weak = inputs["weak_subjects"]
    absences = inputs["absences"]
    consultations = inputs["consultations"]
    concerns = inputs["adviser_concerns"]
    quarter = inputs.get("quarter", 1)
    trend = inputs.get("grade_trend")

    grade_points = 0
    if average < config["general_average"]["critical_below"]:
        grade_points = config["general_average"]["critical_points"]
    elif average < config["general_average"]["passing_below"]:
        grade_points = config["general_average"]["below_passing_points"]

    if weak >= 4:
        weak_points = config["weak_subjects"]["four_or_more_points"]
    elif weak == 3:
        weak_points = config["weak_subjects"]["three_points"]
    elif weak >= 1:
        weak_points = config["weak_subjects"]["one_to_two_points"]
    else:
        weak_points = 0

    if quarter == 1:
        trend_points = None
        trend_value = None
    else:
        trend_value = trend
        trend_points = (
            config["grade_trend"]["points"]
            if trend is not None
            and trend < config["grade_trend"]["decline_below"]
            else 0
        )

    cutoff = absence_cutoff(inputs["required_days"])
    absence_points = (
        config["absences"]["points"] if absences >= cutoff else 0
    )
    consultation_points = (
        config["consultations"]["points"]
        if consultations >= config["consultations"]["threshold"]
        else 0
    )
    concern_points = (
        config["adviser_concerns"]["points"]
        if concerns >= config["adviser_concerns"]["threshold"]
        else 0
    )

    components = {
        "G": grade_points,
        "W": weak_points,
        "A": absence_points,
        "C": consultation_points,
        "B": concern_points,
    }
    if trend_points is not None:
        components["T"] = trend_points

    score = sum(components.values())
    if score == 0:
        label = "low"
    elif score >= config["labels"]["high_min"]:
        label = "high"
    else:
        label = "moderate"

    factors = [
        {
            "feature": "general_average",
            "component": "G",
            "value": average,
            "threshold": config["general_average"]["passing_below"],
            "direction": "below"
            if average < config["general_average"]["passing_below"]
            else "above",
            "points": grade_points,
            "scoring_version": SCORING_VERSION,
        },
        {
            "feature": "weak_subjects",
            "component": "W",
            "value": weak,
            "points": weak_points,
            "scoring_version": SCORING_VERSION,
        },
        {
            "feature": "absences",
            "component": "A",
            "value": absences,
            "threshold": cutoff,
            "direction": "at_or_above" if absences >= cutoff else "below",
            "points": absence_points,
            "scoring_version": SCORING_VERSION,
        },
        {
            "feature": "consultations",
            "component": "C",
            "value": consultations,
            "threshold": config["consultations"]["threshold"],
            "points": consultation_points,
            "scoring_version": SCORING_VERSION,
        },
        {
            "feature": "adviser_concerns",
            "component": "B",
            "value": concerns,
            "threshold": config["adviser_concerns"]["threshold"],
            "points": concern_points,
            "scoring_version": SCORING_VERSION,
        },
    ]
    if trend_points is not None:
        factors.insert(
            2,
            {
                "feature": "grade_trend",
                "component": "T",
                "value": trend_value,
                "threshold": config["grade_trend"]["decline_below"],
                "direction": "below"
                if trend_value is not None
                and trend_value < config["grade_trend"]["decline_below"]
                else "above",
                "points": trend_points,
                "scoring_version": SCORING_VERSION,
            },
        )

    return {
        "scoring_version": SCORING_VERSION,
        "points": components,
        "score": score,
        "max_score": 8 if quarter == 1 else 9,
        "label": label,
        "factors": factors,
        "absence_cutoff": cutoff,
    }


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def build_model() -> DecisionTreeClassifier:
    return DecisionTreeClassifier(
        criterion=DT_CRITERION,
        splitter=DT_SPLITTER,
        max_depth=DT_MAX_DEPTH,
        min_samples_split=DT_MIN_SAMPLES_SPLIT,
        min_samples_leaf=DT_MIN_SAMPLES_LEAF,
        random_state=DT_RANDOM_STATE,
    )


def _row(row: dict, columns: tuple[str, ...]) -> list[float]:
    return [float(row[column]) for column in columns]


def train(
    rows: list[dict],
    *,
    quarter: int,
    model_version: str | None = None,
) -> tuple[DecisionTreeClassifier | None, dict]:
    """Fit the quarterly tree on rule labels. Missing columns are refused."""
    columns = features_for_quarter(quarter)
    valid = [
        row
        for row in rows
        if row.get("label") in LABELS
        and all(row.get(column) is not None for column in columns)
    ]
    if len(valid) < MIN_SAMPLES:
        return None, {"error": "insufficient_training_data", "n_samples": len(valid)}

    labels = [row["label"] for row in valid]
    if len(set(labels)) < 2:
        return None, {"error": "single_class_training_data", "n_samples": len(valid)}

    X = np.array([_row(row, columns) for row in valid], dtype=np.float64)
    y = np.array(labels)
    groups = np.array([row.get("student_id") or index for index, row in enumerate(valid)])
    model = build_model()
    model.fit(X, y)

    comparison = _compare_pilot_trees(valid, quarter)
    version = model_version or model_version_for_quarter(quarter)

    metadata = {
        "model_version": version,
        "scoring_version": SCORING_VERSION,
        "feature_columns": list(columns),
        "eligible_inputs": list(FEATURE_COLUMNS),
        "classes": list(model.classes_),
        "applicable_quarter": quarter,
        "n_samples": len(valid),
        "n_features": len(columns),
        "feature_importances_": {
            column: round(float(value), 4)
            for column, value in zip(columns, model.feature_importances_)
        },
        "student_groups": len(set(groups.tolist())),
        "comparison": comparison,
        "label_source": "rule_based",
        "label_caveat": (
            "Labels come from the quarterly rule score in "
            "ai_engine.quarterly_risk.score_rule, not from counselor-confirmed "
            "outcomes. Accuracy against these labels is circular and must be "
            "read with independent staff ratings."
        ),
    }
    return model, metadata


def _compare_pilot_trees(rows: list[dict], quarter: int) -> dict:
    """Compare the rule-input tree and the full tree on a grouped holdout."""
    six_columns = tuple(
        column
        for column in RULE_FEATURE_COLUMNS
        if not (quarter == 1 and column == "grade_trend")
    )
    full_columns = features_for_quarter(quarter)
    six = _holdout_accuracy(rows, six_columns)
    full = _holdout_accuracy(rows, full_columns)
    return {
        "method": "GroupShuffleSplit by student, 30% holdout, random_state=42",
        "direct_scoring_rule_agreement": 1.0,
        "direct_scoring_note": (
            "By construction: the rule label is the training target, so direct "
            "scoring agrees with itself. Independent staff ratings are the "
            "meaningful comparison and are not available."
        ),
        "six_input_accuracy": six,
        "eight_input_accuracy": full,
        "independent_staff_ratings": "not available",
    }


def _holdout_accuracy(rows: list[dict], columns: tuple[str, ...]):
    usable = [
        row
        for row in rows
        if all(row.get(column) is not None for column in columns)
    ]
    if len(usable) < 10 or len({row.get("student_id") for row in usable}) < 5:
        return None
    X = np.array([_row(row, columns) for row in usable], dtype=np.float64)
    y = np.array([row["label"] for row in usable])
    groups = np.array([row.get("student_id") for row in usable])
    try:
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
        train_index, test_index = next(splitter.split(X, y, groups))
        model = build_model()
        model.fit(X[train_index], y[train_index])
        return round(float(model.score(X[test_index], y[test_index])), 4)
    except ValueError:
        return None


def load_model_for_quarter(quarter: int):
    """Load the active tree for this quarter, or None when unavailable."""
    from ai_engine.risk_scorer import load_stored_model

    stored = load_stored_model(model_version_for_quarter(quarter))
    if stored is None:
        return None
    model, metadata = stored
    if metadata.get("applicable_quarter") != quarter:
        return None
    if list(metadata.get("feature_columns") or []) != list(
        features_for_quarter(quarter)
    ):
        return None
    return model, metadata


def predict(model, metadata: dict, inputs: dict) -> dict:
    """Class estimates by stored class order, category, index and factors."""
    columns = tuple(metadata.get("feature_columns") or FEATURE_COLUMNS)
    missing = [column for column in columns if inputs.get(column) is None]
    if missing:
        return {
            "model_status": "unavailable",
            "reason": "missing_required_model_input",
            "missing_inputs": missing,
            "model_version": metadata.get("model_version"),
        }

    row = _row(inputs, columns)
    X = np.array([row], dtype=np.float64)
    probabilities = model.predict_proba(X)[0]
    classes = list(model.classes_)
    estimates = {
        str(label): float(probability)
        for label, probability in zip(classes, probabilities)
    }

    category, tie = category_from_estimates(estimates)
    index = risk_index_from_estimates(estimates)

    return {
        "model_status": "ready",
        "model_version": metadata.get("model_version"),
        "feature_columns": list(columns),
        "class_estimates": estimates,
        "category": category,
        "index": index,
        "needs_staff_review": category is None,
        "tie": tie,
        "contributing_factors": _decision_path(model, row, inputs, columns),
    }


def category_from_estimates(estimates: dict) -> tuple[str | None, list[str]]:
    """Highest estimate; a tie returns no category and the tied labels."""
    top = max(estimates.values())
    top_labels = [label for label, value in estimates.items() if value == top]
    if len(top_labels) == 1:
        return top_labels[0], []
    return None, top_labels


def risk_index_from_estimates(estimates: dict) -> float:
    """0*P(low) + 50*P(moderate) + 100*P(high), unrounded."""
    return sum(
        estimates.get(label, 0.0) * anchor
        for label, anchor in RISK_INDEX_ANCHORS.items()
    )


def _decision_path(model, row, inputs: dict, columns: tuple[str, ...]) -> list[dict]:
    tree = model.tree_
    indicator = model.decision_path(np.array([row]))
    nodes = indicator.indices[indicator.indptr[0] : indicator.indptr[1]]
    factors = []
    for node_id in nodes:
        if tree.children_left[node_id] == tree.children_right[node_id]:
            continue
        feature_index = int(tree.feature[node_id])
        column = columns[feature_index]
        factors.append(
            {
                "feature": column,
                "value": inputs.get(column),
                "threshold": round(float(tree.threshold[node_id]), 4),
                "direction": (
                    "below" if row[feature_index] <= tree.threshold[node_id] else "above"
                ),
                "model": model_version_for_quarter(inputs.get("quarter", 1)),
            }
        )
    return factors


def build_prediction(inputs: dict, rule: dict, model_result: dict) -> dict:
    """Combine rule and model output for RiskScore/RiskAlert integration."""
    model_ready = model_result.get("model_status") == "ready"
    category = model_result.get("category") if model_ready else None
    needs_review = bool(model_result.get("needs_staff_review")) if model_ready else False
    category_source = "model" if category else "rule"
    risk_level = category or rule["label"]
    risk_score = model_result.get("index") if model_ready else None
    model_version = (
        model_result.get("model_version")
        if model_ready
        else RULE_MODEL_VERSION
    )
    factors = (
        model_result.get("contributing_factors")
        if model_ready
        else rule.get("factors", [])
    )

    explanation = {
        "scoring_version": SCORING_VERSION,
        "quarter": inputs.get("quarter"),
        "calculation_status": "ready",
        "category_source": category_source,
        "model_category_available": model_ready and category is not None,
        "needs_staff_review": needs_review,
        "rule": rule,
        "model": model_result,
        "contributing_factors": factors,
        "data_limits": DATA_LIMITS,
    }
    return {
        "computation_status": "ready",
        "risk_level": risk_level,
        "risk_score": risk_score,
        "risk_index": risk_score,
        "model_version": model_version,
        "category_source": category_source,
        "needs_staff_review": needs_review,
        "model_status": model_result.get("model_status", "unavailable"),
        "source_revision": inputs.get("source_revision"),
        "explanation": explanation,
    }


def held_result(inputs: dict, reason: str) -> dict:
    """A record that cannot be scored yet; still saved as computation history."""
    return {
        "computation_status": "insufficient_data",
        "risk_level": None,
        "risk_score": None,
        "risk_index": None,
        "model_version": SCORING_VERSION,
        "category_source": None,
        "explanation": {
            "scoring_version": SCORING_VERSION,
            "quarter": inputs.get("quarter"),
            "calculation_status": "pending_verification",
            "reason": reason,
            "missing": inputs.get("missing", []),
            "source_revision": inputs.get("source_revision"),
            "data_limits": DATA_LIMITS,
        },
    }
