"""
Two-layer sensitive-message detection.

Layer 1 is deterministic and database-backed: `KeywordTerm` rows plus the
existing `policies` patterns. It runs first and is authoritative when Gemini is
unavailable.

Layer 2 is Gemini classification. It can raise the severity and add categories.
It can never lower Layer 1's result: the union is the maximum severity and the
union of categories. A Gemini failure sets `manual_review` and leaves Layer 1's
answer in force.

The application, not the model, decides whether a message is sensitive.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from apps.chatbot import gemini_client
from apps.chatbot.models import SEVERITY_RANK, KeywordTerm
from apps.chatbot.policies import detect_elevated, detect_urgent

logger = logging.getLogger(__name__)

SEVERITIES = ("low", "medium", "high", "critical")

#: Categories are a fixed vocabulary so a model cannot invent a free-text label
#: that the routing table then has to interpret.
CATEGORIES = (
    "self_harm",
    "suicide",
    "abuse",
    "violence",
    "bullying",
    "distress",
    "academic_distress",
    "family",
    "other",
)


@dataclass
class LayerResult:
    sensitive: bool
    severity: str = "low"
    categories: list[str] = field(default_factory=list)
    matches: list[dict] = field(default_factory=list)
    detail: str = ""
    available: bool = True

    def to_dict(self) -> dict:
        return {
            "sensitive": self.sensitive,
            "severity": self.severity,
            "categories": self.categories,
            "matches": self.matches,
            "detail": self.detail,
            "available": self.available,
        }


@dataclass
class DetectionResult:
    sensitive: bool
    severity: str
    categories: list[str]
    layer1: LayerResult
    layer2: LayerResult | None
    manual_review: bool
    source: str

    def to_dict(self) -> dict:
        return {
            "sensitive": self.sensitive,
            "severity": self.severity,
            "categories": self.categories,
            "layer1": self.layer1.to_dict(),
            "layer2": self.layer2.to_dict() if self.layer2 else None,
            "manual_review": self.manual_review,
            "source": self.source,
        }


def max_severity(*values: str) -> str:
    return max(values, key=lambda value: SEVERITY_RANK.get(value, 0))


def _matches(term: KeywordTerm, text: str) -> bool:
    if not term.term:
        return False
    if term.match_type == KeywordTerm.MatchType.REGEX:
        try:
            return re.search(term.term, text, re.IGNORECASE) is not None
        except re.error:
            # A bad administrator regex must not take screening down. It is
            # logged and treated as no match; the built-in patterns still run.
            logger.warning("Invalid keyword regex ignored: %r", term.term)
            return False
    if term.match_type == KeywordTerm.MatchType.PHRASE:
        return term.term.lower() in text
    return re.search(rf"\b{re.escape(term.term)}\b", text, re.IGNORECASE) is not None


def layer1_screen(text: str) -> LayerResult:
    """Deterministic screening. Never calls an external service."""
    lowered = text.lower()
    categories: list[str] = []
    matches: list[dict] = []
    severity = "low"

    if detect_urgent(lowered):
        severity = "critical"
        categories.append("self_harm")
        matches.append({"source": "policy", "term": "urgent_pattern"})
    elif detect_elevated(lowered):
        severity = max_severity(severity, "medium")
        categories.append("distress")
        matches.append({"source": "policy", "term": "concern_pattern"})

    for term in KeywordTerm.objects.filter(is_active=True):
        if not _matches(term, lowered):
            continue
        severity = max_severity(severity, term.severity)
        if term.category:
            categories.append(term.category)
        matches.append(
            {
                "source": "keyword_term",
                "term": term.term,
                "severity": term.severity,
                "category": term.category,
            }
        )

    # A term with no category still needs a category for routing summaries.
    if matches and not categories:
        categories.append("other")

    return LayerResult(
        sensitive=severity != "low",
        severity=severity,
        categories=sorted(set(categories)),
        matches=matches,
        detail="keyword",
    )


def layer2_classify(text: str) -> LayerResult:
    """Gemini classification. Returns an unavailable result on any failure."""
    try:
        result = gemini_client.classify(text, categories=list(CATEGORIES))
    except gemini_client.GeminiNotConfigured:
        return LayerResult(
            sensitive=False,
            available=False,
            detail="gemini_not_configured",
        )
    except Exception as exc:
        logger.warning("Gemini classification failed: %s", type(exc).__name__)
        return LayerResult(
            sensitive=False,
            available=False,
            detail=f"gemini_error:{type(exc).__name__}",
        )

    severity = result["severity"]
    return LayerResult(
        sensitive=bool(result["sensitive"]) and severity != "low",
        severity=severity,
        categories=result.get("categories") or [],
        detail=result.get("rationale", ""),
        available=True,
    )


def detect(text: str, *, use_gemini: bool = True) -> DetectionResult:
    """Run both layers and combine them by union / maximum."""
    first = layer1_screen(text)
    second: LayerResult | None = None
    manual_review = False

    if use_gemini:
        second = layer2_classify(text)
        if not second.available:
            # Layer 1 still decides. A human must look because the second
            # layer did not run, not because the message is necessarily risky.
            manual_review = True

    severity = first.severity
    categories = list(first.categories)
    layer2_sensitive = False
    if second is not None and second.available:
        severity = max_severity(severity, second.severity)
        categories.extend(second.categories)
        layer2_sensitive = second.sensitive
    sensitive = first.sensitive or layer2_sensitive

    if first.sensitive and layer2_sensitive:
        source = "combined"
    elif layer2_sensitive:
        source = "gemini"
    else:
        source = "keyword"

    return DetectionResult(
        sensitive=sensitive,
        severity=severity if sensitive else "low",
        categories=sorted(set(categories)),
        layer1=first,
        layer2=second,
        manual_review=manual_review,
        source=source,
    )
