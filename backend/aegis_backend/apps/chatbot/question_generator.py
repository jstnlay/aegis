"""
FR-027 — AI chatbot assistance for question generation.

The SRS puts this requirement in the Guidance Module (FR-027/028/029): a
counselor drafts a wellness or behavioral assessment and the chatbot helps by
proposing the item stems. This module is the whole of that assistance.

Two design decisions carry the honesty of the feature and are worth stating
plainly, because "AI-generated questions" is exactly the kind of claim that is
easy to fake:

* **The chatbot's own model chooses the item bank.** The topic the counselor
  types is run through the same intent classifier the student chatbot uses
  (``apps.chatbot.classifier.predict``), phrased the way a student would say it
  so it is in distribution for a model trained on chat utterances. The
  predicted intent selects which bank of stems is drafted first. When neither
  probe classifies confidently — model unavailable, or confidence below
  ``CONFIDENCE_FLOOR`` — the general bank is used, which is a stated fallback
  rather than a guess dressed up as one.

* **Every draft is a self-report stem, never a fact.** A generator can honestly
  produce statements *about the respondent* ("I can talk to someone I trust
  about …"); it cannot produce statements *about the world* and stand behind
  them. That is the reason ``true_false`` is refused rather than half-supported:
  a generated true/false item asserts something we would be inventing.

The drafts are proposals. The counselor owns the question — they edit or discard
every one before adding it, and nothing here writes to the database.
"""

from __future__ import annotations

from apps.chatbot.taxonomy import (
    ACADEMIC_INTENTS,
    ASSESSMENT_INTENTS,
    GUIDANCE_INTENTS,
)

# Fixed response scales. Self-report items are not auto-graduated, so no scale
# point is ever a "correct" answer and `correct_answer` stays None.
AGREEMENT_SCALE = [
    "Strongly disagree",
    "Disagree",
    "Neutral",
    "Agree",
    "Strongly agree",
]
FREQUENCY_SCALE = ["Never", "Rarely", "Sometimes", "Often", "Always"]

#: Question types this generator will draft for. `true_false` is excluded on
#: purpose — see the module docstring.
GENERATABLE_TYPES = ("multiple_choice", "essay", "likert")

#: Upper bound on a single request. Well past the number of unique stems in a
#: single family, so a large request rotates through neighbouring banks rather
#: than repeating an item back to back.
MAX_DRAFTS = 20

# ---------------------------------------------------------------------------
# Item banks, by intent family.
#
# Four lists per family — agreement (likert), frequency (multiple_choice) and
# open (essay) — each written around the counselor's `{topic}` as a noun
# phrase, so any topic fits grammatically without us asserting anything about
# it.
# ---------------------------------------------------------------------------

