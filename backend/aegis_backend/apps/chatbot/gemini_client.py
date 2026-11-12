"""
Central Gemini client.

Every Gemini call in AEGIS goes through this module so model selection,
retries, rate-limit handling, JSON parsing and logging live in one place.

Privacy boundary: callers send only the text they need classified or the
non-identifying facts they need explained. Never send a student name, student
number, email, grade record or counselling note from here. The client does not
enforce that by itself - it cannot know what a string means - so each caller
documents and tests its payload.

Configuration is environment-only:
    GEMINI_API_KEY   required for any call
    GEMINI_MODEL     default "gemini-2.5-flash" (TODO: confirm approved model)
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Attempts per call, including the first. Three is enough to ride out a
#: short 429 burst without holding a request open for a minute.
MAX_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 0.6
MAX_BACKOFF_SECONDS = 8.0

#: Per-request HTTP timeout, in seconds. A student waiting on a chat must not
#: wait on a stalled model call: Layer 1 already has the answer, so the
#: request gives up and the deterministic layer answers.
DEFAULT_TIMEOUT_SECONDS = 15

#: Total budget for one call, retries included. The loop stops starting new
#: attempts once this is spent, so the worst case is bounded no matter how
#: the API behaves.
DEFAULT_DEADLINE_SECONDS = 30


class GeminiError(Exception):
    """Base class. `code` is stable enough for callers to branch on."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


class GeminiNotConfigured(GeminiError):
    def __init__(self):
        super().__init__(
            "not_configured",
            "GEMINI_API_KEY is not set, so Gemini is unavailable.",
        )


class GeminiRateLimited(GeminiError):
    def __init__(self, detail: str = "Gemini rate limit reached."):
        super().__init__("rate_limited", detail)


class GeminiResponseError(GeminiError):
    def __init__(self, detail: str):
        super().__init__("invalid_response", detail)


def configured() -> bool:
    return bool(_keys())


