"""
Model-specific allowlists and safe value normalization for audit changes.

Only explicitly approved fields may enter AuditLog.changes.
Models not present in the allowlist produce no business-field changes.

Architecture:
- Allowlist-driven: denylisting is never used.
- Deterministic: model __str__() is never relied upon.
- JSON-safe: all values normalized to JSON-compatible primitives.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


# ---------------------------------------------------------------------------
# Model-specific allowlists
# ---------------------------------------------------------------------------
# Keys are "app_label.ModelName" strings matching AuditLog.model_name.
# Values are tuples of field names that may appear in changes.

MODEL_ALLOWLISTS: dict[tuple[str, ...]] = {
    "academics.Grade": (
        "score",
        "letter_grade",
        "status",
    ),
    "attendance.AttendanceRecord": (
        "status",
    ),
    "guidance.BehavioralNote": (
        "note_type",
    ),
    "guidance.ConsultationRecord": (
        "status",
        "priority_level",
    ),
    "guidance.RiskAlert": (
        "risk_level",
        "status",
    ),
    "guidance.Intervention": (
        "status",
    ),
    "assessments.Assessment": (
        "title",
        "is_published",
    ),
    "assessments.AssessmentResult": (
        "status",
    ),
}


def get_allowed_fields(model_name: str) -> tuple[str, ...]:
    """Return allowed field names for *model_name*, or empty tuple."""
    return MODEL_ALLOWLISTS.get(model_name, ())


# ---------------------------------------------------------------------------
# Value normalization
# ---------------------------------------------------------------------------

def normalize_value(field_name: str, instance) -> object:
    """Normalize a single model-field value to a JSON-safe primitive.

    Handles: UUID, datetime, date, Decimal, ForeignKey references,
    and standard Python primitives (str, int, float, bool, None).

    For ForeignKey fields, attempts the ``<field>_id`` accessor to
    obtain the raw UUID without materializing the related object.
    """
    if hasattr(instance, f"{field_name}_id"):
        value = getattr(instance, f"{field_name}_id")
    else:
        value = getattr(instance, field_name)

    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


# ---------------------------------------------------------------------------
# Safe field serialization
# ---------------------------------------------------------------------------

def safe_serialize_fields(model_name: str, instance) -> dict:
    """Serialize only allowlisted fields from *instance*.

    Returns a dict of ``{field_name: normalized_value}`` for every
    field in the allowlist.  Fields missing on the instance are skipped.
    Many-to-many relations are never included.
    """
    fields = get_allowed_fields(model_name)
    if not fields:
        return {}

    result: dict[str, object] = {}
    for field_name in fields:
        try:
            field = instance._meta.get_field(field_name)
        except Exception:
            continue
        if field.many_to_many:
            continue
        result[field_name] = normalize_value(field_name, instance)
    return result
