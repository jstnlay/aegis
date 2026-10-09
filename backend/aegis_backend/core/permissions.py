from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == "admin"


class IsFacultyUser(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == "faculty"


class IsGuidanceUser(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == "guidance"


class IsStudentUser(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == "student"


class IsParentUser(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == "parent"


class IsStaffOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ("faculty", "guidance", "admin")


class IsFacultyOrAdminUser(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ("faculty", "admin")


class IsAdminOrReadOnly(BasePermission):
    """Admin can perform any method; other authenticated users can only read."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role == "admin"


class IsFacultyOwnerOfAssignment(BasePermission):
    """
    Object-level: Faculty can only access SubjectAssignment / Schedule
    objects where they are the assigned faculty.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == "admin":
            return True
        if request.user.role == "faculty":
            try:
                faculty_profile = request.user.faculty_profile
            except Exception:
                return False
            return obj.faculty_id == faculty_profile.id
        return False


class IsFacultyOwnerOfGrade(BasePermission):
    """
    Object-level: Faculty can only update grades for their own subject
    assignments (FR-011).

    `has_permission` is deliberately satisfied for both faculty and admin:
    the authorization decision belongs to the object, so an out-of-scope
    update is a refusal the faculty member can act on (403) rather than a
    404 that hides why the save failed.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in ("faculty", "admin")

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == "admin":
            return True
        if request.user.role == "faculty":
            try:
                faculty_profile = request.user.faculty_profile
            except Exception:
                return False
            return obj.subject_assignment.faculty_id == faculty_profile.id
        return False


class IsStudentOwnData(BasePermission):
    """Object-level: Student can only access their own Grade / Enrollment objects."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == "admin":
            return True
        if request.user.role == "faculty":
            return True
        if request.user.role == "student":
            try:
                student_profile = request.user.student_profile
            except Exception:
                return False
            return obj.student_id == student_profile.id
        return False


class IsParentOfStudent(BasePermission):
    """Object-level: Parent can only access data for their linked children."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == "admin":
            return True
        if request.user.role == "faculty":
            return True
        if request.user.role == "student":
            try:
                student_profile = request.user.student_profile
            except Exception:
                return False
            return obj.student_id == student_profile.id
        if request.user.role == "parent":
            try:
                parent_profile = request.user.parent_profile
            except Exception:
                return False
            from apps.accounts.models import ParentStudentLink

            return ParentStudentLink.objects.filter(
                parent=parent_profile, student_id=obj.student_id
            ).exists()
        return False