_ITEM_BANKS: dict[str, dict[str, list[str]]] = {
    # GUIDANCE / SUPPORT intents: help-seeking and coping.
    "concern": {
        "agreement": [
            "I can talk to someone I trust about {topic}.",
            "I know where to ask for help when {topic} becomes difficult.",
            "I feel confident that I can handle {topic}.",
            "I would ask my guidance counselor for support with {topic}.",
            "I can still take part in class activities when {topic} happens.",
            "I recover quickly after {topic} happens.",
        ],
        "frequency": [
            "How often do you talk to someone you trust about {topic}?",
            "How often do you ask for help when {topic} happens?",
            "How often does {topic} affect your schoolwork?",
            "How often do you feel confident about handling {topic}?",
            "How often do you discuss {topic} with your family?",
            "How often do you use a coping strategy when {topic} happens?",
        ],
        "open": [
            "Describe a time when {topic} affected your day at school.",
            "What do you usually do when {topic} happens?",
            "Who would you talk to about {topic}, and why?",
            "What is one thing that helps you when {topic} happens?",
            "What would you like your counselor to understand about {topic}?",
        ],
    },
    # ACADEMIC intents: study strategy and subject help.
    "academic": {
        "agreement": [
            "I can ask my teacher for help when I do not understand {topic}.",
            "I have a study plan for {topic}.",
            "I can explain {topic} in my own words.",
            "I know which part of {topic} I need to work on.",
            "I use my class notes when I review {topic}.",
            "I can keep up with my work on {topic} during a normal week.",
        ],
        "frequency": [
            "How often do you review {topic} on your own?",
            "How often do you ask a classmate for help with {topic}?",
            "How often do you get stuck on {topic} during class?",
            "How often do you use your notes when working on {topic}?",
            "How often do you finish your work on {topic} on time?",
            "How often do you talk to your teacher about {topic}?",
        ],
        "open": [
            "What part of {topic} do you find hardest, and why?",
            "Describe how you usually study {topic}.",
            "What would help you understand {topic} better?",
            "What is one step you will take this week on {topic}?",
            "What has worked for you before when {topic} felt difficult?",
        ],
    },
    # ASSESSMENT intents: taking and preparing for assessments.
    "assessment": {
        "agreement": [
            "I know what is expected of me in {topic}.",
            "I read the instructions for {topic} before I start answering.",
            "I can finish {topic} within the time given.",
            "I feel prepared for {topic}.",
            "I check my answers in {topic} before I submit.",
            "I can ask a teacher when something in {topic} is unclear.",
        ],
        "frequency": [
            "How often do you read the instructions before starting {topic}?",
            "How often do you finish {topic} within the time given?",
            "How often do you check your answers in {topic} before submitting?",
            "How often do you feel rushed while working on {topic}?",
            "How often do you ask for clarification during {topic}?",
            "How often do you review {topic} after it is returned?",
        ],
        "open": [
            "What helps you stay focused during {topic}?",
            "Describe how you prepare for {topic}.",
            "What makes {topic} difficult for you?",
            "What would make {topic} easier next time?",
            "What do you tell yourself before {topic} starts?",
        ],
    },
    # Fallback: GENERAL and ATTENDANCE intents, and any unconfident prediction.
    "general": {
        "agreement": [
            "I can say how I am feeling about {topic}.",
            "I know someone I can talk to about {topic}.",
            "I feel comfortable asking for support with {topic}.",
            "I can manage {topic} alongside my schoolwork.",
            "I notice how {topic} affects my day.",
            "I have something that helps me when {topic} happens.",
        ],
        "frequency": [
            "How often do you think about {topic}?",
            "How often do you talk about {topic} with someone?",
            "How often does {topic} change how you feel during the day?",
            "How often do you ask for support with {topic}?",
            "How often does {topic} affect your sleep?",
            "How often do you notice {topic} during class?",
        ],
        "open": [
            "What does {topic} mean to you?",
            "How does {topic} affect your day at school?",
            "What helps you when {topic} happens?",
            "Is there anything else you want your counselor to know about {topic}?",
            "When did you first notice {topic}, and what was happening then?",
        ],
    },
}

# Rotation used once the primary bank runs out: neighbours first, general last.
_FAMILY_ORDER = ("concern", "academic", "assessment", "general")

_SHAPE_BY_TYPE = {
    "likert": ("agreement", AGREEMENT_SCALE),
    "multiple_choice": ("frequency", FREQUENCY_SCALE),
    "essay": ("open", None),
}


