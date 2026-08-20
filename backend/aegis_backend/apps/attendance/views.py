"""
Attendance ViewSets.

Provides scoped querysets per role and enforces both role-level
and data-scope permissions for attendance records.
"""

from django.db.models import Q
from django.db.models import Count
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import (
    IsAdminUser,
    IsAdminOrReadOnly,
    IsFacultyUser,
)

from .models import AttendanceRecord
from .serializers import (
    AttendanceRecordSerializer,
    AttendanceSummarySerializer,
)

# ---------------------------------------------------------------------------
# Attendance domain constants
# ---------------------------------------------------------------------------

# School policy: number of absences that triggers a parent notification.
# Will be replaced by SystemSetting lookup when CMS module is built (Phase 7).
ABSENCE_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Helpers (duplicated from academics — see Decision G: no cross-phase refactoring)
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


def _faculty_section_q(faculty_profile):
    """Build a Q for sections visible to a faculty member."""
    return Q(section__adviser=faculty_profile) | Q(
        section__subject_assignments__faculty=faculty_profile
    )


# ---------------------------------------------------------------------------
# AttendanceRecord ViewSet
# ---------------------------------------------------------------------------


class AttendanceRecordViewSet(viewsets.ModelViewSet):
    """
    CRUD for AttendanceRecords.

    - Faculty: create/update/delete within their scope (own sections)
    - Student: read-only, sees own records only
    - Parent: read-only, sees linked children's records
    - Guidance: read-only, sees all records
    - Admin: read-only, sees all records

    Custom actions:
    - POST /records/batch-import/ — placeholder (501)
    - GET  /summary/              — per-student attendance summary
    """

    serializer_class = AttendanceRecordSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsFacultyUser()]
        if self.action == "batch_import":
            return [IsFacultyUser()]
        # list, retrieve, summary: any authenticated user (scoped queryset handles access)
        from rest_framework.permissions import IsAuthenticated
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = AttendanceRecord.objects.select_related(
            "student__user",
            "section",
            "recorded_by__user",
        ).all()

        # Query-parameter filtering
        student_id = self.request.query_params.get("student")
        section_id = self.request.query_params.get("section")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        rec_status = self.request.query_params.get("status")

        if student_id:
            qs = qs.filter(student_id=student_id)
        if section_id:
            qs = qs.filter(section_id=section_id)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if rec_status:
            qs = qs.filter(status=rec_status)

        if user.role == "admin":
            return qs
        if user.role == "guidance":
            return qs
        if user.role == "faculty":
            fp = _get_faculty_profile(user)
            if fp is None:
                return AttendanceRecord.objects.none()
            return qs.filter(_faculty_section_q(fp)).distinct()
        if user.role == "student":
            sp = _get_student_profile(user)
            if sp is None:
                return AttendanceRecord.objects.none()
            return qs.filter(student=sp)
        if user.role == "parent":
            student_ids = _get_linked_student_ids(user)
            if not student_ids:
                return AttendanceRecord.objects.none()
            return qs.filter(student_id__in=student_ids)
        return AttendanceRecord.objects.none()

    def perform_create(self, serializer):
        fp = _get_faculty_profile(self.request.user)
        serializer.save(recorded_by=fp)

    def perform_update(self, serializer):
        serializer.save()

    def create(self, request, *args, **kwargs):
        """Create a single attendance record."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        fp = _get_faculty_profile(request.user)
        if fp is None:
            return Response(
                {"detail": "No faculty profile found."},
                status=status.HTTP_403_FORBIDDEN,
            )

        student = data["student"]
        section = data["section"]
        record_date = data["date"]

        # Validate student is enrolled in the specified section
        from apps.academics.models import Enrollment, AcademicYear
        from django.utils import timezone

        current_ay = AcademicYear.objects.filter(is_current=True).first()
        if current_ay is None:
            return Response(
                {"detail": "No current academic year configured."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enrollment_exists = Enrollment.objects.filter(
            student=student,
            section=section,
            academic_year=current_ay,
            is_active=True,
        ).exists()
        if not enrollment_exists:
            return Response(
                {"detail": "Student is not actively enrolled in the specified section."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate faculty has access to this section
        from apps.academics.models import SubjectAssignment
        faculty_has_section_access = (
            section.adviser_id == fp.id
            or SubjectAssignment.objects.filter(
                faculty=fp, section=section, academic_year=current_ay
            ).exists()
        )
        if not faculty_has_section_access:
            return Response(
                {"detail": "You do not have access to record attendance for this section."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check duplicate
        if AttendanceRecord.objects.filter(
            student=student, date=record_date
        ).exists():
            return Response(
                {
                    "detail": (
                        "An attendance record already exists for this student "
                        "on the specified date."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        record = AttendanceRecord.objects.create(
            student=student,
            section=section,
            date=record_date,
            status=data["status"],
            recorded_by=fp,
        )

        # ATTENDANCE_THRESHOLD check (EVT-02)
        if record.status == AttendanceRecord.Status.ABSENT:
            academic_year = section.academic_year
            absence_count = AttendanceRecord.objects.filter(
                student=student,
                section__academic_year=academic_year,
                status=AttendanceRecord.Status.ABSENT,
            ).count()

            if absence_count >= ABSENCE_THRESHOLD:
                from apps.notifications.events import dispatch_event
                from apps.accounts.models import ParentStudentLink

                parent_links = ParentStudentLink.objects.filter(
                    student=student
                ).select_related("parent__user")
                recipients = [pl.parent.user for pl in parent_links]

                dedup_key = f"attendance_threshold:{student.id}:{academic_year.id}"

                dispatch_event(
                    "ATTENDANCE_THRESHOLD",
                    recipients=recipients,
                    sender=None,
                    title="Attendance Alert",
                    message=(
                        f"{student.user.get_full_name()} has reached "
                        f"{absence_count} absences this academic year."
                    ),
                    link=f"/attendance/summary?student={student.id}",
                    deduplication_key=dedup_key,
                )

        output = AttendanceRecordSerializer(record, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Faculty can update their own attendance records."""
        instance = self.get_object()
        if instance.recorded_by.user != request.user:
            return Response(
                {"detail": "You can only update attendance records you have created."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """Faculty can delete their own attendance records."""
        instance = self.get_object()
        if instance.recorded_by.user != request.user:
            return Response(
                {"detail": "You can only delete attendance records you have created."},
                status=status.HTTP_403_FORBIDDEN,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="batch-import")
    def batch_import(self, request):
        """
        POST /attendance/records/batch-import/
        Placeholder for future batch attendance import.
        Returns 501 for now; full implementation deferred to data_import.
        """
        return Response(
            {
                "detail": (
                    "Batch import not yet implemented. "
                    "Use /data-import/ when available."
                )
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """
        GET /attendance/summary/

        Returns per-student attendance counts (present, late, absent)
        for the scoped dataset.

        Query params (optional):
          - section: filter by section UUID
          - student: filter by student UUID
          - date_from: filter records on or after this date
          - date_to: filter records on or before this date

        NOTE: The specification does not define "school days" or an
        attendance-rate formula. This endpoint returns raw counts only.
        The total_records value reflects the number of attendance records
        found (not the total possible school days). Any attendance-rate
        calculation is deferred until the specification defines it.
        """
        qs = self.get_queryset()

        section_id = request.query_params.get("section")
        student_id = request.query_params.get("student")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        if section_id:
            qs = qs.filter(section_id=section_id)
        if student_id:
            qs = qs.filter(student_id=student_id)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        summary_data = (
            qs.values(
                "student",
                "student__user__first_name",
                "student__user__last_name",
                "student__student_id",
                "section__name",
            )
            .annotate(
                present_count=Count("id", filter=Q(status=AttendanceRecord.Status.PRESENT)),
                late_count=Count("id", filter=Q(status=AttendanceRecord.Status.LATE)),
                absent_count=Count("id", filter=Q(status=AttendanceRecord.Status.ABSENT)),
                total_records=Count("id"),
            )
            .order_by("student__user__last_name", "student__user__first_name")
        )

        results = []
        for entry in summary_data:
            results.append({
                "student": entry["student"],
                "student_name": (
                    f"{entry['student__user__first_name']} "
                    f"{entry['student__user__last_name']}"
                ),
                "student_id_code": entry["student__student_id"],
                "section_name": entry["section__name"],
                "present_count": entry["present_count"],
                "late_count": entry["late_count"],
                "absent_count": entry["absent_count"],
                "total_records": entry["total_records"],
            })

        return Response(results)
