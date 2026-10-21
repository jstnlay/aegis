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


def _production_module():
    return importlib.import_module("config.settings.production")


def _restore_production_module():
    """
    Reload the production settings module against the real environment.

    A reload can legitimately fail on a machine whose own environment is not
    production-shaped (a short secret key, no host allow-list). That is the
    module refusing to start, which is the behaviour under test, not a test
    failure, so the restore is best-effort.
    """
    try:
        importlib.reload(_production_module())
    except ImproperlyConfigured:
        pass


class ProductionHostAllowListTests(SimpleTestCase):
    """``DJANGO_ALLOWED_HOSTS`` is required in production."""

    def tearDown(self):
        _restore_production_module()

    def test_missing_allowed_hosts_refuses_to_start(self):
        production = _production_module()

        with mock.patch.dict(os.environ, {"DJANGO_ALLOWED_HOSTS": ""}):
            with self.assertRaises(ImproperlyConfigured):
                importlib.reload(production)

    def test_configured_allowed_hosts_are_used(self):
        production = _production_module()

        with mock.patch.dict(
            os.environ, {"DJANGO_ALLOWED_HOSTS": "aegis.example.com"}
        ):
            reloaded = importlib.reload(production)

        self.assertEqual(reloaded.ALLOWED_HOSTS, ["aegis.example.com"])


class ProductionSecretKeyTests(SimpleTestCase):
    """``DJANGO_SECRET_KEY`` must be a real secret in production."""

    def tearDown(self):
        _restore_production_module()

    def test_weak_secret_key_refuses_to_start(self):
        production = _production_module()

        with mock.patch.dict(os.environ, {"DJANGO_SECRET_KEY": "short-key"}):
            with self.assertRaises(ImproperlyConfigured):
                importlib.reload(production)

    def test_auto_generated_secret_key_refuses_to_start(self):
        production = _production_module()
        insecure = "django-insecure-" + ("a1b2c3d4e5" * 6)

        with mock.patch.dict(os.environ, {"DJANGO_SECRET_KEY": insecure}):
            with self.assertRaises(ImproperlyConfigured):
                importlib.reload(production)

    def test_strong_secret_key_is_accepted(self):
        production = _production_module()
        strong = (
            "k3Qm9Zt7Xp2Lv8Nc4Rb6Wd1Hy5Jf0Sg7Ua3Ee9Ir2Ow5Qt8Yv3Nq6Px1Md4Ch8"
        )  # noqa: S105

        with mock.patch.dict(os.environ, {"DJANGO_SECRET_KEY": strong}):
            reloaded = importlib.reload(production)

        self.assertEqual(reloaded.SECRET_KEY, strong)
