"""
Phase 9 chatbot — intent taxonomy (D25).

INTENT and URGENCY are separate.

Intent taxonomy:
  GENERAL: greeting, help, system_navigation, unknown
  ACADEMIC: ask_grade, ask_academic_performance, ask_subject_help,
            ask_learning_resource, ask_study_strategy, ask_recommendation
  ATTENDANCE: ask_attendance, ask_attendance_status
  ASSESSMENT: ask_assessment, assessment_schedule, assessment_instructions
  GUIDANCE/SUPPORT: guidance_help, express_concern, request_counselor,
                    urgent_concern
"""

from enum import Enum


class ChatIntent(str, Enum):
    # GENERAL
    GREETING = "greeting"
    HELP = "help"
    SYSTEM_NAVIGATION = "system_navigation"
    UNKNOWN = "unknown"

    # ACADEMIC
    ASK_GRADE = "ask_grade"
    ASK_ACADEMIC_PERFORMANCE = "ask_academic_performance"
    ASK_SUBJECT_HELP = "ask_subject_help"
    ASK_LEARNING_RESOURCE = "ask_learning_resource"
    ASK_STUDY_STRATEGY = "ask_study_strategy"
    ASK_RECOMMENDATION = "ask_recommendation"

    # ATTENDANCE
    ASK_ATTENDANCE = "ask_attendance"
    ASK_ATTENDANCE_STATUS = "ask_attendance_status"

    # ASSESSMENT
    ASK_ASSESSMENT = "ask_assessment"
    ASSESSMENT_SCHEDULE = "assessment_schedule"
    ASSESSMENT_INSTRUCTIONS = "assessment_instructions"

    # GUIDANCE / SUPPORT
    GUIDANCE_HELP = "guidance_help"
    EXPRESS_CONCERN = "express_concern"
    REQUEST_COUNSELOR = "request_counselor"
    URGENT_CONCERN = "urgent_concern"


# Intent categories
GENERAL_INTENTS = {
    ChatIntent.GREETING,
    ChatIntent.HELP,
    ChatIntent.SYSTEM_NAVIGATION,
    ChatIntent.UNKNOWN,
}

ACADEMIC_INTENTS = {
    ChatIntent.ASK_GRADE,
    ChatIntent.ASK_ACADEMIC_PERFORMANCE,
    ChatIntent.ASK_SUBJECT_HELP,
    ChatIntent.ASK_LEARNING_RESOURCE,
    ChatIntent.ASK_STUDY_STRATEGY,
    ChatIntent.ASK_RECOMMENDATION,
}

ATTENDANCE_INTENTS = {
    ChatIntent.ASK_ATTENDANCE,
    ChatIntent.ASK_ATTENDANCE_STATUS,
}

ASSESSMENT_INTENTS = {
    ChatIntent.ASK_ASSESSMENT,
    ChatIntent.ASSESSMENT_SCHEDULE,
    ChatIntent.ASSESSMENT_INSTRUCTIONS,
}

GUIDANCE_INTENTS = {
    ChatIntent.GUIDANCE_HELP,
    ChatIntent.EXPRESS_CONCERN,
    ChatIntent.REQUEST_COUNSELOR,
    ChatIntent.URGENT_CONCERN,
}


class UrgencyLevel(str, Enum):
    """D26 urgency levels.

    NORMAL:   normal response
    ELEVATED: supportive response + Guidance contact option
    URGENT:   application-controlled FR-031 escalation
    """

    NORMAL = "normal"
    ELEVATED = "elevated"
    URGENT = "urgent"


# Entities (D25)
ENTITY_TYPES = [
    "subject",
    "topic",
    "term",
    "assessment",
    "resource",
    "grade_level",
]


class ChatEntity:
    """A detected entity in a chat message."""

    def __init__(self, entity_type: str, value: str):
        self.entity_type = entity_type
        self.value = value

    def to_dict(self):
        return {
            "type": self.entity_type,
            "value": self.value,
        }

    def __repr__(self):
        return f"<ChatEntity {self.entity_type}={self.value!r}>"
