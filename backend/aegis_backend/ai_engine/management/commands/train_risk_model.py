"""
Train the Decision Tree risk model (PH9 D6/D7) and persist it.

    python manage.py train_risk_model
    python manage.py train_risk_model --dry-run
    python manage.py train_risk_model --academic-year-id <uuid>

What this produces
------------------
A fitted estimator at `ai_engine/saved_models/decision_tree_v1.pkl`, which is
what `run_risk_computation` loads. Until this command exists,
`run_risk_computation` exits with instructions naming it.

The labels are rule-generated
-----------------------------
`ai_engine.labeler.rule_based_label` scores a feature dict against a rubric
(grade average, weak subjects, trend, attendance, consultation and behavioral
counts) and emits low / moderate / high.

That means the tree learns the rubric, not history. It is a **baseline**, not a
model of real at-risk students, and its apparent accuracy is circular: the
Decision Tree is approximating a decision table that the labeler already
computed from the same features it will be scored on. Reported accuracy
against these labels overstates real performance and must not be quoted as
evidence that the model predicts student risk.

What would change that: `reviewed_label` already accepts a manual label and
takes precedence over the rule. Once counselors confirm which students were
genuinely at risk, those labels replace the rubric and the model becomes
meaningful. Until then the tree is reproducible and inspectable, which is what
makes it safe to ship at all.

Why the model is a file and not a database column
--------------------------------------------------
`risk_scorer.save_model`/`load_model` already write and read a pickle, and the
load path in `run_risk_computation` already expects one. Reusing it is the
smallest change that makes the existing command work.

The limitation is real and is not hidden: Render's free tier has no persistent
disk, so a model saved during a build or a manual run is lost on the next
deploy, and `run_risk_computation` will then correctly refuse to compute and
print this command's name again. Persisting the artifact in the database is
the fix, and it is deliberately not done here -- it needs a migration and a
decision on model lifecycle that has not been taken.
"""

import logging
from datetime import date

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Train the Decision Tree risk model from live student data and persist it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--academic-year-id",
            type=str,
            default=None,
            help="Train against a specific academic year (defaults to the current one).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Train and report, but do not write the model file.",
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
        from ai_engine.config import DT_MIN_SAMPLES_SPLIT
        from ai_engine.feature_engine import compute_student_features
        from ai_engine.labeler import reviewed_label
        from ai_engine.risk_scorer import save_stored_model, train

        from apps.academics.models import AcademicYear, GradingPeriod
        from apps.accounts.models import StudentProfile

        # --- resolve the academic year and completed periods -------------
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

        completed_periods = list(
            GradingPeriod.objects.filter(
                academic_year=academic_year,
                end_date__lte=date.today(),
            ).order_by("order")
        )

        if not completed_periods:
            self.stderr.write(
                "No completed grading periods for "
                f"{academic_year.name}; nothing to compute features from."
            )
            return

        self.stdout.write(
            f"Academic year {academic_year.name}, "
            f"{len(completed_periods)} completed period(s)."
        )

        # --- build the labelled dataset ----------------------------------
        students = StudentProfile.objects.filter(is_active=True)
        dataset = []
        insufficient = 0

        for student in students:
            features = compute_student_features(
                student, completed_periods, academic_year
            )

            if features.get("computation_status") == "insufficient_data":
                insufficient += 1
                continue

            label = reviewed_label(features, None)
            features["label"] = label
            dataset.append(features)

        self.stdout.write(
            f"{len(dataset)} student(s) with computable features "
            f"({insufficient} insufficient)."
        )

        if not dataset:
            self.stderr.write(
                "No student has enough data to train on. Import grades and "
                "attendance first."
            )
            return

        # --- label distribution, before training ------------------------
        # Reported because a model fitted on one class cannot produce a risk
        # distribution, and it would fail silently at prediction time instead.
        distribution: dict[str, int] = {}
        for entry in dataset:
            label = entry["label"]
            distribution[label] = distribution.get(label, 0) + 1

        self.stdout.write("\nRule-generated label distribution:")
        for label in sorted(distribution):
            self.stdout.write(f"  {label:12} {distribution[label]}")

        # --- train --------------------------------------------------------
        model, metadata = train(dataset)

        if model is None:
            self.stderr.write(
                f"Training refused: {metadata.get('error')}. "
                "Import more student records first."
            )
            return

        minimum = options.get("minimum_samples") or DT_MIN_SAMPLES_SPLIT
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

        self.stdout.write("\n  feature importances:")
        for column, importance in sorted(
            metadata["feature_importances_"].items(),
            key=lambda pair: pair[1],
            reverse=True,
        ):
            self.stdout.write(f"    {column:32} {importance}")

        # --- honest caveat ------------------------------------------------
        self.stderr.write(
            "\nNOTE: these labels are rule-generated (labeler.rule_based_label), "
            "so this model reproduces that rubric rather than learning real "
            "at-risk patterns. Do not quote its accuracy as evidence that it "
            "predicts student risk. See the module docstring."
        )

        if options.get("dry_run"):
            self.stdout.write("\nDry run: nothing written.")
            return

        # Record which cohort produced this model, so a later run can say when
        # the stored model predates the current year rather than scoring
        # silently against the wrong baseline.
        metadata = dict(metadata)
        metadata["academic_year_id"] = str(academic_year.id)
        metadata["academic_year_name"] = academic_year.name
        metadata["label_source"] = "rule_based"
        metadata["label_caveat"] = (
            "Labels come from labeler.rule_based_label, a rubric computed from "
            "the same features the model is scored on. Accuracy against these "
            "labels is circular and is not evidence that the model predicts "
            "real student risk."
        )

        artifact = save_stored_model(
            model, metadata, version="v1", academic_year=academic_year
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"\nStored RiskModelArtifact {artifact.pk} "
                f"(version v1, active, {artifact.n_samples} samples)"
            )
        )
        self.stdout.write(
            "The model now lives in the database, so it survives a redeploy. "
            "Run `manage.py run_risk_computation` to score active students."
        )