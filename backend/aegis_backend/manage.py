#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # `test` runs against config.settings.test unless the caller says
    # otherwise. Development settings are production-realistic: live
    # PostgreSQL, full-strength password hashing, and a login throttle of
    # 15/min per IP. None of those suit a suite that logs in hundreds of
    # times from one pseudo-IP, and the failure is easy to misread as a real
    # defect. An explicit --settings still wins - Django overwrites
    # DJANGO_SETTINGS_MODULE from the flag.
    if "DJANGO_SETTINGS_MODULE" not in os.environ:
        is_test = len(sys.argv) > 1 and sys.argv[1] == "test"
        os.environ["DJANGO_SETTINGS_MODULE"] = (
            "config.settings.test" if is_test else "config.settings.development"
        )
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
