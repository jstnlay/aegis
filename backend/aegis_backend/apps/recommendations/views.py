"""
Recommendation endpoints (PH9 D16/D17/D19 — the HTTP surface ai_engine lacked).

Two endpoints, both thin over the existing `ai_engine` code. Neither invents a
recommendation: `ai_engine/recommender.py` computes the list and this view only
decides whether the caller may see it.

  GET  /api/v1/recommendations/students/{id}/   — a student's recommendations
  POST /api/v1/recommendations/interactions/    — record one interaction

Why this lives in its own app rather than in `analytics`:

`ai_engine` is a pure computation package with no HTTP surface, and
`apps/analytics` was declared in PH9 as the read-only aggregation layer with no
models. Adding a write endpoint (the interaction) beside those read-only
aggregations would blur that boundary, so `recommendations` is a separate app
with one responsibility: the recommendation read/write pair.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class RecommendationsView(APIView):
    """
    GET /api/v1/recommendations/students/{id}/

    Returns the recommendations `ai_engine.recommender.recommend()` produces,
    including which method produced them. The method is returned rather than
    hidden because CF and content-based are materially different claims: CF means
    "peers with a similar interaction history", content-based means "matched
    this student's identified academic need". A caller showing these to a student
    needs to know which one they are reading.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        from django.shortcuts import get_object_or_404

        from apps.accounts.models import StudentProfile
        from apps.cms.models import LearningItem, StudentInteraction
        from ai_engine.recommender import recommend

        student = get_object_or_404(StudentProfile, pk=student_id)

        if not self._may_read(request.user, student):
            return Response(
                {"detail": "Access denied."}, status=status.HTTP_403_FORBIDDEN
            )

        # Every interaction in the school, not just this student's. CF computes
        # item-item similarity across the whole cohort; scoping the matrix to one
        # student would make every similarity zero by construction.
        interactions = list(StudentInteraction.objects.select_related("learning_item"))

        # Only APPROVED + ACTIVE items are recommendable. `LearningItem
        # .is_recommendation_eligible` is that rule; it is applied here rather
        # than inside the recommender because the recommender is also used by
        # offline benchmark code that supplies its own item list.
        learning_items = [
            item
            for item in LearningItem.objects.all()
            if item.is_recommendation_eligible
        ]

        features, prediction = self._student_signals(student)

        result = recommend(
            student,
            interactions,
            learning_items,
            feature_dict=features,
            prediction=prediction,
        )

        return Response({"status": "ok", "data": result})

    @staticmethod
    def _student_signals(student):
        """
        Feature dict + prediction for the content-based path.

        Returns `(features, prediction)`. The prediction is empty when the risk
        engine has not run, because a fabricated risk level would let
        `extract_academic_needs` invent a need. `resolve_recommendations` reads
        needs from the feature dict regardless, so content-based still works off
        real grades and attendance alone.
        """
        from apps.academics.models import AcademicYear, GradingPeriod
        from ai_engine.feature_engine import compute_student_features

        year = (
            AcademicYear.objects.filter(is_current=True)
            .order_by("-start_date")
            .first()
        )
        if year is None:
            return {}, {}

        from datetime import date

        completed = list(
            GradingPeriod.objects.filter(
                academic_year=year, end_date__lte=date.today()
            ).order_by("order")
        )

        features = compute_student_features(student, completed, year)

        # The latest stored RiskScore for this student, if the engine has run.
        # A read-only lookup: nothing here triggers a computation.
        from apps.guidance.models import RiskScore

        latest = (
            RiskScore.objects.filter(student=student)
            .order_by("-computed_at")
            .first()
        )
        if latest is None:
            return features, {}

        return features, {
            "risk_level": latest.risk_level,
            "risk_score": latest.risk_score,
            "explanation": latest.explanation or {},
        }

    @staticmethod
    def _may_read(user, student):
        """
        May this caller read this student's recommendations?

        The ladder matches the one `analytics.views._StudentScopedAnalyticsView`
        enforces, so a caller cannot read a student's metrics but be denied their
        recommendations, or the reverse.

        Guidance and admin are excluded. Recommendations are derived from grades
        and attendance and returned to the student and their family; the
        staff-facing risk surface is `RiskAlert`, which has its own
        acknowledge/escalate lifecycle. Opening this endpoint to staff would
        create a second, read-only view of the same signal with none of that
        lifecycle.
        """
        if user.role == "student":
            return user.student_profile.id == student.id

        if user.role == "parent":
            from apps.accounts.models import ParentStudentLink

            return ParentStudentLink.objects.filter(
                parent=user.parent_profile, student=student
            ).exists()

        return False


class StudentInteractionView(APIView):
    """
    POST /api/v1/recommendations/interactions/

    Records that a student interacted with a learning item. This is the only
    write path into the CF signal, and it exists because `StudentInteraction`
    previously had none — which meant collaborative filtering could never
    populate, so `recommend()` always fell back to content-based.

    A student may record interactions only for themselves. Faculty and guidance
    cannot write interaction signals on a student's behalf, because a preference
    signal attributed to someone who did not express it corrupts the matrix.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.utils import timezone

        from apps.cms.models import LearningItem, StudentInteraction

        if request.user.role != "student":
            return Response(
                {"detail": "Only students can record interactions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        learning_item_id = request.data.get("learning_item")
        interaction_type = request.data.get("interaction_type")

        if not learning_item_id:
            return Response(
                {"detail": "learning_item is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if interaction_type not in dict(StudentInteraction.InteractionType.choices):
            return Response(
                {"detail": "interaction_type is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            item = LearningItem.objects.get(pk=learning_item_id)
        except (LearningItem.DoesNotExist, ValueError, TypeError):
            return Response(
                {"detail": "Learning item not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not item.is_recommendation_eligible:
            # Recording an interaction with an unapproved item would put it in
            # the CF matrix without it being recommendable, so the similarity
            # signal would derive from something the system will never surface.
            return Response(
                {"detail": "That learning item is not available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        interaction = StudentInteraction.objects.create(
            student=request.user.student_profile,
            learning_item=item,
            interaction_type=interaction_type,
            interaction_at=timezone.now(),
        )

        return Response(
            {
                "status": "ok",
                "data": {
                    "id": str(interaction.id),
                    "learning_item": str(item.id),
                    "interaction_type": interaction.interaction_type,
                },
            },
            status=status.HTTP_201_CREATED,
        )