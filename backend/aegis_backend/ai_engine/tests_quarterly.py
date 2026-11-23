"""
Acceptance checks for the quarterly pilot computation.

The guide's expected results are the contract here: grade and attendance
boundaries, Q1 without a trend, missing-record hold, the 10-point index
trigger, repeated processing, the index formula and the tie rule.
"""

from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from ai_engine.quarterly_risk import (
    FEATURE_COLUMNS,
    PILOT_SCORING,
    Q1_FEATURE_COLUMNS,
    absence_cutoff,
    build_prediction,
    category_from_estimates,
    compute_quarter_inputs,
    features_for_quarter,
    model_version_for_quarter,
    predict,
    risk_index_from_estimates,
    score_rule,
    train,
)
from ai_engine.tests import AIEngineTestBase
from apps.attendance.models import AttendanceRecord
from apps.guidance.models import RiskAlert, RiskScore


def _inputs(**overrides):
    values = {
        "computation_status": "ready",
        "quarter": 2,
        "general_average": 90.0,
        "weak_subjects": 0,
        "grade_trend": 0.0,
        "absences": 0,
        "required_days": 45,
        "consultations": 0,
        "adviser_concerns": 0,
        "lowest_subject_grade": 85.0,
        "late_rate": 0.0,
    }
    values.update(overrides)
    return values


class RuleScoreBoundaryTest(TestCase):
    def test_general_average_boundaries(self):
        self.assertEqual(
            score_rule(_inputs(general_average=61.99))["points"]["G"],
            PILOT_SCORING["general_average"]["critical_points"],
        )
        self.assertEqual(score_rule(_inputs(general_average=62))["points"]["G"], 1)
        self.assertEqual(score_rule(_inputs(general_average=74.99))["points"]["G"], 1)
        self.assertEqual(score_rule(_inputs(general_average=75))["points"]["G"], 0)

    def test_weak_subject_boundaries(self):
        self.assertEqual(score_rule(_inputs(weak_subjects=0))["points"]["W"], 0)
        self.assertEqual(score_rule(_inputs(weak_subjects=1))["points"]["W"], 1)
        self.assertEqual(score_rule(_inputs(weak_subjects=2))["points"]["W"], 1)
        self.assertEqual(score_rule(_inputs(weak_subjects=3))["points"]["W"], 2)
        self.assertEqual(score_rule(_inputs(weak_subjects=4))["points"]["W"], 3)

    def test_trend_boundary_is_strictly_below_minus_five(self):
        self.assertEqual(score_rule(_inputs(grade_trend=-5))["points"]["T"], 0)
        self.assertEqual(score_rule(_inputs(grade_trend=-5.01))["points"]["T"], 1)

    def test_attendance_boundary_d45(self):
        self.assertEqual(absence_cutoff(45), 5)
        self.assertEqual(score_rule(_inputs(absences=4))["points"]["A"], 0)
        self.assertEqual(score_rule(_inputs(absences=5))["points"]["A"], 1)

    def test_cutoff_rounds_up(self):
        self.assertEqual(absence_cutoff(41), 5)
        self.assertEqual(absence_cutoff(1), 1)

    def test_consultation_and_adviser_thresholds(self):
        self.assertEqual(score_rule(_inputs(consultations=2))["points"]["C"], 0)
        self.assertEqual(score_rule(_inputs(consultations=3))["points"]["C"], 1)
        self.assertEqual(score_rule(_inputs(adviser_concerns=1))["points"]["B"], 0)
        self.assertEqual(score_rule(_inputs(adviser_concerns=2))["points"]["B"], 1)

    def test_q1_has_five_components_and_no_trend(self):
        rule = score_rule(
            _inputs(quarter=1, grade_trend=None, general_average=81)
        )
        self.assertNotIn("T", rule["points"])
        self.assertNotIn("grade_trend", [f["feature"] for f in rule["factors"]])
        self.assertEqual(rule["max_score"], 8)

    def test_worked_example_q2_is_high(self):
        """Guide worked example: S = 0+1+1+1+1+1 = 5 -> High."""
        rule = score_rule(
            _inputs(
                general_average=81,
                weak_subjects=2,
                grade_trend=-7,
                absences=5,
                required_days=45,
                consultations=3,
                adviser_concerns=2,
            )
        )
        self.assertEqual(rule["score"], 5)
        self.assertEqual(rule["label"], "high")

    def test_label_bands(self):
        self.assertEqual(score_rule(_inputs(general_average=90))["label"], "low")
        self.assertEqual(score_rule(_inputs(general_average=70))["label"], "moderate")
        self.assertEqual(
            score_rule(
                _inputs(
                    general_average=61,
                    weak_subjects=3,
                    grade_trend=-7,
                    absences=9,
                    consultations=3,
                )
            )["label"],
            "high",
        )

    def test_q1_rule_only_has_no_index(self):
        rule = score_rule(_inputs(quarter=1, grade_trend=None))
        prediction = build_prediction(
            _inputs(quarter=1, grade_trend=None),
            rule,
            {"model_status": "unavailable", "reason": "no_model_for_quarter"},
        )
        self.assertEqual(prediction["risk_level"], rule["label"])
        self.assertIsNone(prediction["risk_score"])
        self.assertEqual(prediction["category_source"], "rule")


