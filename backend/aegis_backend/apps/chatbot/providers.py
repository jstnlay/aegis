"""
Chatbot response-provider abstraction.

The application still owns intent, permissions, data access, escalation and
fallbacks. A provider only turns an already-authorized request into prose. That
boundary is what lets an external or local model be added without changing the
API, the frontend, or the deterministic path.

Built-in providers
------------------

- ``NoopProvider`` — default. No network, no reply.
- ``OllamaProvider`` — a local model through the Ollama HTTP API. Student data
  never leaves the machine; this is the offline-safe backstop.
- ``OpenAICompatProvider`` — any OpenAI-compatible ``/chat/completions``
  endpoint (Groq, Cerebras, OpenRouter, Mistral, GitHub Models, ...). It is
  **offsite**: its payload is redacted first (``redact``), because a provider
  payload contains real student records.
- ``ChainProvider`` — tries providers in order. The first non-empty reply wins;
  a failure moves to the next; if every provider fails it returns ``None`` and
  the caller uses the deterministic reply.

Configure one provider with ``AEGIS_CHATBOT_PROVIDER``, or an ordered chain with
``AEGIS_CHATBOT_PROVIDER_CHAIN`` (comma-separated dotted paths). The default
chain is **local first, offsite as fallback**, so a normal answer never leaves
the machine and the offsite provider is reached only when the local model is
down::

    AEGIS_CHATBOT_PROVIDER_CHAIN = (
        "apps.chatbot.providers.OllamaProvider,"
        "apps.chatbot.providers.OpenAICompatProvider"
    )
    AEGIS_CHATBOT_USE_LLM = True

If a provider's import, construction or generation fails, the failure is logged
and the next provider is tried; if every provider fails, the deterministic
structured answer is returned. A student never sees a provider exception, and a
provider never receives ORM or database access.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from importlib import import_module
from typing import Any, Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

#: A provider is a prose generator, nothing else. It must not invent facts:
#: it is handed the authorized data and asked to phrase it.
#:
#: The only intent that reaches a provider today is `ASK_STUDY_STRATEGY`, whose
#: answer is open-ended advice, so this prompt asks for advice and nothing else.
#: It used to instruct the model to "state the overall average and the status",
#: which the local model obeyed literally — it replied with a record dump
#: ("**Grade Summary:** Average: 68.6 **Academic Status:** at risk") and invented
#: a recommendation title. The application states every record fact itself, so
#: the prompt no longer invites the model to.
SYSTEM_PROMPT = (
    "You are the AEGIS school assistant. You are asked how a student should "
    "study or improve. Reply with at most three short sentences of practical "
    "advice. Use only the weak subjects you are given, to keep the advice "
    "relevant. The application states the student's grades, average, status "
    "and recommendations itself, so never state or repeat a number, a status, "
    "a grade, a subject score, a section heading or a recommendation title, "
    "and never print a raw field value such as at_risk. Do not invent "
    "subjects, grades, contacts or policies. If you were given no weak "
    "subjects, give general study advice."
)

#: Never sent to an offsite provider. Redaction is best-effort by design: the
#: payload builder is the single place that assembles provider input, so this
#: list is the whole surface.
_IDENTIFYING_KEYS = ("student_id", "student_name")


@dataclass(frozen=True)
class ChatProviderRequest:
    """Only authorized, already-computed data is exposed to a provider."""

    user_role: str
    message: str
    intent: str
    urgency: str
    context: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)


class ChatProvider(Protocol):
    """Minimal contract for a prose generator."""

    #: True when the provider sends the payload off the machine.
    offsite: bool

    def generate(self, request: ChatProviderRequest) -> str | None:
        """Return prose, or ``None`` to request the deterministic fallback."""


class NoopProvider:
    """Default provider: no external service, no reply, no network."""

    offsite = False

    def generate(self, request: ChatProviderRequest) -> str | None:
        return None


def redact(data: dict[str, Any] | None) -> dict[str, Any]:
    """
    Drop direct student identifiers before a payload leaves the machine.

    One level deep, because that is the shape ``service`` builds: a flat map of
    named summaries (``grade_summary``, ``recommendations``, ...). Coursework
    content is the point of the call, so it is kept; the identifying keys are
    not needed to phrase an answer.
    """
    if not isinstance(data, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in data.items():
        if key in _IDENTIFYING_KEYS:
            continue
        if isinstance(value, dict):
            clean[key] = {
                nested_key: nested
                for nested_key, nested in value.items()
                if nested_key not in _IDENTIFYING_KEYS
            }
        else:
            clean[key] = value
    return clean


def _post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str] | None, timeout: float
) -> dict[str, Any]:
    """POST JSON with the standard library. No new dependency for this."""
    from urllib import request as urlrequest

    request_obj = urlrequest.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urlrequest.urlopen(request_obj, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_prompt(request: ChatProviderRequest) -> str:
    lines = [
        f"Role: {request.user_role}",
        f"Question: {request.message}",
    ]
    if request.data:
        lines.append("Data: " + json.dumps(request.data, default=str))
    return "\n".join(lines)


class OllamaProvider:
    """
    Local model over the Ollama HTTP API.

    The backstop of the chain: no API key, no network egress, so it still works
    when every offsite provider is unreachable.
    """

    offsite = False

    def __init__(self) -> None:
        self.url = getattr(settings, "AEGIS_OLLAMA_URL", "http://127.0.0.1:11434")
        self.model = getattr(settings, "AEGIS_OLLAMA_MODEL", "llama3.2:3b")
        self.timeout = getattr(settings, "AEGIS_CHATBOT_TIMEOUT_SECONDS", 8)

    def generate(self, request: ChatProviderRequest) -> str | None:
        payload = {
            "model": self.model,
            "prompt": _build_prompt(request),
            "system": SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "num_predict": getattr(settings, "AEGIS_CHATBOT_MAX_TOKENS", 300)
            },
        }
        data = _post_json(
            self.url.rstrip("/") + "/api/generate",
            payload,
            headers=None,
            timeout=self.timeout,
        )
        reply = (data.get("response") or "").strip()
        return reply or None


class OpenAICompatProvider:
    """
    Any OpenAI-compatible chat endpoint.

    One class serves every free-tier provider that speaks the same schema. It
    is offsite, so the chain hands it a redacted payload.
    """

    offsite = True

    def __init__(self) -> None:
        self.base_url = getattr(settings, "AEGIS_CHATBOT_OPENAI_BASE_URL", "")
        self.api_key = getattr(settings, "AEGIS_CHATBOT_OPENAI_API_KEY", "")
        self.model = getattr(settings, "AEGIS_CHATBOT_OPENAI_MODEL", "")
        self.timeout = getattr(settings, "AEGIS_CHATBOT_TIMEOUT_SECONDS", 8)

    def generate(self, request: ChatProviderRequest) -> str | None:
        if not self.base_url or not self.model:
            # Not configured: treat as unavailable rather than raise, so a
            # chain falls through to the next provider.
            return None

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(request)},
            ],
            "max_tokens": getattr(settings, "AEGIS_CHATBOT_MAX_TOKENS", 300),
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = _post_json(
            self.base_url.rstrip("/") + "/chat/completions",
            payload,
            headers=headers,
            timeout=self.timeout,
        )
        choices = data.get("choices") or []
        if not choices:
            return None
        reply = ((choices[0].get("message") or {}).get("content") or "").strip()
        return reply or None


class ChainProvider:
    """
    Ordered provider chain: first non-empty reply wins.

    An offsite provider gets a redacted payload; a local provider gets the full
    authorized data. A failing provider is logged and skipped, never fatal. If
    every provider fails the chain returns ``None``, which the caller reports as
    ``degraded`` and answers deterministically.
    """

    offsite = False

    def __init__(self, providers: list) -> None:
        self.providers = list(providers)

    def generate(self, request: ChatProviderRequest) -> str | None:
        redact_offsite = getattr(settings, "AEGIS_CHATBOT_REDACT_OFFSITE", True)
        for provider in self.providers:
            outbound = request
            if redact_offsite and getattr(provider, "offsite", False):
                outbound = replace(request, data=redact(request.data))
            try:
                reply = provider.generate(outbound)
            except Exception as error:
                # A missing local model or an unreachable endpoint is a routine
                # availability failure, not a bug: one line, no traceback, so a
                # deployment without a model does not spam the log per message.
                logger.warning(
                    "Chatbot provider %s unavailable (%s); trying the next.",
                    type(provider).__name__,
                    error,
                )
                continue
            if isinstance(reply, str) and reply.strip():
                return reply
        return None


def _instantiate(dotted_path: str):
    """Build one provider by dotted path, or ``None`` when unusable."""
    module_name, separator, class_name = dotted_path.rpartition(".")
    if not separator:
        logger.warning(
            "Invalid chatbot provider path %r; skipping it.", dotted_path
        )
        return None

    try:
        provider = getattr(import_module(module_name), class_name)()
    except Exception:
        logger.exception(
            "Could not load chatbot provider %r; skipping it.", dotted_path
        )
        return None

    if not callable(getattr(provider, "generate", None)):
        logger.warning(
            "Chatbot provider %r has no generate(); skipping it.", dotted_path
        )
        return None

    return provider


def get_provider() -> ChatProvider:
    """
    Build the configured provider, or a chain of them.

    A broken configuration is treated like an offline service: log it and use
    the deterministic path rather than failing the chat request. The local
    provider is what makes the chain survive having no network at all.
    """
    chain = getattr(settings, "AEGIS_CHATBOT_PROVIDER_CHAIN", "") or ""
    paths = [path.strip() for path in chain.split(",") if path.strip()]
    if paths:
        providers = [
            provider
            for provider in (_instantiate(path) for path in paths)
            if provider is not None
        ]
        if not providers:
            return NoopProvider()
        if len(providers) == 1:
            return providers[0]
        return ChainProvider(providers)

    dotted_path = getattr(
        settings,
        "AEGIS_CHATBOT_PROVIDER",
        "apps.chatbot.providers.NoopProvider",
    )
    if not dotted_path:
        return NoopProvider()

    return _instantiate(dotted_path) or NoopProvider()
