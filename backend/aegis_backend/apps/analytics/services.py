"""
Phase 9 analytics aggregation services.

Provides role-controlled backend aggregation APIs.
Admin gets aggregated/anonymized only.

PH9.12 boundary: Admin sees aggregated/anonymized data only unless
explicit approved access exists.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.db.models import Avg, Count, Q
from django.utils import timezone


def _scope_academic_year(academic_year_id=None):
    """Return academic year filter dict (or empty)."""
    if academic_year_id:
        return {"academic_year_id": academic_year_id}
    return {}


def student_academic_metrics(student_profile) -> dict[str, Any]:
    """
    Aggregated academic metrics for a single student.

    Role-safe: caller must verify access before invoking.
    """
    from apps.academics.models import Grade

    grades = Grade.objects.filter(
        student=student_profile,
        score__isnull=False,
        status="finalized",
    ).select_related("subject_assignment__subject", "grading_period")

    if not grades.exists():
        return {"student_id": str(student_profile.id), "has_data": False}

    avg_score = grades.aggregate(avg=Avg("score"))["avg"]
    total_subjects = grades.values("subject_assignment").distinct().count()
    latest_period = (
        grades.select_related("grading_period")
        .order_by("-grading_period__order")
        .first()
    )

    return {
        "student_id": str(student_profile.id),
        "student_name": student_profile.user.get_full_name(),
        "has_data": True,
        "overall_average": round(float(avg_score), 2) if avg_score is not None else None,
        "total_subjects": total_subjects,
        "latest_period": latest_period.grading_period.name if latest_period else None,
        "latest_period_average": avg_score is not None and round(float(avg_score), 2) or None,
    }


def student_period_trend(student_profile) -> dict[str, Any]:
    """
    Real per-grading-period averages for one student.

    PH11.10. ``student_academic_metrics`` reports a single overall average and a
    ``latest_period_average`` that is computed from that *same* overall average —
    it is not a per-period figure, so it cannot stand in for a trend. This
    aggregates the actual finalized grades per period instead.

    Periods are ordered by ``GradingPeriod.order``, the field the academics app
    already orders by, rather than by name: "Second Term" sorts before "First
    Term" alphabetically.

    A period with no finalized grade is omitted rather than reported with a
    zero average, which would assert a failing score the database does not
    contain. A period whose grades are all recorded without a score *is*
    reported, with ``average: None`` and ``grade_count: 0`` — that is a real gap
    in the student's record and hiding it would be as misleading as zero-filling.
    """
    from apps.academics.models import Grade, GradingPeriod

    rows = list(
        Grade.objects.filter(
            student=student_profile,
            status="finalized",
        )
        .values(
            "grading_period__id",
            "grading_period__name",
            "grading_period__order",
            "score",
        )
        .order_by("grading_period__order")
    )

    return {
        "student_id": str(student_profile.id),
        "has_data": bool(rows),
        "periods": _period_buckets(rows),
    }


def _period_buckets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Collapse per-grade rows into per-period averages, ordered by `order`.

    A period averages only the grades that carry a score; `grade_count` reports
    how many did, so a caller can tell a low-scoring period from an unscored
    one. `average` is None when nothing was scored.
    """
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = buckets.setdefault(
            row["grading_period__id"],
            {
                "period_id": row["grading_period__id"],
                "period": row["grading_period__name"],
                "order": row["grading_period__order"],
                "scores": [],
            },
        )
        if row["score"] is not None:
            bucket["scores"].append(float(row["score"]))

    return [
        {
            "period_id": bucket["period_id"],
            "period": bucket["period"],
            "order": bucket["order"],
            "average": (
                round(sum(bucket["scores"]) / len(bucket["scores"]), 2)
                if bucket["scores"]
                else None
            ),
            "grade_count": len(bucket["scores"]),
        }
        for bucket in sorted(buckets.values(), key=lambda entry: entry["order"])
    ]


