"""
PH10.10 — Read-only administrator AuditLog API.

    Authenticated admin
        |
        v
    AuditLogViewSet   (core.permissions.IsAdminUser)
        |
        v
    safe, read-only AuditLog queryset   (select_related "user")
        |
        v
    AuditLogSerializer                  (sanitized read representation)
        |
        v
    paginated response

Scope
-----
The API is READ-ONLY.  It exposes exactly two operations — list and
retrieve of ``AuditLog`` records — for users whose ``role == "admin"``:

    GET /api/v1/audit/logs/
    GET /api/v1/audit/logs/{id}/

Mutation is impossible by construction: the ViewSet restricts
``http_method_names`` to GET / HEAD / OPTIONS (the DefaultRouter maps no
POST / PUT / PATCH / DELETE routes), the serializer is fully read-only,
and nothing here writes.  ``AuditLog`` creation remains exclusively in
``services.record_audit`` (PH10.4).

Privacy and safety
------------------
- ``changes`` is exposed exactly as stored (already PH10.2/PH10.3-safe);
  it is never re-serialized or dereferenced back into live objects.
- ``object_id`` / ``object_repr`` are returned as stored; the target
  object is never fetched, so audit records for deleted targets remain
  readable.
- The actor is exposed as a minimal ``{"id", "name"}`` identity only.
- Requests map to a closed whitelist of metadata filters; no arbitrary
  field filtering, no searching inside ``changes``, no arbitrary client
  ordering.  Response ordering is fixed (``-timestamp`` then ``-id``).
"""

import uuid

from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from core.pagination import StandardResultsPagination
from core.permissions import IsAdminUser

from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer

#: ``AuditLog.pk`` is a UUID.  Restricting the router lookup to UUID
#: syntax means malformed IDs never reach the queryset (they 404 at the
#: URL layer) and only valid-but-missing UUIDs produce the standard 404.
_UUID_LOOKUP = (
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _parse_uuid_param(name, raw):
    """Parse a UUID query parameter, rejecting malformed values (400)."""
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError):
        raise ValidationError({name: "Must be a valid UUID."})


def _parse_datetime_param(name, raw):
    """Parse an ISO-8601 datetime query parameter, rejecting garbage (400)."""
    parsed = parse_datetime(raw)
    if parsed is None:
        raise ValidationError({name: "Must be a valid ISO-8601 datetime."})
    return parsed


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve AuditLog records.  Administrators only.

    Permission behavior:

    - admin           -> allowed
    - faculty/guidance/student/parent -> forbidden (403)
    - anonymous       -> authentication required (401)

    Filters (all optional, all bounded): ``action``, ``model_name``,
    ``user``, ``object_id``, ``search`` (model_name / object_repr only),
    ``start_time`` / ``end_time`` (ISO-8601 datetime range).
    """

    permission_classes = [IsAdminUser]
    serializer_class = AuditLogSerializer
    pagination_class = StandardResultsPagination
    lookup_value_regex = _UUID_LOOKUP

    # GET / HEAD / OPTIONS only — no POST / PUT / PATCH / DELETE routes.
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        """Read-only AuditLog queryset with bounded metadata filters.

        ``select_related("user")`` avoids an N+1 on the actor per row.
        Ordering is fixed: newest first, then ``id`` descending for a
        deterministic tie-break.  No client-supplied ordering is allowed.
        """
        queryset = (
            AuditLog.objects.select_related("user")
            .order_by("-timestamp", "-id")
        )

        params = self.request.query_params

        action = params.get("action")
        if action:
            queryset = queryset.filter(action=action)

        model_name = params.get("model_name")
        if model_name:
            queryset = queryset.filter(model_name=model_name)

        user = params.get("user")
        if user:
            queryset = queryset.filter(user_id=_parse_uuid_param("user", user))

        object_id = params.get("object_id")
        if object_id:
            queryset = queryset.filter(
                object_id=_parse_uuid_param("object_id", object_id)
            )

        # Safe metadata search only: model_name / object_repr.  Searching
        # inside serialized ``changes`` is intentionally not supported.
        search = params.get("search")
        if search:
            queryset = queryset.filter(
                Q(model_name__icontains=search) | Q(object_repr__icontains=search)
            )

        start_time = params.get("start_time")
        if start_time:
            queryset = queryset.filter(
                timestamp__gte=_parse_datetime_param("start_time", start_time)
            )

        end_time = params.get("end_time")
        if end_time:
            queryset = queryset.filter(
                timestamp__lte=_parse_datetime_param("end_time", end_time)
            )

        return queryset