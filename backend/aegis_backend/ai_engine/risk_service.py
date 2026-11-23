"""
AEGIS AI Engine — risk computation orchestration service.

PH9.4: RiskScore persistence + RiskAlert integration.

Architecture:
  RiskScore  = machine-generated computation result/history
  RiskAlert  = actionable Guidance alert/state

Recomputation semantics (PH9.4 correction):
  - Store EVERY computation as a RiskScore (history).
  - Compare current computed state against existing actionable state.
  - Create/update RiskAlert ONLY when a meaningful risk-state change occurs.
  - Do NOT create duplicate actionable alerts for unchanged state.
  - Do NOT create fake alerts for INSUFFICIENT_DATA.
  - Preserve manual alerts (do not overwrite).
  - Preserve status transitions (acknowledge, under_monitoring, resolved, escalated).

PH9.5: Notification integration.
  - Reuse existing dispatch_event() and deduplication_key.
  - RISK_ALERT_GENERATED notification type.
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

logger = logging.getLogger(__name__)


class RiskStateResult:
    """
    Result of a single student's risk computation integration.

    Attributes:
        risk_score_obj: The RiskScore instance (always created).
        risk_alert: created/updated RiskAlert or None.
        state_changed: True if an actionable alert was created/updated.
        notified: True if notification dispatched.
        reason: reason for the outcome.
    """

    def __init__(
        self,
        risk_score_obj,
        risk_alert=None,
        state_changed=False,
        notified=False,
        reason="",
    ):
        self.risk_score_obj = risk_score_obj
        self.risk_alert = risk_alert
        self.state_changed = state_changed
        self.notified = notified
        self.reason = reason


def _compute_meaningful_change(
    current_level,
    current_score,
    existing_alert,
    *,
    current_model_version: str | None = None,
) -> tuple[bool, str, dict | None]:
    """
    Determine whether the computed state represents a meaningful change
    from the existing actionable state.

    Pilot policy from AEGIS_Developer_Implementation_Guide.md:
      no prior alert, category change, or same category with an absolute
      index change of at least 10 points.

    Returns (changed, reason, prior_state). The prior state is recorded on the
    RiskScore explanation so the alert can be audited later.
    """
    if existing_alert is None:
        return True, "no_prior_alert", None

    prior_score = _unrounded_index(existing_alert)
    prior = {
        "alert_id": str(existing_alert.id),
        "level": existing_alert.risk_level,
        "index": prior_score,
        "status": existing_alert.status,
    }

    # A closed alert does not describe the current state.
    if existing_alert.status not in ("active", "under_monitoring"):
        return True, "prior_alert_closed", prior

    if existing_alert.risk_level != current_level:
        return True, "category_changed", prior

    # Same category: only a 10-point move on a comparable model index
    # re-alerts. An index from another model version is not comparable.
    reference = existing_alert.risk_score_ref
    comparable = (
        reference is not None
        and current_model_version is not None
        and reference.model_version == current_model_version
    )
    if comparable and current_score is not None and prior_score is not None:
        diff = abs(float(current_score) - prior_score)
        if diff >= 10:
            return True, "index_moved_at_least_10_points", prior

    return False, "unchanged", prior


def _unrounded_index(existing_alert) -> float | None:
    """
    Prior index for comparison.

    The guide compares unrounded indices, but RiskScore stores two decimals.
    Read the unrounded value recorded by the previous computation first and
    fall back to the stored field for alerts created before that record
    existed.
    """
    reference = existing_alert.risk_score_ref
    if reference is None:
        return None

    explanation = reference.explanation or {}
    recorded = (explanation.get("alert_decision") or {}).get("current") or {}
    value = recorded.get("index")
    if isinstance(value, (int, float)):
        return float(value)
    if reference.risk_score is not None:
        return float(reference.risk_score)
    return None


def _alert_factors(prediction: dict, decision: dict) -> list:
    """
    Model/rule factors plus the alert decision.

    The guide requires the alert to record prior and current values and the
    reason. `risk_factors` is the only per-alert JSON field, and existing
    readers expect objects with a `feature` key, so the decision is one more
    object of that shape.
    """
    factors = list(
        (prediction.get("explanation") or {}).get("contributing_factors") or []
    )
    factors.append(
        {
            "feature": "alert_change",
            "direction": decision["reason"],
            "value": (decision.get("current") or {}).get("index"),
            "threshold": (decision.get("prior") or {}).get("index"),
            "prior": decision.get("prior"),
            "current": decision.get("current"),
            "reason": decision["reason"],
            "source_revision": decision.get("source_revision"),
        }
    )
    if prediction.get("needs_staff_review"):
        factors.append(
            {
                "feature": "model_review",
                "direction": "tie",
                "value": None,
                "threshold": None,
                "reason": (
                    "Model class estimates tied; no model category was "
                    "assigned. Staff review required."
                ),
            }
        )
    return factors


def _revision_prior_alert(student_profile, revision):
    """
    A prior alert for the same source revision, if the batch already ran.

    The guide forbids a second automatic notification when the same release
    or correction is processed again. `source_revision` is a digest of the
    measured values, so the same digest means the same inputs were already
    evaluated even when the alert was since resolved.
    """
    if not revision:
        return None
    from apps.guidance.models import RiskAlert, RiskScore

    prior_scores = RiskScore.objects.filter(
        student=student_profile,
        feature_snapshot__source_revision=revision,
    )
    return (
        RiskAlert.objects.filter(risk_score_ref__in=prior_scores)
        .order_by("-generated_at")
        .first()
    )


def _prior_state(alert) -> dict | None:
    if alert is None:
        return None
    return {
        "alert_id": str(alert.id),
        "level": alert.risk_level,
        "index": _unrounded_index(alert),
        "status": alert.status,
    }


def integrate_risk_result(
    student_profile,
    prediction: dict,
    *, 
    model_version: str = "v1",
    feature_snapshot: dict | None = None,
    dispatch_notifications: bool = True,
) -> RiskStateResult:
    """
    Integrate a single student's risk prediction into RiskScore + RiskAlert.

    Args:
        student_profile: StudentProfile instance
        prediction: dict from risk_scorer.predict_single
        model_version: model version identifier
        feature_snapshot: feature dict used for computation
        dispatch_notifications: whether to dispatch notifications

    Returns:
        RiskStateResult describing what happened.
    """
    from apps.guidance.models import RiskAlert, RiskScore
    from apps.notifications.events import dispatch_event
    from apps.notifications.models import NotificationType
    from apps.accounts.models import User, GuidanceProfile

    now = timezone.now()
    computed_status = prediction.get("computation_status", "ready")
    current_level = prediction.get("risk_level")
    current_score = prediction.get("risk_index", prediction.get("risk_score"))

    # --- Existing actionable alert and the pilot trigger decision ---
    existing_alert = None
    changed = False
    change_reason = "not_evaluated"
    prior_state = None
    if computed_status != "insufficient_data" and current_level is not None:
        existing_alert = (
            RiskAlert.objects.filter(
                student=student_profile,
                status__in=["active", "under_monitoring"],
            )
            .order_by("-generated_at")
            .first()
        )
        if existing_alert is not None:
            changed, change_reason, prior_state = _compute_meaningful_change(
                current_level,
                current_score,
                existing_alert,
                current_model_version=model_version,
            )
        else:
            revision = (feature_snapshot or {}).get("source_revision")
            revision_alert = _revision_prior_alert(student_profile, revision)
            if revision_alert is not None:
                # Same inputs already produced an alert; do not notify again.
                prior_state = _prior_state(revision_alert)
                change_reason = "same_revision_already_evaluated"
            else:
                changed, change_reason, prior_state = _compute_meaningful_change(
                    current_level,
                    current_score,
                    None,
                    current_model_version=model_version,
                )

    # The model predicts a float; RiskScore stores two decimal places. A float
    # such as 66.67 is 66.669999... as a Decimal, which the field rejects, so
    # round through the string form before persisting.
    stored_score = prediction.get("risk_score")
    if stored_score is not None:
        stored_score = Decimal(str(stored_score)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    explanation = dict(prediction.get("explanation") or {})
    decision = {
        "prior": prior_state,
        "current": {
            "level": current_level,
            "index": None if current_score is None else float(current_score),
            "category_source": prediction.get("category_source"),
        },
        "reason": change_reason,
        "triggered": changed,
        "source_revision": (feature_snapshot or {}).get("source_revision"),
    }
    explanation["alert_decision"] = decision
    alert_factors = _alert_factors(prediction, decision)

    # --- Always store RiskScore (history) ---
    risk_score_obj = RiskScore.objects.create(
        student=student_profile,
        computation_status=computed_status,
        risk_score=stored_score,
        risk_level=current_level,
        model_version=model_version,
        feature_snapshot=feature_snapshot or {},
        explanation=explanation,
        computed_at=now,
    )

    # INSUFFICIENT_DATA: store RiskScore only, no RiskAlert
    if computed_status == "insufficient_data":
        return RiskStateResult(
            risk_score_obj=risk_score_obj,
            state_changed=False,
            notified=False,
            reason="insufficient_data: RiskScore stored, no RiskAlert created",
        )

    if current_level is None:
        return RiskStateResult(
            risk_score_obj=risk_score_obj,
            state_changed=False,
            notified=False,
            reason="no_risk_level_available",
        )

    if not changed:
        return RiskStateResult(
            risk_score_obj=risk_score_obj,
            risk_alert=existing_alert,
            state_changed=False,
            notified=False,
            reason="unchanged_state: no new alert, no notification",
        )

    # --- Create or update actionable RiskAlert ---
    if existing_alert is not None and existing_alert.source == "decision_tree":
        # Update existing DT-generated alert (preserve manual alerts)
        existing_alert.risk_level = current_level
        existing_alert.risk_score_ref = risk_score_obj
        existing_alert.risk_factors = alert_factors
        if existing_alert.status == "under_monitoring":
            # Keep as-is; recomputation doesn't auto-change status
            pass
        existing_alert.save()
        alert = existing_alert
        alert_created = False
    else:
        # Create new alert (or existing is a manual alert → don't overwrite)
        if existing_alert is not None and existing_alert.source == "manual":
            # Manual alert exists; AI result should NOT overwrite manual decision.
            # Just record the RiskScore without creating a duplicate alert.
            return RiskStateResult(
                risk_score_obj=risk_score_obj,
                risk_alert=existing_alert,
                state_changed=False,
                notified=False,
                reason="manual_alert_preserved: AI result recorded as RiskScore only",
            )

        alert = RiskAlert.objects.create(
            student=student_profile,
            risk_level=current_level,
            risk_factors=alert_factors,
            source="decision_tree",
            status="active",
            risk_score_ref=risk_score_obj,
            generated_at=now,
        )
        alert_created = True

    # --- Dispatch notification (PH9.5) ---
    notified = False
    if dispatch_notifications:
        # Recipients: Guidance staff (and Adviser + Parent for HIGH)
        recipients = set()
        guidance_users = User.objects.filter(role="guidance")
        recipients.update(guidance_users)

        # HIGH events may notify adviser + parents per approved policy
        if current_level == "high":
            adviser = student_profile.section.adviser if student_profile.section_id else None
            if adviser is not None:
                recipients.add(adviser.user)
            parents = student_profile.parent_links.all()
            for link in parents:
                recipients.add(link.parent.user)

        if recipients:
            dedup_key = (
                f"risk_alert:{student_profile.id}:{current_level}:{now.date()}",
            )
            dispatch_event(
                NotificationType.RISK_ALERT_GENERATED,
                recipients=recipients,
                sender=None,
                title=f"Risk Alert: {student_profile.user.get_full_name()} — {current_level.upper()}",
                message=(
                    f"Risk assessment indicates {current_level.upper()} risk "
                    f"(score: {current_score}). "
                    f"Model version: {model_version}."
                ),
                link="/guidance/risk-alerts",
                # `dedup_key` is a one-element tuple, so this is the string,
                # not its first character.
                deduplication_key=dedup_key[0],
            )
            notified = True

    action = "created" if alert_created else "updated"
    return RiskStateResult(
        risk_score_obj=risk_score_obj,
        risk_alert=alert,
        state_changed=True,
        notified=notified,
        reason=f"actionable_state_change: RiskAlert {action}",
    )
