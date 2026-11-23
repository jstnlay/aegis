"""
Quarterly batch risk computation (pilot scoring version ``quarterly_v1``).

For one completed quarter it computes, per active student, the guide's measured
inputs, the rule score and label, and, when an applicable, complete model is
available, the model category and Risk Index. Every result is stored as a
RiskScore; a RiskAlert follows the pilot notification policy (no prior alert,
category change, or a 10-point same-category index move).

    python manage.py run_risk_computation
    python manage.py run_risk_computation --dry-run
    python manage.py run_risk_computation --quarter-id <uuid>

The rule result is available without a model. A missing or unusable tree makes
only the model category and index unavailable; it does not suppress the rule
result.
"""

import logging

from django.core.management.base import BaseCommand

from ai_engine.quarterly_risk import (
    build_prediction,
    compute_quarter_inputs,
    held_result,
    load_model_for_quarter,
    model_version_for_quarter,
    predict,
    resolve_quarter,
    score_rule,
)
from ai_engine.risk_service import integrate_risk_result

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the quarterly pilot risk computation for active students."

    def add_arguments(self, parser):
        parser.add_argument(
            "--academic-year-id",
            type=str,
            default=None,
            help="Restrict to a specific academic year (id).",
        )
        parser.add_argument(
            "--quarter-id",
            type=str,
            default=None,
            help="Grading period UUID to process (defaults to latest completed).",
        )
        parser.add_argument(
            "--quarter",
            type=int,
            default=None,
            help="Quarter order (1-4) to process.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute but do not persist or notify.",
        )

    def handle(self, *args, **options):
        from datetime import date

        from apps.academics.models import AcademicYear
        from apps.accounts.models import StudentProfile

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

        quarter = resolve_quarter(
            academic_year,
            quarter_id=options.get("quarter_id"),
            order=options.get("quarter"),
        )
        if quarter is None:
            self.stderr.write(
                f"No completed quarter found for {academic_year.name}; "
                "cannot compute risk."
            )
            return
        if quarter.end_date > date.today():
            self.stderr.write(
                f"{quarter.name} has not ended yet; the guide processes "
                "completed quarters only."
            )
            return

        stored = load_model_for_quarter(quarter.order)
        if stored is None:
            self.stderr.write(
                f"No active model for Q{quarter.order}. The rule score and "
                "label will still be computed; the model category and Risk "
                f"Index stay unavailable. Train one with "
                f"`manage.py train_risk_model --quarter-id {quarter.id}`."
            )
            model = None
            metadata = {}
        else:
            model, metadata = stored

        students = StudentProfile.objects.filter(is_active=True)
        self.stdout.write(
            f"Computing Q{quarter.order} ({quarter.name}) of "
            f"{academic_year.name} for {students.count()} student(s)."
        )

        processed = 0
        alerts = 0
        held = 0
        dry_run = options.get("dry_run", False)

        for student in students:
            inputs = compute_quarter_inputs(student, quarter)

            if inputs.get("computation_status") != "ready":
                held += 1
                processed += 1
                if not dry_run:
                    held_prediction = held_result(
                        inputs,
                        "missing required record(s): "
                        + ", ".join(inputs.get("missing") or []),
                    )
                    integrate_risk_result(
                        student,
                        held_prediction,
                        model_version=held_prediction["model_version"],
                        feature_snapshot=inputs,
                        dispatch_notifications=False,
                    )
                continue

            rule = score_rule(inputs)
            if model is None:
                model_result = {
                    "model_status": "unavailable",
                    "reason": "no_model_for_quarter",
                    "model_version": model_version_for_quarter(quarter.order),
                }
            else:
                model_result = predict(model, metadata, inputs)

            prediction = build_prediction(inputs, rule, model_result)
            processed += 1

            if dry_run:
                self.stdout.write(
                    f"  (dry-run) {student.user.get_full_name()}: "
                    f"rule={rule['label']} S={rule['score']} "
                    f"model={model_result.get('category')} "
                    f"index={model_result.get('index')} "
                    f"source={prediction['category_source']}"
                )
                continue

            result = integrate_risk_result(
                student,
                prediction,
                model_version=prediction["model_version"],
                feature_snapshot=inputs,
                dispatch_notifications=True,
            )
            if result.state_changed:
                alerts += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done Q{quarter.order}: {processed} processed, {alerts} "
                f"actionable alerts, {held} held for missing required records."
            )
        )