class IndexAndTieTest(TestCase):
    def test_index_examples_from_the_guide(self):
        self.assertAlmostEqual(
            risk_index_from_estimates(
                {"low": 0.50, "moderate": 0.40, "high": 0.10}
            ),
            30.0,
        )
        self.assertAlmostEqual(
            risk_index_from_estimates(
                {"low": 0.10, "moderate": 0.30, "high": 0.60}
            ),
            75.0,
        )

    def test_a_tie_returns_no_category(self):
        category, tie = category_from_estimates(
            {"low": 0.40, "moderate": 0.40, "high": 0.20}
        )
        self.assertIsNone(category)
        self.assertEqual(sorted(tie), ["low", "moderate"])

    def test_missing_model_input_blocks_the_model(self):
        metadata = {
            "feature_columns": list(FEATURE_COLUMNS),
            "model_version": "quarterly_v1_q2",
        }
        result = predict(None, metadata, _inputs(late_rate=None))
        self.assertEqual(result["model_status"], "unavailable")
        self.assertIn("late_rate", result["missing_inputs"])


class QuarterInputTest(AIEngineTestBase):
    def test_subject_grade_80_is_not_weak(self):
        self.add_grades(self.student_profile, [
            (self.sa_math, self.gp_q1, Decimal("80")),
            (self.sa_eng, self.gp_q1, Decimal("80")),
            (self.sa_sci, self.gp_q1, Decimal("90")),
            (self.sa_math, self.gp_q2, Decimal("80")),
            (self.sa_eng, self.gp_q2, Decimal("80")),
            (self.sa_sci, self.gp_q2, Decimal("90")),
        ])
        self.add_attendance(self.student_profile, self.section, 10, 10)

        inputs = compute_quarter_inputs(self.student_profile, self.gp_q2)
        self.assertEqual(inputs["weak_subjects"], 0)
        self.assertEqual(inputs["computation_status"], "ready")

    def test_blank_attendance_is_not_absent(self):
        self.add_grades(self.student_profile, [
            (self.sa_math, self.gp_q1, Decimal("88")),
            (self.sa_math, self.gp_q2, Decimal("88")),
        ])
        self.add_attendance(self.student_profile, self.section, 10, 10)

        inputs = compute_quarter_inputs(self.student_profile, self.gp_q2)
        self.assertEqual(inputs["required_days"], 10)
        self.assertEqual(inputs["absences"], 0)
        self.assertEqual(inputs["computation_status"], "ready")

    def test_q1_without_previous_grade_is_ready(self):
        self.add_grades(self.student_profile, [
            (self.sa_math, self.gp_q1, Decimal("81")),
        ])
        AttendanceRecord.objects.create(
            student=self.student_profile,
            section=self.section,
            date=self.gp_q1.start_date,
            status="present",
            recorded_by=self.faculty_profile,
        )

        inputs = compute_quarter_inputs(self.student_profile, self.gp_q1)
        self.assertEqual(inputs["computation_status"], "ready")
        self.assertIsNone(inputs["grade_trend"])
        self.assertEqual(inputs["quarter"], 1)

    def test_q2_missing_previous_average_holds_scoring(self):
        self.add_grades(self.student_profile, [
            (self.sa_math, self.gp_q2, Decimal("81")),
        ])
        AttendanceRecord.objects.create(
            student=self.student_profile,
            section=self.section,
            date=self.gp_q2.start_date,
            status="present",
            recorded_by=self.faculty_profile,
        )

        inputs = compute_quarter_inputs(self.student_profile, self.gp_q2)
        self.assertEqual(inputs["computation_status"], "insufficient_data")
        self.assertIn("grade_trend", inputs["missing"])

    def test_missing_school_days_holds_scoring(self):
        self.add_grades(self.student_profile, [
            (self.sa_math, self.gp_q1, Decimal("81")),
            (self.sa_math, self.gp_q2, Decimal("81")),
        ])

        inputs = compute_quarter_inputs(self.student_profile, self.gp_q2)
        self.assertEqual(inputs["computation_status"], "insufficient_data")
        self.assertIn("required_school_days", inputs["missing"])


