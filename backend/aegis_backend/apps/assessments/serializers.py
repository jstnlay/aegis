"""
Assessments serializers.

Role-based field access:
- Students never receive correct_answer while taking assessments
- Published assessments don't expose answer keys to students
"""

from rest_framework import serializers

from .models import Assessment, AssessmentQuestion, AssessmentResult


class AssessmentQuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for assessment questions.
    
    Excludes correct_answer when serializing for students taking the assessment.
    """
    
    class Meta:
        model = AssessmentQuestion
        fields = (
            "id",
            "assessment",
            "question_text",
            "question_type",
            "order",
            "options",
            "correct_answer",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
    
    def to_representation(self, instance):
        """Remove correct_answer for students viewing published assessments."""
        data = super().to_representation(instance)
        request = self.context.get('request')
        
        if request and hasattr(request, 'user'):
            user = request.user
            # Hide correct_answer from students when assessment is published
            if user.role == 'student' and instance.assessment.is_published:
                data.pop('correct_answer', None)
        
        return data


class AssessmentSerializer(serializers.ModelSerializer):
    """
    Serializer for assessments.
    
    Includes nested questions on detail views.
    """
    
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    questions = AssessmentQuestionSerializer(many=True, read_only=True)
    target_sections_details = serializers.SerializerMethodField()
    target_students_details = serializers.SerializerMethodField()
    quarter_name = serializers.CharField(source="quarter.name", read_only=True, default=None)
    # Optional on input: inferred from assessment_type when omitted (§D.3)
    creator_role = serializers.ChoiceField(
        choices=Assessment.CreatorRole.choices,
        required=False,
    )
    
    class Meta:
        model = Assessment
        fields = (
            "id",
            "title",
            "description",
            "assessment_type",
            "creator_role",
            "created_by",
            "created_by_name",
            "target_sections",
            "target_sections_details",
            "target_students",
            "target_students_details",
            "quarter",
            "quarter_name",
            "time_limit_minutes",
            "is_published",
            "published_at",
            "deadline",
            "questions",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_by", "published_at", "created_at", "updated_at")
    
    def get_target_sections_details(self, obj):
        """Return basic info about target sections."""
        return [
            {
                "id": str(section.id),
                "name": section.name,
                "grade_level": section.grade_level.name,
            }
            for section in obj.target_sections.all()
        ]
    
    def get_target_students_details(self, obj):
        """Return basic info about target students."""
        return [
            {
                "id": str(student.id),
                "student_id": student.student_id,
                "name": student.user.full_name,
            }
            for student in obj.target_students.all()
        ]
    
    def validate(self, data):
        """Validate creator_role and assessment_type consistency.

        creator_role may be omitted on create; it is then inferred from the
        assessment_type (academic -> faculty, wellness/behavioral -> guidance)
        and still validated against the requesting user's role.
        """
        request = self.context.get('request')
        assessment_type = data.get('assessment_type') or (self.instance.assessment_type if self.instance else None)

        creator_role = data.get('creator_role')
        if not creator_role and self.instance:
            creator_role = self.instance.creator_role
        if not creator_role:
            # Infer from assessment type per approved ownership rules (§D.3)
            if assessment_type == 'academic':
                creator_role = 'faculty'
            elif assessment_type in ('wellness', 'behavioral'):
                creator_role = 'guidance'
            data['creator_role'] = creator_role
        
        if request and hasattr(request, 'user'):
            user = request.user
            
            # Validate user role matches creator_role
            if creator_role == 'faculty' and user.role != 'faculty':
                raise serializers.ValidationError({
                    "creator_role": "Only faculty users can create assessments with creator_role='faculty'."
                })
            
            if creator_role == 'guidance' and user.role != 'guidance':
                raise serializers.ValidationError({
                    "creator_role": "Only guidance users can create assessments with creator_role='guidance'."
                })
            
            # Validate assessment_type matches creator_role
            if assessment_type == 'academic' and creator_role != 'faculty':
                raise serializers.ValidationError({
                    "creator_role": "Academic assessments must have creator_role='faculty'."
                })
            
            if assessment_type in ['wellness', 'behavioral'] and creator_role != 'guidance':
                raise serializers.ValidationError({
                    "creator_role": "Wellness/behavioral assessments must have creator_role='guidance'."
                })
        
        return data
    
    def create(self, validated_data):
        """Set created_by to current user."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class AssessmentListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for assessment list views.
    
    Excludes nested questions to reduce payload size.
    """
    
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    question_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Assessment
        fields = (
            "id",
            "title",
            "description",
            "assessment_type",
            "creator_role",
            "created_by",
            "created_by_name",
            "time_limit_minutes",
            "is_published",
            "published_at",
            "deadline",
            "question_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_by", "published_at", "created_at", "updated_at")
    
    def get_question_count(self, obj):
        """Return number of questions in the assessment."""
        return obj.questions.count()


class AssessmentResultSerializer(serializers.ModelSerializer):
    """
    Serializer for assessment results.
    """
    
    assessment_title = serializers.CharField(source="assessment.title", read_only=True)
    student_name = serializers.CharField(source="student.user.full_name", read_only=True)
    student_id = serializers.CharField(source="student.student_id", read_only=True)
    
    class Meta:
        model = AssessmentResult
        fields = (
            "id",
            "assessment",
            "assessment_title",
            "student",
            "student_name",
            "student_id",
            "answers",
            "score",
            "total_possible",
            "percentage",
            "status",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "student", "status", "score", "total_possible", "percentage", "started_at", "completed_at", "created_at", "updated_at")
    
    def validate(self, data):
        """Validate answers structure and completed immutability (SEC-008)."""
        # SEC-008: Completed results are immutable — block any mutation attempt
        # Admins are exempt (consistent with existing full-access permission model)
        if self.instance and self.instance.status == "completed":
            request = self.context.get('request')
            is_admin = request and hasattr(request, 'user') and request.user.role == "admin"
            if not is_admin:
                raise serializers.ValidationError({
                    "detail": "Completed assessment results cannot be modified."
                })

        answers = data.get('answers')
        
        if answers is not None:
            if not isinstance(answers, dict):
                raise serializers.ValidationError({
                    "answers": "Answers must be a JSON object."
                })
            
            # Validate that all answer keys are valid question IDs for this assessment
            assessment = data.get('assessment') or (self.instance.assessment if self.instance else None)
            if assessment:
                valid_question_ids = set(str(q.id) for q in assessment.questions.all())
                provided_question_ids = set(answers.keys())
                
                invalid_ids = provided_question_ids - valid_question_ids
                if invalid_ids:
                    raise serializers.ValidationError({
                        "answers": f"Invalid question IDs: {', '.join(invalid_ids)}"
                    })
        
        return data
    
    def create(self, validated_data):
        """Set student to current user's profile."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            user = request.user
            if user.role == 'student' and hasattr(user, 'student_profile'):
                validated_data['student'] = user.student_profile
        return super().create(validated_data)


class AssessmentResultListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for assessment result list views.
    """
    
    assessment_title = serializers.CharField(source="assessment.title", read_only=True)
    student_name = serializers.CharField(source="student.user.full_name", read_only=True)
    student_id = serializers.CharField(source="student.student_id", read_only=True)
    
    class Meta:
        model = AssessmentResult
        fields = (
            "id",
            "assessment",
            "assessment_title",
            "student",
            "student_name",
            "student_id",
            "score",
            "total_possible",
            "percentage",
            "status",
            "started_at",
            "completed_at",
        )
        read_only_fields = fields  # All fields read-only in list view
