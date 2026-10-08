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

# Navigation patterns.
#
# Requires a UI noun, not just "find". "How do I find my grades?" is genuinely
# ambiguous — the user may want the grade — and it resolves to ask_grade, which
# is the more useful reading. Only an explicit page/menu/section reference counts
# as navigation, so this never steals a content question that happens to start
# with "how do I find".
NAVIGATION_PATTERNS = [
    r"\b(where|how)\s*(do|can|to)\s*(i|we)\s*(find|see|view|access|go to)\s+(the\s+)?(page|menu|screen|section|tab|button)\b",
    r"\b(how|paano)\s+.*\b(navigate|navigation)\b",
    r"\b(where)\s+(do|can)\s+(i|we)\s+go\b",
    r"\b(nasa|saan)\s+ako\s+(ma)?\s*(kita|nakita|makita)\b",
]

# Grade patterns. `point|points` is included because "how many points did I get"
# is the most natural way a student asks about a score; without it the message
# fell through to subject-help on the subject name alone.
GRADE_PATTERNS = [
    r"\b(grade|grades|mark|marks|score|scores|point|points)\b",
    r"\bano\s+.*\b(grade)\b",
    r"\b(grade ko|my grade|anong grade)\b",
    r"\bhow many\s+(points|marks)\b",
]

