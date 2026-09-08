"""
Central Audit Service (PH10.4).

The single, controlled mechanism for creating ``AuditLog`` records.

Ownership
---------
PH10.4 owns AUDIT RECORD CREATION.  It does NOT own request middleware
or model signal registration; those belong to later PH10 work.  This
module has no HTTP assumptions, no UI concerns, and no dependency on any
request context.

Architecture flow::

    Caller
      |
      v
    record_audit(action, instance, user, ...)
      |
      |  PH10.2  -> allowlists + safe serialization (redact.py)
      |  PH10.3  -> canonical diff (diff.py) for UPDATE events
      v
    AuditLog

Design constraints:

- Exactly ONE public audit-writing entry point: ``record_audit()``.
- Exactly ONE ``AuditLog`` row is created per invocation.
- Normal Django ORM transaction semantics: the row is created in the
  caller's transaction.  If the caller rolls back, the audit row rolls
  back; if it commits, the audit row commits.  No independent audit
  database and no out-of-transaction writes.
- ``object_repr`` is derived from model metadata + primary key, never
  from model ``__str__()``, and is bounded to 255 characters.
- ``changes`` is produced exclusively through PH10.2 (redact) + PH10.3
  (diff) for UPDATE events.  The public API accepts NO caller-supplied
  ``changes``: CREATE / DELETE / LOGIN / LOGOUT / IMPORT / EXPORT /
  ACCESS always store ``None``.  No caller-provided raw changes can
  bypass PH10.2 safety.

See also
--------
models.AuditLog   : The PH10.1 schema this service populates.
redact            : PH10.2 allowlists, redaction, safe serialization.
diff              : PH10.3 canonical diff utility.
"""

import uuid

from django.utils import timezone

from apps.audit.diff import compute_diff
from apps.audit.models import AuditLog

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AuditServiceError(Exception):
    """Base class for misuse errors raised by the central audit service."""


class InvalidActionError(AuditServiceError, ValueError):
    """Raised when *action* is not one of the 8 specification-defined values."""


class MissingActionError(AuditServiceError, ValueError):
    """Raised when *action* is not provided."""


class TargetConfigurationError(AuditServiceError, ValueError):
    """Raised when the target/object configuration is incoherent."""


# ---------------------------------------------------------------------------
# Fixed authentication-event target metadata
# ---------------------------------------------------------------------------

AUTH_EVENT_MODEL_NAME = "accounts.Authentication"
"""Fixed model_name for LOGIN / LOGOUT events (no domain object exists)."""

AUTH_EVENT_REPRS = {
    AuditLog.Action.LOGIN: "Login",
    AuditLog.Action.LOGOUT: "Logout",
}
"""Non-sensitive, PII-free object_repr for the fixed authentication events."""

MAX_OBJECT_REPR_LENGTH = 255
"""Upper bound of AuditLog.object_repr (matches the model constraint)."""


# ---------------------------------------------------------------------------
# Canonical public entry point
# ---------------------------------------------------------------------------

