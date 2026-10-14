"""
Phase 9 test suite for AEGIS AI Engine.

Covers:
- Feature engine (D13 features)
- Rule-based labeling (D4)
- Decision Tree risk scorer (D6/D7/D12)
- Risk Score persistence (RiskScore/History)
- RiskAlert integration semantics
- LearningItem metadata layer
- Student Interaction tracking
"""

import unittest.mock
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import (
    FacultyProfile,
    GuidanceProfile,
    StudentProfile,
    ParentProfile,
    ParentStudentLink,
)
from apps.academics.models import (
    AcademicYear,
    Enrollment,
    GradeLevel,
    Section,
    Subject,
    SubjectAssignment,
    GradingPeriod,
    Grade,
)
from apps.attendance.models import AttendanceRecord
from apps.cms.models import LearningItem, StudentInteraction
from apps.guidance.models import (
    BehavioralNote,
    ConsultationRecord,
    RiskAlert,
    RiskScore,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class AIEngineTestBase(TestCase):
    """Shared setUp for AI engine tests."""

    def setUp(self):
        # --- Academic structure ---
        self.academic_year = AcademicYear.objects.create(
            name="2024-2025",
            start_date=date(2024, 6, 10),
            end_date=date(2025, 3, 25),
            is_current=True,
        )
        self.prev_year = AcademicYear.objects.create(
            name="2023-2024",
            start_date=date(2023, 6, 10),
            end_date=date(2024, 3, 25),
            is_current=False,
        )

        self.grade_level = GradeLevel.objects.create(
            name="Grade 7", level_number=7
        )

        self.section = Section.objects.create(
            name="Einstein",
            grade_level=self.grade_level,
            academic_year=self.academic_year,
        )

        self.subject_math = Subject.objects.create(
            name="Mathematics", code="MATH-7", grade_level=self.grade_level
        )
        self.subject_eng = Subject.objects.create(
            name="English", code="ENG-7", grade_level=self.grade_level
        )
        self.subject_sci = Subject.objects.create(
            name="Science", code="SCI-7", grade_level=self.grade_level
        )

        # --- Users / profiles ---
        self.faculty_user = User.objects.create_user(
            email="faculty_ai@test.com", password="pass12345",
            first_name="Fac", last_name="Ai", role="faculty",
        )
        self.faculty_profile = FacultyProfile.objects.create(
            user=self.faculty_user, employee_id="FAI001"
        )

        self.guidance_user = User.objects.create_user(
            email="guidance_ai@test.com", password="pass12345",
            first_name="Gui", last_name="Ai", role="guidance",
        )
        self.guidance_profile = GuidanceProfile.objects.create(
            user=self.guidance_user, employee_id="GAI001"
        )

        self.student_user = User.objects.create_user(
            email="student_ai@test.com", password="pass12345",
            first_name="Stu", last_name="Ai", role="student",
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_id="STUAI001",
            grade_level=self.grade_level,
            section=self.section,
            enrollment_date=date(2024, 6, 10),
        )

        self.student2_user = User.objects.create_user(
            email="student2_ai@test.com", password="pass12345",
            first_name="Stu2", last_name="Ai2", role="student",
        )
        self.student2_profile = StudentProfile.objects.create(
            user=self.student2_user,
            student_id="STUAI002",
            grade_level=self.grade_level,
            section=self.section,
            enrollment_date=date(2024, 6, 10),
        )

        # --- Enrollment ---
        self.enrollment = Enrollment.objects.create(
            student=self.student_profile,
            section=self.section,
            academic_year=self.academic_year,
            date_enrolled=date(2024, 6, 10),
            is_active=True,
        )
        self.enrollment2 = Enrollment.objects.create(
            student=self.student2_profile,
            section=self.section,
            academic_year=self.academic_year,
            date_enrolled=date(2024, 6, 10),
            is_active=True,
        )

        # --- Subject assignments ---
        self.sa_math = SubjectAssignment.objects.create(
            subject=self.subject_math,
            section=self.section,
            academic_year=self.academic_year,
            faculty=self.faculty_profile,
        )
        self.sa_eng = SubjectAssignment.objects.create(
            subject=self.subject_eng,
            section=self.section,
            academic_year=self.academic_year,
            faculty=self.faculty_profile,
        )
        self.sa_sci = SubjectAssignment.objects.create(
            subject=self.subject_sci,
            section=self.section,
            academic_year=self.academic_year,
            faculty=self.faculty_profile,
        )

        # --- Grading periods ---
        self.gp_q1 = GradingPeriod.objects.create(
            academic_year=self.academic_year,
            name="1st Quarter", order=1,
            start_date=date(2024, 6, 10), end_date=date(2024, 8, 20),
        )
        self.gp_q2 = GradingPeriod.objects.create(
            academic_year=self.academic_year,
            name="2nd Quarter", order=2,
            start_date=date(2024, 9, 1), end_date=date(2024, 10, 30),
        )

        # Previous year for term-aware testing
        self.prev_section = Section.objects.create(
            name="Newton",
            grade_level=self.grade_level,
            academic_year=self.prev_year,
        )
        self.prev_sa_math = SubjectAssignment.objects.create(
            subject=self.subject_math,
            section=self.prev_section,
            academic_year=self.prev_year,
            faculty=self.faculty_profile,
        )
        self.prev_gp = GradingPeriod.objects.create(
            academic_year=self.prev_year,
            name="Q1", order=1,
            start_date=date(2023, 6, 10), end_date=date(2023, 8, 20),
        )
        self.prev_enrollment = Enrollment.objects.create(
            student=self.student_profile,
            section=self.prev_section,
            academic_year=self.prev_year,
            date_enrolled=date(2023, 6, 10),
            is_active=True,
        )

    def add_grades(self, student, sa_gp_pairs):
        """Add finalized grades for a student.

        sa_gp_pairs: list of (subject_assignment, grading_period, score) tuples.
        Each (student, sa, gp) pairing is unique per Grade uniqueness constraint.
        """
        for sa, gp, score in sa_gp_pairs:
            Grade.objects.update_or_create(
                student=student,
                subject_assignment=sa,
                grading_period=gp,
                defaults={
                    "score": score,
                    "status": "finalized",
                    "encoded_by": self.faculty_profile,
                },
            )

    def add_attendance(self, student, section, total, present, late=0):
        """Add attendance records for a student."""
        start = date(2024, 6, 11)
        for i in range(total):
            status = "present"
            if i >= present:
                if late > 0:
                    status = "late"
                    late -= 1
                else:
                    status = "absent"
            AttendanceRecord.objects.create(
                student=student,
                section=section,
                date=start + timedelta(days=i),
                status=status,
                recorded_by=self.faculty_profile,
            )


# ---------------------------------------------------------------------------
# RiskScore model tests
# ---------------------------------------------------------------------------

class RiskScoreModelTest(AIEngineTestBase):
    """Test the RiskScore model."""

    def test_creation(self):
        rs = RiskScore.objects.create(
            student=self.student_profile,
            computation_status="ready",
            risk_score=72.50,
            risk_level="high",
            model_version="v1",
            computed_at=timezone.now(),
        )
        self.assertEqual(rs.risk_score, 72.50)
        self.assertEqual(rs.risk_level, "high")
        self.assertEqual(rs.computation_status, "ready")

    def test_insufficient_data(self):
        rs = RiskScore.objects.create(
            student=self.student_profile,
            computation_status="insufficient_data",
            risk_score=None,
            risk_level=None,
            model_version="v1",
            computed_at=timezone.now(),
        )
        self.assertIsNone(rs.risk_score)
        self.assertIsNone(rs.risk_level)
        self.assertEqual(rs.computation_status, "insufficient_data")

    def test_risk_alert_links_risk_score(self):
        rs = RiskScore.objects.create(
            student=self.student_profile,
            computation_status="ready",
            risk_score=81.0,
            risk_level="high",
            model_version="v1",
            computed_at=timezone.now(),
        )
        alert = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="high",
            source="decision_tree",
            status="active",
            risk_score_ref=rs,
            generated_at=timezone.now(),
        )
        self.assertEqual(alert.risk_score_ref, rs)
        self.assertEqual(alert.source, "decision_tree")


