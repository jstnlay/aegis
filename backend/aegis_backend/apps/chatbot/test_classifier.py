"""
Tests for the intent classifier.

These lock in the *measured* state, not an aspirational one. The headline
assertion is that the classifier is NOT wired into `classify_intent` — that is
a deliberate decision recorded in `classifier.py`, and a future change that
quietly wires it in should have to change this test deliberately.
"""

from django.test import SimpleTestCase

from apps.chatbot.classifier import (
    CONFIDENCE_FLOOR,
    build_pipeline,
    get_metadata,
    get_model,
    load_dataset,
    predict,
)
from apps.chatbot.dataset import load_dataset as load_rows
from apps.chatbot.policies import classify_intent
from apps.chatbot.taxonomy import ChatIntent


class DatasetIntegrityTest(SimpleTestCase):
    """The committed dataset is the evidence; it must be well-formed."""

    def test_every_row_parses_and_is_labelled(self):
        rows = load_rows()
        self.assertGreater(len(rows), 100)
        for text, intent in rows:
            self.assertTrue(text.strip())
            self.assertIn(
                intent,
                {i.value for i in ChatIntent},
                f"unlabelled intent {intent!r}",
            )

    def test_intent_values_are_real_enum_members(self):
        """A typo'd label would silently create a class nothing routes to."""
        valid = {i.value for i in ChatIntent}
        for _text, intent in load_rows():
            self.assertIn(intent, valid)

    def test_dataset_has_no_student_identifiers(self):
        """
        The dataset is committed to the repository, so it must contain no real
        student id, name or record value.
        """
        import re

        id_pattern = re.compile(r"\b[A-Z]{2,5}\d{4,}\b")
        for text, _intent in load_rows():
            self.assertIsNone(
                id_pattern.search(text), f"possible student id in {text!r}"
            )

    def test_every_intent_is_represented(self):
        covered = {intent for _text, intent in load_rows()}
        missing = {i.value for i in ChatIntent} - covered
        self.assertEqual(missing, set(), "intents with no training examples")


class PipelineConfigTest(SimpleTestCase):
    """The analyzer choice is the whole reason this classifier exists."""

    def test_uses_word_and_character_features(self):
        union = build_pipeline().named_steps["features"]
        analyzers = dict(union.transformer_list)
        self.assertEqual(analyzers["word"].analyzer, "word")
        self.assertEqual(analyzers["char"].analyzer, "char_wb")

    def test_classifier_is_seeded(self):
        """The intent layer must be deterministic (same input, same answer)."""
        clf = build_pipeline().named_steps["clf"]
        self.assertEqual(clf.random_state, 42)


class ModelBehaviourTest(SimpleTestCase):
    """Exercises the fitted model. Slow-ish (fits once, then cached)."""

    def test_model_fits_and_covers_the_taxonomy(self):
        model = get_model()
        self.assertIsNotNone(model)
        metadata = get_metadata()
        self.assertEqual(metadata["n_intents"], len(list(ChatIntent)))

    def test_predict_never_returns_unknown(self):
        for text in ["asdkjh", "", "zzz", "florbeldorbus"]:
            intent, _confidence = predict(text)
            self.assertNotEqual(intent, ChatIntent.UNKNOWN)

    def test_low_confidence_returns_none(self):
        """
        The caller must be able to tell "the model said X" from "the model is
        unsure". Returning None is what keeps a weak guess out of the UI.
        """
        intent, confidence = predict("zzz")
        if intent is None:
            self.assertLess(confidence, CONFIDENCE_FLOOR)

    def test_a_clearly_broken_string_is_not_confidently_classified(self):
        intent, _confidence = predict("qwertyuiopasdfghjkl")
        self.assertIsNone(intent)


class NotWiredInTest(SimpleTestCase):
    """
    The decision this file exists to protect.

    The classifier measured 60.0% out-of-fold against 64.7% for the regex layer
    alone on the same holdout. Routing UNKNOWN through it would replace "I
    didn't fully understand" with a confidently wrong answer.
    """

    def test_classify_intent_does_not_call_the_classifier(self):
        # A typo the regex layer cannot reach. If the classifier were wired in,
        # this would return a non-UNKNOWN intent.
        intent = classify_intent("what is my absense record")
        self.assertEqual(intent, ChatIntent.UNKNOWN)

    def test_regex_layer_is_still_the_only_intent_path(self):
        for text, expected in [
            ("anong grade ko sa math", ChatIntent.ASK_GRADE),
            ("ilang absen ko", ChatIntent.ASK_ATTENDANCE),
            ("how am i doing academically", ChatIntent.ASK_ACADEMIC_PERFORMANCE),
        ]:
            self.assertEqual(classify_intent(text), expected)