class QuarterlyModelTest(TestCase):
    def _rows(self, count=24):
        rows = []
        for index in range(count):
            high = index % 2 == 0
            inputs = _inputs(
                general_average=60.0 if high else 88.0,
                weak_subjects=4 if high else 0,
                grade_trend=-7.0 if high else 1.0,
                absences=6 if high else 0,
                consultations=3 if high else 0,
                adviser_concerns=2 if high else 0,
                lowest_subject_grade=55.0 if high else 82.0,
                late_rate=20.0 if high else 0.0,
            )
            inputs["student_id"] = f"S{index:03d}"
            inputs["label"] = score_rule(inputs)["label"]
            rows.append(inputs)
        return rows

    def test_training_records_the_feature_order_and_quarter(self):
        model, metadata = train(self._rows(), quarter=2)
        self.assertIsNotNone(model)
        self.assertEqual(metadata["feature_columns"], list(FEATURE_COLUMNS))
        self.assertEqual(metadata["applicable_quarter"], 2)
        self.assertEqual(metadata["scoring_version"], "quarterly_v1")
        self.assertEqual(metadata["model_version"], model_version_for_quarter(2))
        self.assertEqual(metadata["n_samples"], 24)

    def test_q1_training_uses_seven_inputs(self):
        rows = self._rows()
        for row in rows:
            row["quarter"] = 1
            row["grade_trend"] = None
            row["label"] = score_rule(row)["label"]
        model, metadata = train(rows, quarter=1)
        self.assertIsNotNone(model)
        self.assertEqual(metadata["feature_columns"], list(Q1_FEATURE_COLUMNS))

    def test_prediction_returns_index_category_and_factors(self):
        rows = self._rows()
        model, metadata = train(rows, quarter=2)
        result = predict(model, metadata, rows[0])
        self.assertEqual(result["model_status"], "ready")
        self.assertIn(result["category"], ("low", "moderate", "high"))
        self.assertGreaterEqual(result["index"], 0)
        self.assertLessEqual(result["index"], 100)
        self.assertTrue(result["contributing_factors"])
        for factor in result["contributing_factors"]:
            self.assertIn(factor["feature"], features_for_quarter(2))


