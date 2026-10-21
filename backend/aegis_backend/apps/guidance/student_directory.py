"""
The guidance student directory, computed on the server.

The directory answers one question: which students are in this counselor's
caseload, and how much guidance activity each of them has. It used to be
answered in the browser: the page fetched five complete lists — every risk
alert, every consultation, every intervention, every assessment result, every
behavioural note — and added them up in JavaScript. The payload grew with the
caseload, and the arithmetic was repeated in every browser on every load.

The same answer, computed with grouped queries: one row per student, and
about a dozen queries in total whatever the caseload size.

The visibility rules are the ones the individual endpoints already enforce,
so the directory shows a counselor exactly what those endpoints would show
them:

- risk alerts: all of them (a counselor sees the whole school's alerts)
- behavioural notes: all of them
- consultations: the counselor's own
- interventions: the counselor's own
- assessment results: the results of assessments the counselor created
"""

from datetime import date, datetime, time

from django.db.models import Case, Count, IntegerField, Max, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.assessments.models import AssessmentResult
from apps.accounts.models import StudentProfile

from .models import (
    BehavioralNote,
    ConsultationRecord,
    Intervention,
    RiskAlert,
)

#: An alert in one of these states is still open.
OPEN_ALERT_STATUSES = (
    RiskAlert.Status.ACTIVE,
    RiskAlert.Status.UNDER_MONITORING,
    RiskAlert.Status.ESCALATED,
)

#: How each risk level ranks, for "the worst one wins".
_RISK_RANK = {
    RiskAlert.RiskLevel.HIGH: 2,
    RiskAlert.RiskLevel.MODERATE: 1,
}
_RANK_TO_LEVEL = {rank: level for level, rank in _RISK_RANK.items()}


def _counts(queryset, field="student_id"):
    """``{student_id: count}`` for a grouped queryset."""
    return {
        row[field]: row["count"]
        for row in queryset.values(field).annotate(count=Count("id"))
    }


def _latest(queryset, field, field_id="student_id"):
    """``{student_id: latest value of ``field``}`` for a grouped queryset."""
    return {
        row[field_id]: row["latest"]
        for row in queryset.values(field_id).annotate(latest=Max(field))
    }


def _as_datetime(value):
    """
    A date or datetime, as an aware datetime, so the sources can be compared.

    The date columns and the datetime columns are compared against each other,
    and one of them is timezone-aware. Mixing the two raises, so a plain date
    is anchored to midnight in the current timezone.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return timezone.make_aware(datetime.combine(value, time.min))
    return None


def student_directory(user) -> list[dict]:
    """
    The caseload directory for ``user``.

    One row per student with any guidance activity visible to them.
    """
    return build_directory(
        user=user,
        consultations=_own_consultations(user),
        interventions=_own_interventions(user),
        results=_own_results(user),
    )


def _own_consultations(user):
    profile = getattr(user, "guidance_profile", None)
    if profile is None:
        return ConsultationRecord.objects.none()
    return ConsultationRecord.objects.filter(counselor=profile)


def _own_interventions(user):
    profile = getattr(user, "guidance_profile", None)
    if profile is None:
        return Intervention.objects.none()
    return Intervention.objects.filter(assigned_counselor=profile)


def _own_results(user):
    return AssessmentResult.objects.filter(assessment__created_by=user)


def build_directory(
    *,
    user,
    consultations,
    interventions,
    results,
) -> list[dict]:
    """
    Assemble the directory rows from the five sources.

    Split out from :func:`student_directory` so the tests can drive it with
    the querysets they choose.
    """
    open_alerts = RiskAlert.objects.filter(status__in=OPEN_ALERT_STATUSES)

    alert_counts = _counts(open_alerts)
    risk_rank = {
        row["student_id"]: row["rank"]
        for row in open_alerts.values("student_id").annotate(
            rank=Max(
                Case(
                    When(risk_level=RiskAlert.RiskLevel.HIGH, then=Value(2)),
                    When(risk_level=RiskAlert.RiskLevel.MODERATE, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
        )
    }

    consultation_counts = _counts(consultations)
    intervention_counts = _counts(interventions)
    result_counts = _counts(results)

    latest_alerts = _latest(open_alerts, "generated_at")
    latest_consultations = _latest(consultations, "session_date")
    latest_interventions = _latest(interventions, "plan_start_date")
    latest_results = {
        row["student_id"]: row["latest"]
        for row in results.values("student_id").annotate(
            latest=Max(Coalesce("completed_at", "started_at"))
        )
    }
    latest_notes = _latest(BehavioralNote.objects.all(), "date_recorded")

    student_ids = set(alert_counts)
    student_ids |= set(consultation_counts)
    student_ids |= set(intervention_counts)
    student_ids |= set(result_counts)
    # Behavioural notes are not an activity type: a student whose only
    # guidance record is a note has no guidance activity and is not listed.
    # A note still counts towards the latest activity of a student who has
    # activity of another kind.

    profiles = {
        profile.id: profile
        for profile in StudentProfile.objects.filter(id__in=student_ids)
        .select_related("user")
    }

    rows = []
    for student_id in student_ids:
        profile = profiles.get(student_id)
        if profile is None:
            continue

        latest = None
        for value in (
            latest_alerts.get(student_id),
            latest_consultations.get(student_id),
            latest_interventions.get(student_id),
            latest_results.get(student_id),
            latest_notes.get(student_id),
        ):
            candidate = _as_datetime(value)
            if candidate is not None and (latest is None or candidate > latest):
                latest = candidate

        rows.append(
            {
                "id": str(profile.id),
                "name": profile.user.get_full_name(),
                "code": profile.student_id,
                "latestActivity": latest.date().isoformat() if latest else None,
                "openAlertCount": alert_counts.get(student_id, 0),
                "atRiskLevel": _RANK_TO_LEVEL.get(
                    risk_rank.get(student_id, 0)
                ),
                "consultationCount": consultation_counts.get(student_id, 0),
                "interventionCount": intervention_counts.get(student_id, 0),
                "resultCount": result_counts.get(student_id, 0),
            }
        )

    rows.sort(key=lambda row: (row["name"] or "", row["code"] or ""))
    return rows