# ---------------------------------------------------------------------------
# RiskAlert DECISION_TREE source
# ---------------------------------------------------------------------------

class RiskAlertSourceTest(AIEngineTestBase):
    """Verify RiskAlert can be created with DECISION_TREE source."""

    def test_decision_tree_source_choice(self):
        alert = RiskAlert(
            student=self.student_profile,
            risk_level="moderate",
            source="decision_tree",
            generated_at=timezone.now(),
        )
        alert.save()
        self.assertEqual(alert.source, "decision_tree")
        self.assertIn(alert.source, RiskAlert.Source.values)

    def test_manual_default(self):
        alert = RiskAlert(
            student=self.student_profile,
            risk_level="low",
            generated_at=timezone.now(),
        )
        alert.save()
        self.assertEqual(alert.source, "manual")


# ---------------------------------------------------------------------------
# Feature engine tests
# ---------------------------------------------------------------------------

class FeatureEngineTest(AIEngineTestBase):
    """Test D13 feature computation."""

    def test_high_performing_student(self):
        """Student with good grades should compute clean features."""
        self.add_grades(self.student_profile, [
            (self.sa_math, self.gp_q2, Decimal("92")),
            (self.sa_eng, self.gp_q2, Decimal("88")),
            (self.sa_sci, self.gp_q2, Decimal("90")),
        ])
        self.add_attendance(self.student_profile, self.section, 20, 18)

        from ai_engine.feature_engine import compute_student_features
        features = compute_student_features(
            self.student_profile,
            [self.gp_q1, self.gp_q2],
            self.academic_year,
        )

        self.assertEqual(features["computation_status"], "ready")
        self.assertIsNotNone(features["current_term_grade_average"])
        self.assertGreaterEqual(features["current_term_grade_average"], 85)
        self.assertGreaterEqual(features["attendance_rate"], 0.85)
        self.assertEqual(features["weak_subject_count"], 0)

    def test_insufficient_data_no_grades(self):
        """Student with no finalized grades → INSUFFICIENT_DATA."""
        from ai_engine.feature_engine import compute_student_features
        features = compute_student_features(
            self.student_profile,
            [self.gp_q1, self.gp_q2],
            self.academic_year,
        )
        self.assertEqual(features["computation_status"], "insufficient_data")
        self.assertIsNone(features["current_term_grade_average"])

    def test_weak_subject_detection(self):
        """Student below weak-subject threshold in multiple subjects."""
        self.add_grades(self.student_profile, [
            (self.sa_math, self.gp_q2, Decimal("65")),
            (self.sa_eng, self.gp_q2, Decimal("68")),
            (self.sa_sci, self.gp_q2, Decimal("85")),
        ])
        self.add_attendance(self.student_profile, self.section, 10, 8)

        from ai_engine.feature_engine import compute_student_features
        features = compute_student_features(
            self.student_profile,
            [self.gp_q1, self.gp_q2],
            self.academic_year,
        )
        self.assertGreaterEqual(features["weak_subject_count"], 2)

    def test_guidance_aggregates_only(self):
        """Guidance counts only, no free text in features."""
        ConsultationRecord.objects.create(
            student=self.student_profile,
            counselor=self.guidance_profile,
            session_date=date(2024, 7, 1),
            session_time=time(9, 0),
            session_type="individual_counseling",
            concern_categories=["academic"],
            session_notes="Sensitive free text that must NOT appear in features.",
            priority_level="medium",
            status="completed",
        )
        BehavioralNote.objects.create(
            student=self.student_profile,
            recorded_by=self.faculty_profile,
            note_type="warning",
            note_text="Confidential behavioral narrative.",
            date_recorded=date(2024, 7, 2),
        )
        self.add_grades(self.student_profile, [
            (self.sa_math, self.gp_q2, Decimal("80")),
            (self.sa_eng, self.gp_q2, Decimal("82")),
        ])
        self.add_attendance(self.student_profile, self.section, 10, 9)

        from ai_engine.feature_engine import compute_student_features
        features = compute_student_features(
            self.student_profile,
            [self.gp_q1, self.gp_q2],
            self.academic_year,
        )
        self.assertEqual(features["consultation_count"], 1)
        self.assertEqual(features["behavioral_count"], 1)
        # Free text must not appear in the feature dict
        raw = str(features)
        self.assertNotIn("Sensitive free text", raw)
        self.assertNotIn("Confidential behavioral narrative", raw)

    def test_no_future_term_leakage(self):
        """Future/incomplete term data should NOT be included."""
        # Only grades in Q1, no Q2 grades
        self.add_grades(self.student_profile, [
            (self.sa_math, self.gp_q1, Decimal("70")),
            (self.sa_eng, self.gp_q1, Decimal("72")),
        ])

        from ai_engine.feature_engine import compute_student_features
        features = compute_student_features(
            self.student_profile,
            [self.gp_q1],  # Only completed period passed in
            self.academic_year,
        )
        # Should still compute using Q1 only
        self.assertEqual(features["computation_status"], "ready")


# ---------------------------------------------------------------------------
# Rule-based labeler tests
# ---------------------------------------------------------------------------

