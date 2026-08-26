"""
Academics ViewSets.

Provides scoped querysets per role and enforces both role-level
and data-scope permissions as required by Phase 2 authorization rules.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import (
    IsAdminUser,
    IsAdminOrReadOnly,
    IsFacultyUser,
    IsFacultyOwnerOfAssignment,
    IsStudentUser,
    IsParentUser,
    IsParentOfStudent,
    IsStudentOwnData,
)

from .models import (
    AcademicYear,
    Enrollment,
    Grade,
    GradeLevel,
    GradingPeriod,
    Schedule,
    Section,
    Subject,
    SubjectAssignment,
)
from .serializers import (
    AcademicYearSerializer,
    EnrollmentSerializer,
    GradeEncodeSerializer,
    GradeSerializer,
    GradeLevelSerializer,
    GradingPeriodSerializer,
    ScheduleSerializer,
    SectionSerializer,
    SubjectAssignmentSerializer,
    SubjectSerializer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_faculty_profile(user):
    """Return the FacultyProfile for the given user, or None."""
    try:
        return user.faculty_profile
    except Exception:
        return None


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
        return False
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
# AcademicYear ViewSet
# ---------------------------------------------------------------------------


class AcademicYearViewSet(viewsets.ModelViewSet):
    """
    CRUD for AcademicYears.

    - Admin: full CRUD
    - Faculty/Guidance/Student/Parent: read-only (list/retrieve)
    """

    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [IsAdminOrReadOnly]


# ---------------------------------------------------------------------------
# GradeLevel ViewSet
# ---------------------------------------------------------------------------


class GradeLevelViewSet(viewsets.ModelViewSet):
    """
    CRUD for GradeLevels.

    - Admin: full CRUD
    - Faculty/Guidance: read-only
    - Student/Parent: read-only
    """

    queryset = GradeLevel.objects.all()
    serializer_class = GradeLevelSerializer
    permission_classes = [IsAdminOrReadOnly]


# ---------------------------------------------------------------------------
# Section ViewSet
# ---------------------------------------------------------------------------


class SectionViewSet(viewsets.ModelViewSet):
    """
    CRUD for Sections.

    - Admin: full CRUD, sees all
    - Faculty: read-only, sees sections they advise or teach
    - Guidance: read-only, sees all sections
    - Student: read-only, sees own section only
    - Parent: read-only, sees linked children's sections
    """

    serializer_class = SectionSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        qs = Section.objects.select_related("grade_level", "adviser__user", "academic_year").all()

        if user.role == "admin":
            return qs
        if user.role == "guidance":
            return qs
        if user.role == "faculty":
            fp = _get_faculty_profile(user)
            if fp is None:
                return Section.objects.none()
            return qs.filter(
                models_Q_or_faculty_sections(fp)
            ).distinct()
        if user.role == "student":
            sp = _get_student_profile(user)
            if sp is None:
                return Section.objects.none()
            return qs.filter(pk=sp.section_id) if sp.section_id else Section.objects.none()
        if user.role == "parent":
            student_ids = _get_linked_student_ids(user)
            if not student_ids:
                return Section.objects.none()
            from apps.accounts.models import StudentProfile
            section_ids = StudentProfile.objects.filter(
                pk__in=student_ids
            ).values_list("section_id", flat=True)
            return qs.filter(pk__in=section_ids).distinct()
        return Section.objects.none()


def models_Q_or_faculty_sections(faculty_profile):
    """Build a Q object for sections a faculty is associated with."""
    from django.db.models import Q

    q = Q(adviser=faculty_profile)
    q |= Q(subject_assignments__faculty=faculty_profile)
    return q


# ---------------------------------------------------------------------------
# Subject ViewSet
# ---------------------------------------------------------------------------


class SubjectViewSet(viewsets.ModelViewSet):
    """
    CRUD for Subjects.

    - Admin: full CRUD
    - Faculty/Guidance: read-only
    - Student/Parent: read-only
    """

    queryset = Subject.objects.select_related("grade_level").all()
    serializer_class = SubjectSerializer
    permission_classes = [IsAdminOrReadOnly]


# ---------------------------------------------------------------------------
# SubjectAssignment ViewSet
# ---------------------------------------------------------------------------


class SubjectAssignmentViewSet(viewsets.ModelViewSet):
    """
    CRUD for SubjectAssignments.

    - Admin: full CRUD, sees all
    - Faculty: read-only, sees only own assignments
    - Guidance: read-only, sees all
    - Student/Parent: read-only, sees assignments for enrolled sections
    """

    serializer_class = SubjectAssignmentSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        qs = SubjectAssignment.objects.select_related(
            "subject", "faculty__user", "section", "academic_year"
        ).all()

        if user.role == "admin":
            return qs
        if user.role == "guidance":
            return qs
        if user.role == "faculty":
            fp = _get_faculty_profile(user)
            if fp is None:
                return SubjectAssignment.objects.none()
            return qs.filter(faculty=fp)
        if user.role == "student":
            sp = _get_student_profile(user)
            if sp is None or sp.section_id is None:
                return SubjectAssignment.objects.none()
            return qs.filter(section_id=sp.section_id)
        if user.role == "parent":
            student_ids = _get_linked_student_ids(user)
            if not student_ids:
                return SubjectAssignment.objects.none()
            from apps.accounts.models import StudentProfile
            section_ids = StudentProfile.objects.filter(
                pk__in=student_ids
            ).values_list("section_id", flat=True)
            return qs.filter(section_id__in=section_ids).distinct()
        return SubjectAssignment.objects.none()


# ---------------------------------------------------------------------------
# Schedule ViewSet
# ---------------------------------------------------------------------------


class ScheduleViewSet(viewsets.ModelViewSet):
    """
    CRUD for Schedules.

    - Admin: full CRUD, sees all
    - Faculty: read-only, sees schedules for own assignments
    - Guidance: read-only, sees all
    - Student: read-only, sees schedules for own section
    - Parent: read-only, sees linked children's section schedules
    """

    serializer_class = ScheduleSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        qs = Schedule.objects.select_related(
            "subject_assignment__subject",
            "subject_assignment__faculty__user",
            "subject_assignment__section",
            "subject_assignment__academic_year",
        ).all()

        if user.role == "admin":
            return qs
        if user.role == "guidance":
            return qs
        if user.role == "faculty":
            fp = _get_faculty_profile(user)
            if fp is None:
                return Schedule.objects.none()
            return qs.filter(subject_assignment__faculty=fp)
        if user.role == "student":
            sp = _get_student_profile(user)
            if sp is None or sp.section_id is None:
                return Schedule.objects.none()
            return qs.filter(subject_assignment__section_id=sp.section_id)
        if user.role == "parent":
            student_ids = _get_linked_student_ids(user)
            if not student_ids:
                return Schedule.objects.none()
            from apps.accounts.models import StudentProfile
            section_ids = StudentProfile.objects.filter(
                pk__in=student_ids
            ).values_list("section_id", flat=True)
            return qs.filter(
                subject_assignment__section_id__in=section_ids
            ).distinct()
        return Schedule.objects.none()


# ---------------------------------------------------------------------------
# GradingPeriod ViewSet
# ---------------------------------------------------------------------------


class GradingPeriodViewSet(viewsets.ModelViewSet):
    """
    CRUD for GradingPeriods.

    - Admin: full CRUD
    - Faculty/Guidance: read-only
    - Student/Parent: read-only
    """

    queryset = GradingPeriod.objects.select_related("academic_year").all()
    serializer_class = GradingPeriodSerializer
    permission_classes = [IsAdminOrReadOnly]


# ---------------------------------------------------------------------------
# Enrollment ViewSet
# ---------------------------------------------------------------------------


class EnrollmentViewSet(viewsets.ModelViewSet):
    """
    CRUD for Enrollments.

    - Admin: full CRUD, sees all
    - Faculty: read-only, sees enrollments for advisory/assigned sections
    - Guidance: read-only, sees all
    - Student: read-only, sees own enrollments
    - Parent: read-only, sees linked children's enrollments
    """

    serializer_class = EnrollmentSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        qs = Enrollment.objects.select_related(
            "student__user", "section", "academic_year"
        ).all()

        if user.role == "admin":
            return qs
        if user.role == "guidance":
            return qs
        if user.role == "faculty":
            fp = _get_faculty_profile(user)
            if fp is None:
                return Enrollment.objects.none()
            return qs.filter(
                models_Q_or_enrollment_sections(fp)
            ).distinct()
        if user.role == "student":
            sp = _get_student_profile(user)
            if sp is None:
                return Enrollment.objects.none()
            return qs.filter(student=sp)
        if user.role == "parent":
            student_ids = _get_linked_student_ids(user)
            if not student_ids:
                return Enrollment.objects.none()
            return qs.filter(student_id__in=student_ids)
        return Enrollment.objects.none()


def models_Q_or_enrollment_sections(faculty_profile):
    """Build a Q for enrollments visible to a faculty member."""
    from django.db.models import Q

    q = Q(section__adviser=faculty_profile)
    q |= Q(section__subject_assignments__faculty=faculty_profile)
    return q


# ---------------------------------------------------------------------------
# Grade ViewSet
# ---------------------------------------------------------------------------


class GradeViewSet(viewsets.ModelViewSet):
    """
    CRUD + custom actions for Grades.

    - Admin: full CRUD, sees all
    - Faculty: create/update own grades; sees grades for own subject assignments
    - Guidance: read-only, sees all
    - Student: read-only, sees own grades only
    - Parent: read-only, sees linked children's grades only

    Custom actions:
    - POST /grades/encode/ — Faculty encodes a single grade
    """

    serializer_class = GradeSerializer

    def get_permissions(self):
        if self.action in ("encode", "batch_import"):
            return [IsFacultyUser()]
        if self.action in ("finalize",):
            return [IsAdminUser()]
        return [IsAdminOrReadOnly()]

    def get_queryset(self):
        user = self.request.user
        qs = Grade.objects.select_related(
            "student__user",
            "subject_assignment__subject",
            "subject_assignment__section",
            "grading_period",
            "encoded_by__user",
        ).all()

        # Query-parameter filtering (A6)
        student_id = self.request.query_params.get("student")
        subject_assignment_id = self.request.query_params.get("subject_assignment")
        grading_period_id = self.request.query_params.get("grading_period")
        grade_status = self.request.query_params.get("status")

        if student_id:
            qs = qs.filter(student_id=student_id)
        if subject_assignment_id:
            qs = qs.filter(subject_assignment_id=subject_assignment_id)
        if grading_period_id:
            qs = qs.filter(grading_period_id=grading_period_id)
        if grade_status:
            qs = qs.filter(status=grade_status)

        if user.role == "admin":
            return qs
        if user.role == "guidance":
            return qs
        if user.role == "faculty":
            fp = _get_faculty_profile(user)
            if fp is None:
                return Grade.objects.none()
            return qs.filter(subject_assignment__faculty=fp)
        if user.role == "student":
            sp = _get_student_profile(user)
            if sp is None:
                return Grade.objects.none()
            return qs.filter(student=sp)
        if user.role == "parent":
            student_ids = _get_linked_student_ids(user)
            if not student_ids:
                return Grade.objects.none()
            return qs.filter(student_id__in=student_ids)
        return Grade.objects.none()

    def perform_create(self, serializer):
        fp = _get_faculty_profile(self.request.user)
        serializer.save(encoded_by=fp)

    @action(detail=False, methods=["post"], url_path="encode")
    def encode(self, request):
        """
        POST /grades/encode/
        Faculty encodes a single grade. Creates a new Grade in draft status.
        """
        serializer = GradeEncodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        fp = _get_faculty_profile(request.user)
        if fp is None:
            return Response(
                {"detail": "No faculty profile found."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Validate the subject assignment belongs to this faculty
        try:
            sa = SubjectAssignment.objects.get(pk=data["subject_assignment"])
        except SubjectAssignment.DoesNotExist:
            return Response(
                {"detail": "Subject assignment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if sa.faculty_id != fp.id:
            return Response(
                {"detail": "You are not assigned to this subject assignment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Validate the grading period exists
        try:
            gp = GradingPeriod.objects.get(pk=data["grading_period"])
        except GradingPeriod.DoesNotExist:
            return Response(
                {"detail": "Grading period not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Validate the student exists
        from apps.accounts.models import StudentProfile
        try:
            student = StudentProfile.objects.get(pk=data["student"])
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # SEC-013: Grading period must belong to same academic year
        if gp.academic_year_id != sa.academic_year_id:
            return Response(
                {"detail": "Grading period does not belong to the same academic year as the subject assignment."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # SEC-013: Student must have valid enrollment for this section/academic year
        if not Enrollment.objects.filter(
            student=student,
            section=sa.section,
            academic_year=sa.academic_year,
            is_active=True,
        ).exists():
            return Response(
                {"detail": "Student is not enrolled in the section for this subject assignment's academic year."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check uniqueness
        if Grade.objects.filter(
            student=student,
            subject_assignment=sa,
            grading_period=gp,
        ).exists():
            return Response(
                {"detail": "A grade already exists for this student, subject assignment, and grading period."},
                status=status.HTTP_409_CONFLICT,
            )

        grade = Grade.objects.create(
            student=student,
            subject_assignment=sa,
            grading_period=gp,
            score=data.get("score"),
            letter_grade=data.get("letter_grade"),
            remarks=data.get("remarks"),
            encoded_by=fp,
            status=Grade.StatusChoices.DRAFT,
        )

        output = GradeSerializer(grade, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="finalize")
    def finalize(self, request, pk=None):
        """
        POST /grades/{id}/finalize/
        Admin finalizes a grade. Changes status from submitted to finalized.
        """
        grade = self.get_object()
        if grade.status != Grade.StatusChoices.SUBMITTED:
            return Response(
                {"detail": "Only submitted grades can be finalized."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        grade.status = Grade.StatusChoices.FINALIZED
        grade.save()

        # GRADE_POSTED notification (EVT-01)
        from apps.notifications.events import dispatch_event
        from apps.accounts.models import ParentStudentLink

        student_user = grade.student.user
        parent_links = ParentStudentLink.objects.filter(
            student=grade.student
        ).select_related("parent__user")
        recipients = [student_user] + [pl.parent.user for pl in parent_links]

        dispatch_event(
            "GRADE_POSTED",
            recipients=recipients,
            sender=None,
            title="Grade Posted",
            message=f"Your grade for {grade.subject_assignment.subject.name} has been finalized.",
            link=f"/academics/grades/{grade.id}",
        )

        output = GradeSerializer(grade, context={"request": request})
        return Response(output.data)

    @action(detail=False, methods=["post"], url_path="batch-import")
    def batch_import(self, request):
        """
        POST /grades/batch-import/
        Placeholder for future batch grade import.
        Returns 501 for now; full implementation deferred to data_import.
        """
        return Response(
            {"detail": "Batch import not yet implemented. Use /data-import/ when available."},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )
