"""
The address of the client, for the two places that need one.

Two different questions are asked of a request, and they have different trust
answers.

**The audit trail records who acted.** It must not record a value the actor
chose, so the forwarded chain is never used: ``X-Forwarded-For`` is a header
the client writes, and the audit ignores it (there are tests for that). The
one forwarded value used is the CDN's own client-IP header, which the CDN
overwrites on every request it forwards, so it names the client rather than
whatever the client claimed.

**A rate limit needs a bucket per client.** Behind a proxy the socket
address is the proxy's, and one proxy serves every client, so the last
forwarded hop is used when there is no CDN header - it is the address the
outermost proxy observed.

Both fall back to the socket address, which is always present and is the only
value nobody can choose.

The CDN header is trusted because the deployment's public URL is served
through Cloudflare, which writes it. The origin is also reachable directly,
without the CDN, and a direct request can set that header itself - so this
is best-effort against an actor who bypasses the CDN, and the socket address
remains the value that cannot be chosen.
"""

#: The header Cloudflare writes on every request it forwards to an origin. It
#: names the client as Cloudflare sees it and is overwritten on every request.
CDN_CLIENT_IP_HEADER = "HTTP_CF_CONNECTING_IP"


def client_address(request) -> str:
    """
    The client address, for the audit trail.

    The CDN's client-IP header when the request came through the CDN,
    otherwise the socket address. The forwarded chain is deliberately not
    consulted: it is written by the client.
    """
    value = request.META.get(CDN_CLIENT_IP_HEADER)
    if value:
        return value.strip()
    return request.META.get("REMOTE_ADDR", "")


def throttle_identity(request) -> str:
    """
    The bucket key for a rate limit.

    The CDN's client-IP header first, then the last forwarded hop - the
    address the outermost proxy observed - then the socket address.
    """
    value = request.META.get(CDN_CLIENT_IP_HEADER)
    if value:
        return value.strip()

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]

    return request.META.get("REMOTE_ADDR", "")
