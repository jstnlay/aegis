"""
Audit trail domain model (PH10.1).

AuditLog stores evidence of system-wide activities and administrative
actions.  The schema follows §E.9 of BACKEND_SPECIFICATION.md exactly
where the specification is prescriptive.

Field semantics:

- ``user``: NULL represents system-generated events (background tasks,
  scheduled computations, AI-generated consequential state changes).
- ``action``: Exactly the 8 specification-defined values.  No extensions.
- ``object_id``: UUIDField — an IMPLEMENTATION DECISION aligned with the
  repository-wide UUID primary key pattern.  The specification defines a
  generic nullable object identifier; UUID is our concrete choice.
- ``object_repr``: Bounded to 255 chars.  Intentionally does NOT use
  model ``__str__()`` to avoid PII leakage.  Will be populated as
  ``<model_name>:<UUID>`` for domain objects and ``Login`` / ``Logout``
  for authentication events.
- ``changes``: Flat ``{"old": {...}, "new": {...}}`` diff of changed
  allowlisted fields.  NULL for actions without diffs (LOGIN, EXPORT).
- ``ip_address``: Nullable.  Captured from ``REMOTE_ADDR`` only — no
  ``X-Forwarded-For`` trust.
- ``user_agent``: Nullable free text.
- ``timestamp``: The only AuditLog timestamp.  No ``created_at`` field.

Immutability: AuditLog records are append-only.  The Admin interface
and the future API will be read-only.  No update/delete API endpoint
is planned.
"""

import uuid

from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models


class AuditLog(models.Model):
    """
    Immutable evidence record of a system-wide activity or
    administrative action.

    Schema source: §E.9 BACKEND_SPECIFICATION.md v2.1.
    """

    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        IMPORT = "import", "Import"
        EXPORT = "export", "Export"
        ACCESS = "access", "Access"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text="Authenticated actor. NULL = system/background event.",
    )

    action = models.CharField(
        max_length=15,
        choices=Action.choices,
    )

    model_name = models.CharField(
        max_length=100,
        help_text="Django app_label.model_name, e.g. 'academics.Grade'.",
    )

    # Implementation decision: UUIDField to match repository-wide UUID PKs.
    # The specification defines a generic nullable object identifier.
    object_id = models.UUIDField(
        null=True,
        blank=True,
    )

    object_repr = models.CharField(
        max_length=255,
        validators=[MaxLengthValidator(255)],
        help_text="Stable, bounded, PII-free human identification string.",
    )

    changes = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text='Flat {"old": {...}, "new": {...}} diff of changed allowlisted fields.',
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Client IP from REMOTE_ADDR. NULL when unavailable.",
    )

    user_agent = models.TextField(
        null=True,
        blank=True,
        default=None,
        help_text="Browser/device user-agent string. Optional.",
    )

    timestamp = models.DateTimeField(
        help_text="Event timestamp. The only AuditLog datetime field.",
    )

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "audit log"
        verbose_name_plural = "audit logs"
        indexes = [
            models.Index(fields=["user"], name="audit_user_idx"),
            models.Index(fields=["model_name"], name="audit_model_name_idx"),
            models.Index(fields=["timestamp"], name="audit_timestamp_idx"),
            models.Index(fields=["action"], name="audit_action_idx"),
        ]

    def __str__(self):
        actor = self.user_id or "system"
        return f"[{self.action}] {self.model_name} by {actor} at {self.timestamp}"
