"""
System-wide settings (FR-034, TC-ADM-11).

Three things make this file rather than the model the interesting half:

* **The registry, not the table, knows the type.** `SystemSetting.value` is
  text. `SETTING_DEFINITIONS` is the single place that says what a setting
  means and where its default comes from, so a setting nobody registered is a
  missing setting, not a silently mistyped one.

* **A bad value degrades, it does not crash.** An administrator can type
  anything into a text field. The serializer validates typed settings on the
  way in; `get_int_setting` is the runtime floor that falls back to the
  registered default rather than raising elsewhere - a mistyped threshold must
  not cost an attendance record its write.

* **Nothing is cached.** The reads are not on a hot path (the threshold is
  consulted only when a record is marked absent) and a cache would have to be
  invalidated across processes to stay correct, which costs more than the
  query it saves.
"""

from __future__ import annotations

from typing import Any

#: The settings the system actually reads. `default` doubles as the value an
#: unsaved setting reads as.
SETTING_DEFINITIONS: dict[str, dict[str, Any]] = {
    "attendance.absence_threshold": {
        "default": 3,
        "description": (
            "Absences in an academic year before a parent attendance alert is "
            "raised."
        ),
    },
    "assessment.default_time_limit": {
        "default": 30,
        "description": (
            "Minutes pre-filled when a new assessment is created. 0 means no "
            "limit."
        ),
    },
    "guidance.risk_score_threshold": {
        "default": 50,
        "description": (
            "Risk score at or above which a student counts as at-risk on the "
            "guidance dashboard."
        ),
    },
    "chatbot.acknowledgment_timer_minutes": {
        "default": 15,
        "description": (
            "Minutes Guidance has to acknowledge a sensitive-message flag "
            "before it is escalated to administrators. A per-severity value "
            "below overrides this one."
        ),
    },
    "chatbot.acknowledgment_timer_minutes.critical": {
        "default": "",
        "description": (
            "Acknowledgment window for critical flags, in minutes. Blank "
            "means use chatbot.acknowledgment_timer_minutes."
        ),
    },
    "chatbot.acknowledgment_timer_minutes.high": {
        "default": "",
        "description": (
            "Acknowledgment window for high flags, in minutes. Blank means "
            "use chatbot.acknowledgment_timer_minutes."
        ),
    },
    "chatbot.acknowledgment_timer_minutes.medium": {
        "default": "",
        "description": (
            "Acknowledgment window for medium flags, in minutes. Blank means "
            "use chatbot.acknowledgment_timer_minutes."
        ),
    },
    "chatbot.acknowledgment_timer_minutes.low": {
        "default": "",
        "description": (
            "Acknowledgment window for low flags, in minutes. Blank means use "
            "chatbot.acknowledgment_timer_minutes."
        ),
    },
    "chatbot.retention_days": {
        "default": 0,
        "description": (
            "Days to keep chatbot messages and closed flags. 0 keeps "
            "everything. manage.py purge_chatbot_data applies it; open "
            "flags are never deleted."
        ),
    },
    "chatbot.notice_version": {
        "default": "2026-11-01",
        "description": (
            "Version of the student chatbot notice. Changing this value "
            "requires every student to accept the notice again."
        ),
    },
    "chatbot.notice_text": {
        "default": (
            "AEGIS stores chatbot messages so a guidance counselor can review "
            "a safety concern. Messages are screened by an automated keyword "
            "layer and may be classified by Gemini, a third-party AI service. "
            "Only the message text is sent for classification; your name, "
            "student number and school records are not. You can ask a "
            "counselor what was stored about you."
        ),
        "description": "Student-facing chatbot privacy and data notice.",
    },
    "chatbot.faculty_notifications_enabled": {
        "default": "true",
        "description": (
            "Whether faculty receive a content-free notice when a student in "
            "their class has a high or critical flag."
        ),
    },
}


class SettingTypeError(ValueError):
    """Raised for a setting that is not registered or cannot be coerced."""

    def __init__(self, key: str, expected: str, value: Any):
        super().__init__(
            f"Setting {key!r} expects {expected}; received {value!r}"
        )
        self.key = key
        self.expected = expected


def all_keys() -> list[str]:
    """Every registered setting key, in the order they are displayed."""
    return list(SETTING_DEFINITIONS)


def default_for(key: str) -> Any:
    """The registered default for `key`. Raises `KeyError` if unregistered."""
    return SETTING_DEFINITIONS[key]["default"]


def value_type_for(key: str) -> str:
    """
    The coercion `key` gets: `"int"` for a registered integer setting, `"text"`
    for anything stored verbatim.

    Text is the default rather than a declared type, so a setting that holds a
    label or a phrase needs nothing added here.
    """
    definition = SETTING_DEFINITIONS.get(key) or {}
    return "int" if isinstance(definition.get("default"), int) else "text"


def coerce(key: str, value: str) -> Any:
    """
    Read `value` as the type registered for `key`.

    Raises `SettingTypeError` when `key` is unregistered or the text cannot be
    read as its registered type.
    """
    if key not in SETTING_DEFINITIONS:
        raise SettingTypeError(key, "a registered setting", value)

    text = (value or "").strip()
    if value_type_for(key) != "int":
        return text

    try:
        return int(text)
    except (TypeError, ValueError):
        raise SettingTypeError(key, "an integer", value) from None


def get_setting(key: str, default: Any = None) -> Any:
    """
    The stored value for `key`, coerced to its registered type.

    A row that is absent or unparseable falls back to the setting's
    **registered** default, so an unsaved or mistyped value reads as the
    documented one rather than as whatever a caller happened to pass. `default`
    only covers a key the registry does not describe at all, which is the one
    case where the registry has no answer.

    Raises `SettingTypeError` when `key` is unregistered - a caller naming a key
    that does not exist is a bug, not a missing value.
    """
    from .models import SystemSetting

    if key not in SETTING_DEFINITIONS:
        raise SettingTypeError(key, "a registered setting", None)

    try:
        row = SystemSetting.objects.get(key=key)
    except SystemSetting.DoesNotExist:
        return default_for(key)

    try:
        return coerce(key, row.value)
    except SettingTypeError:
        return default_for(key)


def get_int_setting(key: str, default: int = 0) -> int:
    """
    Tolerant integer read, for runtime callers.

    Falls back to the registered default for a known setting, or to `default`
    for one the registry does not describe. This is deliberately the only
    settings reader that cannot raise: a caller such as attendance record
    creation has no better answer than the previous behaviour, and must not lose
    a write to a mistyped setting.
    """
    try:
        value = get_setting(key, default=default)
        return int(value)
    except (SettingTypeError, TypeError, ValueError):
        return default
