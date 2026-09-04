"""
AEGIS AI Engine — feature engineering (D13).

Primary features:
  ACADEMIC:  current_term_grade_average, grade_trend,
             weak_subject_count, lowest_subject_grade
  ATTENDANCE: attendance_rate, late_rate
  SUPPORTING AGGREGATES: consultation_count, behavioral_count_by_type

NEVER use as ML features:
  counseling/session notes, counselor recommendation text, intervention
  narratives, progress-note text, raw behavioral narrative, future/
  incomplete-term data.

Missing grade != zero grade.
Zero consultation count may be valid.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from ai_engine.config import (
    FEATURE_COLUMNS,
    WEAK_SUBJECT_THRESHOLD,
)

logger = logging.getLogger(__name__)


def _safe_decimal_avg(values) -> float | None:
    """Compute average of a set of Decimal values, returning None if empty."""
    total = Decimal("0")
    count = 0
    for v in values:
        if v is not None:
            total += Decimal(str(v))
            count += 1
    if count == 0:
        return None
    return float(total / count)


def compute_student_features(
    student_profile,
    completed_grading_periods,
    academic_year,
) -> dict:
    """
    Compute D13 features for a single student.

    Args:
        student_profile: StudentProfile instance
        completed_grading_periods: QuerySet or list of completed
            GradingPeriod objects
        academic_year: AcademicYear instance (for term gating)

    Returns:
        dict of features with keys from FEATURE_COLUMNS plus
        computation_status and student_id.
    """
    from apps.guidance.models import BehavioralNote, ConsultationRecord

    features = {
        "student_id": str(student_profile.id),
        "computation_status": "ready",
        "current_term_grade_average": None,
        "grade_trend": None,
        "weak_subject_count": 0,
        "lowest_subject_grade": None,
        "attendance_rate": None,
        "late_rate": None,
        "consultation_count": 0,
        "behavioral_count": 0,
    }

    # --- Term gating (D3): use only completed periods ---
    from apps.academics.models import Grade

    period_ids = [gp.id for gp in completed_grading_periods]
    grades = Grade.objects.filter(
        student=student_profile,
        grading_period_id__in=period_ids,
        status="finalized",
        score__isnull=False,
    ).select_related("grading_period")

    if not grades.exists():
        features["computation_status"] = "insufficient_data"
        return features

    # --- Academic features ---
    # Normalize: accept both QuerySets and lists of GradingPeriod
    if hasattr(completed_grading_periods, "order_by"):
        period_list = list(completed_grading_periods.order_by("order"))
    else:
        period_list = sorted(completed_grading_periods, key=lambda gp: gp.order)
    latest_period = period_list[-1] if period_list else None
    if latest_period is None:
        features["computation_status"] = "insufficient_data"
        return features

    current_period_grades = grades.filter(grading_period=latest_period)
    current_avg = _safe_decimal_avg(
        current_period_grades.values_list("score", flat=True)
    )
    features["current_term_grade_average"] = current_avg

    # Lowest subject grade in current term
    if current_period_grades.exists():
        lowest = current_period_grades.order_by("score").first()
        features["lowest_subject_grade"] = (
            float(lowest.score) if lowest and lowest.score is not None else None
        )

    # Weak subject count (D14 configurable threshold)
    weak_count = current_period_grades.filter(
        score__lt=Decimal(str(WEAK_SUBJECT_THRESHOLD))
    ).count()
    features["weak_subject_count"] = weak_count

    # Grade trend: compare current period average vs previous period average
    if len(period_list) >= 2:
        prev_period = period_list[-2]
        prev_grades = grades.filter(grading_period=prev_period)
        prev_avg = _safe_decimal_avg(prev_grades.values_list("score", flat=True))
        if prev_avg is not None and current_avg is not None:
            features["grade_trend"] = round(current_avg - prev_avg, 2)

    # --- Attendance features (from AttendanceRecord) ---
    from apps.attendance.models import AttendanceRecord

    attendance = AttendanceRecord.objects.filter(
        student=student_profile,
        date__gte=academic_year.start_date,
        date__lte=academic_year.end_date,
    )
    total_att = attendance.count()
    if total_att > 0:
        present = attendance.filter(status="present").count()
        late = attendance.filter(status="late").count()
        features["attendance_rate"] = round(
            (present + late) / total_att, 4
        )
        features["late_rate"] = round(late / total_att, 4)

    # --- Guidance aggregates (counts ONLY, never free text) ---
    consultation_count = ConsultationRecord.objects.filter(
        student=student_profile,
    ).count()
    features["consultation_count"] = consultation_count

    behavioral_count = BehavioralNote.objects.filter(
        student=student_profile,
    ).count()
    features["behavioral_count"] = behavioral_count

    return features


def compute_features_batch(
    student_profiles,
    completed_grading_periods,
    academic_year,
) -> list[dict]:
    """Compute features for multiple students."""
    return [
        compute_student_features(sp, completed_grading_periods, academic_year)
        for sp in student_profiles
    ]
