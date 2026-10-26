"""
Academics serializers.
"""

from rest_framework import serializers

from apps.accounts.models import StudentProfile
from apps.accounts.validators import validate_guardian_contact

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


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = ("id", "name", "start_date", "end_date", "is_current", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, data):
        if data.get("is_current"):
            qs = AcademicYear.objects.filter(is_current=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"is_current": "Another academic year is already marked as current."}
                )
        return data


class GradeLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeLevel
        fields = ("id", "name", "level_number")
        read_only_fields = ("id",)


class SectionSerializer(serializers.ModelSerializer):
    grade_level_name = serializers.CharField(source="grade_level.name", read_only=True)
    adviser_name = serializers.CharField(source="adviser.user.full_name", read_only=True, default=None)

    class Meta:
        model = Section
        fields = ("id", "name", "grade_level", "grade_level_name", "academic_year", "adviser", "adviser_name")
        read_only_fields = ("id",)


class SubjectSerializer(serializers.ModelSerializer):
    grade_level_name = serializers.CharField(source="grade_level.name", read_only=True)

    class Meta:
        model = Subject
        fields = ("id", "name", "code", "grade_level", "grade_level_name")
        read_only_fields = ("id",)


class SubjectAssignmentSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_code = serializers.CharField(source="subject.code", read_only=True)
    faculty_name = serializers.CharField(source="faculty.user.full_name", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    class Meta:
        model = SubjectAssignment
        fields = (
            "id",
            "subject",
            "subject_name",
            "subject_code",
            "faculty",
            "faculty_name",
            "section",
            "section_name",
            "academic_year",
            "academic_year_name",
        )
        read_only_fields = ("id",)


class ScheduleSerializer(serializers.ModelSerializer):
    subject_assignment_detail = SubjectAssignmentSerializer(source="subject_assignment", read_only=True)

    class Meta:
        model = Schedule
        fields = (
            "id",
            "subject_assignment",
            "subject_assignment_detail",
            "day_of_week",
            "start_time",
            "end_time",
            "room",
        )
        read_only_fields = ("id",)

    def validate(self, data):
        if data.get("start_time") and data.get("end_time"):
            if data["start_time"] >= data["end_time"]:
                raise serializers.ValidationError({"end_time": "End time must be after start time."})
        return data


class GradingPeriodSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    class Meta:
        model = GradingPeriod
        fields = (
            "id",
            "academic_year",
            "academic_year_name",
            "name",
            "order",
            "start_date",
            "end_date",
        )
        read_only_fields = ("id",)

    def validate(self, data):
        start = data.get("start_date")
        end = data.get("end_date")
        ay = data.get("academic_year") or (self.instance and self.instance.academic_year)

        if start and end and start >= end:
            raise serializers.ValidationError({"end_date": "End date must be after start date."})

        if ay and start and start < ay.start_date:
            raise serializers.ValidationError(
                {"start_date": "Start date cannot be before the academic year start date."}
            )
        if ay and end and end > ay.end_date:
            raise serializers.ValidationError(
                {"end_date": "End date cannot be after the academic year end date."}
            )
        return data


class StudentProfileManageSerializer(serializers.ModelSerializer):
    """
    Faculty write surface for an advisory student's profile (FR-007).

    Only the fields an adviser legitimately maintains are writable, and each
    one is required: the QA log treats a profile update that arrives
    incomplete as an invalid submission that must not be stored
    (TC-FAC-04), so a partially-filled advisory record is rejected here
    rather than saved.

    Identity and enrollment bookkeeping stay out of an adviser's scope and
    are read-only: the school-assigned `student_id`, `enrollment_date`, the
    linked `User` account, and `is_active` (an administrator decision).
    """

    student_name = serializers.CharField(source="user.full_name", read_only=True)

    grade_level = serializers.PrimaryKeyRelatedField(
        queryset=GradeLevel.objects.all()
    )
    section = serializers.PrimaryKeyRelatedField(queryset=Section.objects.all())
    # Blank is not "clear the value": a whitespace-only guardian contact is
    # the same incomplete record the QA log rejects. The value must also be
    # a real phone number (TC-FAC-01/02): letters were saved before the
    # format check existed.
    guardian_contact = serializers.CharField(
        max_length=StudentProfile._meta.get_field("guardian_contact").max_length,
        validators=[validate_guardian_contact],
    )
    date_of_birth = serializers.DateField()

    class Meta:
        model = StudentProfile
        fields = (
            "id",
            "student_name",
            "student_id",
            "grade_level",
            "section",
            "guardian_contact",
            "date_of_birth",
            "is_active",
        )
        read_only_fields = ("id", "student_id", "is_active")

    def validate_section(self, value):
        grade_level = self.initial_data.get("grade_level") or (
            self.instance.grade_level_id if self.instance else None
        )
        if grade_level and str(grade_level) != str(value.grade_level_id):
            raise serializers.ValidationError(
                "Section does not belong to the selected grade level."
            )
        return value

    def validate_date_of_birth(self, value):
        from django.utils import timezone

        if value > timezone.localdate():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value


class EnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.user.full_name", read_only=True)
    student_id = serializers.CharField(source="student.student_id", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    class Meta:
        model = Enrollment
        fields = (
            "id",
            "student",
            "student_name",
            "student_id",
            "section",
            "section_name",
            "academic_year",
            "academic_year_name",
            "date_enrolled",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class GradeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.user.full_name", read_only=True)
    student_id = serializers.CharField(source="student.student_id", read_only=True)
    subject_name = serializers.CharField(source="subject_assignment.subject.name", read_only=True)
    subject_code = serializers.CharField(source="subject_assignment.subject.code", read_only=True)
    section_name = serializers.CharField(source="subject_assignment.section.name", read_only=True)
    grading_period_name = serializers.CharField(source="grading_period.name", read_only=True)
    encoded_by_name = serializers.CharField(source="encoded_by.user.full_name", read_only=True)

    class Meta:
        model = Grade
        fields = (
            "id",
            "student",
            "student_name",
            "student_id",
            "subject_assignment",
            "subject_name",
            "subject_code",
            "section_name",
            "grading_period",
            "grading_period_name",
            "score",
            "letter_grade",
            "remarks",
            "encoded_by",
            "encoded_by_name",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_score(self, value):
        if value is not None and (value < 0 or value > 100):
            raise serializers.ValidationError("Score must be between 0 and 100.")
        return value

    def to_representation(self, instance):
        """
        Withhold the student's identity from administrators without family
        consent (NFR-010, TC-ADM-17).

        The view sets `anonymize_students` only for the admin role, and
        `consented_student_ids` to the students with an active `ConsentRecord`.
        Every other role reads through this untouched - a faculty member's own
        subjects, a student's own rows and a parent's linked children are each
        that role's own scope, not the administrator's oversight, and NFR-010
        names only the administrator.
        """
        data = super().to_representation(instance)
        if not self.context.get("anonymize_students"):
            return data
        consented = self.context.get("consented_student_ids") or set()
        if instance.student_id in consented:
            data["family_consent_on_file"] = True
            return data
        # `student` (the profile UUID) is withheld with the name and the
        # school ID. Left in place it would be a stable pseudonym, resolvable
        # to a name in one call to the profile endpoint - which would make
        # this redaction a label rather than a boundary. Nothing on the admin
        # screen reads it (finalize acts on the grade id), so withholding it
        # costs that screen nothing.
        data["student"] = None
        data["student_name"] = "Name withheld — no family consent"
        data["student_id"] = "ID withheld — no family consent"
        data["family_consent_on_file"] = False
        return data

    def validate(self, data):
        score = data.get("score", getattr(self.instance, "score", None))
        status_val = data.get("status", getattr(self.instance, "status", None))

        if status_val == Grade.StatusChoices.FINALIZED and score is None:
            raise serializers.ValidationError(
                {"score": "A finalized grade must have a score."}
            )

        # SEC-013: Enrollment / section integrity validation
        student = data.get("student") or (
            self.instance.student if self.instance else None
        )
        sa = data.get("subject_assignment") or (
            self.instance.subject_assignment if self.instance else None
        )
        gp = data.get("grading_period") or (
            self.instance.grading_period if self.instance else None
        )

        if student and sa and gp:
            if gp.academic_year_id != sa.academic_year_id:
                raise serializers.ValidationError(
                    {
                        "grading_period": (
                            "Grading period does not belong to the same "
                            "academic year as the subject assignment."
                        )
                    }
                )

            if not Enrollment.objects.filter(
                student=student,
                section=sa.section,
                academic_year=sa.academic_year,
                is_active=True,
            ).exists():
                raise serializers.ValidationError(
                    {
                        "student": (
                            "Student is not enrolled in the section for "
                            "this subject assignment's academic year."
                        )
                    }
                )

        return data


class GradeEncodeSerializer(serializers.Serializer):
    """Serializer for the POST /grades/encode/ endpoint."""

    student = serializers.UUIDField()
    subject_assignment = serializers.UUIDField()
    grading_period = serializers.UUIDField()
    score = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=None)
    letter_grade = serializers.CharField(max_length=5, required=False, default=None, allow_blank=True)
    remarks = serializers.CharField(max_length=255, required=False, default=None, allow_blank=True)

    def validate_score(self, value):
        if value is not None and (value < 0 or value > 100):
            raise serializers.ValidationError("Score must be between 0 and 100.")
        return value
