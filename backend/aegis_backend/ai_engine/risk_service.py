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
) -> bool:
    """
    Determine whether the computed state represents a meaningful change
    from the existing actionable state.

    Meaningful change = risk level escalation/improvement OR significant
    within-level score movement.

    PH9.4: MODERATE/55 → MODERATE/57 = NO change.
           MODERATE/57 → HIGH/81 = actionable state change.
    """
    if existing_alert is None:
        # No existing actionable alert → creating one is a change
        return True

    # If existing alert is not ACTIVE, a new computation is a change
    if existing_alert.status not in ("active", "under_monitoring"):
        return True

    existing_level = existing_alert.risk_level
    if existing_level != current_level:
        # Level change is always actionable
        return True

    # Same level — check significant within-level movement (>= 10 points)
    if current_score is not None:
        existing_score = getattr(existing_alert.risk_score_ref, "risk_score", None)
        if existing_score is not None:
            diff = abs(float(current_score) - float(existing_score))
            if diff >= 10:
                return True

    return False


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

    # --- Always store RiskScore (history) ---
    risk_score_obj = RiskScore.objects.create(
        student=student_profile,
        computation_status=computed_status,
        risk_score=prediction.get("risk_score"),
        risk_level=prediction.get("risk_level"),
        model_version=model_version,
        feature_snapshot=feature_snapshot or {},
        explanation=prediction.get("explanation", {}),
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

    current_level = prediction.get("risk_level")
    current_score = prediction.get("risk_score")

    if current_level is None:
        return RiskStateResult(
            risk_score_obj=risk_score_obj,
            state_changed=False,
            notified=False,
            reason="no_risk_level_available",
        )

    # --- Find existing actionable alert for this student ---
    existing_alert = RiskAlert.objects.filter(
        student=student_profile,
        status__in=["active", "under_monitoring"],
    ).order_by("-generated_at").first()

    # --- Determine meaningful change ---
    changed = _compute_meaningful_change(
        current_level, current_score, existing_alert
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
        existing_alert.risk_factors = prediction.get("explanation", {}).get(
            "contributing_factors", []
        )
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
            risk_factors=prediction.get("explanation", {}).get(
                "contributing_factors", []
            ),
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
