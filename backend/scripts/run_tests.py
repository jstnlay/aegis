"""
Run the backend test suite against the test settings, every time.

Why this exists
---------------
``manage.py test`` now selects ``config.settings.test`` on its own, but that
default only covers the ``manage.py`` entry point. A ``django-admin test``, a
CI job writing its own command, or a shell that already exports
``DJANGO_SETTINGS_MODULE`` all bypass it and fall back to development settings.
Development settings are production-realistic, and every part of that is wrong
for a suite like this one:

* PostgreSQL instead of in-memory SQLite, so a run needs a live database and
  a ``--keepdb`` database can drift out of step with the migrations.
* Password hashing at Django's full 1,500,000 PBKDF2 iterations. The fixtures
  build users per test, measured near 1.76s per hash, which pushes a full run
  past two hours.
* A login throttle of 15/min per client IP. The suite logs in hundreds of
  times from one pseudo-IP, so past the 15th login every request returns 429.

That last one is the dangerous one, because it does not look like a rate
limit. ``audit_successful_logout()`` wraps ``record_audit()`` in
``except Exception``, so a 429 raised during login surfaces further down as a
*missing AuditLog row*, and the failing set moves between runs as the budget
is spent in a different place. It cost a full afternoon to trace once.

This script makes that state unreachable: it sets the settings module in the
environment before Django starts, so no entry point can select anything else.

    python scripts/run_tests.py                    # whole suite
    python scripts/run_tests.py apps.audit         # one app
    python scripts/run_tests.py apps.audit core -v 2

Any argument is passed straight through to ``manage.py test``.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "aegis_backend"

TEST_SETTINGS = "config.settings.test"


def main(argv):
    argv = list(argv)
    if not any(arg.startswith("--settings") for arg in argv):
        argv += [f"--settings={TEST_SETTINGS}"]

    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = TEST_SETTINGS

    command = [sys.executable, "manage.py", "test", *argv]
    print(f"$ DJANGO_SETTINGS_MODULE={TEST_SETTINGS} manage.py test {' '.join(argv)}")
    return subprocess.call(command, cwd=str(BACKEND), env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
