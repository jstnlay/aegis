"""
Assessments ViewSets.

Provides scoped querysets per role and enforces both role-level
and data-scope permissions as required by Phase 6 authorization rules.
"""

from django.db import transaction
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Assessment, AssessmentQuestion, AssessmentResult
from .serializers import (
    AssessmentSerializer,
    AssessmentListSerializer,
    AssessmentQuestionSerializer,
    AssessmentResultSerializer,
    AssessmentResultListSerializer,
)
from .permissions import (
    IsAssessmentCreator,
    CanCreateAssessment,
    CanViewAssessmentResult,
    CanSubmitAssessment,
)
from .utils import (
    auto_grade_assessment,
    notify_assessment_deployment,
    notify_assessment_completion,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_student_profile(user):
    """Return the StudentProfile for the given user, or None."""
    try:
        return user.student_profile
    except Exception:
        return None


def _get_parent_profile(user):
    """Return the ParentProfile for the given user, or None."""
    try:
        return user.parent_profile
    except Exception:
        return None


def _get_linked_student_ids(user):
    """Return a set of StudentProfile IDs linked to this parent."""
    from apps.accounts.models import ParentStudentLink
    
    try:
        parent_profile = user.parent_profile
    except Exception:
        return set()
    return set(
        ParentStudentLink.objects.filter(parent=parent_profile).values_list(
            "student_id", flat=True
        )
    )


# ---------------------------------------------------------------------------
# Assessment ViewSet
# ---------------------------------------------------------------------------

class AssessmentViewSet(viewsets.ModelViewSet):
    """
    CRUD for Assessments.
    
    Faculty can create and manage academic assessments.
    Guidance can create and manage wellness/behavioral assessments.
    Students can view published assessments assigned to them.
    Parents can view published assessments assigned to their children.
    """
    
    queryset = Assessment.objects.all()
    serializer_class = AssessmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        """Dynamic permissions based on action."""
        if self.action == 'create':
            return [IsAuthenticated(), CanCreateAssessment()]
        elif self.action in ['update', 'partial_update', 'destroy', 'deploy']:
            return [IsAuthenticated(), IsAssessmentCreator()]
        return [IsAuthenticated()]
    
    def get_serializer_class(self):
        """Use list serializer for list action."""
        if self.action == 'list':
            return AssessmentListSerializer
        return AssessmentSerializer
    
    def get_queryset(self):
        """Scope assessments by role."""
        user = self.request.user
        
        # Admins see all assessments
        if user.role == "admin":
            return Assessment.objects.all()
        
        # Faculty see their own academic assessments
        if user.role == "faculty":
            return Assessment.objects.filter(
                created_by=user,
                assessment_type="academic"
            )
        
        # Guidance see their own wellness/behavioral assessments
        if user.role == "guidance":
            return Assessment.objects.filter(
                created_by=user,
                assessment_type__in=["wellness", "behavioral"]
            )
        
        # Students see published assessments assigned to them
        if user.role == "student":
            student_profile = _get_student_profile(user)
            if not student_profile:
                return Assessment.objects.none()
            
            # Published assessments where:
            # - student is explicitly targeted, OR
            # - student's section is targeted (and no explicit students), OR
            # - no sections and no students (but this shouldn't happen per spec)
            from django.db.models import Q
            return Assessment.objects.filter(
                is_published=True
            ).filter(
                Q(target_students=student_profile) |
                Q(target_sections=student_profile.section, target_students__isnull=True)
            ).distinct()
        
        # Parents see published assessments assigned to their children
        if user.role == "parent":
            linked_student_ids = _get_linked_student_ids(user)
            if not linked_student_ids:
                return Assessment.objects.none()
            
            # Get sections of linked students
            from apps.accounts.models import StudentProfile
            linked_section_ids = StudentProfile.objects.filter(
                id__in=linked_student_ids
            ).values_list('section_id', flat=True)
            
            from django.db.models import Q
            return Assessment.objects.filter(
                is_published=True
            ).filter(
                Q(target_students__id__in=linked_student_ids) |
                Q(target_sections__id__in=linked_section_ids, target_students__isnull=True)
            ).distinct()
        
        return Assessment.objects.none()
    
    def perform_destroy(self, instance):
        """Only allow deletion of unpublished assessments."""
        if instance.is_published:
            raise serializers.ValidationError({
                "detail": "Published assessments cannot be deleted."
            })
        instance.delete()
    
    @action(detail=True, methods=['post'])
    def deploy(self, request, pk=None):
        """
        Deploy (publish) an assessment and dispatch notifications.

        POST /api/v1/assessments/assessments/{id}/deploy/
        Sets is_published=True, published_at=now, then dispatches
        ASSESSMENT_DEPLOYED to target students and their parents.
        """
        assessment = self.get_object()

        if assessment.is_published:
            return Response(
                {"detail": "Assessment is already published."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validation gate: required questions must exist before deployment
        if not assessment.questions.exists():
            return Response(
                {"detail": "Cannot publish assessment without questions."},
                status=status.HTTP_400_BAD_REQUEST
            )

        assessment.is_published = True
        assessment.save()

        # Dispatch ASSESSMENT_DEPLOYED (EVT-05)
        notify_assessment_deployment(assessment)

        serializer = self.get_serializer(assessment)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# AssessmentQuestion ViewSet
# ---------------------------------------------------------------------------

class AssessmentQuestionViewSet(viewsets.ModelViewSet):
    """
    CRUD for AssessmentQuestions.
    
    Only the assessment creator can manage questions.
    """
    
    queryset = AssessmentQuestion.objects.all()
    serializer_class = AssessmentQuestionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Scope questions by assessment ownership."""
        user = self.request.user
        
        # Admins see all questions
        if user.role == "admin":
            return AssessmentQuestion.objects.all()
        
        # Faculty/guidance see questions for their own assessments
        if user.role in ["faculty", "guidance"]:
            return AssessmentQuestion.objects.filter(
                assessment__created_by=user
            )
        
        # Students see questions for published assessments assigned to them
        if user.role == "student":
            student_profile = _get_student_profile(user)
            if not student_profile:
                return AssessmentQuestion.objects.none()
            
            from django.db.models import Q
            return AssessmentQuestion.objects.filter(
                assessment__is_published=True
            ).filter(
                Q(assessment__target_students=student_profile) |
                Q(assessment__target_sections=student_profile.section, assessment__target_students__isnull=True)
            ).distinct()
        
        return AssessmentQuestion.objects.none()
    
    def perform_create(self, serializer):
        """Prevent non-creators from adding questions; block published assessments."""
        user = self.request.user
        assessment = serializer.validated_data.get('assessment')

        # Only the assessment creator (or an admin) may add questions.
        if assessment and user.role != "admin" and assessment.created_by != user:
            raise PermissionDenied(
                {"detail": "Only the assessment creator can add questions."}
            )

        if assessment and assessment.is_published:
            raise serializers.ValidationError({
                "assessment": "Cannot add questions to published assessments."
            })
        serializer.save()

    def perform_update(self, serializer):
        """Prevent updating questions in published assessments."""
        if serializer.instance.assessment.is_published:
            raise serializers.ValidationError({
                "detail": "Cannot modify questions in published assessments."
            })
        serializer.save()

    def perform_destroy(self, instance):
        """Prevent deleting questions from published assessments."""
        if instance.assessment.is_published:
            raise serializers.ValidationError({
                "detail": "Cannot delete questions from published assessments."
            })
        instance.delete()


# ---------------------------------------------------------------------------
# AssessmentResult ViewSet
# ---------------------------------------------------------------------------

class AssessmentResultViewSet(viewsets.ModelViewSet):
    """
    CRUD for AssessmentResults.
    
    Students can submit results for assessments assigned to them.
    Faculty/guidance can view results for assessments they created.
    Parents can view results for their children.
    """
    
    queryset = AssessmentResult.objects.all()
    serializer_class = AssessmentResultSerializer
    permission_classes = [IsAuthenticated, CanViewAssessmentResult]
    
    def get_permissions(self):
        """Dynamic permissions based on action."""
        if self.action == 'create':
            return [IsAuthenticated(), CanSubmitAssessment()]
        return [IsAuthenticated(), CanViewAssessmentResult()]
    
    def get_serializer_class(self):
        """Use list serializer for list action."""
        if self.action == 'list':
            return AssessmentResultListSerializer
        return AssessmentResultSerializer
    
    def get_queryset(self):
        """Scope results by role."""
        user = self.request.user
        
        # Admins see all results
        if user.role == "admin":
            return AssessmentResult.objects.all()
        
        # Faculty/guidance see results for assessments they created
        if user.role in ["faculty", "guidance"]:
            return AssessmentResult.objects.filter(
                assessment__created_by=user
            )
        
        # Students see their own results
        if user.role == "student":
            student_profile = _get_student_profile(user)
            if not student_profile:
                return AssessmentResult.objects.none()
            return AssessmentResult.objects.filter(student=student_profile)
        
        # Parents see results for their children
        if user.role == "parent":
            linked_student_ids = _get_linked_student_ids(user)
            if not linked_student_ids:
                return AssessmentResult.objects.none()
            return AssessmentResult.objects.filter(
                student_id__in=linked_student_ids
            )
        
        return AssessmentResult.objects.none()
    
    def _assert_not_completed(self, result):
        """Raise if the result is completed (SEC-008 immutability boundary).

        Admins are exempt — they retain full data-management access consistent
        with their existing permission model across all assessment endpoints.
        """
        if result.status == AssessmentResult.Status.COMPLETED:
            if self.request.user.role != "admin":
                raise serializers.ValidationError({
                    "detail": "Completed assessment results cannot be modified or deleted."
                })

    def update(self, request, *args, **kwargs):
        """Block update on completed results (SEC-008)."""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        self._assert_not_completed(instance)
        return super().update(request, *args, partial=partial, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Block patch on completed results (SEC-008)."""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        """Block deletion of completed results (SEC-008)."""
        self._assert_not_completed(instance)
        instance.delete()

    @transaction.atomic
    def perform_create(self, serializer):
        """
        Submit an assessment result (student takes the assessment).

        - Validates publication, targeting, and duplicate submissions
        - Auto-grades MC/true_false questions
        - Marks the result completed (status + completed_at)
        - Dispatches ASSESSMENT_COMPLETED (EVT-06) to the assessment creator
        """
        user = self.request.user
        student_profile = _get_student_profile(user)

        if not student_profile:
            raise serializers.ValidationError({
                "detail": "Only students can submit assessments."
            })

        assessment = serializer.validated_data.get('assessment')

        # Prevent duplicate submissions (one result per student per assessment)
        if AssessmentResult.objects.filter(
            assessment=assessment,
            student=student_profile
        ).exists():
            raise serializers.ValidationError({
                "detail": "You have already submitted this assessment."
            })

        # Cannot submit an unpublished assessment
        if not assessment.is_published:
            raise serializers.ValidationError({
                "detail": "Cannot submit unpublished assessment."
            })

        # Student must be targeted by this assessment
        from django.db.models import Q
        is_targeted = Assessment.objects.filter(
            id=assessment.id
        ).filter(
            Q(target_students=student_profile) |
            Q(target_sections=student_profile.section, target_students__isnull=True)
        ).exists()

        if not is_targeted:
            raise serializers.ValidationError({
                "detail": "This assessment is not assigned to you."
            })

        # Save, auto-grade, and mark completed
        result = serializer.save(student=student_profile)
        auto_grade_assessment(result)
        result.status = AssessmentResult.Status.COMPLETED
        result.save()

        # Dispatch ASSESSMENT_COMPLETED (EVT-06) to the creator
        notify_assessment_completion(result)
