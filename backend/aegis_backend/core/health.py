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

    Readiness also reports which cache the rate limits are counted in: a
    shared cache, a per-process one, or a shared one that does not answer. A
    misconfigured shared cache is indistinguishable from a working one from
    the outside - every limit is simply not enforced - so it has to be said.
"""

from django.conf import settings
from django.core.cache import cache as default_cache
from django.db import connection
from django.db.utils import OperationalError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle


def cache_round_trips() -> bool:
    """
    Does the configured cache actually store and return a value?

    The rate limits live in the cache, and the Redis client is configured to
    treat an unreachable cache as an empty one instead of failing the request.
    That is right for an outage and wrong for a misconfiguration: an empty
    cache looks exactly like a cache that works and enforces nothing. A
    deployment with a bad REDIS_URL then passes every health check while its
    login limit, import limit and export limit are all off.

    One round-trip says which of the two it is.
    """
    key = "aegis:ready:cache"
    try:
        default_cache.set(key, "ok", 30)
        return default_cache.get(key) == "ok"
    except Exception:
        return False


def cache_mode() -> str:
    """
    Which cache the rate limits are counted in: "shared", "local" or "broken".

    The three states need three different answers, and a boolean cannot tell
    them apart:

    - "shared"  - a shared cache is configured and answers. One limit for the
      whole deployment, whatever the worker count.
    - "local"   - the per-process cache is in use. Every limit is multiplied
      by the number of workers, and the deployment has no shared history.
    - "broken"  - a shared cache is configured but does not answer. The
      client treats it as empty, so no limit is enforced at all.

    It names a topology, not a host, a port or a credential.
    """
    if not getattr(settings, "REDIS_URL", ""):
        return "local"
    return "shared" if cache_round_trips() else "broken"


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
    Readiness: the process can reach its database, and its cache works.

    A database that refuses the connection is a 503, so a load balancer stops
    sending traffic here instead of handing requests to a process that would
    fail them.

    The cache is reported but not enforced. A dead cache does not make the
    process unable to serve requests - the limits are simply not being
    counted - so it must not take the instance out of rotation. It is
    reported because "the limits are silently off" is worth knowing about.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except OperationalError:
        return Response(
            {"status": "unavailable", "database": False, "cache": cache_mode()},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {"status": "ok", "database": True, "cache": cache_mode()}
    )