def student_attendance_trend(
    student_profile, from_date=None, to_date=None
) -> dict[str, Any]:
    """
    Per-day present / late / absent counts for one student.

    PH11.10. ``student_attendance_summary`` returns whole-period totals, so it
    cannot plot attendance over time; ``/attendance/summary/`` returns per-section
    counts with no date dimension at all. This aggregates the real
    ``AttendanceRecord`` rows by date.

    Days with no record are absent from ``days`` rather than being emitted with
    zeroes. A school day on which nothing was recorded is a gap in the data, not
    a day the student was absent, and filling it would assert an absence that
    was never recorded.

    Days are ordered ascending by date. When no range is supplied the full record
    history is returned; the caller is responsible for bounding it.
    """
    from apps.attendance.models import AttendanceRecord

    records = AttendanceRecord.objects.filter(student=student_profile)
    if from_date is not None:
        records = records.filter(date__gte=from_date)
    if to_date is not None:
        records = records.filter(date__lte=to_date)

    buckets: dict[Any, dict[str, int]] = {}
    for record_date, status in records.values_list("date", "status"):
        bucket = buckets.setdefault(
            record_date, {"present": 0, "late": 0, "absent": 0}
        )
        if status in bucket:
            bucket[status] += 1

    days = [
        {
            "date": day.isoformat(),
            "present": counts["present"],
            "late": counts["late"],
            "absent": counts["absent"],
            "total": counts["present"] + counts["late"] + counts["absent"],
        }
        for day, counts in sorted(buckets.items())
    ]

    return {
        "student_id": str(student_profile.id),
        "has_data": bool(days),
        "days": days,
    }


def school_wide_period_trend(academic_year_id=None) -> dict[str, Any]:
    """
    Per-grading-period averages across every student.

    PH11.10. The school-wide counterpart of ``student_period_trend``, for the
    "school-wide academic performance" visual reports the specification asks for.
    Same treatment of empty periods: reported with ``average: None``, never
    zero-filled.
    """
    from apps.academics.models import Grade

    filters = {"status": "finalized"}
    if academic_year_id:
        filters["subject_assignment__academic_year_id"] = academic_year_id

    rows = list(
        Grade.objects.filter(**filters)
        .values(
            "grading_period__id",
            "grading_period__name",
            "grading_period__order",
            "score",
        )
        .order_by("grading_period__order")
    )

    return {"periods": _period_buckets(rows)}


def school_wide_attendance_trend(from_date=None, to_date=None) -> dict[str, Any]:
    """
    Per-day present / late / absent counts across every student.

    PH11.10. School-wide counterpart of ``student_attendance_trend``. Aggregate
    counts only — no student is identified, which is what NFR-010 requires of an
    administrator-facing view.
    """
    from apps.attendance.models import AttendanceRecord

    records = AttendanceRecord.objects.all()
    if from_date is not None:
        records = records.filter(date__gte=from_date)
    if to_date is not None:
        records = records.filter(date__lte=to_date)

    buckets: dict[Any, dict[str, int]] = {}
    for record_date, status in records.values_list("date", "status"):
        bucket = buckets.setdefault(
            record_date, {"present": 0, "late": 0, "absent": 0}
        )
        if status in bucket:
            bucket[status] += 1

    days = [
        {
            "date": day.isoformat(),
            "present": counts["present"],
            "late": counts["late"],
            "absent": counts["absent"],
            "total": counts["present"] + counts["late"] + counts["absent"],
        }
        for day, counts in sorted(buckets.items())
    ]

    return {"days": days}


def student_attendance_summary(student_profile) -> dict[str, Any]:
    """Attendance summary for a single student."""
    from apps.attendance.models import AttendanceRecord

    records = AttendanceRecord.objects.filter(student=student_profile)
    total = records.count()
    if total == 0:
        return {"student_id": str(student_profile.id), "has_data": False}

    present = records.filter(status="present").count()
    late = records.filter(status="late").count()
    absent = records.filter(status="absent").count()

    return {
        "student_id": str(student_profile.id),
        "has_data": True,
        "total_days": total,
        "present_days": present,
        "late_days": late,
        "absent_days": absent,
        "attendance_rate": round((present + late) / total, 4),
        "late_rate": round(late / total, 4),
        "absence_rate": round(absent / total, 4),
    }