# Academic performance
PERFORMANCE_PATTERNS = [
    r"\b(performance|academic|academically)\b",
    r"\b(gawa|ginagawa)\s*(ko|sa)\b",
    r"\b(how|am)\s*(am|i)\s*(doing|performing)\b",
    r"\b(am i)\s+(doing well|improving|getting better)\b",
    r"\b(overall)\s+(performance|academic)\b",
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

# Study strategy. `how do i study` is matched before the bare `study` token in
# RESOURCE_PATTERNS because both fire on it, and "how do I study better" is a
# method question, not a request for a document.
STRATEGY_PATTERNS = [
    r"\b(strategy|technique|tips|study plan|how to study|how should i study)\b",
    r"\b(paano mag-aral|paano mag aral|pano mag-aaral)\b",
    r"\b(how)\s+(do|can|should)\s+(i|we)\s+(study|review|prepare)\b",
]

# Recommendation
RECOMMENDATION_PATTERNS = [
    r"\b(recommend|suggest|suggestion)\w*",
    r"\bwhat should (i|we) (study|review|do)\b",
    r"\b(what|ano)\s+(should|can)\s+(i|we)\s+(review|study|do)\b",
    r"\b(recommendation)\b",
    r"\b(any)\s+(suggestion|recommendation|advice|tip)\b",
    r"\b(need)\s+(suggestion|recommendation|advice)\b",
]

# Attendance
#
# `absen` covers the Filipino stem used bare ("ilang absen ko"), which the
# English-only `absent\w*` never matched, so the message fell through to
# UNKNOWN and the bot answered "I didn't fully understand". `pasok`/`late`/
# `tardiness` are how it is actually asked in Taglish.
ATTENDANCE_PATTERNS = [
    r"\b(attendance|absent|absences|absence|absent\w*|present|late|tardiness|tardy)\b",
    r"\b(absen|pasok|late|oras)\b",
    r"\b(pasok)\b",
    r"\b(ilan|how many)\s+(ang\s+)?(absen|missed)\w*",
    r"\b(how many|ilan)\s+(times|days)\s+(did|ng)\s+(i|ko)\s+(miss|absent|skip)",
]

# Attendance *status* — "how am I doing on attendance", as opposed to the raw
# count. Separated from ASK_ATTENDANCE because a student asking whether they are
# in trouble is asking a different question from one asking for a number, and
# they get different answers. Without this branch the intent was declared in
# `taxonomy.ChatIntent` and gated per role, but no code path could ever return it.
ATTENDANCE_STATUS_PATTERNS = [
    r"\b(am i|how am i|are i)\s+(doing|ok|fine)\b.*\b(attend\w*)\b",
    r"\b(attend\w*)\s+(record|status|rate)\b",
    r"\b(ok|okay|fine|good)\s+ba\s+(ang\s+)?(attend\w*|pasok)\b",
    r"\b(attend\w*)\s+ko\b",
]

# Assessment
ASSESSMENT_PATTERNS = [
    r"\b(assessment|exam|test|quiz|final)\b",
    r"\b(periodical|quarterly|long test)\b",
]

# Assessment schedule
SCHEDULE_PATTERNS = [
    r"\b(schedule|when|date|anong araw)\b",
    r"\b(kailan|ano ang araw)\b",
    r"\b(when is|what time is)\b",
]

# Assessment *instructions* — how an assessment is administered, as opposed to
# when it happens (`assessment_schedule`) or what it covers (`ask_assessment`).
# Declared in `taxonomy.ChatIntent` and gated per role from PH9, but with no
# branch able to return it until now.
INSTRUCTIONS_PATTERNS = [
    r"\b(how|instruction\w*|direction\w*|guideline\w*|rule\w*)\b.*\b(assess|quiz|exam|test)\w*",
    r"\b(assess|quiz|exam|test)\w*\b.*\b(instruction|how many question|how long|how many minutes|pass|open book)\b",
    r"\b(paano)\s+(mag\s*submit|magkwento|sumagot|mag-answer)",
    r"\b(ano ang)\s+(instruction\w*|pano)\b",
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
#
# `makipag-usap` / `makipagkilala` are how "I want to talk to someone" is
# actually written in Taglish. Without them, "gusto ko makipag-usap sa
# counselor" fell through to GUIDANCE_HELP (a bare `counselor` match) and
# answered "Guidance is available to support you" — which is not what was asked.
# The explicit talk-to-someone phrasing is what distinguishes the two intents.
COUNSELOR_PATTERNS = [
    r"\b(counselor|guidance)\s*(appointment|meet|schedule)\b",
    r"\b(meet|talk|speak)\s*(with|to)?\s*(a|counselor|someone|guidance)\b",
    r"\b(makipag-usap|makipag-usap|makipagkilala|kausap)\b",
    r"\b(gusto| gusto)\s*ko\s+(makipag|makipag-?usap)\w*",
]

# Urgent concern patterns (FR-031 escalation)
#
# Precision matters more than recall here, and not for a subtle reason: a match
# here dispatches a real BEHAVIORAL_WARNING notification to a guidance counselor
# (service.create_escalation). A broad bare `\bhurt\b` or `\bkill\b` escalated
# "I hurt my ankle playing basketball" and "I'm killing it in math" — a
# counselor paged about a sprained ankle, which trains staff to ignore the
# channel and makes a real crisis notice less likely to be read.
#
# So self-harm wording is matched as a phrase with the first-person subject
# attached, not as a bare verb:
#   hurt      -> "hurt myself", "hurting myself", "I want to hurt ..."
#   kill      -> "kill myself", "killing myself", "want to kill ..."
# A bare "hurt"/"kill" is deliberately NOT a trigger. Recessive phrasing that
# names no actor ("want to disappear", "don't want to be here") is covered by
# the self-harm phrase patterns below.
URGENT_PATTERNS = [
    # Explicit, unambiguous escalation requests.
    r"\b(urgent|emergency|crisis)\b",
    r"\b(help me now|i need help now|need help immediately)\b",
    # Named crisis services / self-harm methods.
    r"\b(suicide|suicidal|self.harm|self-harm)\b",
    # First-person self-harm. The subject must be attached so "I hurt my ankle"
    # does not match.
    r"\b(hurt|harm|harming|hurts)\s+(my|my\s*own)self\b",
    r"\b(hurt|harm|harming|hurts)\s+myself\b",
    r"\b(been|always|constantly|keep|keeps|keeping)\s+(hurting|harming|hurt|harm)\s+myself\b",
    r"\b(kill|killing|kills)\s+(my|my\s*own)self\b",
    r"\b(kill|killing)\s+myself\b",
    r"\b(want|wants|wanted|wish|wishes)\s+to\s+(kill|hurt|harm)\b",
    r"\b(going|gonna|plan|planning|planning)\s+to\s+(kill|hurt|harm)\b",
    # Recessive phrasing with no actor named.
    r"\b(don'?t|do not)\s+want\s+to\s+(live|be here|exist)\b",
    r"\bwant\s+to\s+disappear\b",
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

    # Assessment. Instructions are checked before schedule because
    # "How many questions is the quiz?" contains "how", which SCHEDULE treats as
    # a when-question; a duration/rule question is not a scheduling question.
    if any(re.search(p, lower) for p in ASSESSMENT_PATTERNS):
        if any(re.search(p, lower) for p in INSTRUCTIONS_PATTERNS):
            return ChatIntent.ASSESSMENT_INSTRUCTIONS
        if any(re.search(p, lower) for p in SCHEDULE_PATTERNS):
            return ChatIntent.ASSESSMENT_SCHEDULE
        return ChatIntent.ASK_ASSESSMENT

    # Attendance. Status is checked before the raw count because
    # "Am I doing okay with my attendance?" matches both, and the status
    # reading is the one the student meant.
    if any(re.search(p, lower) for p in ATTENDANCE_STATUS_PATTERNS):
        return ChatIntent.ASK_ATTENDANCE_STATUS
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