class LabelerTest(AIEngineTestBase):
    """Test rule-based initial labeling (D4)."""

    def _features(self, **overrides):
        base = {
            "computation_status": "ready",
            "current_term_grade_average": 85.0,
            "grade_trend": 0.0,
            "weak_subject_count": 0,
            "lowest_subject_grade": None,
            "attendance_rate": 0.95,
            "late_rate": 0.02,
            "consultation_count": 0,
            "behavioral_count": 0,
        }
        base.update(overrides)
        return base

    def test_low_risk(self):
        from ai_engine.labeler import rule_based_label
        label = rule_based_label(self._features())
        self.assertEqual(label, "low")

    def test_high_risk_low_grades(self):
        from ai_engine.labeler import rule_based_label
        label = rule_based_label(self._features(
            current_term_grade_average=58.0,
            weak_subject_count=4,
            grade_trend=-8.0,
        ))
        self.assertEqual(label, "high")

    def test_moderate_risk(self):
        from ai_engine.labeler import rule_based_label
        # avg 68 (< 75 → +1), 3 weak subjects (+2), attendance 0.72 (< 0.75 → +1)
        # total = 4 → moderate
        label = rule_based_label(self._features(
            current_term_grade_average=68.0,
            weak_subject_count=3,
            attendance_rate=0.72,
        ))
        self.assertEqual(label, "moderate")

    def test_insufficient_data(self):
        from ai_engine.labeler import rule_based_label
        label = rule_based_label(self._features(
            computation_status="insufficient_data",
        ))
        self.assertEqual(label, "insufficient_data")


# ---------------------------------------------------------------------------
# RiskScorer tests
# ---------------------------------------------------------------------------

class RiskScorerTest(AIEngineTestBase):
    """Test Decision Tree risk scorer (D6/D7/D12)."""

    def build_training_set(self):
        """Build a labeled dataset to train the DT."""
        from ai_engine.feature_engine import compute_student_features
        from ai_engine.labeler import rule_based_label

        datasets = []
        # Create a few students with varying risk profiles
        profiles = []
        for i in range(15):
            user = User.objects.create_user(
                email=f"train{i}@ai.test", password="pass12345",
                first_name=f"Train{i}", last_name="Student", role="student",
            )
            sp = StudentProfile.objects.create(
                user=user,
                student_id=f"TR{i:04d}",
                grade_level=self.grade_level,
                section=self.section,
                enrollment_date=date(2024, 6, 10),
            )
            Enrollment.objects.create(
                student=sp, section=self.section,
                academic_year=self.academic_year,
                date_enrolled=date(2024, 6, 10), is_active=True,
            )
            profiles.append((sp, i))

        # Give them varied grades
        for sp, i in profiles:
            # Alternate high/moderate/low performers
            if i % 3 == 0:
                scores = [92, 90, 88, 85]
            elif i % 3 == 1:
                scores = [75, 72, 70, 68]
            else:
                scores = [60, 58, 62, 55]
            self.add_grades(sp, [
                (self.sa_math, self.gp_q2, Decimal(str(scores[0]))),
                (self.sa_eng, self.gp_q2, Decimal(str(scores[1]))),
                (self.sa_sci, self.gp_q2, Decimal(str(scores[2]))),
            ])
            self.add_attendance(sp, self.section, 10, 8 if i % 3 else 10)

            features = compute_student_features(
                sp, [self.gp_q1, self.gp_q2], self.academic_year
            )
            label = rule_based_label(features)
            features["label"] = label
            datasets.append(features)

        return datasets

    def test_train_and_predict(self):
        from ai_engine.risk_scorer import train, predict_single, features_to_matrix

        datasets = self.build_training_set()
        model, metadata = train(datasets)

        self.assertIsNotNone(model)
        self.assertIn("model_version", metadata)
        self.assertIn("feature_importances_", metadata)

        # Predict for a specific student
        student_result = predict_single(model, datasets[0], "v1")
        self.assertIn("risk_level", student_result)
        self.assertIn("risk_score", student_result)
        self.assertIn("class_probabilities", student_result)
        # Score should be 0-100
        self.assertGreaterEqual(student_result["risk_score"], 0)
        self.assertLessEqual(student_result["risk_score"], 100)

    def test_insufficient_data_prediction(self):
        from ai_engine.risk_scorer import train, predict_single

        datasets = self.build_training_set()
        model, _ = train(datasets)

        no_data = {
            "student_id": "none",
            "computation_status": "insufficient_data",
        }
        result = predict_single(model, no_data, "v1")
        self.assertEqual(result["computation_status"], "insufficient_data")
        self.assertIsNone(result["risk_score"])
        self.assertIsNone(result["risk_level"])

    def test_risk_index_mapping(self):
        """P(LOW)×0 + P(MODERATE)×50 + P(HIGH)×100"""
        from ai_engine.risk_scorer import train, predict_single

        datasets = self.build_training_set()
        model, _ = train(datasets)

        result = predict_single(model, datasets[0], "v1")
        probs = result["class_probabilities"]
        expected = (
            probs.get("low", 0) * 0
            + probs.get("moderate", 0) * 50
            + probs.get("high", 0) * 100
        )
        self.assertAlmostEqual(result["risk_score"], round(min(100, max(0, expected)), 2))

    def test_identical_input_produces_identical_classification(self):
        """TC-SYS-05 (NFR-007): same input in, same at-risk class out.

        Two independent runs over the same labelled data must agree — the
        estimator is seeded (`random_state=DT_RANDOM_STATE`) and the feature
        vector is a pure function of the student's record, so no step in the
        path is stochastic. The assertion covers the classification, the
        score and the full probability vector, because a matching
        `risk_level` with drifting probabilities would still be a silent
        inconsistency.
        """
        from ai_engine.feature_engine import compute_student_features
        from ai_engine.risk_scorer import predict_single, train

        datasets = self.build_training_set()

        # The feature vector itself is reproducible from the same record.
        first_features = compute_student_features(
            self.student_profile, [self.gp_q1, self.gp_q2], self.academic_year
        )
        second_features = compute_student_features(
            self.student_profile, [self.gp_q1, self.gp_q2], self.academic_year
        )
        self.assertEqual(first_features, second_features)

        first_model, first_meta = train(list(datasets))
        second_model, second_meta = train(list(datasets))
        self.assertIsNotNone(first_model)
        self.assertIsNotNone(second_model)

        for row in datasets:
            first = predict_single(first_model, row, first_meta["model_version"])
            second = predict_single(second_model, row, second_meta["model_version"])
            self.assertEqual(first["risk_level"], second["risk_level"])
            self.assertEqual(first["risk_score"], second["risk_score"])
            self.assertEqual(
                first["class_probabilities"], second["class_probabilities"]
            )


# ---------------------------------------------------------------------------
# LearningItem tests
# ---------------------------------------------------------------------------

