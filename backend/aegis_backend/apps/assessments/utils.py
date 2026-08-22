"""
Utility functions for assessments.

Auto-grading and notification dispatch.

Auto-grading model (per approved specification):
  - Only multiple_choice and true_false questions are auto-gradable.
  - Each auto-gradable question with a defined correct_answer is worth
    exactly one (1) point.
  - essay and likert questions are never auto-graded.
"""

from decimal import Decimal

from apps.notifications.events import dispatch_event

AUTO_GRADABLE_TYPES = ("multiple_choice", "true_false")


def auto_grade_assessment(result):
    """
    Auto-grade an assessment result for multiple_choice and true_false questions.

    Scoring: each auto-gradable question with a defined correct_answer is
    worth 1 point. score = number of correct answers, total_possible =
    number of auto-gradable questions with a correct_answer. percentage is
    computed when total_possible > 0.

    Updates result.score, result.total_possible and result.percentage in
    place. Does NOT save the result.

    Args:
        result: AssessmentResult instance with answers populated
    """
    earned_score = Decimal("0")
    total_possible = Decimal("0")

    for question in result.assessment.questions.all():
        # Only auto-grade supported types with an answer key
        if question.question_type not in AUTO_GRADABLE_TYPES:
            continue
        if not question.correct_answer:
            continue

        total_possible += Decimal("1")

        student_answer = result.answers.get(str(question.id))
        if student_answer is not None and str(student_answer) == question.correct_answer:
            earned_score += Decimal("1")

    result.score = earned_score
    result.total_possible = total_possible
    if total_possible > 0:
        result.percentage = (earned_score / total_possible * Decimal("100")).quantize(
            Decimal("0.01")
        )


def _get_targeted_students(assessment):
    """Return the set of StudentProfiles this assessment is deployed to."""
    from apps.accounts.models import StudentProfile

    # Explicit student targeting overrides section targeting
    if assessment.target_students.exists():
        return set(assessment.target_students.all())

    if assessment.target_sections.exists():
        students = set()
        for section in assessment.target_sections.all():
            students.update(
                StudentProfile.objects.filter(section=section, is_active=True)
            )
        return students

    return set()


def notify_assessment_deployment(assessment):
    """
    Dispatch notifications when an assessment is published/deployed.

    DOMAIN EVENT: ASSESSMENT_DEPLOYED (EVT-05)
    Recipients: Target students + parents of target students.

    Args:
        assessment: Assessment instance that was just published
    """
    for student_profile in _get_targeted_students(assessment):
        dispatch_event(
            event_type="ASSESSMENT_DEPLOYED",
            recipients=[student_profile.user],
            sender=assessment.created_by,
            title=f"New Assessment: {assessment.title}",
            message=(
                f"A new {assessment.get_assessment_type_display().lower()} "
                "assessment has been assigned to you."
            ),
            link=f"/assessments/{assessment.id}",
        )

        # Parents of target students (EVT-05)
        for parent_link in student_profile.parent_links.select_related("parent__user"):
            dispatch_event(
                event_type="ASSESSMENT_DEPLOYED",
                recipients=[parent_link.parent.user],
                sender=assessment.created_by,
                title=f"Assessment Assigned: {assessment.title}",
                message=(
                    f"An assessment has been assigned to "
                    f"{student_profile.user.get_full_name()}."
                ),
                link=f"/assessments/{assessment.id}",
            )


def notify_assessment_completion(result):
    """
    Dispatch notification when a student submits/completes an assessment.

    DOMAIN EVENT: ASSESSMENT_COMPLETED (EVT-06)
    Recipients: Assessment creator only (Faculty/Guidance).

    Args:
        result: AssessmentResult instance that was just submitted
    """
    assessment = result.assessment
    student = result.student

    dispatch_event(
        event_type="ASSESSMENT_COMPLETED",
        recipients=[assessment.created_by],
        sender=student.user,
        title=f"Assessment Completed: {assessment.title}",
        message=f"{student.user.get_full_name()} has completed the assessment.",
        link=f"/assessments/{assessment.id}/results/{result.id}",
    )
