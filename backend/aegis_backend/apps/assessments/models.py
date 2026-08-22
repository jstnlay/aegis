"""
Assessments app models.

Academic and wellness/behavioral assessments, questions, and results.
Faculty creates academic assessments. Guidance creates wellness/behavioral assessments.
Students take and submit assigned assessments.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimestampedModel


class Assessment(TimestampedModel):
    """
    An assessment that can be assigned to students.
    
    Academic assessments are created by faculty.
    Wellness/behavioral assessments are created by guidance.
    """
    
    class AssessmentType(models.TextChoices):
        ACADEMIC = "academic", "Academic"
        WELLNESS = "wellness", "Wellness"
        BEHAVIORAL = "behavioral", "Behavioral"
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    assessment_type = models.CharField(max_length=15, choices=AssessmentType.choices)
    
    class CreatorRole(models.TextChoices):
        FACULTY = "faculty", "Faculty"
        GUIDANCE = "guidance", "Guidance"
    
    creator_role = models.CharField(max_length=10, choices=CreatorRole.choices, blank=True)
    
    # Creator (Faculty or Guidance)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="created_assessments",
    )
    
    # Target scoping
    target_sections = models.ManyToManyField(
        "academics.Section",
        blank=True,
        related_name="assessments",
    )
    target_students = models.ManyToManyField(
        "accounts.StudentProfile",
        blank=True,
        related_name="targeted_assessments",
    )
    
    # Optional grading period link for academic assessments
    quarter = models.ForeignKey(
        "academics.GradingPeriod",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assessments",
    )
    
    # Publication and deadline
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(blank=True, null=True)
    deadline = models.DateTimeField(blank=True, null=True)
    time_limit_minutes = models.PositiveIntegerField(blank=True, null=True)
    
    class Meta(TimestampedModel.Meta):
        verbose_name = "assessment"
        verbose_name_plural = "assessments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["assessment_type", "is_published"]),
            models.Index(fields=["created_by"]),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.get_assessment_type_display()})"
    
    def clean(self):
        # Infer creator_role from assessment_type when not provided (§D.3):
        # academic -> faculty, wellness/behavioral -> guidance
        if not self.creator_role:
            if self.assessment_type == self.AssessmentType.ACADEMIC:
                self.creator_role = self.CreatorRole.FACULTY
            elif self.assessment_type in [self.AssessmentType.WELLNESS, self.AssessmentType.BEHAVIORAL]:
                self.creator_role = self.CreatorRole.GUIDANCE

        if not self.creator_role:
            raise ValidationError({
                "creator_role": "creator_role could not be determined from assessment_type."
            })

        # Validate creator_role matches assessment_type
        if self.assessment_type == self.AssessmentType.ACADEMIC:
            if self.creator_role != self.CreatorRole.FACULTY:
                raise ValidationError({
                    "creator_role": "Academic assessments must have creator_role='faculty'."
                })
        elif self.assessment_type in [self.AssessmentType.WELLNESS, self.AssessmentType.BEHAVIORAL]:
            if self.creator_role != self.CreatorRole.GUIDANCE:
                raise ValidationError({
                    "creator_role": "Wellness/behavioral assessments must have creator_role='guidance'."
                })
        
        # Validate created_by user role matches creator_role
        if self.created_by_id:
            if self.creator_role == self.CreatorRole.FACULTY and self.created_by.role != "faculty":
                raise ValidationError({
                    "created_by": "Faculty creator_role requires a faculty user."
                })
            elif self.creator_role == self.CreatorRole.GUIDANCE and self.created_by.role != "guidance":
                raise ValidationError({
                    "created_by": "Guidance creator_role requires a guidance user."
                })
        
        # Validate deadline is in the future
        if self.deadline and self.deadline <= timezone.now():
            raise ValidationError({
                "deadline": "Deadline must be in the future."
            })
    
    def save(self, *args, **kwargs):
        self.full_clean()
        # Set published_at when first published
        if self.is_published and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class AssessmentQuestion(TimestampedModel):
    """
    A question within an assessment.
    """
    
    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = "multiple_choice", "Multiple Choice"
        TRUE_FALSE = "true_false", "True/False"
        ESSAY = "essay", "Essay"
        LIKERT = "likert", "Likert Scale"
    
    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    order = models.PositiveIntegerField()
    
    # For multiple_choice: JSON array of option strings
    # For likert: JSON array of scale options (e.g., ["Strongly Disagree", "Disagree", "Neutral", "Agree", "Strongly Agree"])
    options = models.JSONField(blank=True, null=True)
    
    # Correct answer (for auto-gradable questions: multiple_choice, true_false)
    # Stores the answer text that matches one of the options
    correct_answer = models.TextField(blank=True, null=True)
    
    class Meta(TimestampedModel.Meta):
        verbose_name = "assessment question"
        verbose_name_plural = "assessment questions"
        ordering = ["assessment", "order"]
        unique_together = ("assessment", "order")
    
    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}"
    
    def clean(self):
        # Validate options exist for question types that need them
        if self.question_type == self.QuestionType.MULTIPLE_CHOICE:
            if not self.options or not isinstance(self.options, list) or len(self.options) < 2:
                raise ValidationError({
                    "options": "Multiple choice questions must have at least 2 options as a JSON array."
                })
        
        if self.question_type == self.QuestionType.LIKERT:
            if not self.options or not isinstance(self.options, list) or len(self.options) < 2:
                raise ValidationError({
                    "options": "Likert questions must have at least 2 scale options as a JSON array."
                })
        
        # Validate correct_answer for auto-gradable questions
        if self.question_type == self.QuestionType.MULTIPLE_CHOICE:
            if self.correct_answer and self.options:
                if self.correct_answer not in self.options:
                    raise ValidationError({
                        "correct_answer": "Correct answer must be one of the provided options."
                    })
        
        if self.question_type == self.QuestionType.TRUE_FALSE:
            if self.correct_answer and self.correct_answer not in ["True", "False"]:
                raise ValidationError({
                    "correct_answer": "True/False correct answer must be 'True' or 'False'."
                })
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class AssessmentResult(TimestampedModel):
    """
    A student's submission/result for an assessment.
    """
    
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
    
    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.PROTECT,
        related_name="results",
    )
    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.PROTECT,
        related_name="assessment_results",
    )
    
    # Answers stored as: { "<question_id>": "<answer>" }
    answers = models.JSONField(default=dict, blank=True)
    
    # Grading
    score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
    )
    total_possible = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
    )
    
    # Status and timing
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta(TimestampedModel.Meta):
        verbose_name = "assessment result"
        verbose_name_plural = "assessment results"
        ordering = ["-started_at"]
        unique_together = ("assessment", "student")
        indexes = [
            models.Index(fields=["assessment", "student"]),
            models.Index(fields=["student"]),
        ]
    
    def __str__(self):
        return f"{self.student} — {self.assessment.title}"
    
    def clean(self):
        # Validate answers is a dict
        if self.answers is not None and not isinstance(self.answers, dict):
            raise ValidationError({
                "answers": "Answers must be a JSON object."
            })
        
        # Validate score <= total_possible if both provided
        if self.score is not None and self.total_possible is not None:
            if self.score > self.total_possible:
                raise ValidationError({
                    "score": "Score cannot exceed total possible."
                })
        
        # Validate percentage is between 0 and 100
        if self.percentage is not None:
            if self.percentage < 0 or self.percentage > 100:
                raise ValidationError({
                    "percentage": "Percentage must be between 0 and 100."
                })
    
    def save(self, *args, **kwargs):
        self.full_clean()
        
        # Set completed_at when status changes to completed
        if self.status == self.Status.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()
        
        super().save(*args, **kwargs)