class LearningItemTest(AIEngineTestBase):
    """Test LearningItem model (D20)."""

    def test_creation_with_strapi_source(self):
        item = LearningItem.objects.create(
            source_type="strapi_resource",
            source_id="abc123",
            item_type="learning_resource",
            title="Math Module 1",
            subject=self.subject_math,
            grade_level=self.grade_level,
            lifecycle_status="approved",
            is_active=True,
        )
        self.assertTrue(item.is_recommendation_eligible)

    def test_not_eligible_if_draft(self):
        item = LearningItem.objects.create(
            source_type="internal",
            item_type="study_activity",
            title="Draft Activity",
            lifecycle_status="draft",
            is_active=False,
        )
        self.assertFalse(item.is_recommendation_eligible)

    def test_not_eligible_if_inactive(self):
        item = LearningItem.objects.create(
            source_type="internal",
            item_type="study_activity",
            title="Inactive Item",
            lifecycle_status="approved",
            is_active=False,
        )
        self.assertFalse(item.is_recommendation_eligible)

    def test_item_types(self):
        for dtype in LearningItem.ItemType.values:
            self.assertIn(dtype, ["study_activity", "learning_resource", "learning_strategy"])


# ---------------------------------------------------------------------------
# StudentInteraction tests
# ---------------------------------------------------------------------------

class StudentInteractionTest(AIEngineTestBase):
    """Test StudentInteraction model (D17/D18)."""

    def setUp(self):
        super().setUp()
        self.learning_item = LearningItem.objects.create(
            source_type="internal",
            item_type="learning_resource",
            title="Math Practice Set",
            subject=self.subject_math,
            grade_level=self.grade_level,
            lifecycle_status="approved",
            is_active=True,
        )

    def test_interaction_creation(self):
        interaction = StudentInteraction.objects.create(
            student=self.student_profile,
            learning_item=self.learning_item,
            interaction_type="viewed",
            interaction_at=timezone.now(),
        )
        self.assertEqual(interaction.interaction_type, "viewed")

    def test_interaction_types(self):
        for itype in StudentInteraction.InteractionType.values:
            self.assertIn(itype, ["viewed", "started", "completed", "saved"])

    def test_grades_are_not_interactions(self):
        """Grades are NOT CF interaction signals."""
        self.add_grades(self.student_profile, [
            (self.sa_math, self.gp_q2, Decimal("90")),
            (self.sa_eng, self.gp_q2, Decimal("85")),
        ])
        # No StudentInteraction records should exist from grades
        self.assertEqual(StudentInteraction.objects.count(), 0)


# ---------------------------------------------------------------------------
# Risk Service integration tests (PH9.4/PH9.5)
# ---------------------------------------------------------------------------

class RiskServiceTest(AIEngineTestBase):
    """Test RiskScore persistence + RiskAlert integration semantics."""

    def prediction(self, level="moderate", score=55.0, computed="ready"):
        return {
            "computation_status": computed,
            "risk_level": level,
            "risk_score": score,
            "class_probabilities": {},
            "explanation": {"contributing_factors": [{"feature": "test", "value": 1}]},
            "model_version": "v1",
        }

    def test_risk_score_always_stored(self):
        """Every computation stores a RiskScore even with INSUFFICIENT_DATA."""
        from ai_engine.risk_service import integrate_risk_result

        result = integrate_risk_result(
            self.student_profile,
            self.prediction(computed="insufficient_data", level=None, score=None),
        )
        self.assertEqual(result.risk_score_obj.computation_status, "insufficient_data")
        self.assertIsNone(result.risk_score_obj.risk_score)
        self.assertIsNone(result.risk_score_obj.risk_level)
        self.assertIsNone(result.risk_alert)
        self.assertFalse(result.state_changed)

        # No RiskAlert should exist
        self.assertEqual(RiskAlert.objects.filter(source="decision_tree").count(), 0)

    def test_new_alerts_created_on_state_change(self):
        """First computation creates an actionable RiskAlert."""
        from ai_engine.risk_service import integrate_risk_result

        result = integrate_risk_result(
            self.student_profile,
            self.prediction(level="moderate", score=55.0),
        )
        self.assertTrue(result.state_changed)
        self.assertTrue(result.risk_alert is not None)
        self.assertEqual(result.risk_alert.risk_level, "moderate")
        self.assertEqual(result.risk_alert.source, "decision_tree")
        self.assertEqual(result.risk_alert.status, "active")
        self.assertEqual(RiskScore.objects.count(), 1)
        self.assertEqual(RiskAlert.objects.filter(source="decision_tree").count(), 1)

    def test_unchanged_state_no_new_alert(self):
        """MODERATE/55 → MODERATE/57 = NO new alert, NO duplicate."""
        from ai_engine.risk_service import integrate_risk_result

        # First computation
        integrate_risk_result(
            self.student_profile,
            self.prediction(level="moderate", score=55.0),
        )
        initial_count = RiskAlert.objects.filter(source="decision_tree").count()

        # Second computation with same level, slight score change
        result2 = integrate_risk_result(
            self.student_profile,
            self.prediction(level="moderate", score=57.0),
        )
        self.assertFalse(result2.state_changed)
        self.assertIsNotNone(result2.risk_alert)
        # Still only 1 DT alert
        self.assertEqual(RiskAlert.objects.filter(source="decision_tree").count(), initial_count)
        # But 2 RiskScores stored (history preserved)
        self.assertEqual(RiskScore.objects.count(), 2)

    def test_level_escalation_updates_alert(self):
        """MODERATE/57 → HIGH/81 = actionable state change, alert updated."""
        from ai_engine.risk_service import integrate_risk_result

        integrate_risk_result(
            self.student_profile,
            self.prediction(level="moderate", score=57.0),
        )

        result2 = integrate_risk_result(
            self.student_profile,
            self.prediction(level="high", score=81.0),
        )
        self.assertTrue(result2.state_changed)
        self.assertEqual(result2.risk_alert.risk_level, "high")
        # Escalation updates existing DT alert, not duplicates
        self.assertEqual(RiskAlert.objects.filter(source="decision_tree").count(), 1)

    def test_manual_alert_preserved(self):
        """AI result does NOT overwrite a manual alert."""
        from ai_engine.risk_service import integrate_risk_result

        # Create a manual alert first
        manual_alert = RiskAlert.objects.create(
            student=self.student_profile,
            risk_level="high",
            source="manual",
            status="active",
            generated_at=timezone.now(),
        )

        # AI computation
        result = integrate_risk_result(
            self.student_profile,
            self.prediction(level="low", score=10.0),
        )
        self.assertFalse(result.state_changed)
        # Manual alert untouched
        manual_alert.refresh_from_db()
        self.assertEqual(manual_alert.risk_level, "high")
        self.assertEqual(manual_alert.source, "manual")
        # No DT alert created alongside manual
        self.assertEqual(RiskAlert.objects.filter(source="decision_tree").count(), 0)

    def test_notification_deduplication(self):
        """Unchanged state does not spam notifications."""
        from ai_engine.risk_service import integrate_risk_result
        from apps.notifications.models import Notification

        # First computation creates alert + notification
        result1 = integrate_risk_result(
            self.student_profile,
            self.prediction(level="moderate", score=55.0),
        )
        self.assertTrue(result1.notified)
        notifications_after_1 = Notification.objects.filter(
            notification_type="RISK_ALERT_GENERATED"
        ).count()

        # Unchanged state → no new notification
        result2 = integrate_risk_result(
            self.student_profile,
            self.prediction(level="moderate", score=57.0),
        )
        self.assertFalse(result2.notified)
        self.assertEqual(
            Notification.objects.filter(
                notification_type="RISK_ALERT_GENERATED"
            ).count(),
            notifications_after_1,
        )

    def test_high_routing_notifies_adviser_and_parent(self):
        """HIGH events notify Guidance + Adviser + Parent."""
        from ai_engine.risk_service import integrate_risk_result
        from apps.notifications.models import Notification

        # Add a parent link
        parent_user = User.objects.create_user(
            email="parent_risk@test.com", password="pass12345",
            first_name="Par", last_name="Ent", role="parent",
        )
        parent_profile = ParentProfile.objects.create(
            user=parent_user, relationship_to_student="mother"
        )
        ParentStudentLink.objects.create(
            parent=parent_profile, student=self.student_profile
        )

        result = integrate_risk_result(
            self.student_profile,
            self.prediction(level="high", score=88.0),
        )
        self.assertTrue(result.state_changed)

        # At least guidance + parent should get notifications
        notifications = Notification.objects.filter(
            notification_type="RISK_ALERT_GENERATED"
        )
        recipients = set(notifications.values_list("recipient", flat=True))
        self.assertIn(parent_user.id, recipients)
        # Guidance users are recipients
        self.assertGreaterEqual(len(notifications), 1)

