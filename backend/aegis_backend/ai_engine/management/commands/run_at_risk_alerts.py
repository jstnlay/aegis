"""Run the binary at-risk Decision Tree and create actionable alerts."""

from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from ai_engine.at_risk import (
    MODEL_VERSION,
    has_active_at_risk_alert,
    load_stored_model,
    predict,
)


class Command(BaseCommand):
    help = "Score active students with the binary at-risk model and alert Guidance."

    def add_arguments(self, parser):
        parser.add_argument("--academic-year-id", default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from apps.academics.models import AcademicYear, GradingPeriod
        from apps.accounts.models import StudentProfile, User
        from apps.guidance.models import RiskAlert, RiskScore
        from apps.notifications.events import dispatch_event
        from apps.notifications.models import NotificationType
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
            self.stderr.write("No current academic year found; cannot score.")
            return

        periods = list(
            GradingPeriod.objects.filter(
                academic_year=year, end_date__lte=date.today()
            ).order_by("order")
        )
        if not periods:
            self.stderr.write("No completed grading periods; cannot score.")
            return

        stored = load_stored_model()
        if stored is None:
            self.stderr.write(
                "No active at-risk model. Run `manage.py train_at_risk_model` first."
            )
            return
        model, _metadata = stored

        guidance = list(User.objects.filter(role="guidance", is_active=True))
        processed = 0
        alerts = 0
        skipped = 0
        dry_run = options.get("dry_run", False)

        for student in StudentProfile.objects.filter(is_active=True):
            features = compute_student_features(student, periods, year)
            if features.get("computation_status") == "insufficient_data":
                continue
            prediction = predict(model, features)
            processed += 1

            if dry_run:
                self.stdout.write(
                    f"  (dry-run) {student.user.get_full_name()}: "
                    f"at_risk={prediction['at_risk']} "
                    f"probability={prediction['probability']}"
                )
                continue

            score = RiskScore.objects.create(
                student=student,
                computation_status="ready",
                risk_score=prediction["risk_score"],
                risk_level=prediction["risk_level"],
                model_version=MODEL_VERSION,
                feature_snapshot=features,
                explanation=prediction["explanation"],
                computed_at=timezone.now(),
            )

            if not prediction["at_risk"]:
                continue

            if has_active_at_risk_alert(student):
                skipped += 1
                continue

            factors = list(prediction["explanation"]["contributing_factors"])
            factors.append(
                {
                    "model": MODEL_VERSION,
                    "feature": "at_risk_model",
                    "value": prediction["probability"],
                    "direction": "at_or_above",
                }
            )
            alert = RiskAlert.objects.create(
                student=student,
                risk_level=RiskAlert.RiskLevel.HIGH,
                risk_factors=factors,
                source=RiskAlert.Source.DECISION_TREE,
                status=RiskAlert.Status.ACTIVE,
                risk_score_ref=score,
                generated_at=timezone.now(),
            )
            alerts += 1
            if guidance:
                dispatch_event(
                    NotificationType.RISK_ALERT_GENERATED,
                    recipients=guidance,
                    sender=None,
                    title=f"At-risk alert: {student.user.get_full_name()}",
                    message=(
                        "The at-risk Decision Tree flagged this student. "
                        "Open Risk Alerts to review the contributing factors."
                    ),
                    link="/app/risk-alerts",
                    deduplication_key=f"at_risk:{alert.id}",
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {processed} processed, {alerts} new alerts, "
                f"{skipped} already covered by an active alert."
            )
        )