def _keys() -> list[str]:
    """
    Every configured key, in order: the primary first, then the fallbacks.

    `GEMINI_API_KEY` is the primary. `GEMINI_API_KEYS` is a comma- or
    whitespace-separated list of fallbacks. A key is never logged, never
    returned by `status()` and never leaves the process.
    """
    primary = str(getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    raw = str(getattr(settings, "GEMINI_API_KEYS", "") or "")
    extra = [item.strip() for item in re.split(r"[,\s]+", raw) if item.strip()]

    keys: list[str] = []
    for key in ([primary] if primary else []) + extra:
        if key and key not in keys:
            keys.append(key)
    return keys


#: Which key this process is using, and which ones it has given up on.
#:
#: A key whose quota is exhausted is skipped for the rest of the process: it
#: will not come back within a deployment's lifetime, and re-trying it on
#: every message would add a wasted round trip to every chat.
#:
#: A key that was merely rate limited is not given up on — that clears in
#: seconds — it is simply moved past for this call.
_KEY_STATE: dict[str, Any] = {"index": 0, "exhausted": set()}


def _current_key() -> str | None:
    """The key to use now, or None when every key is exhausted."""
    keys = _keys()
    if not keys:
        return None
    start = _KEY_STATE["index"] % len(keys)
    for offset in range(len(keys)):
        index = (start + offset) % len(keys)
        key = keys[index]
        if key not in _KEY_STATE["exhausted"]:
            _KEY_STATE["index"] = index
            return key
    return None


def _advance_key(*, exhausted: bool = False) -> None:
    """Move to the next key, optionally remembering that this one is spent."""
    keys = _keys()
    if not keys:
        return
    current = _current_key()
    if exhausted and current is not None:
        _KEY_STATE["exhausted"].add(current)
    _KEY_STATE["index"] = (_KEY_STATE["index"] + 1) % len(keys)


def _key_slot(api_key: str) -> int:
    """
    The 1-based position of a key in the configured list.

    Log lines carry this instead of the key: a log is a place a secret ends
    up, and "key 3 of 5" is enough to say which one was tried.
    """
    keys = _keys()
    try:
        return keys.index(api_key) + 1
    except ValueError:
        return 0


def model_name() -> str:
    return getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash")


def _models() -> list[str]:
    """
    Every configured model, in order: the primary first, then the fallbacks.

    A model can be saturated — the API answers `503 — This model is currently
    experiencing high demand` — while the account is perfectly healthy. That
    is a reason to try a different model, not a different key, so the two
    lists rotate independently.
    """
    primary = str(getattr(settings, "GEMINI_MODEL", "") or "").strip()
    raw = str(getattr(settings, "GEMINI_MODEL_FALLBACKS", "") or "")
    extra = [item.strip() for item in re.split(r"[,\s]+", raw) if item.strip()]

    models: list[str] = []
    for model in ([primary] if primary else []) + extra:
        if model and model not in models:
            models.append(model)
    return models


#: Which model this process is using.
_MODEL_STATE: dict[str, Any] = {"index": 0}


def _current_model() -> str:
    models = _models()
    if not models:
        return ""
    return models[_MODEL_STATE["index"] % len(models)]


def _advance_model() -> None:
    """Move to the next configured model."""
    models = _models()
    if not models:
        return
    _MODEL_STATE["index"] = (_MODEL_STATE["index"] + 1) % len(models)


def timeout_seconds() -> int:
    """Per-request HTTP timeout. Overridable, because a school network is
    not Google's network."""
    try:
        value = int(getattr(settings, "GEMINI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        value = DEFAULT_TIMEOUT_SECONDS
    return max(1, value)


def deadline_seconds() -> int:
    """Total budget for one call, retries included."""
    try:
        value = int(
            getattr(settings, "GEMINI_DEADLINE_SECONDS", DEFAULT_DEADLINE_SECONDS)
        )
    except (TypeError, ValueError):
        value = DEFAULT_DEADLINE_SECONDS
    return max(1, value)


def _sdk_installed() -> bool:
    try:
        import google.genai  # noqa: F401
    except Exception:
        return False
    return True


def status() -> dict[str, Any]:
    """Admin-facing model status. No secret is returned."""
    keys = _keys()
    models = _models()
    return {
        "configured": bool(keys),
        "sdk_installed": _sdk_installed(),
        "model": _current_model() or model_name(),
        "models": models,
        "available": bool(keys) and _sdk_installed(),
        "timeout_seconds": timeout_seconds(),
        "deadline_seconds": deadline_seconds(),
        # How many keys are configured and how many are spent. Never the keys.
        "key_count": len(keys),
        "keys_exhausted": len(_KEY_STATE["exhausted"]),
        "last_failure": dict(_LAST_FAILURE),
    }


#: The last failure this process saw, so the administrator can tell "no key"
#: from "the quota ran out" from "the API is down". The value is a short
#: reason, never a payload and never a key.
_LAST_FAILURE: dict[str, Any] = {"reason": "", "at": None}


def _record_failure(reason: str) -> None:
    _LAST_FAILURE["reason"] = reason[:200]
    _LAST_FAILURE["at"] = timezone.now().isoformat()


def _clear_failure() -> None:
    _LAST_FAILURE["reason"] = ""
    _LAST_FAILURE["at"] = None


def _client(api_key: str):
    if not api_key:
        raise GeminiNotConfigured()
    try:
        from google import genai
    except Exception as exc:  # pragma: no cover - depends on install
        raise GeminiError(
            "sdk_missing",
            "google-genai is not installed. Run pip install -r requirements/base.txt.",
        ) from exc
    return genai.Client(
        api_key=api_key,
        # A stalled request must not hold a student's chat open. The timeout
        # is per HTTP call; the deadline in `_generate` bounds the retries.
        http_options={"timeout": timeout_seconds() * 1000},
    )


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code == 429 or "429" in text or "resource_exhausted" in text or "rate limit" in text


def _is_quota_exhausted(exc: Exception) -> bool:
    """
    Is this the account's quota gone, rather than a burst of requests?

    The API answers both with RESOURCE_EXHAUSTED. A per-minute limit clears in
    seconds and is worth retrying; "you exceeded your current quota, please
    check your plan and billing details" does not clear in seconds, and
    retrying it three times only makes every chat wait longer before the
    deterministic layer answers.
    """
    text = str(exc).lower()
    return (
        "check your plan and billing details" in text
        or "exceeded your current quota" in text
    )


def _is_saturation(exc: Exception) -> bool:
    """
    Is the model itself unavailable, rather than the key?

    The API answers `503 — This model is currently experiencing high demand`
    when a model is saturated, and `504 DEADLINE_EXCEEDED` when the operation
    runs out of time inside the service. Both are about the model, so the
    answer is a different model, not a different key.
    """
    text = str(exc).lower()
    if "high demand" in text or "deadline_exceeded" in text:
        return True
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int) and code in (500, 502, 503, 504):
        return True
    return any(
        token in text for token in ("service unavailable", "gateway timeout")
    )


def _is_retryable(exc: Exception) -> bool:
    if _is_quota_exhausted(exc):
        return False
    if _is_rate_limit(exc):
        return True
    text = str(exc).lower()
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int) and code >= 500:
        return True
    return any(token in text for token in ("timeout", "unavailable", "503", "502", "500"))


def _parse_json(text: str | None) -> dict[str, Any]:
    if not text:
        raise GeminiResponseError("Gemini returned an empty response.")
    cleaned = text.strip()
    # Models occasionally wrap JSON in a fenced block even when asked not to.
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except ValueError as exc:
        raise GeminiResponseError("Gemini did not return valid JSON.") from exc
    if not isinstance(value, dict):
        raise GeminiResponseError("Gemini returned JSON that is not an object.")
    return value


def _generate(
    *,
    contents: str,
    system_instruction: str,
    schema: dict[str, Any] | None = None,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """
    Call Gemini and return parsed JSON.

    Retries 429/5xx with backoff, and moves to the next configured key when
    a key is rate limited or has spent its quota. The deadline bounds the
    whole thing, so a caller never waits on more than that.
    """
    config: dict[str, Any] = {
        "system_instruction": system_instruction,
        "temperature": temperature,
        "response_mime_type": "application/json",
    }
    if schema is not None:
        config["response_schema"] = schema

    last_error: Exception | None = None
    deadline = time.monotonic() + deadline_seconds()
    # The deadline is the real bound; this is only a ceiling. It has to be big
    # enough to reach a working key/model combination, because a saturated
    # model on a good key is a different problem from a spent key.
    max_attempts = max(MAX_ATTEMPTS, len(_keys()) + len(_models()))
    for attempt in range(1, max_attempts + 1):
        if time.monotonic() >= deadline:
            # The budget for this call is spent. Stop retrying and let the
            # caller fall back to the deterministic layer.
            logger.warning(
                "gemini_call_deadline model=%s attempt=%s deadline_seconds=%s",
                model_name(),
                attempt,
                deadline_seconds(),
            )
            break
        api_key = _current_key()
        if api_key is None:
            # Every key has spent its quota. There is nothing left to try.
            _record_failure("every configured key has spent its quota")
            raise GeminiError(
                "no_available_key",
                "Every configured Gemini key has spent its quota.",
            )

        client = _client(api_key)
        model = _current_model()
        started = time.monotonic()
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            elapsed_ms = round((time.monotonic() - started) * 1000)
            logger.info(
                "gemini_call model=%s attempt=%s elapsed_ms=%s key_slot=%s",
                model,
                attempt,
                elapsed_ms,
                _key_slot(api_key),
            )
            _clear_failure()
            return _parse_json(getattr(response, "text", None))
        except GeminiError:
            raise
        except Exception as exc:
            last_error = exc
            logger.warning(
                "gemini_call_failed model=%s attempt=%s error=%s key_slot=%s",
                model,
                attempt,
                type(exc).__name__,
                _key_slot(api_key),
            )
            if _is_quota_exhausted(exc):
                _record_failure("quota exhausted: check the plan and billing")
                # This key is spent for good. Do not use it again in this
                # process; move on to the next one.
                _advance_key(exhausted=True)
                continue
            if _is_rate_limit(exc):
                _record_failure("rate limited")
                # A burst limit clears in seconds, so the key is not given up
                # on — it is just moved past for this call.
                _advance_key()
                continue
            if _is_saturation(exc):
                _record_failure(f"{model} is saturated")
                # The key is fine; the model is not. Try another model.
                _advance_model()
                continue
            if attempt >= max_attempts or not _is_retryable(exc):
                _record_failure(f"{type(exc).__name__}")
                break
            delay = min(
                MAX_BACKOFF_SECONDS,
                BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)),
            )
            # Jitter avoids a burst of retries from parallel requests.
            time.sleep(delay + random.uniform(0, 0.25))

    if last_error is not None and _is_rate_limit(last_error):
        raise GeminiRateLimited(str(last_error)[:300])
    raise GeminiError(
        "call_failed",
        f"Gemini call failed: {type(last_error).__name__ if last_error else 'unknown'}",
    )


