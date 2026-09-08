"""
Audit serializers.

- Backwards-compatible diff entry-point (PH10.2 public API): delegates to
  the canonical ``diff.compute_diff`` (PH10.3) after validating the
  explicit ``model_name`` parameter that callers supplied in PH10.2.

  New code should prefer ``diff.compute_diff`` which derives the model
  name automatically from instance metadata.

- PH10.10 read-only ``AuditLogSerializer`` for the administrator audit
  API: exposes the already-PH10.2-safe audit representation without ever
  reconstructing sensitive data from related objects.
"""

from rest_framework import serializers

from apps.audit.diff import compute_diff
from apps.audit.models import AuditLog


def compute_changes(model_name: str, old_instance, new_instance) -> dict | None:
    """Compute the safe diff between two model snapshots.

    This is a thin backwards-compatible wrapper around
    :func:`~apps.audit.diff.compute_diff`.  It validates the caller-supplied
    *model_name* against the actual model label derived from the instances
    before delegating.

    Parameters
    ----------
    model_name : str
        ``app_label.ModelName`` matching ``AuditLog.model_name``.
    old_instance : Model or None
        The model instance *before* the change.
    new_instance : Model or None
        The model instance *after* the change.

    Returns
    -------
    dict or None
        ``{"old": {field: value}, "new": {field: value}}`` containing
        only allowlisted fields whose values differ.  ``None`` when
        nothing changed or the model has no allowlist entry.

    Raises
    ------
    ValueError
        If either *old_instance* or *new_instance* is a valid model but
        its actual model label does not match the supplied *model_name*.

    See Also
    --------
    diff.compute_diff : The canonical interface that derives model_name
        from instance metadata.
    """
    if old_instance is not None and new_instance is not None:
        old_meta = getattr(old_instance, "_meta", None)
        new_meta = getattr(new_instance, "_meta", None)
        if old_meta is not None and new_meta is not None:
            actual_label = old_meta.label
            new_actual_label = new_meta.label
            if actual_label != new_actual_label:
                raise TypeError(
                    f"Mismatched model types: {actual_label} vs {new_actual_label}"
                )
            if model_name != actual_label:
                raise ValueError(
                    f"model_name '{model_name}' does not match actual model '{actual_label}'"
                )

    return compute_diff(old_instance, new_instance)


# ---------------------------------------------------------------------------
# PH10.10 — Read-only AuditLog representation (administrator API)
# ---------------------------------------------------------------------------


class AuditLogSerializer(serializers.ModelSerializer):
    """Read-only representation of one AuditLog record.

    Exposes only the fields an administrator needs to inspect the audit
    trail: who performed the event, what model/object was involved, the
    action and timestamp, the PH10.2-safe ``changes`` diff, and the stored
    request metadata.

    Safety guarantees:

    - Fully read-only: every field is ``read_only``, so this serializer
      can never create, update, or delete an ``AuditLog`` row.
    - ``changes`` is returned exactly as stored — the PH10.2/PH10.3-safe
      diff.  It is never re-serialized, deserialized, or dereferenced back
      into live domain objects.
    - ``object_id`` / ``object_repr`` are returned exactly as stored; the
      target object is never fetched, so records for deleted objects stay
      readable.
    - ``user`` exposes only the minimal safe identity (id + display name),
      never password hashes, tokens, or profile data.
    """

    user = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "timestamp",
            "user",
            "action",
            "model_name",
            "object_id",
            "object_repr",
            "changes",
            "ip_address",
            "user_agent",
        )
        read_only_fields = fields

    def get_user(self, obj):
        """Minimal safe actor identity, or None for system events.

        Matches the repository's established admin representation
        (``data_import`` jobs): ``{"id", "name"}``.  No password, hash,
        token, secret, or extended profile data is ever included.
        """
        user = obj.user
        if user is None:
            return None
        return {
            "id": str(user.pk),
            "name": user.get_full_name() or user.email,
        }