def record_audit(
    *,
    action=None,
    instance=None,
    old_instance=None,
    new_instance=None,
    user=None,
    ip_address=None,
    user_agent=None,
    model_name=None,
    object_id=None,
    object_repr=None,
):
    """Create exactly one :class:`~apps.audit.models.AuditLog` record.

    This is the single source of truth for AuditLog creation.  The actor
    (*user*), request metadata (*ip_address*, *user_agent*), and the
    event *timestamp* are preserved on the created record.

    Parameters
    ----------
    action : str or None
        One of the 8 specification-defined actions:
        ``create``, ``update``, ``delete``, ``login``, ``logout``,
        ``import``, ``export``, ``access``.  Required; ``None`` (the
        default) raises :class:`MissingActionError`.
    instance : Model or None
        The domain object the event concerns.  Its model metadata,
        primary key, and a safe representation are derived here.
    old_instance : Model or None
        Pre-change snapshot for UPDATE events.
    new_instance : Model or None
        Post-change snapshot for UPDATE events.
    user : accounts.User or None
        The actor.  ``None`` = system/background event.
    ip_address : str or None
        Client IP (from REMOTE_ADDR) when available.  The service does
        not inspect HTTP requests or trust ``X-Forwarded-For``.
    user_agent : str or None
        Browser/device user-agent string when available.
    model_name : str or None
        Explicit ``app_label.ModelName`` override for events without a
        usable domain instance.  Derived from instance metadata when an
        instance is present.
    object_id : UUID or None
        Explicit object identifier override.  From ``instance.pk`` when
        an instance is present.  ``None`` when the event has no target.
    object_repr : str or None
        Explicit safe representation override.  Derived as
        ``<ModelName>:<UUID>`` (domain objects) or ``Login``/``Logout``
        (authentication events) otherwise.

    Notes
    -----
    *changes* is never a caller-suppliable parameter.  ``AuditLog.changes``
    is populated exclusively by the service through the PH10.3 canonical
    diff utility (which serializes via PH10.2 allowlists) for UPDATE
    events.  Every other action stores ``NULL``, so no caller-provided
    raw values can ever bypass PH10.2 redaction.

    Returns
    -------
    AuditLog
        The created, persisted record.

    Raises
    ------
    InvalidActionError
        If *action* is not one of the 8 defined AuditLog actions.
    MissingActionError
        If *action* is ``None``.
    TypeError or ValueError
        Propagated from the PH10.3 canonical diff utility for
        mismatched old/new model types.
    ValueError
        If an UPDATE is requested without both old_instance and
        new_instance, or if an explicit object_id/object_repr is
        incoherent with a supplied instance.
    """
    if action is None:
        raise MissingActionError("action is required")

    normalized_action = normalize_action(action)

    # --- Domain-instance metadata (may be None for auth/system events) -----
    canonical_instance = None
    if normalized_action in (AuditLog.Action.UPDATE,):
        old_meta = getattr(old_instance, "_meta", None)
        new_meta = getattr(new_instance, "_meta", None)
        if old_instance is not None and new_instance is not None:
            if old_meta.model != new_meta.model:
                raise TypeError(
                    f"Cannot diff mismatched model types: "
                    f"{old_meta.label} vs {new_meta.label}"
                )
            canonical_instance = new_instance
        elif old_instance is not None:
            canonical_instance = old_instance
        else:
            canonical_instance = new_instance
        if canonical_instance is None:
            raise ValueError(
                "UPDATE requires old_instance and new_instance (or a "
                "referenced instance) so a safe diff can be produced"
            )
    elif instance is not None:
        canonical_instance = instance

    # --- Derive model_name ------------------------------------------------
    resolved_model_name = _derive_model_name(
        canonical_instance, model_name, normalized_action
    )

    # --- Derive object_id ---------------------------------------------------
    resolved_object_id = _derive_object_id(
        canonical_instance, object_id, normalized_action
    )

    # --- Derive object_repr ------------------------------------------------
    resolved_object_repr = _derive_object_repr(
        canonical_instance,
        resolved_model_name,
        resolved_object_id,
        object_repr,
        normalized_action,
    )

    # --- Changes ------------------------------------------------------------
    # Changes are generated exclusively through PH10.3 (which serializes
    # via PH10.2 allowlists) for UPDATE events.  All other actions store
    # NULL.  The public API accepts no caller-supplied changes, so raw
    # sensitive data can never reach AuditLog.changes.
    resolved_changes = None
    if (
        normalized_action == AuditLog.Action.UPDATE
        and old_instance is not None
        and new_instance is not None
    ):
        resolved_changes = compute_diff(old_instance, new_instance)

    # --- Create exactly one AuditLog ---------------------------------------
    audit_log = AuditLog.objects.create(
        user=user if user is not None else None,
        action=normalized_action,
        model_name=resolved_model_name,
        object_id=resolved_object_id if resolved_object_id is not None else None,
        object_repr=resolved_object_repr,
        changes=resolved_changes,
        ip_address=ip_address if ip_address is not None else None,
        user_agent=user_agent if user_agent is not None else None,
        timestamp=timezone.now(),
    )

    return audit_log


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def normalize_action(action):
    """Return the canonical AuditLog action value.

    Accepts either the raw string value (``"create"``) or the
    ``AuditLog.Action`` enum member (``AuditLog.Action.CREATE``).

    Raises
    ------
    InvalidActionError
        If *action* is not one of the 8 specification-defined values.
    """
    if hasattr(action, "value"):
        raw = action.value
    else:
        raw = action

    if raw not in AuditLog.Action.values:
        raise InvalidActionError(
            f"Invalid audit action: {raw!r}. "
            f"Allowed: {list(AuditLog.Action.values)}"
        )
    return raw


