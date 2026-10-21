"""
Health and readiness probe.

A deployment needs one endpoint that answers "is this process able to serve
traffic?" without a token, without a database round-trip per caller, and
without telling an anonymous caller anything about the deployment.

Two states, deliberately:

- ``/api/v1/health/`` — liveness. The process is up. It touches nothing
  outside the process, so a slow or unreachable database does not make the
  orchestrator kill a process that is still healthy.
- ``/api/v1/ready/`` — readiness. The process can serve real requests, which
  means the database answers. This is what a load balancer routes on.

Both report a status and a boolean. Neither reports the database host, the
driver version, the schema version, the exception, or anything else that
would help someone map the deployment.
"""

from django.db import connection
from django.db.utils import OperationalError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle


class HealthRateThrottle(AnonRateThrottle):
    """
    Per-client-IP cap on probe traffic (scope: "health").

    Probes are anonymous and cheap, but they are also the cheapest thing to
    hammer: an unauthenticated endpoint that opens a database connection is
    a denial-of-service amplifier. The rate is generous enough for a probe
    that polls once a second.
    """

    scope = "health"


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([HealthRateThrottle])
def health(request):
    """Liveness: the process is running and serving requests."""
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([HealthRateThrottle])
def ready(request):
    """
    Readiness: the process can reach its database.

    A database that refuses the connection is a 503, so a load balancer stops
    sending traffic here instead of handing requests to a process that would
    fail them.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except OperationalError:
        return Response(
            {"status": "unavailable", "database": False},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"status": "ok", "database": True})
