"""Shared account-field validators (PH12 — TC-FAC-01/02 stranded finding).

A guardian contact is a phone number: the log recorded the system saving
values that carry letters and far more digits than any phone number, so the
format is validated once here in the `accounts` app every writer imports
from (the faculty advisory-profile serializer and the student master-list
importer), not copy-pasted per surface.
"""

import re

from django.core.exceptions import ValidationError

#: Separators a caller may decorate the digits with (dashes are the PH
#: convention already used by the seed data, e.g. ``0917-555-0100``).
_GUARDIAN_SEPARATORS = re.compile(r"[\s()\-\.]")

#: 7–15 digits covers local (11) and international (a single leading ``+``)
#: numbers per the ITU E.164 envelope the contact is dialed within.
_GUARDIAN_DIGITS_RE = re.compile(r"^\d{7,15}$")


def validate_guardian_contact(value) -> None:
    """Reject letters and phone-number-implausible digit counts."""
    if value is None:
        return
    text = str(value)
    if not text.strip():
        return
    stripped = _GUARDIAN_SEPARATORS.sub("", text.strip())
    if stripped.startswith("+"):
        stripped = stripped[1:]
    if not _GUARDIAN_DIGITS_RE.match(stripped):
        raise ValidationError(
            "Guardian contact must be a phone number of 7-15 digits "
            "(letters are not accepted).",
            code="invalid_guardian_contact",
        )
