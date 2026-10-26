#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def _is_test_run(argv):
    """True when this invocation is ``manage.py test``."""
    args = [arg for arg in argv[1:] if not arg.startswith("-")]
    return bool(args) and args[0] == "test"


def _requested_settings(argv):
    """The settings module named on the command line, if any."""
    for index, arg in enumerate(argv):
        if arg.startswith("--settings="):
            return arg.split("=", 1)[1]
        if arg == "--settings" and index + 1 < len(argv):
            return argv[index + 1]
    return None


TEST_SETTINGS = "config.settings.test"
DEVELOPMENT_SETTINGS = "config.settings.development"

# The suite logs in hundreds of times from one client IP, so it needs a login
# throttle it cannot exhaust. Development settings cap login at 15/min and
# hash passwords at Django's full 1,500,000 PBKDF2 iterations, which turns a
# 30-second run into a two-hour one.
TEST_SETTINGS_HINT = (
    "Run the suite as `python scripts/run_tests.py`, or with "
    "`manage.py test --settings=config.settings.test`."
)


def _configure_settings(argv):
    """
    Choose the settings module, and refuse a test run pointed elsewhere.

    `test` defaults to the test settings. An explicit `--settings` wins, as
    it does in Django, but when that explicit value is not the test settings
    the run is about to behave in a way that does not look like a
    configuration mistake: login returns 429 past the 15th request from one
    IP, `audit_successful_logout()` swallows that exception, and the test
    reports a *missing AuditLog row* instead of an HTTP error. The failing
    set then moves between runs. Naming the cause here is the whole point of
    this function.
    """
    requested = _requested_settings(argv)
    if requested is not None:
        if _is_test_run(argv) and requested != TEST_SETTINGS:
            raise SystemExit(
                f"Refusing to run tests with --settings={requested}.\n"
                f"{TEST_SETTINGS_HINT}"
            )
        os.environ["DJANGO_SETTINGS_MODULE"] = requested
        return

    if "DJANGO_SETTINGS_MODULE" in os.environ:
        selected = os.environ["DJANGO_SETTINGS_MODULE"]
        if _is_test_run(argv) and selected != TEST_SETTINGS:
            raise SystemExit(
                f"Refusing to run tests with DJANGO_SETTINGS_MODULE={selected}.\n"
                f"{TEST_SETTINGS_HINT}"
            )
        return

    os.environ["DJANGO_SETTINGS_MODULE"] = (
        TEST_SETTINGS if _is_test_run(argv) else DEVELOPMENT_SETTINGS
    )


def main():
    """Run administrative tasks."""
    _configure_settings(sys.argv)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