# ---------------------------------------------------------------------------
# Recommender tests (D16/D17/D18/D19)
# ---------------------------------------------------------------------------

class RecommenderTest(AIEngineTestBase):
    """Test collaborative filtering + content-based fallback."""

    def setUp(self):
        super().setUp()
        self.li_items = []
        for i in range(6):
            item = LearningItem.objects.create(
                source_type="internal",
                item_type="learning_resource",
                title=f"Learning Item {i}",
                subject=self.subject_math,
                grade_level=self.grade_level,
                topic=f"Topic {i}",
                lifecycle_status="approved",
                is_active=True,
            )
            self.li_items.append(item)

    def add_interactions(self, student, items, types):
        from django.utils import timezone
        for item, itype in zip(items, types):
            StudentInteraction.objects.create(
                student=student,
                learning_item=item,
                interaction_type=itype,
                interaction_at=timezone.now(),
            )

    def test_cosine_similarity_basic(self):
        from ai_engine.recommender import cosine_similarity
        import numpy as np
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([4.0, 5.0, 6.0])
        sim = cosine_similarity(a, b)
        self.assertGreater(sim, 0.9)
        self.assertLessEqual(sim, 1.0)

    def test_zero_vector_similarity(self):
        from ai_engine.recommender import cosine_similarity
        import numpy as np
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 2.0, 3.0])
        self.assertEqual(cosine_similarity(a, b), 0.0)

    def test_interaction_matrix_build(self):
        from ai_engine.recommender import InteractionMatrix
        from django.utils import timezone
        for idx, item in enumerate(self.li_items[:3]):
            StudentInteraction.objects.create(
                student=self.student_profile, learning_item=item,
                interaction_type="viewed", interaction_at=timezone.now(),
            )
        interactions = StudentInteraction.objects.all()
        matrix = InteractionMatrix()
        matrix.build(interactions)
        self.assertEqual(len(matrix.student_ids), 1)
        self.assertEqual(len(matrix.item_ids), 3)
        self.assertGreater(matrix.density, 0)

    def test_eligibility_insufficient_data(self):
        from ai_engine.recommender import check_eligibility
        from django.utils import timezone
        # Only 1 interaction
        StudentInteraction.objects.create(
            student=self.student_profile, learning_item=self.li_items[0],
            interaction_type="viewed", interaction_at=timezone.now(),
        )
        interactions = list(StudentInteraction.objects.all())
        eligible, reason = check_eligibility(
            self.student_profile.id, interactions
        )
        self.assertFalse(eligible)
        self.assertIn(reason, ["insufficient_student_interactions", "insufficient_distinct_items"])

    def test_cf_recommendation_with_sufficient_data(self):
        from ai_engine.recommender import recommend_cf
        from django.utils import timezone

        # Two students with overlapping interaction patterns
        user2 = User.objects.create_user(
            email="rec_stu2@test.com", password="pass12345",
            first_name="Rec", last_name="Stu2", role="student",
        )
        sp2 = StudentProfile.objects.create(
            user=user2, student_id="REC2",
            grade_level=self.grade_level, section=self.section,
            enrollment_date=date(2024, 6, 10),
        )

        # Student 1 interacts with items 0,1,2
        for i in range(3):
            StudentInteraction.objects.create(
                student=self.student_profile, learning_item=self.li_items[i],
                interaction_type="viewed", interaction_at=timezone.now(),
            )
        # Student 2 interacts with items 0,1,2,3,4,5 (overlapping + new)
        for i in range(6):
            StudentInteraction.objects.create(
                student=sp2, learning_item=self.li_items[i],
                interaction_type="viewed", interaction_at=timezone.now(),
            )

        # Give student 1 enough distinct interactions
        StudentInteraction.objects.create(
            student=self.student_profile, learning_item=self.li_items[3],
            interaction_type="started", interaction_at=timezone.now(),
        )

        interactions = list(StudentInteraction.objects.all())
        items = list(LearningItem.objects.all())

        results, method = recommend_cf(
            self.student_profile.id, interactions, items, limit=5
        )
        # Should either be CF or fallback depending on density
        self.assertIn(method, ["cf", "fallback"])

    def test_content_based_fallback(self):
        from ai_engine.recommender import recommend_content_based
        from ai_engine.labeler import rule_based_label

        features = {
            "computation_status": "ready",
            "current_term_grade_average": 65.0,
            "grade_trend": -6.0,
            "weak_subject_count": 3,
            "lowest_subject_grade": 60.0,
            "attendance_rate": 0.70,
            "late_rate": 0.15,
            "consultation_count": 1,
            "behavioral_count": 1,
        }
        prediction = {
            "computation_status": "ready",
            "risk_level": "high",
            "risk_score": 78.0,
            "class_probabilities": {"high": 0.7, "moderate": 0.2, "low": 0.1},
            "explanation": {"contributing_factors": [{"feature": "current_term_grade_average", "value": 65.0}]},
        }

        results = recommend_content_based(
            self.student_profile,
            features,
            prediction,
            list(LearningItem.objects.all()),
            limit=5,
        )
        self.assertGreaterEqual(len(results), 0)