def section_performance(section, academic_year_id=None) -> dict[str, Any]:
    """Aggregated performance metrics for a section."""
    from apps.academics.models import Grade

    filters = {"subject_assignment__section": section}
    if academic_year_id:
        filters["subject_assignment__academic_year_id"] = academic_year_id

    grades = Grade.objects.filter(**filters, score__isnull=False, status="finalized")

    stats = grades.aggregate(
        avg=Avg("score"),
        count=Count("id"),
    )

    total_students = section.enrollments.filter(
        is_active=True,
        **({"academic_year_id": academic_year_id} if academic_year_id else {}),
    ).count()

    return {
        "section_id": str(section.id),
        "section_name": section.name,
        "grade_level": section.grade_level.name,
        "total_students": total_students,
        "grade_average": round(float(stats["avg"]), 2) if stats["avg"] else None,
        "total_grades": stats["count"],
    }


def grade_level_comparison() -> dict[str, Any]:
    """Compare average performance across grade levels."""
    from apps.academics.models import Grade, GradeLevel

    results = []
    for gl in GradeLevel.objects.all():
        grades = Grade.objects.filter(
            subject_assignment__section__grade_level=gl,
            score__isnull=False,
            status="finalized",
        )
        avg = grades.aggregate(avg=Avg("score"))["avg"]
        results.append({
            "grade_level_id": str(gl.id),
            "grade_level_name": gl.name,
            "average": round(float(avg), 2) if avg else None,
            "grade_count": grades.count(),
        })
    return {"grade_levels": results}


def subject_trends(academic_year_id=None) -> dict[str, Any]:
    """Subject performance trends."""
    from apps.academics.models import Grade

    filters = {"score__isnull": False, "status": "finalized"}
    if academic_year_id:
        filters["subject_assignment__academic_year_id"] = academic_year_id

    grades = (
        Grade.objects.filter(**filters)
        .select_related("subject_assignment__subject", "grading_period")
    )

    subject_aggregates = {}
    for g in grades:
        subj_code = g.subject_assignment.subject.code
        period_name = g.grading_period.name
        subject_aggregates.setdefault(subj_code, {}).setdefault(period_name, []).append(
            float(g.score)
        )

    result = {}
    for code, periods in subject_aggregates.items():
        result[code] = {
            period: round(sum(scores) / len(scores), 2)
            for period, scores in periods.items()
        }
    return {"subject_trends": result}


def school_wide_aggregates() -> dict[str, Any]:
    """School-wide aggregate metrics (anonymized for admin)."""
    from apps.academics.models import Grade, GradeLevel
    from apps.accounts.models import StudentProfile

    total_students = StudentProfile.objects.filter(is_active=True).count()
    avg_grade = Grade.objects.filter(
        score__isnull=False, status="finalized"
    ).aggregate(avg=Avg("score"))["avg"]

    return {
        "total_students": total_students,
        "overall_grade_average": round(float(avg_grade), 2) if avg_grade else None,
        "grade_levels": GradeLevel.objects.count(),
    }


def risk_distribution() -> dict[str, Any]:
    """Distribution of risk levels across students (from latest RiskScore)."""
    from apps.guidance.models import RiskScore

    # Latest RiskScore per student (only READY status)
    latest_scores = set()
    all_scores = RiskScore.objects.filter(computation_status="ready")
    distribution = {"low": 0, "moderate": 0, "high": 0, "insufficient_data": 0}

    for score in all_scores:
        student_key = str(score.student_id)
        if student_key in latest_scores:
            continue
        latest_scores.add(student_key)
        if score.risk_level:
            distribution[score.risk_level] = distribution.get(score.risk_level, 0) + 1
        else:
            distribution["insufficient_data"] += 1

    return {"distribution": distribution, "total_with_scores": len(latest_scores)}


def low_performance_students(threshold=75, limit=20) -> list[dict[str, Any]]:
    """Students with lowest current-term grade averages."""
    from apps.academics.models import Grade

    # Group grades by student and compute average
    grade_rows = (
        Grade.objects.filter(score__isnull=False, status="finalized")
        .select_related("student__user")
    )

    student_scores = {}
    for g in grade_rows:
        sid = str(g.student_id)
        student_scores.setdefault(sid, {"name": g.student.user.get_full_name(), "scores": []})
        student_scores[sid]["scores"].append(float(g.score))

    result = []
    for sid, data in student_scores.items():
        if not data["scores"]:
            continue
        avg = sum(data["scores"]) / len(data["scores"])
        if avg < threshold:
            result.append({
                "student_id": sid,
                "student_name": data["name"],
                "average": round(avg, 2),
            })

    result.sort(key=lambda x: x["average"])
    return result[:limit]
