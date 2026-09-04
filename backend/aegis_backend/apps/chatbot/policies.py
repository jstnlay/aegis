"""
Phase 9 chatbot — deterministic intent/rule layer.

Local-first, least-privilege, role-aware. This is the deterministic
intent classifier used when the LLM is unavailable or for low-confidence
queries. It uses lightweight keyword/pattern matching + simple entity
extraction — no external dependencies.

INTENT and URGENCY are separate (D25).
"""

from __future__ import annotations

import re
from typing import Any

from apps.chatbot.taxonomy import (
    ChatEntity,
    ChatIntent,
    UrgencyLevel,
)

# ---------------------------------------------------------------------------
# Keyword rules (deterministic matching)
# ---------------------------------------------------------------------------

# Greeting patterns
GREETING_PATTERNS = [
    r"\b(hi|hello|hey|good\s*(morning|afternoon|evening)|kumusta|kamusta)\b",
    r"^hi\b",
]

# Help patterns
HELP_PATTERNS = [
    r"\bhelp\b",
    r"\btulong\b",
    r"\bwhat can you do\b",
    r"\bano kaya mo\b",
]

# Navigation patterns
NAVIGATION_PATTERNS = [
    r"\b(where|how)\s*(do|can)\s*(i|to)\s*(find|see|view)\b",
    r"\b(how|paano)\s*.*\b(navigate|access)\b",
]

# Grade patterns
GRADE_PATTERNS = [
    r"\b(grade|grades|mark|marks|score|scores)\b",
    r"\bano\s+.*\b(grade)\b",
    r"\b(grade ko|my grade|anong grade)\b",
]

# Academic performance
PERFORMANCE_PATTERNS = [
    r"\b(performance|academic)\b",
    r"\b(gawa|ginagawa)\s*(ko|sa)\b",
    r"\bhow\s*(am|i)\s*(doing|performing)\b",
]

# Subject help
SUBJECT_HELP_PATTERNS = [
    r"\b(subject|math|english|science|filipino|mapeh|tle|araling)\b",
    r"\btulong\s*(sa|ko)\b",
]

# Learning resource
RESOURCE_PATTERNS = [
    r"\b(resource|material|module|lesson|reviewer|handout)\b",
    r"\b(magaaral|study|learn)\b",
]

# Study strategy
STRATEGY_PATTERNS = [
    r"\b(strategy|technique|tips|study plan|how to study)\b",
    r"\b(paano mag-aral|paano mag aral)\b",
]

# Recommendation
RECOMMENDATION_PATTERNS = [
    r"\b(recommend|suggest|what should (i|we) (study|review|do))\b",
    r"\b(recommendation)\b",
]

# Attendance
ATTENDANCE_PATTERNS = [
    r"\b(attendance|absent|present|late|tardiness)\b",
    r"\b(pasok)\b",
]

# Assessment
ASSESSMENT_PATTERNS = [
    r"\b(assessment|exam|test|quiz|final)\b",
    r"\b(periodical|quarterly|long test)\b",
]

# Assessment schedule
SCHEDULE_PATTERNS = [
    r"\b(schedule|when|date|anong araw)\b",
]

# Guidance help
GUIDANCE_HELP_PATTERNS = [
    r"\b(guidance|counseling|counselor)\b",
]

# Express concern
CONCERN_PATTERNS = [
    r"\b(concern|worr(y|ied)|nervous|anxious|stressed|stress)\b",
    r"\b(alanganin|nag-aalala|problema)\b",
]

# Request counselor
COUNSELOR_PATTERNS = [
    r"\b(counselor|guidance)\s*(appointment|meet|schedule)\b",
    r"\b(meet|talk|speak)\s*(with|to)?\s*(a|counselor|someone|guidance)\b",
]

# Urgent concern patterns (FR-031 escalation)
URGENT_PATTERNS = [
    r"\b(urgent|emergency|crisis|suicide|self.harm|hurt|kill)\b",
    r"\b(help me now|i need help now)\b",
]

# Subject names for entity extraction
SUBJECT_KEYWORDS = {
    "math": "Mathematics",
    "mathematics": "Mathematics",
    "english": "English",
    "science": "Science",
    "filipino": "Filipino",
    "mapeh": "MAPEH",
    "tle": "TLE",
    "araling panlipunan": "Araling Panlipunan",
    "ap": "Araling Panlipunan",
    "esp": "Edukasyon sa Pagpapakatao",
}

# Topic keywords (lightweight)
TOPIC_KEYWORDS = {
    "algebra": "Algebra",
    "geometry": "Geometry",
    "trigonometry": "Trigonometry",
    "fractions": "Fractions",
    "grammar": "Grammar",
    "vocabulary": "Vocabulary",
    "reading": "Reading",
    "biology": "Biology",
    "chemistry": "Chemistry",
    "physics": "Physics",
}


def _extract_subject_entities(text: str) -> list[ChatEntity]:
    """Extract subject entities from message text."""
    entities = []
    lower = text.lower()
    for keyword, name in SUBJECT_KEYWORDS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", lower):
            entities.append(ChatEntity("subject", name))
    return entities


def _extract_topic_entities(text: str) -> list[ChatEntity]:
    """Extract topic entities from message text."""
    entities = []
    lower = text.lower()
    for keyword, name in TOPIC_KEYWORDS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", lower):
            entities.append(ChatEntity("topic", name))
    return entities


