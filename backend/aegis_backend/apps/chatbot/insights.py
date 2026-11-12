"""
Guidance drafting helpers: intervention suggestions and assessment items.

Neither function writes to the database. They return proposals that a counselor
must review and save through the normal intervention/assessment endpoints.

Privacy: the flag's free-text message is never sent to Gemini here. Only the
severity and the fixed category vocabulary are sent.
"""

from __future__ import annotations

import logging

from apps.chatbot import gemini_client
from apps.chatbot.question_generator import generate_question_drafts

logger = logging.getLogger(__name__)

FALLBACK_INTERVENTIONS = {
    "critical": [
        "Contact the student privately today and confirm immediate safety.",
        "Follow the school's crisis protocol and involve the designated lead.",
        "Notify the family with the student's knowledge unless safety requires otherwise.",
    ],
    "high": [
        "Schedule a same-day check-in with the student.",
        "Agree on one trusted adult the student can reach this week.",
        "Record a follow-up date and review it within seven days.",
    ],
    "medium": [
        "Offer a supportive conversation within two school days.",
        "Share one coping or help-seeking strategy and ask what fits.",
        "Check in again after one week.",
    ],
    "low": [
        "Acknowledge the concern and remind the student that Guidance is available.",
    ],
}


def intervention_suggestions(flag) -> dict:
    """Return Gemini suggestions, or a deterministic severity-based fallback."""
    fallback = FALLBACK_INTERVENTIONS.get(flag.severity, FALLBACK_INTERVENTIONS["low"])
    if gemini_client.configured():
        schema = {
            "type": "object",
            "properties": {
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 5,
                }
            },
            "required": ["suggestions"],
        }
        prompt = (
            f"Severity: {flag.severity}. Categories: {', '.join(flag.categories) or 'none'}. "
            "Propose concrete, non-clinical next steps a school guidance counselor "
            "can take. Do not diagnose. Do not claim to know facts not supplied."
        )
        try:
            result = gemini_client.generate_json(
                prompt=prompt,
                schema=schema,
                system_instruction=(
                    "You advise a school guidance office. Return only actionable "
                    "steps that respect student privacy."
                ),
            )
            suggestions = [
                str(item)[:300]
                for item in (result.get("suggestions") or [])
                if str(item).strip()
            ]
            if suggestions:
                return {"source": "gemini", "suggestions": suggestions[:5]}
        except Exception as exc:
            logger.warning("Gemini intervention suggestion failed: %s", type(exc).__name__)
    return {"source": "fallback", "suggestions": list(fallback)}


def assessment_drafts(flag, *, topic: str | None = None, count: int = 3) -> dict:
    """
    Draft wellness/behavioral items for the flag.

    Gemini gets severity/categories only. The deterministic generator is the
    fallback and also supplies the fixed response scale. Nothing is saved.
    """
    chosen_topic = (topic or "").strip() or (
        f"support after a {flag.severity} concern"
    )
    if gemini_client.configured():
        schema = {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 10,
                }
            },
            "required": ["questions"],
        }
        prompt = (
            f"Write {count} short self-report questions for a student wellness "
            f"check-in about: {chosen_topic}. Severity: {flag.severity}. "
            "Use first person or direct questions. Do not assert facts, do not "
            "diagnose, and do not include names or student records."
        )
        try:
            result = gemini_client.generate_json(
                prompt=prompt,
                schema=schema,
                system_instruction=(
                    "You draft school counseling self-report items. Return only "
                    "questions that a student can answer about themselves."
                ),
            )
            questions = [
                str(item).strip()[:500]
                for item in (result.get("questions") or [])
                if str(item).strip()
            ]
            if questions:
                return {
                    "source": "gemini",
                    "topic": chosen_topic,
                    "drafts": [
                        {
                            "question_text": question,
                            "question_type": "essay",
                            "options": None,
                            "correct_answer": None,
                        }
                        for question in questions[:count]
                    ],
                }
        except Exception as exc:
            logger.warning("Gemini assessment draft failed: %s", type(exc).__name__)

    try:
        result = generate_question_drafts(
            topic=chosen_topic,
            question_type="likert",
            count=max(1, min(count, 10)),
            family="concern",
        )
    except Exception:
        result = {"drafts": []}
    return {"source": "fallback", "topic": chosen_topic, "drafts": result["drafts"]}
