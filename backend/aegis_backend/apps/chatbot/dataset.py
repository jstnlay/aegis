"""Hand-labeled intent dataset for the AEGIS assistant.

One JSON object per line: {"text": ..., "intent": ...}

Why this file is committed rather than generated or trained into a binary:

  - It is the evidence. A capstone reviewer can read exactly what the classifier
    was taught and check the labels, which a pickled Pipeline does not allow.
  - It makes the model reproducible. `classifier.train()` reads this file, so
    the model is a pure function of the repository contents. There is no
    artifact to go stale, and no "model file missing" failure mode.

Labeling rules applied, so the labels are consistent rather than per-row taste:

  1. The label is what the *speaker meant*, not which keyword they used.
     "how many absences do i have" is ask_attendance even though "absences" was
     not previously in any pattern list.
  2. Register is deliberately mixed: English, Taglish (no diacritics, as typed),
     and clipped/typo forms. Roughly a third of each intent is a form that the
     regex layer in `policies.py` fails on, because the point of the classifier
     is that stratum and not the stratum regex already handles.
  3. Taglish is written the way it is actually typed, not translated English:
     "anong grade ko", "ilang absen ko", "okay ba", "yung", "ba".
  4. URGENT_CONCERN examples are self-harm and crisis wording only. The
     classifier never sees them at inference time -- `classify_intent` returns on
     the regex urgency check first -- so these rows exist to keep the taxonomy
     balanced for the reachability assertion, not to gate escalation. Escalation
     safety must not depend on a model.
  5. No row contains a real student name, id, or record value.
"""

import json
from pathlib import Path

DATASET_PATH = Path(__file__).resolve().parent / "data" / "intent_dataset.jsonl"


def load_dataset(path=None):
    """
    Read the labeled dataset.

    Returns a list of (text, intent_value) tuples. Raises on a malformed row
    rather than skipping it: a silently dropped label would quietly shrink the
    training set and nobody would notice until accuracy fell.
    """
    target = path or DATASET_PATH
    rows = []
    with open(target, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                text = payload["text"]
                intent = payload["intent"]
            except (json.JSONDecodeError, KeyError) as exc:
                raise ValueError(
                    f"{target}:{line_number} is malformed: {exc}"
                ) from exc
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{target}:{line_number} has empty text")
            rows.append((text.strip(), intent))
    return rows