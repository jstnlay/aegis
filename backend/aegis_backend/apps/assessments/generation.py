"""
Faculty assessment drafting.

The assistant proposes an academic assessment and its questions. Nothing is
published: the assessment is created as an AI-generated draft with
``review_status="pending"`` and a faculty member must approve it through the
review endpoint before deployment. That gate lives on the model as well
(``Assessment.clean``), so a later code path cannot bypass it.

Privacy: Gemini receives the teacher's topic and the requested question type.
It never receives a student name, student number, section roster or grade.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.chatbot import gemini_client
from apps.chatbot.question_generator import (
    GENERATABLE_TYPES,
    QuestionGenerationError,
    generate_question_drafts,
)
from apps.assessments.models import Assessment, AssessmentQuestion

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 20


class AssessmentGenerationError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _gemini_questions(topic: str, question_type: str, count: int) -> list[dict]:
    if not gemini_client.configured():
        return []
    schema = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_QUESTIONS,
                "items": {
                    "type": "object",
                    "properties": {
                        "question_text": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "correct_answer": {"type": "string"},
                    },
                    "required": ["question_text"],
                },
            }
        },
        "required": ["questions"],
    }
    prompt = (
        f"Write {count} academic assessment questions about: {topic}. "
        f"Question type: {question_type}. "
        "Do not include names, student records or invented facts about a "
        "person. Return only the questions."
    )
    try:
        result = gemini_client.generate_json(
            prompt=prompt,
            schema=schema,
            system_instruction=(
                "You draft academic assessment questions for a teacher to "
                "review. Return questions only, never student data."
            ),
        )
    except Exception as exc:
        logger.warning("Gemini assessment generation failed: %s", type(exc).__name__)
        return []

    drafts = []
    for item in (result.get("questions") or [])[:count]:
        text = str(item.get("question_text") or "").strip()
        if not text:
            continue
        options = item.get("options")
        if question_type in ("multiple_choice", "likert"):
            if not isinstance(options, list) or len(options) < 2:
                continue
            options = [str(option).strip()[:200] for option in options if str(option).strip()]
            if len(options) < 2:
                continue
        else:
            options = None
        correct = str(item.get("correct_answer") or "").strip() or None
        if correct and options and correct not in options:
            correct = None
        drafts.append(
            {
                "question_text": text[:2000],
                "options": options,
                "correct_answer": correct,
            }
        )
    return drafts


def _deterministic_questions(topic: str, question_type: str, count: int) -> list[dict]:
    result = generate_question_drafts(
        topic=topic,
        question_type=question_type,
        count=count,
        family="academic",
    )
    return result["drafts"]


def generate_academic_assessment(
    *,
    user,
    title: str,
    topic: str,
    question_type: str = "multiple_choice",
    count: int = 5,
    target_sections=None,
    target_students=None,
) -> tuple[Assessment, str]:
    """Create an unreviewed AI draft. Returns ``(assessment, source)``."""
    if question_type not in GENERATABLE_TYPES:
        raise AssessmentGenerationError(
            "QUESTION_TYPE_UNSUPPORTED",
            "Drafting supports multiple_choice, likert and essay.",
        )
    if count < 1 or count > MAX_QUESTIONS:
        raise AssessmentGenerationError(
            "QUESTION_COUNT_INVALID",
            f"count must be between 1 and {MAX_QUESTIONS}.",
        )

    cleaned_topic = " ".join(topic.split()).strip()
    cleaned_title = " ".join(title.split()).strip() or cleaned_topic
    if not cleaned_topic:
        raise AssessmentGenerationError("TOPIC_REQUIRED", "topic must not be empty.")

    questions = _gemini_questions(cleaned_topic, question_type, count)
    source = "gemini"
    if not questions:
        try:
            questions = _deterministic_questions(cleaned_topic, question_type, count)
        except QuestionGenerationError as exc:
            raise AssessmentGenerationError(exc.code, exc.detail) from exc
        source = "fallback"

    with transaction.atomic():
        assessment = Assessment.objects.create(
            title=cleaned_title[:255],
            description=(
                f"AI-generated draft about {cleaned_topic}. Review every "
                "question before publishing."
            ),
            assessment_type=Assessment.AssessmentType.ACADEMIC,
            creator_role=Assessment.CreatorRole.FACULTY,
            created_by=user,
            ai_generated=True,
            review_status=Assessment.ReviewStatus.PENDING,
        )
        if target_sections:
            assessment.target_sections.set(target_sections)
        if target_students:
            assessment.target_students.set(target_students)

        AssessmentQuestion.objects.bulk_create(
            [
                AssessmentQuestion(
                    assessment=assessment,
                    question_text=draft["question_text"],
                    question_type=question_type,
                    order=index,
                    options=draft.get("options"),
                    correct_answer=draft.get("correct_answer"),
                )
                for index, draft in enumerate(questions, start=1)
            ]
        )

    return assessment, source


def review_assessment(
    assessment: Assessment,
    *,
    reviewer,
    decision: str,
    note: str = "",
) -> Assessment:
    """Record a human review decision. Approval is required before publishing."""
    if decision not in (
        Assessment.ReviewStatus.APPROVED,
        Assessment.ReviewStatus.CHANGES_REQUESTED,
    ):
        raise ValueError("decision must be approved or changes_requested.")
    assessment.review_status = decision
    assessment.reviewed_by = reviewer
    assessment.reviewed_at = timezone.now()
    assessment.review_note = note.strip()
    assessment.save(
        update_fields=[
            "review_status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "updated_at",
        ]
    )
    return assessment
