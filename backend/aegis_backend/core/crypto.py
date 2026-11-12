"""
Field-level encryption for student free text.

What this protects
------------------
The chatbot tables hold what a student actually typed: the message, the
assistant's reply, the flag summary a counselor reads first, and the private
case notes. With disk-level encryption that is a deployment decision nobody
here can make. With *this*, the ciphertext is what sits in the column, so a
database dump, a backup, a `SELECT` from a compromised reporting replica or a
copy of the Postgres volume does not hand over a student's disclosure in
plain text.

The algorithm
-------------
AES-SIV (RFC 5297) through ``cryptography``'s ``AESSIV``, with a 64-byte key
(two 256-bit keys: one for the synthetic IV, one for the encryption).

SIV rather than plain AES-GCM for one reason: **SIV is deterministic.** The
same plaintext encrypts to the same ciphertext, so ``filter(message="...")``
still works. A randomised mode would make every lookup on an encrypted column
impossible, and the codebase looks up flags by the message a student sent.

The cost of determinism is the one honest caveat: two identical messages
encrypt to identical ciphertexts, so an attacker with the database can count
repeats. For student free text that is a smaller risk than a plaintext dump,
and it is stated here rather than discovered later.

Key handling
------------
Keys live in the environment, never in the database:

    FIELD_ENCRYPTION_KEYS=kid1:base64key,kid2:base64key

The first entry encrypts; every entry decrypts. That is what makes a rotation
possible: add a new key, deploy, then drop the old one once nothing is
encrypted with it any more. ``FIELD_ENCRYPTION_KEY`` is the single-key
shortcut and is treated as the key id ``default``.

With no key configured the functions are a no-op: the value is stored as it
is. That keeps development and the test suite working, and it is never silent
in production — ``apps.chatbot.checks`` refuses to start a production
deployment without a key when ``FIELD_ENCRYPTION_REQUIRED`` is on, and the
administrator console says whether encryption is on.
"""

from __future__ import annotations

import base64
import binascii
import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

#: Version tag on every ciphertext. A future format change bumps it, and old
#: ciphertext keeps its own tag so it can still be read.
TOKEN_PREFIX = "enc1:"

#: The algorithm name, for the administrator console and the docs.
ALGORITHM = "AES-SIV-512"

#: Key length in bytes. AES-SIV needs 512 bits (two 256-bit keys).
KEY_BYTES = 64

_cipher_cls = None


def _aessiv():
    """The cipher class, imported lazily so the SDK stays optional."""
    global _cipher_cls
    if _cipher_cls is None:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESSIV
        except Exception as exc:  # pragma: no cover - depends on install
            raise ImproperlyConfigured(
                "The 'cryptography' package is required for field encryption. "
                "Run pip install -r requirements/base.txt."
            ) from exc
        _cipher_cls = AESSIV
    return _cipher_cls


def _decode_key(encoded: str) -> bytes:
    try:
        raw = base64.b64decode(encoded.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImproperlyConfigured(
            "A field encryption key is not valid base64."
        ) from exc
    if len(raw) != KEY_BYTES:
        raise ImproperlyConfigured(
            f"A field encryption key must be {KEY_BYTES} bytes "
            f"({KEY_BYTES * 8} bits), got {len(raw)}. Generate one with "
            "'manage.py generate_encryption_key'."
        )
    return raw


def key_pairs() -> list[tuple[str, bytes]]:
    """
    Every configured key as ``(key_id, key_bytes)``.

    The first entry is the one used for writes. The order is the order the
    operator wrote them in, which is what makes "add a new key, deploy, drop
    the old one" work.
    """
    pairs: list[tuple[str, bytes]] = []

    raw = str(getattr(settings, "FIELD_ENCRYPTION_KEYS", "") or "")
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        key_id, separator, encoded = item.partition(":")
        if not separator or not key_id.strip():
            raise ImproperlyConfigured(
                "FIELD_ENCRYPTION_KEYS entries must look like 'key_id:base64key'."
            )
        pairs.append((key_id.strip(), _decode_key(encoded)))

    single = str(getattr(settings, "FIELD_ENCRYPTION_KEY", "") or "").strip()
    if single:
        if not any(key_id == "default" for key_id, _ in pairs):
            pairs.append(("default", _decode_key(single)))

    return pairs


def is_enabled() -> bool:
    """Is field encryption actually on?"""
    try:
        return bool(key_pairs())
    except ImproperlyConfigured:
        return False


def is_encrypted(value) -> bool:
    """Does this value look like something we encrypted?"""
    return isinstance(value, str) and value.startswith(TOKEN_PREFIX)


def encrypt(text: str) -> str:
    """
    Encrypt a value.

    With no key configured the value is returned unchanged, and the column
    holds plaintext. That is a development convenience, not a policy: the
    production check refuses to start without a key.
    """
    if text is None or text == "":
        return text
    if is_encrypted(text):
        return text

    pairs = key_pairs()
    if not pairs:
        return text

    key_id, key = pairs[0]
    ciphertext = _aessiv()(key).encrypt(text.encode("utf-8"), None)
    return f"{TOKEN_PREFIX}{key_id}:{base64.b64encode(ciphertext).decode('ascii')}"


def decrypt(token: str) -> str:
    """
    Decrypt a value we encrypted.

    A token whose key is not configured is an error, not a silent pass-through:
    a deployment that lost its key must fail loudly rather than serve a
    counselor a wall of base64.
    """
    if not is_encrypted(token):
        return token

    version, separator, rest = token.partition(":")
    key_id, _, encoded = rest.partition(":")
    if not separator or not key_id or not encoded:
        raise ValueError("This value is not a readable encrypted field.")

    pairs = dict(key_pairs())
    key = pairs.get(key_id)
    if key is None:
        raise ImproperlyConfigured(
            f"FIELD_ENCRYPTION_KEYS has no key with id '{key_id}'. The data "
            "cannot be read until that key is configured."
        )

    plaintext = _aessiv()(key).decrypt(base64.b64decode(encoded), None)
    return plaintext.decode("utf-8")


def status() -> dict:
    """Administrator-facing state. Never returns a key."""
    try:
        pairs = key_pairs()
    except ImproperlyConfigured as exc:
        return {
            "enabled": False,
            "algorithm": ALGORITHM,
            "key_count": 0,
            "active_key_id": None,
            "error": str(exc),
        }
    return {
        "enabled": bool(pairs),
        "algorithm": ALGORITHM,
        "key_count": len(pairs),
        "active_key_id": pairs[0][0] if pairs else None,
        "error": None,
    }