def classify(text: str, *, categories: list[str]) -> dict[str, Any]:
    """
    Classify one message for sensitivity.

    Only `text` is sent. No user id, name, email, role or record is attached.
    """
    schema = {
        "type": "object",
        "properties": {
            "sensitive": {"type": "boolean"},
            "severity": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
            },
            "categories": {
                "type": "array",
                "items": {"type": "string", "enum": categories},
            },
            "rationale": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["sensitive", "severity", "categories", "confidence"],
    }
    result = _generate(
        contents=text,
        system_instruction=(
            "You are a school safety classifier. Decide whether the message "
            "contains a sensitive student-support signal. Do not diagnose. "
            "Use critical only for immediate danger or self-harm intent, high "
            "for credible threats or abuse, medium for distress, and low for "
            "none. Return JSON only."
        ),
        schema=schema,
        temperature=0.0,
    )
    severity = result.get("severity")
    if severity not in ("low", "medium", "high", "critical"):
        raise GeminiResponseError("Gemini returned an unknown severity.")
    try:
        confidence = float(result.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    raw_categories = result.get("categories") or []
    clean_categories = [
        str(value)
        for value in raw_categories
        if str(value) in categories
    ]
    return {
        "sensitive": bool(result.get("sensitive")),
        "severity": severity,
        "categories": clean_categories,
        "rationale": str(result.get("rationale") or "")[:500],
        "confidence": max(0.0, min(1.0, confidence)),
    }


def chat(
    *,
    system_instruction: str,
    message: str,
    context: dict[str, Any] | None = None,
) -> str:
    """Role-aware reply generation. Returns plain text."""
    payload = message
    if context:
        payload = (
            f"User message:\n{message}\n\n"
            "Authorized facts (the only facts you may use):\n"
            f"{json.dumps(context, default=str, ensure_ascii=False)}"
        )
    schema = {
        "type": "object",
        "properties": {"reply": {"type": "string"}},
        "required": ["reply"],
    }
    result = _generate(
        contents=payload,
        system_instruction=system_instruction,
        schema=schema,
        temperature=0.4,
    )
    reply = str(result.get("reply") or "").strip()
    if not reply:
        raise GeminiResponseError("Gemini returned an empty reply.")
    return reply[:2000]


def generate_json(
    *,
    prompt: str,
    schema: dict[str, Any],
    system_instruction: str,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """Generic structured generation for assessment and explanation features."""
    return _generate(
        contents=prompt,
        system_instruction=system_instruction,
        schema=schema,
        temperature=temperature,
    )
