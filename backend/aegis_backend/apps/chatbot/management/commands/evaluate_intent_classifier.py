"""Measure the intent classifier against a held-out probe set.

Read-only: it fits, scores, prints, and exits. Nothing is persisted.

    python manage.py evaluate_intent_classifier --holdout path/to/probes.jsonl

Default holdout is `apps/chatbot/data/holdout_probe.jsonl`, which is NOT part of
the training set. Keeping the probes in a separate file is what makes the
number mean anything — scored on its own training data it would report ~100%
and prove nothing.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.chatbot.classifier import evaluate, get_metadata, get_model, predict
from apps.chatbot.dataset import DATASET_PATH
from apps.chatbot.policies import classify_intent
from apps.chatbot.taxonomy import ChatIntent

DEFAULT_HOLDOUT = DATASET_PATH.parent / "holdout_probe.jsonl"


def _combined_intent(text: str):
    """The path that runs at inference time: regex first, classifier on UNKNOWN."""
    intent = classify_intent(text)
    if intent == ChatIntent.UNKNOWN:
        guess, _confidence = predict(text)
        if guess is not None:
            intent = guess
    return intent


class Command(BaseCommand):
    help = "Score the intent classifier against a held-out probe set."

    def add_arguments(self, parser):
        parser.add_argument(
            "--holdout",
            type=str,
            default=str(DEFAULT_HOLDOUT),
            help="JSONL probe file (one {text, intent} per line).",
        )

    def handle(self, *args, **options):
        path = Path(options["holdout"])

        probes = []
        with open(path, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    probes.append((payload["text"], payload["intent"]))
                except (json.JSONDecodeError, KeyError) as exc:
                    raise ValueError(f"{path}:{line_number} malformed: {exc}")

        model = get_model()
        if model is None:
            self.stderr.write("Classifier unavailable.")
            return

        metadata = get_metadata()
        self.stdout.write(
            f"trained on {metadata.get('n_samples')} samples, "
            f"{metadata.get('n_intents')} intents"
        )
        self.stdout.write(f"holdout: {len(probes)} probes from {path.name}")

        # Baseline: what the regex layer alone achieves on the same probes.
        regex_correct = 0
        for text, expected in probes:
            if classify_intent(text).value == expected:
                regex_correct += 1
        self.stdout.write(
            f"\nregex layer alone : {regex_correct}/{len(probes)} "
            f"= {regex_correct / len(probes) * 100:.1f}%"
        )

        # Combined: regex first, classifier only on UNKNOWN. This is the path
        # that actually runs at inference time.
        combined_correct = 0
        for text, expected in probes:
            if _combined_intent(text).value == expected:
                combined_correct += 1
        self.stdout.write(
            f"combined path     : {combined_correct}/{len(probes)} "
            f"= {combined_correct / len(probes) * 100:.1f}%"
        )

        result = evaluate(probes)
        self.stdout.write(
            f"classifier alone  : {result['correct']}/{result['total']} "
            f"= {result['accuracy'] * 100:.1f}%"
        )

        self.stdout.write("\nper-intent (combined path):")
        combined_per_class: dict[str, dict[str, int]] = {}
        for text, expected in probes:
            bucket = combined_per_class.setdefault(
                expected, {"total": 0, "correct": 0}
            )
            bucket["total"] += 1
            if _combined_intent(text).value == expected:
                bucket["correct"] += 1

        for intent, bucket in sorted(combined_per_class.items()):
            share = bucket["correct"] / bucket["total"]
            marker = "" if share == 1.0 else "   <-- below 100%"
            self.stdout.write(
                f"  {intent:28} {bucket['correct']}/{bucket['total']}{marker}"
            )

        # Show what the combined path still gets wrong, so the remaining gap is
        # visible rather than averaged away.
        self.stdout.write("\nremaining misses on the combined path:")
        for text, expected in probes:
            intent = _combined_intent(text)
            if intent.value != expected:
                self.stdout.write(
                    f"  {text!r}: expected={expected} got={intent.value}"
                )