def _extract_entities(text: str) -> list[ChatEntity]:
    """Combine entity extraction from all entity types."""
    entities = []
    entities.extend(_extract_subject_entities(text))
    entities.extend(_extract_topic_entities(text))
    return entities


def detect_urgent(text: str) -> bool:
    """Detect urgent concern signals (D26)."""
    lower = text.lower()
    return any(re.search(pat, lower) for pat in URGENT_PATTERNS)


def detect_elevated(text: str) -> bool:
    """Detect elevated concern (supportive response needed)."""
    lower = text.lower()
    return any(re.search(pat, lower) for pat in CONCERN_PATTERNS)


def classify_urgency(text: str) -> UrgencyLevel:
    """
    Classify urgency level for a message.

    - URGENT if urgent concern patterns match (FR-031 escalation)
    - ELEVATED if concern is expressed
    - NORMAL otherwise

    IMPORTANT: Not keyword-only simplistic emergency logic; this provides
    the deterministic baseline. The application controls escalation.
    """
    lower = text.lower()
    if detect_urgent(lower):
        return UrgencyLevel.URGENT
    if detect_elevated(lower):
        if re.search(r"\b(counselor|guidance)\b", lower):
            return UrgencyLevel.ELEVATED
        return UrgencyLevel.ELEVATED
    return UrgencyLevel.NORMAL


def classify_intent(text: str) -> ChatIntent:
    """
    Deterministic intent classification using pattern matching.

    Priority order: urgent → guidance → attendance → assessment →
    academic → general.

    This is the fallback when the LLM is unavailable, or the
    low-confidence path. It does NOT use the LLM.
    """
    lower = text.lower().strip()

    # Urgent concern has highest priority
    if detect_urgent(lower):
        return ChatIntent.URGENT_CONCERN

    # Guidance / concern intents (COUNSELOR before GUIDANCE_HELP
    # because "counselor" also matches the guidance-help pattern)
    if re.search(r"\bbullying|harass\w*\b", lower):
        return ChatIntent.URGENT_CONCERN
    if any(re.search(p, lower) for p in COUNSELOR_PATTERNS):
        return ChatIntent.REQUEST_COUNSELOR
    if any(re.search(p, lower) for p in CONCERN_PATTERNS):
        return ChatIntent.EXPRESS_CONCERN
    if any(re.search(p, lower) for p in GUIDANCE_HELP_PATTERNS):
        return ChatIntent.GUIDANCE_HELP

    # Assessment
    if any(re.search(p, lower) for p in ASSESSMENT_PATTERNS):
        if any(re.search(p, lower) for p in SCHEDULE_PATTERNS):
            return ChatIntent.ASSESSMENT_SCHEDULE
        return ChatIntent.ASK_ASSESSMENT

    # Attendance
    if any(re.search(p, lower) for p in ATTENDANCE_PATTERNS):
        return ChatIntent.ASK_ATTENDANCE

    # Academic (grade/perf checked before subject-help so an explicit
    # grade query with a subject name is still classified as grade)
    if any(re.search(p, lower) for p in RECOMMENDATION_PATTERNS):
        return ChatIntent.ASK_RECOMMENDATION
    if any(re.search(p, lower) for p in STRATEGY_PATTERNS):
        return ChatIntent.ASK_STUDY_STRATEGY
    if any(re.search(p, lower) for p in RESOURCE_PATTERNS):
        return ChatIntent.ASK_LEARNING_RESOURCE
    if any(re.search(p, lower) for p in GRADE_PATTERNS):
        return ChatIntent.ASK_GRADE
    if any(re.search(p, lower) for p in PERFORMANCE_PATTERNS):
        return ChatIntent.ASK_ACADEMIC_PERFORMANCE
    if any(re.search(p, lower) for p in SUBJECT_HELP_PATTERNS):
        return ChatIntent.ASK_SUBJECT_HELP

    # General
    if any(re.search(p, lower) for p in GREETING_PATTERNS):
        return ChatIntent.GREETING
    if any(re.search(p, lower) for p in HELP_PATTERNS):
        return ChatIntent.HELP
    if any(re.search(p, lower) for p in NAVIGATION_PATTERNS):
        return ChatIntent.SYSTEM_NAVIGATION

    return ChatIntent.UNKNOWN


class ChatParseResult:
    """Result of deterministic parsing."""

    def __init__(
        self,
        intent: ChatIntent,
        urgency: UrgencyLevel,
        entities: list[ChatEntity],
        confidence: float = 1.0,
    ):
        self.intent = intent
        self.urgency = urgency
        self.entities = entities
        self.confidence = confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "urgency": self.urgency.value,
            "entities": [e.to_dict() for e in self.entities],
            "confidence": self.confidence,
        }


def parse_message(text: str) -> ChatParseResult:
    """
    Deterministic parse of a chat message.

    Returns intent + urgency + entities with confidence.
    """
    intent = classify_intent(text)
    urgency = classify_urgency(text)
    entities = _extract_entities(text)

    # Confidence estimation (simple heuristic)
    confidence = 1.0
    if intent == ChatIntent.UNKNOWN:
        confidence = 0.1
    elif intent in (
        ChatIntent.ASK_SUBJECT_HELP,
        ChatIntent.ASK_ACADEMIC_PERFORMANCE,
    ) and not entities:
        confidence = 0.5

    return ChatParseResult(
        intent=intent,
        urgency=urgency,
        entities=entities,
        confidence=confidence,
    )