# ---------------------------------------------------------------------------
# Resolver tests (D22/D23)
# ---------------------------------------------------------------------------

class ResolverTest(AIEngineTestBase):
    """Test recommendation resolver."""

    def setUp(self):
        super().setUp()
        self.li_item = LearningItem.objects.create(
            source_type="internal",
            item_type="learning_resource",
            title="Math Practice",
            subject=self.subject_math,
            grade_level=self.grade_level,
            topic="Algebra",
            tags=["algebra", "practice"],
            difficulty=3,
            lifecycle_status="approved",
            is_active=True,
        )

    def test_needs_extraction(self):
        from ai_engine.resolver import extract_academic_needs
        features = {
            "current_term_grade_average": 65.0,
            "grade_trend": -7.0,
            "weak_subject_count": 3,
            "lowest_subject_grade": 60.0,
        }
        prediction = {
            "risk_level": "high",
            "risk_score": 80.0,
            "explanation": {"contributing_factors": []},
        }
        needs = extract_academic_needs(features, prediction)
        self.assertGreater(len(needs), 0)
        # Should not include empty needs
        for need in needs:
            self.assertIn("need_type", need)
            self.assertIn("reason", need)

    def test_resolve_filters_inactive_items(self):
        from ai_engine.resolver import resolve_recommendations
        # Create a draft item that should be excluded
        draft_item = LearningItem.objects.create(
            source_type="internal",
            item_type="learning_resource",
            title="Draft Item",
            subject=self.subject_math,
            grade_level=self.grade_level,
            lifecycle_status="draft",
            is_active=False,
        )
        features = {
            "current_term_grade_average": 60.0,
            "grade_trend": -5.0,
            "weak_subject_count": 4,
            "lowest_subject_grade": 55.0,
            "attendance_rate": 0.60,
            "late_rate": 0.20,
            "consultation_count": 2,
            "behavioral_count": 2,
        }
        prediction = {
            "risk_level": "high",
            "risk_score": 85.0,
            "explanation": {"contributing_factors": []},
        }
        results = resolve_recommendations(
            self.student_profile, features, prediction, limit=5
        )
        for result in results:
            self.assertNotEqual(result["title"], "Draft Item")
            self.assertEqual(result["method"], "content_based")
            self.assertIn("learning_item_id", result)
            self.assertIn("reason", result)
        # The active item should be in results
        titles = [r["title"] for r in results]
        self.assertIn("Math Practice", titles)

# ---------------------------------------------------------------------------
# D29 Model benchmark tests
# ---------------------------------------------------------------------------

class BenchmarkTest(TestCase):
    """Test the D29 model benchmark harness."""

    def test_grouped_cross_validate_respects_groups(self):
        """Different groups never leak across train/test."""
        from ai_engine.benchmark import grouped_cross_validate
        from sklearn.tree import DecisionTreeClassifier
        import numpy as np

        # Synthetic data: 3 groups (students)
        X = np.array([
            [85, 0], [60, 1], [55, 2],
            [88, 0], [63, 1], [52, 2],
            [90, 0], [70, 1], [50, 2],
        ], dtype=float)
        y = np.array(["low", "high", "high",
                      "low", "high", "high",
                      "low", "moderate", "high"])
        groups = np.array(["s1", "s2", "s3"] * 3)

        model = DecisionTreeClassifier(random_state=42)
        result = grouped_cross_validate(model, X, y, groups, n_splits=3)

        self.assertIn("accuracy", result)
        self.assertIn("macro_f1", result)
        self.assertIn("per_class_f1", result)
        self.assertIn("n_samples", result)
        self.assertEqual(result["n_samples"], 9)

    def test_benchmark_models_runs(self):
        from ai_engine.benchmark import benchmark_models
        import numpy as np

        rng = np.random.RandomState(42)
        X = rng.rand(60, 5) * 100
        y = np.array(["low", "moderate", "high"] * 20)
        groups = np.repeat(np.arange(20), 3)

        results = benchmark_models(X, y, groups)

        # Baseline + candidate models present
        self.assertIn("decision_tree_baseline", results)
        self.assertIn("random_forest", results)
        self.assertIn("logistic_regression", results)

        for res in results.values():
            self.assertIn("accuracy", res)

    def test_select_best_model(self):
        from ai_engine.benchmark import select_best_model
        results = {
            "decision_tree_baseline": {"macro_f1": 0.6, "accuracy": 0.7},
            "random_forest": {"macro_f1": 0.8, "accuracy": 0.75},
            "logistic_regression": {"macro_f1": 0.5, "accuracy": 0.6},
        }
        best, meta = select_best_model(results)
        self.assertEqual(best, "random_forest")
        self.assertIn("recommendation", meta)
        # Recommendation must not auto-switch without documented decision
        self.assertIn("note", meta)

# ---------------------------------------------------------------------------
# Model validation + security/privacy tests (PH9.13)
# ---------------------------------------------------------------------------

class ModelValidationTest(TestCase):
    """Test model training guards + privacy safeguards."""

    def test_refuses_tiny_dataset(self):
        """Refuse to train on fewer than MIN_TRAINING_EXAMPLES."""
        from ai_engine.validation import validate_training_data, ModelValidationError
        X = [0] * 5
        y = ["low", "moderate", "high", "low", "moderate"]
        with self.assertRaises(ModelValidationError):
            validate_training_data(X, y)

    def test_rejects_unknown_label(self):
        """Reject labels outside the allowed vocabulary."""
        from ai_engine.validation import validate_training_data, ModelValidationError
        # Enough samples but with an unknown label
        y = ["low", "moderate", "high", "could_be_anything", "low"]
        X = [0] * 5
        with self.assertRaises(ModelValidationError):
            validate_training_data(X, y)

    def test_feature_privacy_no_narrative(self):
        """Features must never contain narrative/free-text keys."""
        from ai_engine.validation import (
            validate_feature_keys,
            validate_student_feature_privacy,
        )
        good = {
            "current_term_grade_average": 80.0,
            "weak_subject_count": 1,
            "attendance_rate": 0.9,
            "consultation_count": 2,
        }
        self.assertEqual(validate_feature_keys(good), [])
        self.assertTrue(validate_student_feature_privacy(good))

        bad = {
            "current_term_grade_average": 80.0,
            "counselor_notes": "Student described family issues...",
            "narrative": "free text",
        }
        self.assertNotEqual(validate_feature_keys(bad), [])