class AlertPolicyTest(AIEngineTestBase):
    def _alert(self, level, score):
        risk_score = RiskScore.objects.create(
            student=self.student_profile,
            computation_status="ready",
            risk_score=score,
            risk_level=level,
            model_version="quarterly_v1_q2",
            computed_at=timezone.now(),
        )
        return RiskAlert.objects.create(
            student=self.student_profile,
            risk_level=level,
            source=RiskAlert.Source.DECISION_TREE,
            status=RiskAlert.Status.ACTIVE,
            risk_score_ref=risk_score,
            generated_at=timezone.now(),
        )

    def _prediction(self, level, index):
        return {
            "computation_status": "ready",
            "risk_level": level,
            "risk_score": index,
            "risk_index": index,
            "category_source": "model",
            "explanation": {"contributing_factors": []},
        }

    @mock.patch("apps.notifications.events.dispatch_event")
    def test_same_category_ten_point_move_re_alerts(self, dispatch):
        from ai_engine.risk_service import integrate_risk_result

        self._alert("moderate", 40)
        result = integrate_risk_result(
            self.student_profile,
            self._prediction("moderate", 50),
            model_version="quarterly_v1_q2",
        )
        self.assertTrue(result.state_changed)
        self.assertEqual(result.risk_alert.risk_score_ref.risk_score, Decimal("50.00"))

    @mock.patch("apps.notifications.events.dispatch_event")
    def test_same_category_9_99_point_move_does_not_re_alert(self, dispatch):
        from ai_engine.risk_service import integrate_risk_result

        self._alert("moderate", 40)
        result = integrate_risk_result(
            self.student_profile,
            self._prediction("moderate", 49.99),
            model_version="quarterly_v1_q2",
        )
        self.assertFalse(result.state_changed)

    @mock.patch("apps.notifications.events.dispatch_event")
    def test_category_change_alerts(self, dispatch):
        from ai_engine.risk_service import integrate_risk_result

        self._alert("low", 20)
        result = integrate_risk_result(
            self.student_profile,
            self._prediction("moderate", 45),
            model_version="quarterly_v1_q2",
        )
        self.assertTrue(result.state_changed)
        self.assertEqual(result.risk_alert.risk_level, "moderate")

    @mock.patch("apps.notifications.events.dispatch_event")
    def test_repeated_processing_does_not_duplicate_the_alert(self, dispatch):
        from ai_engine.risk_service import integrate_risk_result

        first = integrate_risk_result(
            self.student_profile,
            self._prediction("moderate", 30),
            model_version="quarterly_v1_q2",
        )
        second = integrate_risk_result(
            self.student_profile,
            self._prediction("moderate", 30),
            model_version="quarterly_v1_q2",
        )
        self.assertTrue(first.state_changed)
        self.assertFalse(second.state_changed)
        self.assertEqual(RiskAlert.objects.count(), 1)
        self.assertEqual(dispatch.call_count, 1)

    @mock.patch("apps.notifications.events.dispatch_event")
    def test_resolved_alert_for_the_same_revision_is_not_reopened(self, dispatch):
        """
        Guide: reprocessing the same release must not notify again. A resolved
        alert for an identical source revision stays closed.
        """
        from ai_engine.risk_service import integrate_risk_result

        snapshot = {"source_revision": "rev-1"}
        first = integrate_risk_result(
            self.student_profile,
            self._prediction("moderate", 30),
            model_version="quarterly_v1_q2",
            feature_snapshot=snapshot,
        )
        first.risk_alert.status = RiskAlert.Status.RESOLVED
        first.risk_alert.save()

        second = integrate_risk_result(
            self.student_profile,
            self._prediction("moderate", 30),
            model_version="quarterly_v1_q2",
            feature_snapshot=snapshot,
        )
        self.assertFalse(second.state_changed)
        self.assertEqual(RiskAlert.objects.count(), 1)
        self.assertEqual(
            second.risk_score_obj.explanation["alert_decision"]["reason"],
            "same_revision_already_evaluated",
        )
        self.assertEqual(dispatch.call_count, 1)

    @mock.patch("apps.notifications.events.dispatch_event")
    def test_prior_and_current_values_are_recorded(self, dispatch):
        from ai_engine.risk_service import integrate_risk_result

        self._alert("moderate", 40)
        result = integrate_risk_result(
            self.student_profile,
            self._prediction("high", 75),
            model_version="quarterly_v1_q2",
        )
        decision = result.risk_score_obj.explanation["alert_decision"]
        self.assertEqual(decision["prior"]["level"], "moderate")
        self.assertEqual(decision["prior"]["index"], 40.0)
        self.assertEqual(decision["current"]["level"], "high")
        self.assertEqual(decision["reason"], "category_changed")
        self.assertTrue(decision["triggered"])

        recorded = [
            factor
            for factor in result.risk_alert.risk_factors
            if isinstance(factor, dict)
            and factor.get("feature") == "alert_change"
        ]
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["prior"]["level"], "moderate")
        self.assertEqual(recorded[0]["current"]["level"], "high")
        self.assertEqual(recorded[0]["reason"], "category_changed")

    @mock.patch("apps.notifications.events.dispatch_event")
    def test_index_from_another_model_version_is_not_comparable(self, dispatch):
        """
        Guide: apply the numeric trigger only to comparable model indices.
        A legacy binary-model score must not drive a 10-point re-alert.
        """
        from ai_engine.risk_service import integrate_risk_result

        alert = self._alert("moderate", 40)
        RiskScore.objects.filter(id=alert.risk_score_ref_id).update(model_version="v1")

        result = integrate_risk_result(
            self.student_profile,
            self._prediction("moderate", 90),
            model_version="quarterly_v1_q2",
        )
        self.assertFalse(result.state_changed)

    @mock.patch("apps.notifications.events.dispatch_event")
    def test_unrounded_prior_index_is_used_for_the_trigger(self, dispatch):
        """
        Guide: compare unrounded indices. A prior 40.009 stored as 40.00 must
        not look like a 10-point move to 50.00 (true move 9.991).
        """
        from ai_engine.risk_service import integrate_risk_result

        prior_score = RiskScore.objects.create(
            student=self.student_profile,
            computation_status="ready",
            risk_score=Decimal("40.00"),
            risk_level="moderate",
            model_version="quarterly_v1_q2",
            explanation={"alert_decision": {"current": {"index": 40.009}}},
            computed_at=timezone.now(),
        )
        RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="moderate",
            source=RiskAlert.Source.DECISION_TREE,
            status=RiskAlert.Status.ACTIVE,
            risk_score_ref=prior_score,
            generated_at=timezone.now(),
        )

        result = integrate_risk_result(
            self.student_profile,
            self._prediction("moderate", 50.0),
            model_version="quarterly_v1_q2",
        )
        self.assertFalse(result.state_changed)
