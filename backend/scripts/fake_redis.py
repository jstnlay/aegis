"""
A Redis stand-in for local development.

The rate limits (login, token refresh, import, export, password change,
registration) run through the default cache. With more than one worker the
local-memory cache gives each worker its own bucket, so the limits are
multiplied by the number of workers. A shared Redis fixes that; this script
provides one on the machine that is developing, so the shared-cache path can
be exercised without installing a Redis service.

`fakeredis` speaks the Redis protocol, so `django-redis` talks to it exactly
as it would to a real Redis. The data lives in memory and is lost when the
script stops.

    python scripts/fake_redis.py            # serves on 127.0.0.1:6379
    python scripts/fake_redis.py 6380       # another port

Then point the backend at it:

    REDIS_URL=redis://127.0.0.1:6379/0

This is a development tool. It is not in the runtime requirements, and it is
not a substitute for a real Redis in production: a stand-in on one machine
still shares nothing with a second machine.
"""

import sys


def main():
    try:
        from fakeredis import TcpFakeServer
    except ImportError:
        print(
            "fakeredis is not installed. It is a development-only dependency:\n"
            "    pip install -r requirements/development.txt",
            file=sys.stderr,
        )
        return 1

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 6379
    server = TcpFakeServer(("127.0.0.1", port), server_type="redis")
    print(f"fake redis on 127.0.0.1:{port} — ctrl-c to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