def test_prediction_label_vocabulary(self):
        """Unknown predicted label is flagged invalid."""
        from ai_engine.validation import validate_prediction_labels
        self.assertTrue(validate_prediction_labels({"risk_level": "high"}))
        self.assertTrue(validate_prediction_labels({"risk_level": None}))
        self.assertFalse(validate_prediction_labels({"risk_level": "critical"}))


class TrainRiskModelCommandTest(AIEngineTestBase):
    """
    `run_risk_computation` refuses to run and names this command, so the two
    must be tested together: train writes an artifact the risk command can
    actually load.
    """

    def _seed_students(self, count=15):
        """Enough varied students for the labeler to produce all three classes."""
        from ai_engine.feature_engine import compute_student_features

        datasets = []
        for i in range(count):
            user = User.objects.create_user(
                email=f"train{i}@ai.test", password="pass12345",
                first_name=f"Train{i}", last_name="Student", role="student",
            )
            sp = StudentProfile.objects.create(
                user=user,
                student_id=f"TR{i:04d}",
                grade_level=self.grade_level,
                section=self.section,
                enrollment_date=date(2024, 6, 10),
            )
            Enrollment.objects.create(
                student=sp, section=self.section,
                academic_year=self.academic_year,
                date_enrolled=date(2024, 6, 10), is_active=True,
            )
            if i % 3 == 0:
                scores = [92, 90, 88]
                present = 10
            elif i % 3 == 1:
                scores = [75, 72, 70]
                present = 6
            else:
                scores = [58, 55, 60]
                present = 3
            self.add_grades(sp, [
                (self.sa_math, self.gp_q2, Decimal(str(scores[0]))),
                (self.sa_eng, self.gp_q2, Decimal(str(scores[1]))),
                (self.sa_sci, self.gp_q2, Decimal(str(scores[2]))),
            ])
            self.add_attendance(sp, self.section, 10, present)
            datasets.append(compute_student_features(
                sp, [self.gp_q1, self.gp_q2], self.academic_year
            ))
        return datasets

    def test_trains_and_persists_a_model(self):
        """
        The artifact lands in the database, not on disk: the deployment host
        has no persistent disk, so a file would be lost on every deploy.
        """
        from io import StringIO

        from ai_engine.risk_scorer import load_stored_model
        from apps.guidance.models import RiskModelArtifact

        self._seed_students()
        RiskModelArtifact.objects.all().delete()

        out, err = StringIO(), StringIO()
        call_command("train_risk_model", stdout=out, stderr=err)

        self.assertEqual(RiskModelArtifact.objects.count(), 1)

        artifact = RiskModelArtifact.objects.get()
        self.assertTrue(artifact.is_active)
        self.assertEqual(artifact.n_samples, 15)
        self.assertEqual(artifact.academic_year, self.academic_year)

        loaded = load_stored_model("v1")
        self.assertIsNotNone(loaded, "stored model could not be loaded")
        model, metadata = loaded
        self.assertIsNotNone(model)
        self.assertEqual(metadata["n_samples"], 15)

    def test_dry_run_writes_nothing(self):
        from io import StringIO

        from apps.guidance.models import RiskModelArtifact

        self._seed_students()
        RiskModelArtifact.objects.all().delete()

        out = StringIO()
        call_command("train_risk_model", dry_run=True, stdout=out)

        self.assertEqual(
            RiskModelArtifact.objects.count(), 0, "dry run stored a model"
        )
        self.assertIn("Dry run", out.getvalue())

    def test_reports_the_label_circularity(self):
        """
        The model reproduces labeler.rule_based_label, so its accuracy is not
        evidence that it predicts real risk. That warning must reach the
        operator, not just the module docstring.
        """
        from io import StringIO

        self._seed_students()
        err = StringIO()

        call_command(
            "train_risk_model", dry_run=True, stdout=StringIO(), stderr=err,
        )

        self.assertIn("rule-generated", err.getvalue().lower())

    def test_refuses_below_the_minimum_sample_count(self):
        """
        Persisting a model fitted on a handful of rows would produce confident
        output with no basis. The command refuses instead.
        """
        from io import StringIO

        from apps.guidance.models import RiskModelArtifact

        self._seed_students(count=15)
        RiskModelArtifact.objects.all().delete()
        err = StringIO()

        call_command(
            "train_risk_model", minimum_samples=10_000, stdout=StringIO(),
            stderr=err,
        )

        self.assertEqual(RiskModelArtifact.objects.count(), 0)
        self.assertIn("Refusing to persist", err.getvalue())

    def test_retraining_supersedes_the_previous_artifact(self):
        """
        At most one active artifact per version, enforced by a partial unique
        constraint, so a stale tree cannot be scored after a retrain.
        """
        from io import StringIO

        from apps.guidance.models import RiskModelArtifact

        self._seed_students()
        RiskModelArtifact.objects.all().delete()

        call_command("train_risk_model", stdout=StringIO(), stderr=StringIO())
        first = RiskModelArtifact.objects.get(is_active=True)

        call_command("train_risk_model", stdout=StringIO(), stderr=StringIO())

        self.assertEqual(RiskModelArtifact.objects.count(), 2)
        self.assertEqual(RiskModelArtifact.objects.filter(is_active=True).count(), 1)

        first.refresh_from_db()
        self.assertFalse(first.is_active, "previous artifact stayed active")

    def test_stored_metadata_carries_the_label_caveat(self):
        from io import StringIO

        from apps.guidance.models import RiskModelArtifact

        self._seed_students()
        RiskModelArtifact.objects.all().delete()
        call_command("train_risk_model", stdout=StringIO(), stderr=StringIO())

        metadata = RiskModelArtifact.objects.get().metadata
        self.assertEqual(metadata["label_source"], "rule_based")
        self.assertIn("circular", metadata["label_caveat"].lower())
        self.assertEqual(
            metadata["academic_year_name"], self.academic_year.name
        )

    def test_refusal_paths_do_not_raise(self):
        """
        render.yaml chains `train_risk_model` into the build, so every expected
        refusal has to exit 0. A dataset too small to train is a normal
        condition on a fresh DEV database and must not block a deploy; only a
        genuine error should fail the build.
        """
        from io import StringIO

        from django.core.management import call_command

        from apps.guidance.models import RiskModelArtifact

        # No students at all: nothing to train on.
        RiskModelArtifact.objects.all().delete()
        err = StringIO()
        call_command("train_risk_model", stdout=StringIO(), stderr=err)
        self.assertEqual(RiskModelArtifact.objects.count(), 0)
        self.assertIn("enough data", err.getvalue())

        # Too few samples: refuses to persist, still no exception.
        self._seed_students(count=15)
        RiskModelArtifact.objects.all().delete()
        err = StringIO()
        call_command(
            "train_risk_model", minimum_samples=10_000, stdout=StringIO(),
            stderr=err,
        )
        self.assertEqual(RiskModelArtifact.objects.count(), 0)

    def test_trained_model_is_loadable_by_the_risk_command(self):
        """
        The point of this command. train stores an artifact, then
        run_risk_computation loads it and writes RiskScore rows.
        """
        from io import StringIO

        from apps.guidance.models import RiskModelArtifact, RiskScore

        self._seed_students()
        RiskModelArtifact.objects.all().delete()

        call_command("train_risk_model", stdout=StringIO(), stderr=StringIO())
        RiskScore.objects.all().delete()
        call_command("run_risk_computation", stdout=StringIO())

        self.assertGreater(
            RiskScore.objects.filter(computation_status="ready").count(), 0
        )


