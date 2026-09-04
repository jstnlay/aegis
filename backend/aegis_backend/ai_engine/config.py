"""
AEGIS AI Engine — configuration.

All configurable policy points for the AI engine. These are NOT
hard-coded school policies. They provide safe defaults that can be
updated when the client finalizes official policies (D14).
"""

from django.conf import settings


# ---------------------------------------------------------------------------
# Grade / academic policy (D14 — OPEN, configurable)
# ---------------------------------------------------------------------------

# Default passing grade. Override via AEGIS_PASSING_GRADE setting.
PASSING_GRADE = getattr(settings, "AEGIS_PASSING_GRADE", 75)

# Default weak-subject threshold. Override via AEGIS_WEAK_SUBJECT_THRESHOLD.
WEAK_SUBJECT_THRESHOLD = getattr(settings, "AEGIS_WEAK_SUBJECT_THRESHOLD", 70)

# Grade averaging: "mean" | "weighted". Default "mean".
GRADE_AVERAGING_METHOD = getattr(settings, "AEGIS_GRADE_AVERAGING_METHOD", "mean")

# ---------------------------------------------------------------------------
# Risk computation (D7 — baseline Decision Tree config)
# ---------------------------------------------------------------------------

DT_CRITERION = "gini"
DT_SPLITTER = "best"
DT_MAX_DEPTH = 4
DT_MIN_SAMPLES_SPLIT = 10
DT_MIN_SAMPLES_LEAF = 5
DT_RANDOM_STATE = 42

# ---------------------------------------------------------------------------
# Risk Index anchors (D6/D12)
# ---------------------------------------------------------------------------

RISK_INDEX_ANCHORS = {
    "low": 0,
    "moderate": 50,
    "high": 100,
}

# ---------------------------------------------------------------------------
# CF thresholds (D19 — baselines, to be validated against actual data)
# ---------------------------------------------------------------------------

CF_MIN_INTERACTIONS_PER_STUDENT = 5
CF_MIN_DISTINCT_ITEMS_PER_STUDENT = 3
CF_MIN_STUDENTS_PER_ITEM = 3

# ---------------------------------------------------------------------------
# Feature columns (D13)
# ---------------------------------------------------------------------------

ACADEMIC_FEATURES = [
    "current_term_grade_average",
    "grade_trend",
    "weak_subject_count",
    "lowest_subject_grade",
]

ATTENDANCE_FEATURES = [
    "attendance_rate",
    "late_rate",
]

SUPPORT_FEATURES = [
    "consultation_count",
    "behavioral_count",
]

FEATURE_COLUMNS = ACADEMIC_FEATURES + ATTENDANCE_FEATURES + SUPPORT_FEATURES

# Features that are NEVER used for ML
EXCLUDED_FEATURES = [
    "counseling_session_notes",
    "counselor_recommendations_text",
    "intervention_narratives",
    "progress_note_text",
    "raw_behavioral_narrative",
]
