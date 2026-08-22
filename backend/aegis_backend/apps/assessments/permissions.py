"""
Permissions for assessments.

Role-based and object-level permissions for assessments, questions, and results.
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAssessmentCreator(BasePermission):
    """
    Object-level: Only the creator (faculty/guidance) can modify their assessments.
    Admins can access all assessments.
    """
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admins have full access
        if request.user.role == "admin":
            return True
        
        # Creator can modify their own assessments
        if request.method in SAFE_METHODS:
            # Read access: creator and students who are targeted
            return obj.created_by == request.user or self._is_targeted_student(request.user, obj)
        
        # Write access: only creator
        return obj.created_by == request.user
    
    def _is_targeted_student(self, user, assessment):
        """Check if user is a student targeted by this assessment."""
        if user.role != "student":
            return False
        
        try:
            student_profile = user.student_profile
        except Exception:
            return False
        
        # Check if student is explicitly targeted
        if assessment.target_students.filter(id=student_profile.id).exists():
            return True
        
        # Check if student's section is targeted
        if student_profile.section:
            return assessment.target_sections.filter(id=student_profile.section_id).exists()
        
        return False


class CanCreateAssessment(BasePermission):
    """
    Permission to create assessments.
    
    Faculty can create academic assessments.
    Guidance can create wellness/behavioral assessments.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admins can create any assessment
        if request.user.role == "admin":
            return True
        
        # Faculty and guidance can create assessments
        return request.user.role in ["faculty", "guidance"]


class CanViewAssessmentResult(BasePermission):
    """
    Object-level: Control who can view assessment results.
    
    - Students can view their own results
    - Parents can view their children's results
    - Faculty/guidance can view results for assessments they created
    - Admins can view all results
    """
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admins have full access
        if request.user.role == "admin":
            return True
        
        # Assessment creator can view results
        if obj.assessment.created_by == request.user:
            return True
        
        # Student can view their own result
        if request.user.role == "student":
            try:
                student_profile = request.user.student_profile
                return obj.student_id == student_profile.id
            except Exception:
                return False
        
        # Parent can view their child's result
        if request.user.role == "parent":
            try:
                parent_profile = request.user.parent_profile
                from apps.accounts.models import ParentStudentLink
                return ParentStudentLink.objects.filter(
                    parent=parent_profile,
                    student_id=obj.student_id
                ).exists()
            except Exception:
                return False
        
        return False


class CanSubmitAssessment(BasePermission):
    """
    Permission to submit an assessment result.
    
    Only students can submit assessments assigned to them.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Only students can submit assessments
        return request.user.role == "student"
