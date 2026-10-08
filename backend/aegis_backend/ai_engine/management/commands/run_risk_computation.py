"""
Scheduled batch risk computation (PH9 D9 primary trigger).

Computes risk scores for all active students and integrates them into
RiskScore + RiskAlert (+ notifications).

Run via Celery beat / cron:
    python manage.py run_risk_computation

Requires a trained model on disk (ai_engine/saved_models/decision_tree_v1.pkl).
Write one with `python manage.py train_risk_model`. When the model is absent this
command refuses to run rather than inventing a score: an unfitted estimator would
raise, and a fabricated 0 would read as real risk data.
"""

import logging

from django.core.management.base import BaseCommand

from ai_engine.feature_engine import compute_student_features
from ai_engine.risk_service import integrate_risk_result
from ai_engine.risk_scorer import load_model, predict_single

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run scheduled batch risk computation for all active students."

    def add_arguments(self, parser):
        parser.add_argument(
            "--academic-year-id",
            type=str,
            default=None,
            help="Restrict to a specific academic year (id).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute but do not persist or notify.",
        )

    def handle(self, *args, **options):
        from apps.accounts.models import StudentProfile
        from apps.academics.models import AcademicYear, GradingPeriod
        from datetime import date

        academic_year = None
        if options.get("academic_year_id"):
            academic_year = AcademicYear.objects.get(
                id=options["academic_year_id"]
            )
        else:
            academic_year = (
                AcademicYear.objects.filter(is_current=True)
                .order_by("-start_date")
                .first()
            )

        if academic_year is None:
            self.stderr.write(
                "No current academic year found; cannot compute risk."
            )
            return

        # Completed grading periods (periods whose end_date is in the past)
        today = date.today()
        completed_periods = GradingPeriod.objects.filter(
            academic_year=academic_year,
            end_date__lte=today,
        ).order_by("order")

        if not completed_periods.exists():
            self.stdout.write(
                "No completed grading periods; skipping risk computation."
            )
            return

        # A trained estimator is required. Never fall back to a placeholder.
        try:
            model, _metadata = load_model()
        except FileNotFoundError:
            self.stderr.write(
                "No trained risk model found. Run `manage.py train_risk_model` "
                "first; refusing to compute risk without one."
            )
            return

        # All active students (optionally scoped by academic year via enrollment)
        students = StudentProfile.objects.filter(is_active=True)

        self.stdout.write(
            f"Computing risk for {students.count()} students across "
            f"{completed_periods.count()} completed period(s) of "
            f"{academic_year.name}."
        )

        processed = 0
        alerts = 0
        insufficient = 0
        dry_run = options.get("dry_run", False)

        for student in students:
            features = compute_student_features(
                student, list(completed_periods), academic_year
            )

            if features.get("computation_status") == "insufficient_data":
                if not dry_run:
                    integrate_risk_result(
                        student,
                        {
                            "computation_status": "insufficient_data",
                            "risk_level": None,
                            "risk_score": None,
                            "explanation": {},
                        },
                        model_version="v1",
                        feature_snapshot=features,
                        dispatch_notifications=False,
                    )
                insufficient += 1
                processed += 1
                continue

            prediction = predict_single(model, features, "v1")

            if not dry_run:
                result = integrate_risk_result(
                    student,
                    prediction,
                    model_version="v1",
                    feature_snapshot=features,
                    dispatch_notifications=True,
                )
                if result.state_changed:
                    alerts += 1
            else:
                self.stdout.write(
                    f"  (dry-run) {student.user.get_full_name()}: "
                    f"{prediction.get('risk_level')} "
                    f"score={prediction.get('risk_score')}"
                )
            processed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {processed} processed, {alerts} actionable alerts, "
                f"{insufficient} insufficient-data."
            )
        )
