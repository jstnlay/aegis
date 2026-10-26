"""
Production settings checks.

The production settings module refuses to load without an explicit Host
allow-list or a real secret key, because both defaults are wrong in opposite
directions: an empty list takes the API down and "*" accepts any Host header,
which is how a Host-header injection reaches the application; a short or
auto-generated secret key signs everything Django signs and is guessable. A
deployment mistake should be a start-up failure, not a running service
answering on an unknown host with a guessable key.
"""

import importlib
import os
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from decouple import UndefinedValueError


#: A secret key that satisfies production.py's rule (>=50 chars, more than
#: four distinct characters, not a ``django-insecure-`` key). Tests that are
#: not about the secret key use it so they exercise their own rule rather
#: than whatever key the machine running the suite happens to have.
VALID_SECRET_KEY = (
    "k3Qm9Zt7Xp2Lv8Nc4Rb6Wd1Hy5Jf0Sg7Ua3Ee9Ir2Ow5Qt8Yv3Nq6Px1Md4Ch8"
)  # noqa: S105

#: A host allow-list that satisfies production.py's rule.
VALID_ALLOWED_HOSTS = "aegis.example.com"


def _valid_environment():
    """The smallest environment production.py accepts."""
    return {
        "DJANGO_SECRET_KEY": VALID_SECRET_KEY,
        "DJANGO_ALLOWED_HOSTS": VALID_ALLOWED_HOSTS,
    }


def _production_module(environment=None):
    """
    Import ``config.settings.production`` against a known environment.

    The module validates its configuration while it is being imported, so
    importing it under the ambient environment only works on a machine that
    happens to be production-shaped. CI is not: there is no ``.env``, and
    the ``DJANGO_SECRET_KEY`` the backend job sets to boot ``base.py`` is
    deliberately a throwaway. Importing under that environment raised
    ``ImproperlyConfigured`` before the first assertion ran, which is why
    every test in this module failed on CI while passing locally.

    Passing the environment in makes each test independent of the machine it
    runs on, and makes the value in the patch the only thing that decides the
    outcome.
    """
    with mock.patch.dict(os.environ, environment or _valid_environment()):
        return importlib.import_module("config.settings.production")


def _reload_production_module(environment):
    """
    Reload the module so its import-time guards run again.

    The reload has to happen inside the patch: ``_production_module`` returns
    after its own context manager has already exited, so reloading the value
    it returned would re-run the guards against the ambient environment and
    defeat the test.
    """
    with mock.patch.dict(os.environ, environment):
        return importlib.reload(importlib.import_module("config.settings.production"))


def _restore_production_module():
    """
    Reload the production settings module against the real environment.

    A reload can legitimately fail on a machine whose own environment is not
    production-shaped (a short secret key, no host allow-list). That is the
    module refusing to start, which is the behaviour under test, not a test
    failure, so the restore is best-effort. ``UndefinedValueError`` is caught
    alongside ``ImproperlyConfigured`` because the test settings module,
    which base.py belongs to, reads ``DJANGO_SECRET_KEY`` with no default:
    with no ``.env`` and no environment variable, the reload cannot even
    reach production.py's own guard.
    """
    try:
        importlib.reload(_production_module())
    except (ImproperlyConfigured, UndefinedValueError):
        pass


class ProductionHostAllowListTests(SimpleTestCase):
    """``DJANGO_ALLOWED_HOSTS`` is required in production."""

    def tearDown(self):
        _restore_production_module()

    def test_missing_allowed_hosts_refuses_to_start(self):
        with self.assertRaises(ImproperlyConfigured):
            _reload_production_module(
                {"DJANGO_ALLOWED_HOSTS": "", "DJANGO_SECRET_KEY": VALID_SECRET_KEY}
            )

    def test_configured_allowed_hosts_are_used(self):
        reloaded = _reload_production_module(
            {
                "DJANGO_ALLOWED_HOSTS": "aegis.example.com",
                "DJANGO_SECRET_KEY": VALID_SECRET_KEY,
            }
        )

        self.assertEqual(reloaded.ALLOWED_HOSTS, ["aegis.example.com"])


class ProductionSecretKeyTests(SimpleTestCase):
    """``DJANGO_SECRET_KEY`` must be a real secret in production."""

    def tearDown(self):
        _restore_production_module()

    def test_weak_secret_key_refuses_to_start(self):
        with self.assertRaises(ImproperlyConfigured):
            _reload_production_module(
                {
                    "DJANGO_SECRET_KEY": "short-key",
                    "DJANGO_ALLOWED_HOSTS": VALID_ALLOWED_HOSTS,
                }
            )

    def test_auto_generated_secret_key_refuses_to_start(self):
        insecure = "django-insecure-" + ("a1b2c3d4e5" * 6)

        with self.assertRaises(ImproperlyConfigured):
            _reload_production_module(
                {
                    "DJANGO_SECRET_KEY": insecure,
                    "DJANGO_ALLOWED_HOSTS": VALID_ALLOWED_HOSTS,
                }
            )

    def test_strong_secret_key_is_accepted(self):
        reloaded = _reload_production_module(
            {
                "DJANGO_SECRET_KEY": VALID_SECRET_KEY,
                "DJANGO_ALLOWED_HOSTS": VALID_ALLOWED_HOSTS,
            }
        )

        self.assertEqual(reloaded.SECRET_KEY, VALID_SECRET_KEY)
