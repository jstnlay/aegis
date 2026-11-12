"""
Tests for the binary at-risk Decision Tree.

The model answers a narrow operational question — is this student at risk right
now — from four features a school can explain to a family. What these tests
protect is not predictive accuracy (the labels are a documented rubric, so
accuracy against them is circular) but the properties a counselor relies on:

* the rubric behaves as written;
* training refuses thin or one-sided data rather than producing a confident
  model from nothing;
* the prediction names the factors that produced it;
* a stored model round-trips;
* a second run does not stack a second alert on a student.
"""

from datetime import date

from django.test import TestCase

from ai_engine.at_risk import (
    FEATURE_COLUMNS,
    MIN_SAMPLES,
    MODEL_VERSION,
    has_active_at_risk_alert,
    load_stored_model,
    predict,
    rule_label,
    save_stored_model,
    train,
)


def _features(attendance=0.95, average=90.0, weak=0, trend=1.0):
    return {
        "attendance_rate": attendance,
        "current_term_grade_average": average,
        "weak_subject_count": weak,
        "grade_trend": trend,
    }


def _dataset(size=40):
    """Half at risk, half not, spread across the feature space."""
    rows = []
    for index in range(size):
        if index % 2 == 0:
            features = _features(attendance=0.70, average=60.0, weak=3, trend=-6.0)
        else:
            features = _features(attendance=0.97, average=91.0, weak=0, trend=2.0)
        features["at_risk_label"] = rule_label(features)
        rows.append(features)
    return rows


class RuleLabelTest(TestCase):
    """The rubric is the contract the tree learns from."""

    def test_low_average_is_at_risk(self):
        self.assertEqual(rule_label(_features(average=70.0)), 1)

    def test_low_attendance_is_at_risk(self):
        self.assertEqual(rule_label(_features(attendance=0.80)), 1)

    def test_two_weak_subjects_is_at_risk(self):
        self.assertEqual(rule_label(_features(weak=2)), 1)

    def test_declining_trend_is_at_risk(self):
        self.assertEqual(rule_label(_features(trend=-4.0)), 1)

    def test_a_healthy_profile_is_not_at_risk(self):
        self.assertEqual(rule_label(_features()), 0)


class TrainTest(TestCase):
    def test_thin_data_is_refused(self):
        model, metadata = train(_dataset(size=MIN_SAMPLES - 1))
        self.assertIsNone(model)
        self.assertEqual(metadata["error"], "insufficient_training_data")

    def test_single_class_data_is_refused(self):
        rows = []
        for _ in range(MIN_SAMPLES + 5):
            features = _features()
            features["at_risk_label"] = 0
            rows.append(features)
        model, metadata = train(rows)
        self.assertIsNone(model)
        self.assertEqual(metadata["error"], "single_class_training_data")

    def test_training_records_the_features_it_used(self):
        dataset = _dataset()
        model, metadata = train(dataset)
        self.assertIsNotNone(model)
        self.assertEqual(metadata["model_version"], MODEL_VERSION)
        self.assertEqual(metadata["feature_columns"], list(FEATURE_COLUMNS))
        self.assertEqual(metadata["n_samples"], len(dataset))
        self.assertIn("label_caveat", metadata)

    def test_insufficient_data_rows_are_skipped(self):
        dataset = _dataset()
        dataset[0] = {
            **_features(),
            "at_risk_label": 1,
            "computation_status": "insufficient_data",
        }
        model, metadata = train(dataset)
        self.assertIsNotNone(model)
        self.assertEqual(metadata["n_samples"], len(dataset) - 1)


class PredictTest(TestCase):
    def setUp(self):
        self.model, _metadata = train(_dataset())

    def test_a_struggling_student_is_flagged(self):
        result = predict(self.model, _features(attendance=0.70, average=60.0, weak=3, trend=-6.0))
        self.assertTrue(result["at_risk"])
        self.assertEqual(result["risk_level"], "high")

    def test_a_stable_student_is_not_flagged(self):
        result = predict(self.model, _features())
        self.assertFalse(result["at_risk"])
        self.assertEqual(result["risk_level"], "low")

    def test_the_decision_path_names_the_factors(self):
        result = predict(self.model, _features(attendance=0.70, average=60.0))
        factors = result["explanation"]["contributing_factors"]
        self.assertTrue(factors)
        for factor in factors:
            self.assertIn(factor["feature"], FEATURE_COLUMNS)
            self.assertIn(factor["direction"], ("below", "above"))
            self.assertEqual(factor["model"], MODEL_VERSION)


class StoredModelTest(TestCase):
    def test_model_round_trips_through_the_database(self):
        model, metadata = train(_dataset())
        artifact = save_stored_model(model, metadata)
        self.assertEqual(artifact.version, MODEL_VERSION)
        self.assertTrue(artifact.is_active)

        stored = load_stored_model()
        self.assertIsNotNone(stored)
        stored_model, stored_metadata = stored
        self.assertEqual(stored_metadata["model_version"], MODEL_VERSION)
        self.assertTrue(
            predict(stored_model, _features(attendance=0.70, average=60.0))["at_risk"]
        )

    def test_saving_again_deactivates_the_previous_artifact(self):
        from apps.guidance.models import RiskModelArtifact

        model, metadata = train(_dataset())
        first = save_stored_model(model, metadata)
        second = save_stored_model(model, metadata)
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(
            RiskModelArtifact.objects.filter(
                version=MODEL_VERSION, is_active=True
            ).count(),
            1,
        )


class DuplicateAlertTest(TestCase):
    """A repeated run must not stack alerts on one student."""

    def setUp(self):
        from apps.accounts.models import StudentProfile, User
        from django.utils import timezone

        from apps.guidance.models import RiskAlert

        self.user = User.objects.create_user(
            email="at_risk@test.com", password="pass12345", role="student"
        )
        self.student = StudentProfile.objects.create(
            user=self.user,
            student_id="ATRISK001",
            enrollment_date=date(2025, 6, 1),
        )
        self.alert = RiskAlert.objects.create(
            student=self.student,
            risk_level=RiskAlert.RiskLevel.HIGH,
            risk_factors=[{"model": MODEL_VERSION, "feature": "at_risk_model"}],
            source=RiskAlert.Source.DECISION_TREE,
            status=RiskAlert.Status.ACTIVE,
            generated_at=timezone.now(),
        )

    def test_an_active_alert_from_this_model_blocks_a_duplicate(self):
        self.assertTrue(has_active_at_risk_alert(self.student))

    def test_a_resolved_alert_does_not_block_a_new_one(self):
        from apps.guidance.models import RiskAlert

        self.alert.status = RiskAlert.Status.RESOLVED
        self.alert.save(update_fields=["status"])
        self.assertFalse(has_active_at_risk_alert(self.student))

    def test_an_alert_from_another_model_does_not_block(self):
        from apps.guidance.models import RiskAlert

        self.alert.risk_factors = [{"model": "v1", "feature": "grade_average"}]
        self.alert.save(update_fields=["risk_factors"])
        self.assertFalse(has_active_at_risk_alert(self.student))
