"""
Train the quarterly pilot Decision Tree and persist it.

    python manage.py train_risk_model
    python manage.py train_risk_model --dry-run
    python manage.py train_risk_model --academic-year-id <uuid>
    python manage.py train_risk_model --quarter-id <uuid>

The training target is the rule label from
``ai_engine.quarterly_risk.score_rule``: 0 points = low, 1-4 = moderate,
5 or more = high. The tree learns that rubric, not counselor-confirmed
outcomes, so accuracy against these labels is circular. The command says so
before it writes anything.

Model inputs and order come from the guide: general average, weak subjects,
grade trend, absences, consultations, adviser concerns, lowest subject grade
and late rate. Q1 has no grade trend and is stored as a separate seven-input
artifact.

The artifact carries the feature order, class labels, applicable quarter,
scoring version and model version, so a later quarter cannot load a tree that
does not belong to it.
"""

import logging
from datetime import date

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Train the quarterly pilot Decision Tree from live student data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--academic-year-id",
            type=str,
            default=None,
            help="Train against a specific academic year (defaults to the current one).",
        )
        parser.add_argument(
            "--quarter-id",
            type=str,
            default=None,
            help="Grading period UUID to train for (defaults to latest completed).",
        )
        parser.add_argument(
            "--quarter",
            type=int,
            default=None,
            help="Quarter order (1-4) to train for.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Train and report, but do not write the model artifact.",
        )
        parser.add_argument(
            "--minimum-samples",
            type=int,
            default=None,
            help=(
                "Refuse to train below this many labelled samples. "
                "Defaults to the model's own min_samples_split."
            ),
        )

    def handle(self, *args, **options):
        from ai_engine.quarterly_risk import (
            MIN_SAMPLES,
            compute_quarter_inputs,
            model_version_for_quarter,
            resolve_quarter,
            score_rule,
            train,
        )
        from ai_engine.risk_scorer import save_stored_model

        from apps.academics.models import AcademicYear
        from apps.accounts.models import StudentProfile

        # --- resolve the academic year and quarter ------------------------
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
            self.stderr.write("No current academic year found; cannot train.")
            return

        quarter = resolve_quarter(
            academic_year,
            quarter_id=options.get("quarter_id"),
            order=options.get("quarter"),
        )
        if quarter is None:
            self.stderr.write(
                f"No completed quarter found for {academic_year.name}; "
                "nothing to train on."
            )
            return
        if quarter.end_date > date.today():
            self.stderr.write(
                f"{quarter.name} has not ended yet; the guide processes "
                "completed quarters only."
            )
            return

        self.stdout.write(
            f"Academic year {academic_year.name}, quarter {quarter.name} "
            f"(order {quarter.order})."
        )

        # --- build the labelled dataset ----------------------------------
        students = StudentProfile.objects.filter(is_active=True)
        dataset = []
        insufficient = 0

        for student in students:
            inputs = compute_quarter_inputs(student, quarter)
            if inputs.get("computation_status") != "ready":
                insufficient += 1
                continue
            rule = score_rule(inputs)
            row = dict(inputs)
            row["label"] = rule["label"]
            dataset.append(row)

        self.stdout.write(
            f"{len(dataset)} student(s) with a computable rule score "
            f"({insufficient} held for missing required records)."
        )

        if not dataset:
            self.stderr.write(
                "No student has enough data to train on. Import grades and "
                "attendance first, or correct the missing records."
            )
            return

        # --- label distribution, before training -------------------------
        distribution: dict[str, int] = {}
        for entry in dataset:
            label = entry["label"]
            distribution[label] = distribution.get(label, 0) + 1

        self.stdout.write("\nRule-generated label distribution:")
        for label in sorted(distribution):
            self.stdout.write(f"  {label:12} {distribution[label]}")

        # --- train --------------------------------------------------------
        model, metadata = train(dataset, quarter=quarter.order)

        if model is None:
            self.stderr.write(
                f"Training refused: {metadata.get('error')}. "
                "Import more student records first."
            )
            return

        minimum = options.get("minimum_samples") or MIN_SAMPLES
        if len(dataset) < minimum:
            self.stderr.write(
                f"Refusing to persist: {len(dataset)} labelled samples is below "
                f"the minimum of {minimum}. A model fitted on this little data "
                "would not generalise."
            )
            return

        self.stdout.write("\nTrained model:")
        self.stdout.write(f"  samples        {metadata['n_samples']}")
        self.stdout.write(f"  features       {metadata['n_features']}")
        self.stdout.write(f"  classes        {', '.join(metadata['classes'])}")
        self.stdout.write(f"  quarter        {quarter.name} (Q{quarter.order})")

        self.stdout.write("\n  feature importances:")
        for column, importance in sorted(
            metadata["feature_importances_"].items(),
            key=lambda pair: pair[1],
            reverse=True,
        ):
            self.stdout.write(f"    {column:24} {importance}")

        comparison = metadata.get("comparison") or {}
        self.stdout.write("\n  pilot comparison (rule-label agreement):")
        self.stdout.write(
            f"    direct score     {comparison.get('direct_scoring_rule_agreement')}"
        )
        self.stdout.write(
            f"    six-input tree   {comparison.get('six_input_accuracy')}"
        )
        self.stdout.write(
            f"    full tree        {comparison.get('eight_input_accuracy')}"
        )
        self.stdout.write(
            "    independent staff ratings: "
            f"{comparison.get('independent_staff_ratings')}"
        )

        # --- honest caveat ------------------------------------------------
        self.stderr.write(
            "\nNOTE: these labels are rule-generated "
            "(ai_engine.quarterly_risk.score_rule), so this model reproduces "
            "that rubric rather than learning real at-risk patterns. Do not "
            "quote its accuracy as evidence that it predicts student risk. "
            "The pilot comparison must include independent staff ratings."
        )

        if options.get("dry_run"):
            self.stdout.write("\nDry run: nothing written.")
            return

        # Record which cohort produced this model so a later quarter cannot
        # silently score against a tree trained somewhere else.
        metadata = dict(metadata)
        metadata["academic_year_id"] = str(academic_year.id)
        metadata["academic_year_name"] = academic_year.name
        metadata["quarter_name"] = quarter.name

        version = model_version_for_quarter(quarter.order)
        artifact = save_stored_model(
            model, metadata, version=version, academic_year=academic_year
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"\nStored RiskModelArtifact {artifact.pk} "
                f"(version {version}, active, {artifact.n_samples} samples)"
            )
        )
        self.stdout.write(
            "The model now lives in the database, so it survives a redeploy. "
            "Run `manage.py run_risk_computation` to score active students."
        )