def _derive_model_name(instance, model_name, action):
    """Resolve the ``app_label.ModelName`` for the audit target.

    Instance metadata wins when an instance is present; an explicit
    *model_name* is used otherwise.  Login/logout events have no domain
    object and map to the fixed ``accounts.Authentication`` value.
    """
    if action in (AuditLog.Action.LOGIN, AuditLog.Action.LOGOUT):
        if model_name not in (None, AUTH_EVENT_MODEL_NAME):
            raise TargetConfigurationError(
                f"{action!r} events must not carry a model_name override; "
                f"they always resolve to {AUTH_EVENT_MODEL_NAME!r}"
            )
        return AUTH_EVENT_MODEL_NAME

    meta = getattr(instance, "_meta", None)
    if meta is not None:
        derived = meta.label
        if model_name is not None and model_name != derived:
            raise TargetConfigurationError(
                f"model_name {model_name!r} does not match the instance "
                f"model {derived!r}"
            )
        return derived

    if model_name is not None:
        if not model_name or not isinstance(model_name, str):
            raise TargetConfigurationError(
                "model_name must be a non-empty 'app_label.ModelName' string"
            )
        return model_name

    raise TargetConfigurationError(
        "Cannot determine model_name: no instance was supplied and "
        "model_name was not provided"
    )


def _derive_object_id(instance, object_id, action):
    """Resolve the object UUID for the audit target.

    Uses ``instance.pk`` when an instance is present.  An explicit
    *object_id* is allowed only when it matches the instance PK or when
    no instance is present (system/import/export events).  Login/logout
    events always yield ``None``.
    """
    if action in (AuditLog.Action.LOGIN, AuditLog.Action.LOGOUT):
        if object_id is not None:
            raise TargetConfigurationError(
                f"{action!r} events must not carry an object_id; they "
                f"always resolve to NULL"
            )
        return None

    meta = getattr(instance, "_meta", None)
    if meta is not None:
        pk = getattr(instance, "pk", None)
        if pk is not None:
            if object_id is not None and object_id != pk:
                raise TargetConfigurationError(
                    "object_id does not match the supplied instance primary key"
                )
            return pk if isinstance(pk, uuid.UUID) else _coerce_uuid_object_id(pk)
        if object_id is not None:
            return object_id
        return None

    if object_id is not None:
        return _coerce_uuid_object_id(object_id)
    return None


def _coerce_uuid_object_id(object_id):
    """Coerce *object_id* to a UUID, rejecting malformed values."""
    if isinstance(object_id, uuid.UUID):
        return object_id
    try:
        return uuid.UUID(str(object_id))
    except (ValueError, TypeError) as exc:
        raise TargetConfigurationError(
            f"object_id must be a UUID-compatible value, got {object_id!r}"
        ) from exc


def _derive_object_repr(instance, model_name, object_id, object_repr, action):
    """Resolve the bounded, PII-free human identification string.

    For authentication events the fixed, non-sensitive values ``Login``
    and ``Logout`` are used.  For domain objects the preferred form is
    ``<ModelName>:<UUID>`` derived from metadata + primary key — never
    from ``model.__str__()``.  An explicit *object_repr* is accepted only
    when it is a bounded, non-sensitive override supplied by a trusted
    caller (e.g. ``ImportJob:<UUID>`` for import/export events).
    """
    if action in (AuditLog.Action.LOGIN, AuditLog.Action.LOGOUT):
        if object_repr is not None and object_repr != AUTH_EVENT_REPRS[action]:
            raise TargetConfigurationError(
                f"{action!r} events must not carry an object_repr override; "
                f"they always resolve to {AUTH_EVENT_REPRS[action]!r}"
            )
        return AUTH_EVENT_REPRS[action]

    if instance is not None:
        if object_repr is not None:
            raise TargetConfigurationError(
                "Do not pass an explicit object_repr together with a model "
                "instance; the service derives a safe representation from "
                "metadata + primary key"
            )
        pk = getattr(instance, "pk", None)
        label = getattr(getattr(instance, "_meta", None), "label", None)
        if label is not None:
            short_name = label.split(".")[-1]
            if pk is not None:
                return _bounded_repr(f"{short_name}:{pk}")
            return _bounded_repr(label)

    if object_repr is not None:
        return _bounded_repr(object_repr)

    if model_name is not None and object_id is not None:
        short_name = model_name.split(".")[-1]
        return _bounded_repr(f"{short_name}:{object_id}")

    if model_name is not None:
        return _bounded_repr(model_name)

    raise TargetConfigurationError(
        "Cannot determine object_repr: no instance, object_id, or "
        "explicit object_repr was provided"
    )


def _bounded_repr(value):
    """Coerce *value* to str and bound it to ``object_repr`` length."""
    text = str(value)
    if not text:
        raise TargetConfigurationError("object_repr must not be empty")
    if len(text) > MAX_OBJECT_REPR_LENGTH:
        raise TargetConfigurationError(
            f"object_repr exceeds {MAX_OBJECT_REPR_LENGTH} characters"
        )
    return text