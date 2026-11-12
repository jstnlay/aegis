"""
Default Layer 1 screening terms.

The keyword table is administrator-editable, so these are *defaults*, not
policy: the migration seeds them once and an administrator may deactivate or
delete any of them afterwards. `seed_keyword_terms` is idempotent — it only
creates terms that are missing, so re-running it never overwrites an edit.

The built-in patterns in `policies.py` still run on every message. These terms
cover the vocabulary that policy patterns deliberately do not, because a
deterministic pattern that matches bare words is how you page a counselor
about a sprained ankle.
"""

from __future__ import annotations

#: (term, match_type, severity, category, notes)
DEFAULT_KEYWORD_TERMS: list[tuple[str, str, str, str, str]] = [
    # Critical — immediate danger or self-harm intent.
    ("suicide", "keyword", "critical", "suicide", "Explicit suicide wording."),
    ("suicidal", "keyword", "critical", "suicide", "Explicit suicide wording."),
    ("kill myself", "phrase", "critical", "suicide", "Explicit self-harm intent."),
    ("end my life", "phrase", "critical", "self_harm", "Explicit self-harm intent."),
    ("hurt myself", "phrase", "critical", "self_harm", "Explicit self-harm intent."),
    ("cut myself", "phrase", "critical", "self_harm", "Explicit self-harm intent."),
    ("overdose", "keyword", "critical", "self_harm", "Overdose wording."),
    # High — credible threat or abuse. Phrased rather than single words:
    # "abuse", "threaten" and "gun" all have ordinary uses in a school
    # conversation, and a term that cries wolf teaches staff to ignore the
    # channel that matters.
    ("kill you", "phrase", "high", "violence", "Credible threat wording."),
    ("hurt you", "phrase", "high", "violence", "Credible threat wording."),
    ("beat me up", "phrase", "high", "violence", "Credible threat wording."),
    ("suicide pact", "phrase", "high", "suicide", "Shared self-harm intent."),
    ("abuse me", "phrase", "high", "abuse", "Abuse disclosure."),
    ("abused at home", "phrase", "high", "abuse", "Abuse disclosure."),
    ("being abused", "phrase", "high", "abuse", "Abuse disclosure."),
    ("molest", "keyword", "high", "abuse", "Abuse disclosure."),
    ("threatened me", "phrase", "high", "violence", "Threat disclosure."),
    ("they threatened", "phrase", "high", "violence", "Threat disclosure."),
    ("threatened my", "phrase", "high", "violence", "Threat disclosure."),
    ("with a gun", "phrase", "high", "violence", "Weapon mention."),
    ("bring a gun", "phrase", "high", "violence", "Weapon mention."),
    # Medium — distress, bullying, academic and family strain.
    ("bullied", "keyword", "medium", "bullying", "Bullying disclosure."),
    ("bullied me", "phrase", "medium", "bullying", "Bullying disclosure."),
    ("bulling", "keyword", "medium", "bullying", "Bullying disclosure."),
    ("bullying", "keyword", "medium", "bullying", "Bullying disclosure."),
    ("harass", "keyword", "medium", "bullying", "Harassment disclosure."),
    ("feeling depressed", "phrase", "medium", "distress", "Distress disclosure."),
    ("feel hopeless", "phrase", "medium", "distress", "Distress disclosure."),
    ("worthless", "keyword", "medium", "distress", "Distress disclosure."),
    ("no point living", "phrase", "medium", "distress", "Distress disclosure."),
    ("panic attack", "phrase", "medium", "distress", "Distress disclosure."),
    ("cannot sleep", "phrase", "medium", "distress", "Distress disclosure."),
    ("i give up", "phrase", "medium", "academic_distress", "Academic distress."),
    ("failing everything", "phrase", "medium", "academic_distress", "Academic distress."),
    ("want to drop out", "phrase", "medium", "academic_distress", "Academic distress."),
    ("parents do not care", "phrase", "medium", "family", "Family strain."),
    ("run away from home", "phrase", "medium", "family", "Family strain."),
    ("no one cares about me", "phrase", "medium", "distress", "Distress disclosure."),
]


def seed_keyword_terms(*, terms=DEFAULT_KEYWORD_TERMS) -> int:
    """Create the missing default terms. Returns how many rows were created."""
    from apps.chatbot.models import KeywordTerm

    created = 0
    for term, match_type, severity, category, notes in terms:
        _, was_created = KeywordTerm.objects.get_or_create(
            term=term,
            match_type=match_type,
            defaults={
                "severity": severity,
                "category": category,
                "notes": notes,
                "is_active": True,
            },
        )
        if was_created:
            created += 1
    return created
