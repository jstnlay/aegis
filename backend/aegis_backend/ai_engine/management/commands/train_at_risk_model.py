"""Train the four-feature binary at-risk Decision Tree."""

from datetime import date

from django.core.management.base import BaseCommand

from ai_engine.at_risk import (
    FEATURE_COLUMNS,
    MIN_SAMPLES,
    rule_label,
    save_stored_model,
    train,
)


class Command(BaseCommand):
    help = "Train the binary at-risk Decision Tree from live student features."

    def add_arguments(self, parser):
        parser.add_argument("--academic-year-id", default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from apps.academics.models import AcademicYear, GradingPeriod
        from apps.accounts.models import StudentProfile
        from ai_engine.feature_engine import compute_student_features

        if options.get("academic_year_id"):
            year = AcademicYear.objects.get(id=options["academic_year_id"])
        else:
            year = (
                AcademicYear.objects.filter(is_current=True)
                .order_by("-start_date")
                .first()
            )
        if year is None:
            self.stderr.write("No current academic year found; cannot train.")
            return

        periods = list(
            GradingPeriod.objects.filter(
                academic_year=year, end_date__lte=date.today()
            ).order_by("order")
        )
        if not periods:
            self.stderr.write("No completed grading periods; cannot train.")
            return

        dataset = []
        insufficient = 0
        for student in StudentProfile.objects.filter(is_active=True):
            features = compute_student_features(student, periods, year)
            if features.get("computation_status") == "insufficient_data":
                insufficient += 1
                continue
            features["at_risk_label"] = rule_label(features)
            dataset.append(features)

        self.stdout.write(
            f"{len(dataset)} student(s) with features, {insufficient} insufficient."
        )
        if len(dataset) < MIN_SAMPLES:
            self.stderr.write(
                f"Refusing to train: {len(dataset)} samples is below {MIN_SAMPLES}."
            )
            return

        model, metadata = train(dataset)
        if model is None:
            self.stderr.write(f"Training refused: {metadata.get('error')}.")
            return

        positives = sum(int(item["at_risk_label"]) for item in dataset)
        self.stdout.write(
            f"Trained on {metadata['n_samples']} samples "
            f"({positives} at risk, {metadata['n_samples'] - positives} not)."
        )
        self.stdout.write("Feature columns: " + ", ".join(FEATURE_COLUMNS))

        if options.get("dry_run"):
            self.stdout.write("Dry run: nothing written.")
            return

        metadata["academic_year_id"] = str(year.id)
        metadata["academic_year_name"] = year.name
        artifact = save_stored_model(model, metadata, academic_year=year)
        self.stdout.write(
            self.style.SUCCESS(
                f"Stored RiskModelArtifact {artifact.pk} "
                f"({artifact.version}, {artifact.n_samples} samples)."
            )
        )
