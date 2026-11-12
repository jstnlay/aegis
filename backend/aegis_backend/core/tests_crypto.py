"""
Tests for field-level encryption of student free text.

What matters is not that the bytes changed — it is that the application still
sees the plain text, that the column does not, and that a deployment without a
key cannot start.
"""

import base64
import secrets

from django.core.checks import Error
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from apps.chatbot import checks
from core import crypto
from core.crypto import ALGORITHM, decrypt, encrypt, is_enabled, is_encrypted


def _key(seed: int = 1) -> str:
    """A deterministic 64-byte key, base64-encoded, for the tests."""
    return base64.b64encode(secrets.token_bytes(64)).decode("ascii")


class CryptoTest(TestCase):
    def test_without_a_key_nothing_is_encrypted(self):
        with override_settings(FIELD_ENCRYPTION_KEYS="", FIELD_ENCRYPTION_KEY=""):
            self.assertFalse(is_enabled())
            self.assertEqual(encrypt("hello"), "hello")
            self.assertEqual(decrypt("hello"), "hello")

    def test_with_a_key_the_value_changes_and_reads_back(self):
        with override_settings(FIELD_ENCRYPTION_KEYS=f"k1:{_key()}"):
            token = encrypt("I want to hurt myself")
            self.assertTrue(is_encrypted(token))
            self.assertNotIn("hurt myself", token)
            self.assertEqual(decrypt(token), "I want to hurt myself")

    def test_the_same_text_encrypts_the_same_way(self):
        """Determinism is what keeps an equality lookup working."""
        with override_settings(FIELD_ENCRYPTION_KEYS=f"k1:{_key()}"):
            self.assertEqual(encrypt("same"), encrypt("same"))

    def test_a_second_key_cannot_read_the_first(self):
        with override_settings(FIELD_ENCRYPTION_KEYS=f"k1:{_key(1)}"):
            token = encrypt("private")
        with override_settings(FIELD_ENCRYPTION_KEYS=f"k2:{_key(2)}"):
            with self.assertRaises(ImproperlyConfigured):
                decrypt(token)

    def test_an_old_key_still_reads_after_a_rotation(self):
        """Rotation: add a key, deploy, drop the old one later."""
        old = _key(1)
        new = _key(2)
        with override_settings(FIELD_ENCRYPTION_KEYS=f"k1:{old}"):
            token = encrypt("written before the rotation")
        with override_settings(FIELD_ENCRYPTION_KEYS=f"k2:{new},k1:{old}"):
            self.assertEqual(decrypt(token), "written before the rotation")

    def test_the_new_key_is_used_for_writes(self):
        old = _key(1)
        new = _key(2)
        with override_settings(FIELD_ENCRYPTION_KEYS=f"k1:{old},k2:{new}"):
            token = encrypt("after the rotation")
        self.assertTrue(token.startswith("enc1:k1:"))

    def test_a_malformed_key_is_refused(self):
        with override_settings(FIELD_ENCRYPTION_KEYS="k1:not-base64!"):
            with self.assertRaises(ImproperlyConfigured):
                crypto.key_pairs()

    def test_a_short_key_is_refused(self):
        short = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        with override_settings(FIELD_ENCRYPTION_KEYS=f"k1:{short}"):
            with self.assertRaises(ImproperlyConfigured):
                crypto.key_pairs()

    def test_a_malformed_entry_is_refused(self):
        with override_settings(FIELD_ENCRYPTION_KEYS="no-colon-here"):
            with self.assertRaises(ImproperlyConfigured):
                crypto.key_pairs()

    def test_status_never_returns_a_key(self):
        key = _key()
        with override_settings(FIELD_ENCRYPTION_KEYS=f"k1:{key}"):
            state = crypto.status()
        self.assertTrue(state["enabled"])
        self.assertEqual(state["algorithm"], ALGORITHM)
        self.assertEqual(state["key_count"], 1)
        self.assertNotIn(key, repr(state))


class DeploymentCheckTest(TestCase):
    def test_a_deployment_that_requires_encryption_refuses_without_a_key(self):
        with override_settings(
            FIELD_ENCRYPTION_REQUIRED=True,
            FIELD_ENCRYPTION_KEYS="",
            FIELD_ENCRYPTION_KEY="",
        ):
            errors = checks.check_field_encryption(None)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], Error)
        self.assertEqual(errors[0].id, "chatbot.E001")

    def test_a_deployment_with_a_key_passes(self):
        with override_settings(
            FIELD_ENCRYPTION_REQUIRED=True,
            FIELD_ENCRYPTION_KEYS=f"k1:{_key()}",
            FIELD_ENCRYPTION_KEY="",
        ):
            self.assertEqual(checks.check_field_encryption(None), [])

    def test_a_development_deployment_is_not_blocked(self):
        with override_settings(
            FIELD_ENCRYPTION_REQUIRED=False,
            FIELD_ENCRYPTION_KEYS="",
            FIELD_ENCRYPTION_KEY="",
        ):
            self.assertEqual(checks.check_field_encryption(None), [])

    def test_the_check_is_actually_registered(self):
        """
        Django does not import an app's checks module for you.

        A check that is written but never registered is a check that never
        runs, and the deployment would start without a key while the code
        reads as though it could not.
        """
        from django.core.checks import registry

        with override_settings(
            FIELD_ENCRYPTION_REQUIRED=True,
            FIELD_ENCRYPTION_KEYS="",
            FIELD_ENCRYPTION_KEY="",
        ):
            errors = [
                error for error in registry.run_checks() if error.id == "chatbot.E001"
            ]
        self.assertEqual(len(errors), 1)
