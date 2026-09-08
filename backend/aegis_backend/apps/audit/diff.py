"""
Canonical audit diff utility — PH10.3.

Compares two model instances through PH10.2 safe serialization and
produces the flat ``{"old": {...}, "new": {...}}`` diff representation
required by ``AuditLog.changes``.

Architecture
------------
- PH10.2 (redact.py) owns allowlists, redaction, normalization.
- PH10.3 (this module) owns: snapshot comparison, change detection,
  and final diff construction.
- This module never re-implements value normalization.
"""

from apps.audit.redact import get_allowed_fields, safe_serialize_fields


# ---------------------------------------------------------------------------
# Canonical diff function
# ---------------------------------------------------------------------------

def compute_diff(old_instance, new_instance) -> dict | None:
    """Compute the safe audit diff between two model instances.

    Derives the model name from ``old_instance._meta.label`` so callers
    never need to pass a redundant string.

    Parameters
    ----------
    old_instance : django.db.models.Model
        The model instance *before* the change.  May be ``None`` for
        CREATE semantics (returns ``None``).
    new_instance : django.db.models.Model
        The model instance *after* the change.  May be ``None`` for
        DELETE semantics (returns ``None``).

    Returns
    -------
    dict or None
        ``{"old": {field: value}, "new": {field: value}}`` containing
        only allowlisted fields whose values differ.

        Returns ``None`` when:
        - either input is ``None``
        - the model has no allowlist entry
        - no allowlisted fields changed
        - inputs cannot be compared (non-model objects)

    Raises
    ------
    TypeError
        If both inputs are valid model instances but belong to
        different model classes.

    Immutability
    ------------
    Neither input instance nor any internal data structure is mutated.
    This function has no side effects and is deterministic.
    """
    # --- None / missing-input guards --------------------------------------
    if old_instance is None or new_instance is None:
        return None

    # --- Validate both inputs have model metadata -------------------------
    old_meta = getattr(old_instance, "_meta", None)
    new_meta = getattr(new_instance, "_meta", None)

    if old_meta is None or new_meta is None:
        return None

    # --- Compare model classes --------------------------------------------
    if old_meta.model != new_meta.model:
        raise TypeError(
            f"Cannot diff mismatched model types: "
            f"{old_meta.label} vs {new_meta.label}"
        )

    # --- Derive model name ------------------------------------------------
    model_name = old_meta.label

    # --- Unknown / unallowlisted model ------------------------------------
    if not get_allowed_fields(model_name):
        return None

    # --- Safe serialize both snapshots (PH10.2) ---------------------------
    old_data = safe_serialize_fields(model_name, old_instance)
    new_data = safe_serialize_fields(model_name, new_instance)

    # --- Detect changes ---------------------------------------------------
    old_changed: dict = {}
    new_changed: dict = {}

    for key in new_data:
        old_val = old_data.get(key)
        new_val = new_data[key]
        if old_val != new_val:
            old_changed[key] = old_val
            new_changed[key] = new_val

    if not old_changed and not new_changed:
        return None

    return {"old": old_changed, "new": new_changed}
