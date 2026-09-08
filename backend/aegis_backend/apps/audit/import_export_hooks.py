"""
PH10.9 — Import / Export audit hooks.

Thin integration points that connect the data_import operations to the
PH10.4 central audit service, following the same pattern as PH10.7.

- ``audit_successful_import(job)``     — called from
  ``ImportJobViewSet.create()`` after a job reaches the COMPLETED state.
- ``audit_successful_export(model_name)`` — called from
  ``ExportViewMixin.get()`` after a file payload is generated, passing the
  real domain model of the dataset that was exported.

Design constraints
------------------
- An operation (import/export) produces EXACTLY ONE AuditLog row, never
  one per imported/exported row.
- The audit writes WHO performed WHAT operation and WHEN only.  No file
  contents, imported/exported rows, grades, attendance details, notes,
  recommendations, risk factors, assessment answers, passwords, tokens,
  credentials, or request bodies are ever stored in AuditLog.
- The audit side-effect is fire-and-forget (PH10.7's principle): if the
  business operation succeeds but the audit write fails, the business
  outcome is unchanged — the failure is logged internally without
  sensitive data and not re-raised.
- PH10.6 ``get_audit_context()`` supplies the actor, IP, and user-agent.
  Outside a request (or when no actor is authenticated) these all resolve
  to ``None``; no SystemUser is ever invented.

Import target representation
----------------------------
Imports are tied to a real, persistent job object: ``ImportJob``.  The
audit therefore uses ``model_name="data_import.ImportJob"``,
``object_id=<job UUID>``, ``object_repr="ImportJob:<uuid>"``.

Export target representation
----------------------------
Exports have NO job model and NO persistent target object of their own.
They do, however, operate on real, existing datasets.  The semantically
correct representation is therefore:

- ``model_name`` = the REAL domain model of the exported dataset
  (``academics.Grade``, ``attendance.AttendanceRecord``, or
  ``accounts.StudentProfile``).  No model name is ever invented; it is
  always a model that already exists in the codebase.  In particular it
  is NOT ``data_import.ImportJob`` (exports do not touch ImportJob) and
  NOT a fabricated ``data_import.ExportJob``.
- ``object_id`` = ``None`` — the event is operation-scoped, not a single
  exported row or object.
- ``object_repr`` = the fixed, bounded, non-sensitive label ``Export``
  (mirrors the Login/Logout convention for operation-level events).
"""
import logging

from apps.audit.context import get_audit_context
from apps.audit.services import record_audit

logger = logging.getLogger(__name__)

#: Fixed model_name for import events: ImportJob is the real job-tracking
#: model created by a successful import and is the import's target identity.
IMPORT_MODEL_NAME = "data_import.ImportJob"

#: Fixed, non-sensitive object_repr for export events (mirrors the
#: Login/Logout convention in the central service).
EXPORT_EVENT_REPR = "Export"


def audit_successful_import(job):
    """Record exactly one IMPORT audit event after a successful import.

    The caller guarantees *job* has reached the terminal COMPLETED state
    before invoking this hook.  The audit write is isolated: if it
    raises, the failure is logged internally and NOT re-raised, so a
    successful import always completes.
    """
    context = get_audit_context()
    try:
        record_audit(
            action="import",
            user=context.user,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            model_name=IMPORT_MODEL_NAME,
            object_id=job.id,
            object_repr=f"ImportJob:{job.id}",
        )
    except Exception:
        logger.exception("IMPORT audit record failed (import outcome unchanged)")


def audit_successful_export(model_name):
    """Record exactly one EXPORT audit event after a successful export.

    *model_name* is the real domain model label of the dataset that was
    exported (``academics.Grade``, ``attendance.AttendanceRecord``, or
    ``accounts.StudentProfile``) — never a fabricated job model and never
    ``data_import.ImportJob``, because exports do not operate on
    ImportJob.  There is no ExportJob model and no persistent target
    object, so ``object_id`` is None and the fixed, non-sensitive
    ``object_repr`` ``Export`` is used.  The audit write is isolated
    exactly like the import hook.
    """
    context = get_audit_context()
    try:
        record_audit(
            action="export",
            user=context.user,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            model_name=model_name,
            object_repr=EXPORT_EVENT_REPR,
        )
    except Exception:
        logger.exception("EXPORT audit record failed (export outcome unchanged)")
