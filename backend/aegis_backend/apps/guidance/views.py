"""
Guidance ViewSets.

Provides scoped querysets per role and enforces both role-level
and data-scope permissions for guidance records.

BehavioralNote: Faculty creates (immutable); Guidance/Student/Parent read.
ConsultationRecord: Guidance CRUD; Student/Parent read.
RiskAlert: Guidance CRUD with status transitions; scoped read.
Intervention: Guidance CRUD with nested steps and notes.
GuidanceReportView: JSON report for a specific student.
"""

from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.access import record_object_access

from core.permissions import (
    IsFacultyUser,
    IsGuidanceUser,
)

from .models import (
    BehavioralNote,
    ConsultationRecord,
    Intervention,
    InterventionStep,
    ProgressNote,
    RiskAlert,
)
from .serializers import (
    BehavioralNoteSerializer,
    ConsultationRecordSerializer,
    GuidanceReportSerializer,
    InterventionSerializer,
    InterventionStepSerializer,
    ProgressNoteSerializer,
    RiskAlertSerializer,
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


def _get_guidance_profile(user):
    """Return the GuidanceProfile for the given user, or None."""
    try:
        return user.guidance_profile
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


def _get_all_guidance_users():
    """Return all User objects with role='guidance'."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return list(User.objects.filter(role="guidance"))


def _get_linked_parent_users(student_profile):
    """Return User objects of parents linked to this student."""
    from apps.accounts.models import ParentStudentLink

    links = ParentStudentLink.objects.filter(
        student=student_profile
    ).select_related("parent__user")
    return [link.parent.user for link in links]


def _faculty_section_ids(faculty_profile):
    """Return the set of Section IDs that a faculty member has access to."""
    from apps.academics.models import AcademicYear, Section, SubjectAssignment

    current_ay = AcademicYear.objects.filter(is_current=True).first()
    if current_ay is None:
        return set()

    section_ids = set()

    # Sections where this faculty is the adviser
    section_ids.update(
        Section.objects.filter(
            adviser=faculty_profile, academic_year=current_ay
        ).values_list("id", flat=True)
    )

    # Sections where this faculty has a subject assignment
    section_ids.update(
        SubjectAssignment.objects.filter(
            faculty=faculty_profile, academic_year=current_ay
        ).values_list("section_id", flat=True)
    )

    return section_ids


# ---------------------------------------------------------------------------
# BehavioralNote ViewSet
# ---------------------------------------------------------------------------


class BehavioralNoteViewSet(viewsets.ModelViewSet):
    """
    BehavioralNote endpoints.

    - Faculty: create within their scope (own sections). Immutable after creation.
    - Guidance: read all notes.
    - Student: read own notes only.
    - Parent: read linked children's notes only.

    No PUT/PATCH/DELETE — BehavioralNote is immutable after creation.

    Sensitive read: ``retrieve`` emits one PH10.8 ACCESS audit event per
    successful authorized retrieval (behavioral narrative content).
    """

    serializer_class = BehavioralNoteSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if self.action == "create":
            return [IsFacultyUser()]
        from rest_framework.permissions import IsAuthenticated

        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = BehavioralNote.objects.select_related(
            "student__user",
            "recorded_by__user",
        ).all()

        if user.role == "guidance":
            return qs
        if user.role == "faculty":
            fp = _get_faculty_profile(user)
            if fp is None:
                return BehavioralNote.objects.none()
            section_ids = _faculty_section_ids(fp)
            if not section_ids:
                return BehavioralNote.objects.none()
            from django.db.models import Subquery
            from apps.academics.models import Enrollment

            enrolled_student_ids = Enrollment.objects.filter(
                section_id__in=section_ids,
                academic_year__is_current=True,
                is_active=True,
            ).values_list("student_id", flat=True)
            return qs.filter(student_id__in=Subquery(enrolled_student_ids))
        if user.role == "student":
            sp = _get_student_profile(user)
            if sp is None:
                return BehavioralNote.objects.none()
            return qs.filter(student=sp)
        if user.role == "parent":
            student_ids = _get_linked_student_ids(user)
            if not student_ids:
                return BehavioralNote.objects.none()
            return qs.filter(student_id__in=student_ids)
        return BehavioralNote.objects.none()

    def retrieve(self, request, *args, **kwargs):
        """Authorized sensitive read — emits one ACCESS audit event."""
        instance = self.get_object()
        record_object_access(instance)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """Create a behavioral note. Faculty only."""
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

        # Validate student enrollment in a section
        from apps.academics.models import AcademicYear, Enrollment

        current_ay = AcademicYear.objects.filter(is_current=True).first()
        if current_ay is None:
            return Response(
                {"detail": "No current academic year configured."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enrollment = Enrollment.objects.filter(
            student=student,
            academic_year=current_ay,
            is_active=True,
        ).first()
        if enrollment is None:
            return Response(
                {"detail": "Student is not actively enrolled in any section."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        section = enrollment.section

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
                {"detail": "You do not have access for this student's section."},
                status=status.HTTP_403_FORBIDDEN,
            )

        note = BehavioralNote.objects.create(
            student=student,
            recorded_by=fp,
            note_type=data["note_type"],
            note_text=data["note_text"],
            date_recorded=data["date_recorded"],
        )

        # Dispatch notifications for warning and incident types
        if note.note_type in ("warning", "incident"):
            from apps.notifications.events import dispatch_event

            event_type = (
                "BEHAVIORAL_WARNING"
                if note.note_type == "warning"
                else "BEHAVIORAL_INCIDENT"
            )
            recipients = _get_all_guidance_users()

            dispatch_event(
                event_type,
                recipients=recipients,
                sender=request.user,
                title=f"Behavioral {note.get_note_type_display()}",
                message=(
                    f"{student.user.get_full_name()} — "
                    f"{note.get_note_type_display()} recorded."
                ),
                link=f"/guidance/behavioral-notes/{note.id}",
            )

        output = BehavioralNoteSerializer(note, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# ConsultationRecord ViewSet
# ---------------------------------------------------------------------------


class ConsultationRecordViewSet(viewsets.ModelViewSet):
    """
    ConsultationRecord endpoints.

    - Guidance: CRUD own consultation records.
    - Student: read consultations where they are the subject.
    - Parent: read consultations for linked children.
    - Faculty/Admin: no access.

    Sensitive read: ``retrieve`` emits one PH10.8 ACCESS audit event per
    successful authorized retrieval (session notes / recommendations).
    """

    serializer_class = ConsultationRecordSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            return [IsGuidanceUser()]
        from rest_framework.permissions import IsAuthenticated

        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = ConsultationRecord.objects.select_related(
            "student__user",
            "counselor__user",
        ).all()

        if user.role == "guidance":
            gp = _get_guidance_profile(user)
            if gp is None:
                return ConsultationRecord.objects.none()
            return qs.filter(counselor=gp)
        if user.role == "student":
            sp = _get_student_profile(user)
            if sp is None:
                return ConsultationRecord.objects.none()
            return qs.filter(student=sp)
        if user.role == "parent":
            student_ids = _get_linked_student_ids(user)
            if not student_ids:
                return ConsultationRecord.objects.none()
            return qs.filter(student_id__in=student_ids)
        return ConsultationRecord.objects.none()

    def retrieve(self, request, *args, **kwargs):
        """Authorized sensitive read — emits one ACCESS audit event."""
        instance = self.get_object()
        record_object_access(instance)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        gp = _get_guidance_profile(self.request.user)
        serializer.save(counselor=gp)

    def create(self, request, *args, **kwargs):
        """Create a consultation record. Guidance only."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        gp = _get_guidance_profile(request.user)
        if gp is None:
            return Response(
                {"detail": "No guidance profile found."},
                status=status.HTTP_403_FORBIDDEN,
            )

        consultation = ConsultationRecord.objects.create(
            student=serializer.validated_data["student"],
            counselor=gp,
            session_date=serializer.validated_data["session_date"],
            session_time=serializer.validated_data["session_time"],
            session_type=serializer.validated_data["session_type"],
            concern_categories=serializer.validated_data["concern_categories"],
            session_notes=serializer.validated_data["session_notes"],
            recommendations=serializer.validated_data.get("recommendations"),
            next_session_date=serializer.validated_data.get("next_session_date"),
            priority_level=serializer.validated_data["priority_level"],
            status=serializer.validated_data.get(
                "status", ConsultationRecord.Status.ONGOING
            ),
        )

        # CONSULTATION_SCHEDULED notification (EVT-10)
        if consultation.next_session_date is not None:
            from apps.notifications.events import dispatch_event

            student = consultation.student
            recipients = [student.user]
            recipients.extend(_get_linked_parent_users(student))

            dispatch_event(
                "CONSULTATION_SCHEDULED",
                recipients=recipients,
                sender=request.user,
                title="Consultation Scheduled",
                message=(
                    f"A consultation session for {student.user.get_full_name()} "
                    f"is scheduled on {consultation.next_session_date}."
                ),
                link=f"/guidance/consultations/{consultation.id}",
            )

        output = ConsultationRecordSerializer(
            consultation, context={"request": request}
        )
        return Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Update a consultation record. Guidance only, own records."""
        instance = self.get_object()
        if instance.counselor.user != request.user:
            return Response(
                {"detail": "You can only update your own consultation records."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        consultation = serializer.save()

        # CONSULTATION_SCHEDULED notification if next_session_date changed
        if consultation.next_session_date is not None:
            from apps.notifications.events import dispatch_event

            student = consultation.student
            recipients = [student.user]
            recipients.extend(_get_linked_parent_users(student))

            dispatch_event(
                "CONSULTATION_SCHEDULED",
                recipients=recipients,
                sender=request.user,
                title="Consultation Scheduled",
                message=(
                    f"A consultation session for {student.user.get_full_name()} "
                    f"is scheduled on {consultation.next_session_date}."
                ),
                link=f"/guidance/consultations/{consultation.id}",
            )

        return Response(serializer.data)


# ---------------------------------------------------------------------------
# RiskAlert ViewSet
# ---------------------------------------------------------------------------


class RiskAlertViewSet(viewsets.ModelViewSet):
    """
    RiskAlert endpoints.

    - Guidance: CRUD all alerts. Source forced to 'manual'.
    - Faculty: read alerts for advisory/subject students.
    - Student: read own alerts.
    - Parent: read linked children's alerts.

    Custom actions: acknowledge, escalate, resolve.

    Sensitive read: ``retrieve`` emits one PH10.8 ACCESS audit event per
    successful authorized retrieval (risk factors / risk level).  The
    state-transition actions are WRITES (already audited by PH10.5
    signals), not reads, so they emit no ACCESS event.
    """

    serializer_class = RiskAlertSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            return [IsGuidanceUser()]
        from rest_framework.permissions import IsAuthenticated

        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = RiskAlert.objects.select_related(
            "student__user",
            "assigned_counselor__user",
        ).all()

        if user.role == "guidance":
            return qs
        if user.role == "faculty":
            fp = _get_faculty_profile(user)
            if fp is None:
                return RiskAlert.objects.none()
            section_ids = _faculty_section_ids(fp)
            if not section_ids:
                return RiskAlert.objects.none()
            from django.db.models import Subquery
            from apps.academics.models import Enrollment

            enrolled_student_ids = Enrollment.objects.filter(
                section_id__in=section_ids,
                academic_year__is_current=True,
                is_active=True,
            ).values_list("student_id", flat=True)
            return qs.filter(student_id__in=Subquery(enrolled_student_ids))
        if user.role == "student":
            sp = _get_student_profile(user)
            if sp is None:
                return RiskAlert.objects.none()
            return qs.filter(student=sp)
        if user.role == "parent":
            student_ids = _get_linked_student_ids(user)
            if not student_ids:
                return RiskAlert.objects.none()
            return qs.filter(student_id__in=student_ids)
        return RiskAlert.objects.none()

    def retrieve(self, request, *args, **kwargs):
        """Authorized sensitive read — emits one ACCESS audit event."""
        instance = self.get_object()
        record_object_access(instance)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(
            source=RiskAlert.Source.MANUAL,
            generated_at=timezone.now(),
        )

    @action(detail=True, methods=["post"], url_path="acknowledge")
    def acknowledge(self, request, pk=None):
        """Transition risk alert status to 'under_monitoring'."""
        alert = self.get_object()
        if alert.status != RiskAlert.Status.ACTIVE:
            return Response(
                {"detail": "Only active alerts can be acknowledged."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        alert.status = RiskAlert.Status.UNDER_MONITORING
        alert.save(update_fields=["status", "last_updated"])
        return Response(RiskAlertSerializer(alert).data)

    @action(detail=True, methods=["post"], url_path="escalate")
    def escalate(self, request, pk=None):
        """Transition risk alert status to 'escalated'."""
        alert = self.get_object()
        if alert.status not in (
            RiskAlert.Status.ACTIVE,
            RiskAlert.Status.UNDER_MONITORING,
        ):
            return Response(
                {"detail": "Only active or under-monitoring alerts can be escalated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        alert.status = RiskAlert.Status.ESCALATED
        alert.save(update_fields=["status", "last_updated"])
        return Response(RiskAlertSerializer(alert).data)

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        """Transition risk alert status to 'resolved'."""
        alert = self.get_object()
        if alert.status not in (
            RiskAlert.Status.ACTIVE,
            RiskAlert.Status.UNDER_MONITORING,
        ):
            return Response(
                {"detail": "Only active or under-monitoring alerts can be resolved."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        alert.status = RiskAlert.Status.RESOLVED
        alert.save(update_fields=["status", "last_updated"])
        return Response(RiskAlertSerializer(alert).data)


# ---------------------------------------------------------------------------
# Intervention ViewSet
# ---------------------------------------------------------------------------


class InterventionViewSet(viewsets.ModelViewSet):
    """
    Intervention endpoints.

    - Guidance: CRUD own interventions. Nested steps and notes.

    Custom actions:
    - GET/POST /interventions/{id}/steps/
    - GET/PATCH /interventions/{id}/steps/{step_id}/
    - GET/POST /interventions/{id}/notes/
    - POST /interventions/{id}/complete/

    Sensitive read: ``retrieve`` emits one PH10.8 ACCESS audit event per
    successful authorized retrieval (the intervention plan).  The nested
    ``steps`` / ``notes`` list reads are list-style reads of the same
    canonical resource and are deliberately NOT separately audited, so a
    single navigation to an intervention produces exactly one event.
    """

    serializer_class = InterventionSerializer
    permission_classes = [IsGuidanceUser]

    def get_queryset(self):
        user = self.request.user
        gp = _get_guidance_profile(user)
        if gp is None:
            return Intervention.objects.none()
        return Intervention.objects.select_related(
            "student__user",
            "assigned_counselor__user",
            "risk_alert",
        ).filter(assigned_counselor=gp)

    def retrieve(self, request, *args, **kwargs):
        """Authorized sensitive read — emits one ACCESS audit event."""
        instance = self.get_object()
        record_object_access(instance)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        gp = _get_guidance_profile(self.request.user)
        serializer.save(assigned_counselor=gp, status=Intervention.Status.ACTIVE)

    @action(detail=True, methods=["get", "post"], url_path="steps")
    def steps(self, request, pk=None):
        """List or create intervention steps."""
        intervention = self.get_object()

        if request.method == "GET":
            steps = intervention.steps.all().order_by("order")
            serializer = InterventionStepSerializer(steps, many=True)
            return Response(serializer.data)

        serializer = InterventionStepSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        step = serializer.save(intervention=intervention)
        return Response(
            InterventionStepSerializer(step).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["get", "patch"],
        url_path=r"steps/(?P<step_id>[^/.]+)",
    )
    def step_detail(self, request, pk=None, step_id=None):
        """Retrieve or update a specific intervention step."""
        intervention = self.get_object()
        step = get_object_or_404(
            InterventionStep, id=step_id, intervention=intervention
        )

        if request.method == "GET":
            return Response(InterventionStepSerializer(step).data)

        previous_status = step.status
        serializer = InterventionStepSerializer(
            step, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        step = serializer.save()

        # INTERVENTION_UPDATE notification if status changed
        if previous_status != step.status:
            from apps.notifications.events import dispatch_event

            gp = _get_guidance_profile(request.user)
            if gp is not None:
                dispatch_event(
                    "INTERVENTION_UPDATE",
                    recipients=[gp.user],
                    sender=request.user,
                    title="Intervention Step Updated",
                    message=(
                        f"Step '{step.title}' status changed from "
                        f"{previous_status} to {step.status}."
                    ),
                    link=f"/guidance/interventions/{intervention.id}",
                )

        return Response(InterventionStepSerializer(step).data)

    @action(detail=True, methods=["get", "post"], url_path="notes")
    def notes(self, request, pk=None):
        """List or create progress notes for an intervention."""
        intervention = self.get_object()

        if request.method == "GET":
            notes = intervention.progress_notes.all()
            serializer = ProgressNoteSerializer(notes, many=True)
            return Response(serializer.data)

        serializer = ProgressNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gp = _get_guidance_profile(request.user)
        if gp is None:
            return Response(
                {"detail": "No guidance profile found."},
                status=status.HTTP_403_FORBIDDEN,
            )
        note = serializer.save(intervention=intervention, recorded_by=gp)
        return Response(
            ProgressNoteSerializer(note).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """Complete an intervention and resolve linked risk alert if present."""
        intervention = self.get_object()

        if intervention.status != Intervention.Status.ACTIVE:
            return Response(
                {"detail": "Only active interventions can be completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        intervention.status = Intervention.Status.COMPLETED
        intervention.save(update_fields=["status", "updated_at"])

        # Resolve linked risk alert if present and not already resolved
        if (
            intervention.risk_alert is not None
            and intervention.risk_alert.status != RiskAlert.Status.RESOLVED
        ):
            intervention.risk_alert.status = RiskAlert.Status.RESOLVED
            intervention.risk_alert.save(
                update_fields=["status", "last_updated"]
            )

        return Response(InterventionSerializer(intervention).data)


# ---------------------------------------------------------------------------
# GuidanceReportView
# ---------------------------------------------------------------------------


class GuidanceReportView(APIView):
    """
    GET /guidance/reports/student/{student_id}/

    Returns structured JSON guidance report for a student.
    Guidance counselors only.

    Sensitive read: a successful report generation for a student emits
    one PH10.8 ACCESS audit event targeting the StudentProfile (the
    report aggregates behavioral notes, consultations, interventions and
    risk alerts for the student).
    """

    permission_classes = [IsGuidanceUser]

    def get(self, request, student_id=None):
        from apps.accounts.models import StudentProfile

        student = get_object_or_404(StudentProfile, id=student_id)
        record_object_access(student)

        # Behavioral note counts by type
        behavioral_counts = dict(
            BehavioralNote.objects.filter(student=student)
            .values_list("note_type")
            .annotate(count=Count("id"))
            .values_list("note_type", "count")
        )
        behavioral_note_counts = {
            "positive": behavioral_counts.get("positive", 0),
            "warning": behavioral_counts.get("warning", 0),
            "incident": behavioral_counts.get("incident", 0),
        }

        # Consultation summary
        consultations = ConsultationRecord.objects.filter(student=student)
        consultation_total = consultations.count()
        consultation_by_status = dict(
            consultations.values_list("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )
        consultation_by_priority = dict(
            consultations.values_list("priority_level")
            .annotate(count=Count("id"))
            .values_list("priority_level", "count")
        )

        # Intervention summary
        interventions = Intervention.objects.filter(student=student)
        intervention_total = interventions.count()
        intervention_by_status = dict(
            interventions.values_list("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        # Risk alert history
        alerts = RiskAlert.objects.filter(student=student).order_by(
            "-generated_at"
        )
        risk_alert_history = [
            {
                "id": str(a.id),
                "risk_level": a.risk_level,
                "status": a.status,
                "source": a.source,
                "generated_at": a.generated_at.isoformat(),
            }
            for a in alerts
        ]

        report_data = {
            "student": student.id,
            "student_name": student.user.get_full_name(),
            "student_id_code": student.student_id,
            "behavioral_note_counts": behavioral_note_counts,
            "consultation_summary": {
                "total": consultation_total,
                "by_status": consultation_by_status,
                "by_priority": consultation_by_priority,
            },
            "intervention_summary": {
                "total": intervention_total,
                "active": intervention_by_status.get("active", 0),
                "completed": intervention_by_status.get("completed", 0),
                "cancelled": intervention_by_status.get("cancelled", 0),
            },
            "risk_alert_history": risk_alert_history,
        }

        serializer = GuidanceReportSerializer(report_data)
        return Response(serializer.data)
