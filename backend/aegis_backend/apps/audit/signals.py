"""
PH10.5 — Model signal wiring to the central audit service.

Normal domain CRUD flows through Django model signals into the single
PH10.4 :func:`~apps.audit.services.record_audit` entry point.  Signals are
deliberately THIN: they only (a) detect the event, (b) capture the minimal
pre-change state required for a faithful UPDATE diff, and (c) call
``record_audit``.  NO redaction, diffing, object_repr building, action
validation, or AuditLog creation logic lives here — all of that remains in
the centralised PH10.2 / PH10.3 / PH10.4 service.

Only models justified by the PH10 audit-event matrix are instrumented.
``AuditLog`` itself is intentionally NOT instrumented, so an audit write
never recursively produces another audit event.

Actor context: PH10.5 reads the PH10.6 request-scoped audit context through
the safe :func:`~apps.audit.context.get_audit_context` accessor.  Inside an
HTTP request the authenticated actor, client IP, and user-agent travel with
the event; outside a request (management commands, AI/background RiskAlert
writes) the context is empty and events are recorded with ``user=None``,
``ip_address=None``, ``user_agent=None`` — without inventing a human actor.
Signals never inspect ``request`` directly and never touch ContextVar
internals.
"""

from django.db.models.signals import post_save, pre_delete, pre_save

from apps.audit.context import get_audit_context
from apps.audit.services import record_audit

_PRE_SAVE_SNAPSHOT_ATTR = "_aegis_audit_pre_save_snapshot"
"""Instance-scoped attribute carrying the true pre-change state.

This is NOT a global mutable store: it lives on the exact model instance
that flows from ``pre_save`` to ``post_save`` and is tied to that instance's
primary key.  Nothing else can observe or mutate it.
"""


# ---------------------------------------------------------------------------
# Pre-save: capture the true BEFORE state for UPDATE diffing
# ---------------------------------------------------------------------------

def _capture_pre_save_snapshot(sender, instance, **kwargs):
    """Capture the current DB state of *instance* before it is overwritten.

    The instrumented models all use ``UUIDField(default=uuid.uuid4)``, so
    ``instance.pk`` is populated at construction time even for a brand-new
    record.  We therefore distinguish CREATE from UPDATE by probing the
    database: if a row already exists for this PK the write is an UPDATE and
    we snapshot the pre-change row; otherwise it is a CREATE and no snapshot
    is captured.

    The captured snapshot is a fresh DB-loaded instance of the same model
    and same primary key, stashed on the instance so ``post_save`` can hand
    it to ``record_audit`` as ``old_instance``.  All diffing and redaction
    happens inside the service, never here.
    """
    pk = instance.pk
    if pk is None:
        return
    try:
        old = sender.objects.get(pk=pk)
    except sender.DoesNotExist:
        return
    setattr(instance, _PRE_SAVE_SNAPSHOT_ATTR, old)


# ---------------------------------------------------------------------------
# Post-save: CREATE / UPDATE
# ---------------------------------------------------------------------------

def _audit_post_save(sender, instance, created, **kwargs):
    """Record a single CREATE or UPDATE audit event after a save.

    ``created`` definitively separates CREATE from UPDATE even though the
    UUID PK is pre-populated.  Exactly one record_audit call happens per
    save, so one domain operation yields exactly one audit event.
    """
    context = get_audit_context()
    if created:
        record_audit(
            action="create",
            instance=instance,
            user=context.user,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        )
        return

    old = getattr(instance, _PRE_SAVE_SNAPSHOT_ATTR, None)
    record_audit(
        action="update",
        old_instance=old,
        new_instance=instance,
        user=context.user,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


# ---------------------------------------------------------------------------
# Pre-delete: preserve identity metadata before the row disappears
# ---------------------------------------------------------------------------

def _audit_pre_delete(sender, instance, **kwargs):
    """Record a single DELETE audit event.

    Runs in ``pre_delete`` so the instance still exists: its model name,
    object id, and safe object_repr are all available.  ``record_audit``
    stores ``changes=None`` for delete events.  The deleted object is never
    accessed after deletion.
    """
    context = get_audit_context()
    record_audit(
        action="delete",
        instance=instance,
        user=context.user,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def connect_signals():
    """Connect the thin audit receivers to every instrumented model.

    Imported lazily by ``AuditConfig.ready()`` so model classes are fully
    loaded (avoids circular imports).  Idempotent by construction: called
    once from ``ready()``.
    """
    from apps.academics.models import Grade
    from apps.assessments.models import Assessment, AssessmentResult
    from apps.attendance.models import AttendanceRecord
    from apps.guidance.models import (
        BehavioralNote,
        ConsultationRecord,
        Intervention,
        RiskAlert,
    )

    senders = [
        Grade,
        AttendanceRecord,
        BehavioralNote,
        ConsultationRecord,
        Intervention,
        RiskAlert,
        Assessment,
        AssessmentResult,
    ]

    for sender in senders:
        pre_save.connect(_capture_pre_save_snapshot, sender=sender, weak=False)
        post_save.connect(_audit_post_save, sender=sender, weak=False)
        pre_delete.connect(_audit_pre_delete, sender=sender, weak=False)

    # AuditLog itself is deliberately NOT instrumented, so writing an audit
    # record never triggers another audit event (no recursion).
