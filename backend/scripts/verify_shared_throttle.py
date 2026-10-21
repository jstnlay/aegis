"""
Check that the rate limits are shared across processes.

The throttles (login, token refresh, import, export, password change,
registration) run through the default cache. With the local-memory cache each
process keeps its own bucket, so with two workers the login limit is twice
what it says it is. With a shared cache the bucket is one.

This runs the same failed sign-in twice, in two separate processes, against
whatever cache the environment selects, and reports whether the second one
was throttled.

    python scripts/verify_shared_throttle.py

Set ``REDIS_URL`` first to check the shared path; leave it unset to see the
per-process behaviour side by side.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "aegis_backend"

PROBE = """
import os, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
import django
django.setup()
from unittest import mock
from django.conf import settings
from rest_framework.test import APIClient
from core.throttling import LoginRateThrottle

with mock.patch.dict(LoginRateThrottle.THROTTLE_RATES, {"login": "1/min"}):
    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "probe@example.com", "password": "wrong"},
        format="json",
        REMOTE_ADDR="203.0.113.5",
    )
print(response.status_code, settings.CACHES["default"]["BACKEND"])
"""


def run_probe():
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip().splitlines()
    if not output:
        print(result.stderr.strip()[-500:])
        return None, None
    status, backend = output[-1].split(" ", 1)
    return int(status), backend


def main():
    first_status, backend = run_probe()
    second_status, _ = run_probe()

    if first_status is None:
        print("the probe could not run", file=sys.stderr)
        return 1

    print(f"cache backend : {backend}")
    print(f"first process : {first_status}")
    print(f"second process: {second_status}")

    if second_status == 429:
        print("\nThe limit is shared: the second process was throttled by the")
        print("first one's attempt. This is what a multi-worker deployment needs.")
        return 0

    print("\nThe limit is per process: each worker keeps its own bucket, so the")
    print("effective limit is multiplied by the number of workers. Set REDIS_URL")
    print("to share it, or run a single worker.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
