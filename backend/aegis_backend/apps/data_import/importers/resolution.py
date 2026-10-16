"""
Human-readable key resolution for imports (PH12).

An import file is written by a school, not by a database.  It names a section
"Grade 8 - Bonifacio" and a term "Term 2"; it does not carry internal UUIDs.
Every resolver here therefore accepts the school form and the UUID form, so an
existing UUID file keeps working and a hand-made school file does too.

A resolver returns exactly one record or raises ``RowError``.  A value that
matches nothing, and a value that matches more than one record, are both
errors: imports never guess which record a row meant.
"""

from django.core.exceptions import ValidationError

from apps.academics.models import GradingPeriod, Section, SubjectAssignment

from ..constants import ImportErrorCode
from .base import RowError


def _norm(value):
    """Casefolded, whitespace-collapsed comparison form."""
    return " ".join(str(value).strip().casefold().split())


def _by_uuid(model, raw):
    """
    Return the record whose primary key is ``raw``, or ``None``.

    ``raw`` is client input.  A malformed or unknown UUID returns ``None`` so
    the caller can try the human-readable forms; a value that *is* a UUID is
    never also matched as a name.
    """
    try:
        return model.objects.get(pk=raw)
    except (model.DoesNotExist, ValidationError, ValueError, TypeError):
        return None


def _one(matches, raw, what, code, label):
    """Return the single match, or raise the right RowError for 0 or many."""
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RowError(
            code,
            f"No {what} matches {raw!r} for the current academic year.",
        )
    rendered = ", ".join(sorted(label(match) for match in matches))
    raise RowError(
        code,
        f"{raw!r} matches more than one {what} ({rendered}). "
        "Write the full name, or the record's UUID.",
    )


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def section_label(section):
    """The unambiguous way to write one section: 'Grade 8 - Bonifacio'."""
    level = section.grade_level.name if section.grade_level_id else ""
    return f"{level} - {section.name}" if level else section.name


def _section_labels(section):
    """Every form a school may write for one section, normalized."""
    names = {_norm(section.name)}
    level = section.grade_level.name if section.grade_level_id else ""
    if level:
        names.add(_norm(f"{level} {section.name}"))
        names.add(_norm(f"{level} - {section.name}"))
    return names


def resolve_section(raw, academic_year):
    """Resolve a section by UUID, bare name, or 'Grade 8 - Bonifacio'."""
    by_uuid = _by_uuid(Section, raw)
    if by_uuid is not None:
        return by_uuid

    wanted = _norm(raw)
    matches = [
        section
        for section in Section.objects.filter(
            academic_year=academic_year
        ).select_related("grade_level")
        if wanted in _section_labels(section)
    ]
    return _one(
        matches, raw, "section", ImportErrorCode.INVALID_SECTION, section_label
    )


# ---------------------------------------------------------------------------
# Grading periods
# ---------------------------------------------------------------------------


def resolve_grading_period(raw, academic_year):
    """Resolve a grading period by UUID or by name (e.g. 'Term 2')."""
    by_uuid = _by_uuid(GradingPeriod, raw)
    if by_uuid is not None:
        return by_uuid

    wanted = _norm(raw)
    matches = [
        period
        for period in GradingPeriod.objects.filter(academic_year=academic_year)
        if _norm(period.name) == wanted
    ]
    return _one(
        matches,
        raw,
        "grading period",
        ImportErrorCode.INVALID_GRADING_PERIOD,
        lambda period: period.name,
    )


# ---------------------------------------------------------------------------
# Subject assignments
# ---------------------------------------------------------------------------


def resolve_subject_assignment(section, subject_code, academic_year):
    """
    Resolve one subject assignment from its section and subject code.

    The section is already resolved, so this narrows to the subjects taught in
    that section this year: a code that is taught nowhere, or taught twice in
    the same section, is an error rather than a guess.
    """
    wanted = _norm(subject_code)
    matches = [
        assignment
        for assignment in SubjectAssignment.objects.filter(
            section=section, academic_year=academic_year
        ).select_related("subject")
        if wanted in {_norm(assignment.subject.code), _norm(assignment.subject.name)}
    ]
    return _one(
        matches,
        subject_code,
        f"subject in section {section_label(section)!r}",
        ImportErrorCode.INVALID_SUBJECT_ASSIGNMENT,
        lambda assignment: assignment.subject.code,
    )