class QuestionGenerationError(ValueError):
    """Raised for a request this generator will not answer. Carries a code."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def select_family(topic: str) -> tuple[str, float]:
    """
    Classify `topic` with the chatbot's intent model and map it to a bank.

    Returns `(family, confidence)`. `family` is `"general"` whenever neither
    probe is classified confidently — `classifier.predict` already returns
    `None` for both an unavailable model and a prediction below
    `CONFIDENCE_FLOOR`, and the caller is told the confidence so it can say how
    much weight the selection carried.

    The topic is classified twice. A counselor types a noun phrase ("exam
    anxiety"), while the model was trained on chat utterances, so the phrase is
    first wrapped the way a student would actually say it. That is not a
    trick to raise the score: a bare noun phrase genuinely is out of
    distribution for this model, and the second probe is the unmodified topic
    so a topic that reads as a sentence on its own is not rewritten away.
    """
    from apps.chatbot.classifier import predict

    probes = (f"I need help with {topic}", topic)
    confidence = 0.0
    for text in probes:
        try:
            intent, confidence = predict(text)
        except Exception:  # pragma: no cover - classifier is best-effort here
            return "general", 0.0
        if intent is None:
            continue
        if intent in GUIDANCE_INTENTS:
            return "concern", confidence
        if intent in ACADEMIC_INTENTS:
            return "academic", confidence
        if intent in ASSESSMENT_INTENTS:
            return "assessment", confidence
    return "general", confidence


def _stem_family_order(primary: str) -> list[str]:
    """Primary first, then the rest of `_FAMILY_ORDER`, general last."""
    rest = [name for name in _FAMILY_ORDER if name != primary]
    # Keep `general` as the final fallback even when it is not the primary.
    rest.sort(key=lambda name: name == "general")
    return [primary, *rest]


def generate_question_drafts(
    topic: str,
    question_type: str,
    count: int,
) -> dict:
    """
    Draft `count` candidate questions about `topic`.

    Returns ``{"family", "confidence", "drafts"}`` where each draft is
    ``{"question_text", "options", "correct_answer"}`` — shaped exactly like a
    ``POST /assessments/assessment-questions/`` body minus ``assessment`` and
    ``order``, so the caller can hand a draft straight to the form.

    Raises :class:`QuestionGenerationError` for a type this generator will not
    draft or a count outside 1..MAX_DRAFTS.
    """
    if question_type not in GENERATABLE_TYPES:
        raise QuestionGenerationError(
            "QUESTION_TYPE_UNSUPPORTED",
            "AI drafting supports multiple_choice, likert and essay. "
            "A generated true/false item would assert a fact the system "
            "cannot verify, so it is not generated.",
        )
    if not isinstance(count, int) or isinstance(count, bool):
        raise QuestionGenerationError(
            "QUESTION_COUNT_INVALID", "count must be an integer."
        )
    if count < 1 or count > MAX_DRAFTS:
        raise QuestionGenerationError(
            "QUESTION_COUNT_INVALID",
            f"count must be between 1 and {MAX_DRAFTS}.",
        )

    cleaned_topic = " ".join(topic.split()).rstrip(".")
    if not cleaned_topic:
        raise QuestionGenerationError(
            "TOPIC_REQUIRED", "topic must not be empty."
        )

    shape, scale = _SHAPE_BY_TYPE[question_type]
    family, confidence = select_family(cleaned_topic)

    drafts: list[dict] = []
    seen: set[str] = set()
    for bank_name in _stem_family_order(family):
        for stem in _ITEM_BANKS[bank_name][shape]:
            # `str.format` is fed only our own literal template; `topic` is a
            # value, never a format string, so a topic containing braces is
            # harmless.
            text = stem.format(topic=cleaned_topic)
            if text in seen:
                continue
            seen.add(text)
            drafts.append(
                {
                    "question_text": text,
                    "options": list(scale) if scale else None,
                    "correct_answer": None,
                }
            )
            if len(drafts) == count:
                return {
                    "family": family,
                    "confidence": round(confidence, 4),
                    "drafts": drafts,
                }

    # Unreachable in practice: every shape holds at least MAX_DRAFTS distinct
    # stems across the four banks. Guarded rather than assumed - a future edit
    # that shortens a bank must fail loudly here, not silently return fewer
    # drafts than asked for.
    raise QuestionGenerationError(
        "QUESTION_COUNT_TOO_HIGH",
        f"Only {len(drafts)} distinct drafts are available for this topic.",
    )