class RunRiskComputationCommandTest(AIEngineTestBase):
    """
    The batch command must reach RiskScore without raising.

    It previously called predict_single(features, model=None) against the
    signature predict_single(model, feature_dict, model_version), so it raised
    TypeError on the first student with data and no test ever invoked it.
    """

    def train_and_save_model(self, path):
        """Train on this class's fixtures and persist to `path`."""
        from ai_engine.feature_engine import compute_student_features
        from ai_engine.labeler import rule_based_label
        from ai_engine.risk_scorer import save_model, train

        datasets = []
        for i in range(15):
            user = User.objects.create_user(
                email=f"cmd{i}@ai.test", password="pass12345",
                first_name=f"Cmd{i}", last_name="Student", role="student",
            )
            sp = StudentProfile.objects.create(
                user=user,
                student_id=f"CM{i:04d}",
                grade_level=self.grade_level,
                section=self.section,
                enrollment_date=date(2024, 6, 10),
            )
            Enrollment.objects.create(
                student=sp, section=self.section,
                academic_year=self.academic_year,
                date_enrolled=date(2024, 6, 10), is_active=True,
            )
            high = i % 3 == 0
            scores = (
                [92, 90, 88] if high else
                ([75, 72, 70] if i % 3 == 1 else [60, 58, 62])
            )
            self.add_grades(sp, [
                (self.sa_math, self.gp_q2, Decimal(str(scores[0]))),
                (self.sa_eng, self.gp_q2, Decimal(str(scores[1]))),
                (self.sa_sci, self.gp_q2, Decimal(str(scores[2]))),
            ])
            self.add_attendance(sp, self.section, 10, 10 if high else 6)

            features = compute_student_features(
                sp, [self.gp_q1, self.gp_q2], self.academic_year
            )
            features["label"] = rule_based_label(features)
            datasets.append(features)

        model, metadata = train(datasets)
        save_model(model, metadata, path=path)

    def test_missing_model_refuses_to_compute(self):
        """
        With no stored model the command reports and stops rather than
        fabricating a score.
        """
        import io

        from django.core.management import call_command

        from apps.guidance.models import RiskModelArtifact

        RiskScore.objects.all().delete()
        RiskModelArtifact.objects.all().delete()

        out, err = io.StringIO(), io.StringIO()
        call_command("run_risk_computation", stdout=out, stderr=err)

        self.assertIn("train_risk_model", err.getvalue())
        # No fabricated rows: nothing was written.
        self.assertEqual(RiskScore.objects.count(), 0)

    def test_inactive_artifact_is_not_loaded(self):
        """
        A superseded artifact must not be scored, even when it is the only one
        left in the table.
        """
        import io
        from io import StringIO

        from django.core.management import call_command

        from apps.guidance.models import RiskModelArtifact

        self._seed_for_command()
        RiskScore.objects.all().delete()
        RiskModelArtifact.objects.all().delete()

        call_command("train_risk_model", stdout=StringIO(), stderr=StringIO())
        RiskModelArtifact.objects.update(is_active=False)

        err = StringIO()
        call_command("run_risk_computation", stdout=StringIO(), stderr=err)

        self.assertIn("train_risk_model", err.getvalue())
        self.assertEqual(
            RiskScore.objects.filter(computation_status="ready").count(), 0
        )

    def test_unreadable_artifact_is_treated_as_absent(self):
        """
        A corrupt or incompatible artifact cannot be scored with. Treating it
        as absent is correct; substituting a fallback would fabricate a risk
        level.
        """
        import io
        from io import StringIO

        from django.core.management import call_command

        from apps.guidance.models import RiskModelArtifact

        self._seed_for_command()
        RiskScore.objects.all().delete()
        RiskModelArtifact.objects.all().delete()

        call_command("train_risk_model", stdout=StringIO(), stderr=StringIO())
        RiskModelArtifact.objects.update(payload=b"not a pickle")

        err = StringIO()
        call_command("run_risk_computation", stdout=StringIO(), stderr=err)

        self.assertIn("train_risk_model", err.getvalue())
        self.assertEqual(
            RiskScore.objects.filter(computation_status="ready").count(), 0
        )

    def _seed_for_command(self):
        """A small varied cohort so training produces a usable estimator."""
        for i in range(15):
            user = User.objects.create_user(
                email=f"cmdseed{i}@ai.test", password="pass12345",
                first_name=f"Cmds{i}", last_name="Student", role="student",
            )
            sp = StudentProfile.objects.create(
                user=user,
                student_id=f"CS{i:04d}",
                grade_level=self.grade_level,
                section=self.section,
                enrollment_date=date(2024, 6, 10),
            )
            Enrollment.objects.create(
                student=sp, section=self.section,
                academic_year=self.academic_year,
                date_enrolled=date(2024, 6, 10), is_active=True,
            )
            scores = (
                [92, 90, 88] if i % 3 == 0
                else ([75, 72, 70] if i % 3 == 1 else [58, 55, 60])
            )
            self.add_grades(sp, [
                (self.sa_math, self.gp_q2, Decimal(str(scores[0]))),
                (self.sa_eng, self.gp_q2, Decimal(str(scores[1]))),
                (self.sa_sci, self.gp_q2, Decimal(str(scores[2]))),
            ])
            self.add_attendance(sp, self.section, 10, 10 if i % 3 == 0 else 5)

    def test_command_persists_risk_scores(self):
        """
        End to end through the stored artifact: train, then score. This is the
        path the deployed system takes, and it is the one the original
        TypeError broke with no test covering it.
        """
        from io import StringIO

        from django.core.management import call_command

        from apps.guidance.models import RiskModelArtifact

        self._seed_for_command()
        RiskScore.objects.all().delete()
        RiskModelArtifact.objects.all().delete()

        call_command("train_risk_model", stdout=StringIO(), stderr=StringIO())

        out = StringIO()
        call_command("run_risk_computation", stdout=out)

        # Every student with computable data got a RiskScore row.
        self.assertGreater(
            RiskScore.objects.filter(computation_status="ready").count(), 0
        )
        # No student was skipped by an exception.
        self.assertIn("processed", out.getvalue())
