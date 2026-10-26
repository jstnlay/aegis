"""
Guidance-records importer (PH11).

Consumes normalized rows (CSV or XLSX) and writes real ``ConsultationRecord``
records.  Before this importer existed, ``guidance_records`` was an accepted
import type whose rows were all ``SKIPPED``: an admin could upload a file and
be told nothing was stored.  FR-037 requires the guidance file to be parsed,
mapped, and stored in the Guidance DB.

Accepted columns::

    student_id         (required)  StudentProfile.student_id school code
    session_date       (required)  YYYY-MM-DD (not in the future)
    session_time       (required)  HH:MM (24-hour)
    session_type       (required)  individual_counseling | group |
                                   parent_conference | follow_up
    concern_categories (required)  |-separated: academic | behavioral |
                                   emotional | family | bullying | other
    session_notes      (required)  free text, non-empty
    priority_level     (required)  high | medium | low
    recommendations    (optional)  free text
    next_session_date  (optional)  YYYY-MM-DD (may be in the future)
    status             (optional)  ongoing | completed | follow_up
                                   (defaults to ongoing)

``counselor`` / ``recorded_by`` are FORBIDDEN: attribution is always
server-controlled, mirroring the attendance importer's rule for
``recorded_by``.  A client-supplied counselor would let an upload forge who
conducted a session.  Re-uploading a session for the same student, date and
time updates that record in place and keeps its existing counselor.

The ``session_date`` future-date rule mirrors ``BehavioralNote.clean()`` in
the same app rather than inventing a new one.
"""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..constants import ImportErrorCode, RecordStatus
from .base import (
    GUIDANCE_ALLOWED_COLUMNS,
    GUIDANCE_FORBIDDEN_COLUMNS,
    GUIDANCE_REQUIRED_COLUMNS,
    InFileDuplicateTracker,
    RowError,
    column_value,
    memo,
    recompute_job_counters,
    validate_headers,
)

#: Accepted ``session_time`` formats (24-hour clock).
_TIME_FORMATS = ("%H:%M", "%H:%M:%S")

#: Mirrors ``ConsultationRecord.SessionType``.
_VALID_SESSION_TYPES = frozenset(
    ("individual_counseling", "group", "parent_conference", "follow_up")
)

#: Mirrors ``ConsultationRecord.PriorityLevel``.
_VALID_PRIORITIES = frozenset(("high", "medium", "low"))

#: Mirrors ``ConsultationRecord.Status``.
_VALID_STATUSES = frozenset(("ongoing", "completed", "follow_up"))

#: Mirrors the valid set enforced by ``ConsultationRecord.clean()``.
_VALID_CONCERN_CATEGORIES = frozenset(
    ("academic", "behavioral", "emotional", "family", "bullying", "other")
)

#: Separators accepted between concern categories.
_CATEGORY_SEPARATORS = ("|", ";")


class GuidanceRecordsImporter:
    """Process guidance-records rows for a single ImportJob."""

    def __init__(self, job, records, user):
        self.job = job
        self.records = records
        self.user = user
        #: One lookup per distinct student (and attributed counselor), not per row.
        self.cache = {}

    def process(self, headers):
        """
        Validate headers, then each row, writing ConsultationRecord rows.

        Returns nothing; updates each ImportRecord and the job in place.
        """
        header_error = validate_headers(
            headers,
            required=GUIDANCE_REQUIRED_COLUMNS,
            allowed=GUIDANCE_ALLOWED_COLUMNS,
            forbidden=GUIDANCE_FORBIDDEN_COLUMNS,
        )
        if header_error is not None:
            self._fail_all(header_error)
            return

        tracker = InFileDuplicateTracker()

        for record in self.records:
            try:
                self._process_row(record, tracker)
            except RowError as exc:
                record.status = RecordStatus.ERROR
                record.error_message = exc.message
                record.mapped_to_model = ""
                record.mapped_to_id = None
            except Exception:
                # Any unexpected failure in a single row is isolated: mark it
                # ERROR with a safe message; never crash the whole job.
                record.status = RecordStatus.ERROR
                record.error_message = "The row could not be processed."
                record.mapped_to_model = ""
                record.mapped_to_id = None
            record.save()

        recompute_job_counters(self.job, self.records)

    # ------------------------------------------------------------------ #

    def _process_row(self, record, tracker):
        from apps.guidance.models import ConsultationRecord

        row = record.data

        student_id = column_value(row, "student_id")
        date_raw = column_value(row, "session_date")
        time_raw = column_value(row, "session_time")
        type_raw = column_value(row, "session_type").lower()
        concerns_raw = column_value(row, "concern_categories")
        notes_raw = column_value(row, "session_notes")
        priority_raw = column_value(row, "priority_level").lower()

        if not student_id:
            raise RowError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN, "student_id is required."
            )
        if not date_raw:
            raise RowError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN, "session_date is required."
            )
        if not time_raw:
            raise RowError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN, "session_time is required."
            )
        if not type_raw:
            raise RowError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN, "session_type is required."
            )
        if not concerns_raw:
            raise RowError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN,
                "concern_categories is required.",
            )
        if not notes_raw:
            raise RowError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN, "session_notes is required."
            )
        if not priority_raw:
            raise RowError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN, "priority_level is required."
            )

        student = memo(self.cache, ("student", student_id), lambda: self._resolve_student(student_id))
        session_date = self._resolve_date(date_raw, future_allowed=False)
        session_time = self._resolve_time(time_raw)
        self._resolve_choice(
            type_raw, _VALID_SESSION_TYPES, ImportErrorCode.INVALID_SESSION_TYPE,
            "session_type",
        )
        self._resolve_choice(
            priority_raw, _VALID_PRIORITIES, ImportErrorCode.INVALID_PRIORITY_LEVEL,
            "priority_level",
        )
        concerns = self._resolve_concerns(concerns_raw)

        status_raw = column_value(row, "status").lower()
        if status_raw:
            self._resolve_choice(
                status_raw, _VALID_STATUSES, ImportErrorCode.INVALID_SESSION_STATUS,
                "status",
            )
        else:
            status_raw = "ongoing"

        next_session_raw = column_value(row, "next_session_date")
        next_session_date = (
            self._resolve_date(next_session_raw, future_allowed=True)
            if next_session_raw
            else None
        )

        # --- in-file duplicate ------------------------------------------
        dup_key = (student_id, str(session_date), str(session_time))
        if tracker.is_dup(dup_key):
            raise RowError(
                ImportErrorCode.DUPLICATE_ROW,
                "This row duplicates another row in the same file "
                "(same student, date and time).",
            )
        tracker.mark(dup_key)

        # --- existing record: update in place ---------------------------
        # A re-upload of the same session applies the corrected content
        # (already validated above) instead of rejecting the row.  The
        # counselor stays as first attributed: re-attribution would demand a
        # risk alert or intervention that may no longer exist.
        record_obj = ConsultationRecord.objects.filter(
            student=student,
            session_date=session_date,
            session_time=session_time,
        ).first()

        counselor = (
            record_obj.counselor
            if record_obj is not None
            else memo(
                self.cache,
                ("counselor", student_id),
                lambda: self._resolve_counselor(student),
            )
        )

        recommendations = column_value(row, "recommendations") or None

        # --- primary operation: persist the record ----------------------
        with transaction.atomic():
            if record_obj is None:
                record_obj = ConsultationRecord(
                    student=student,
                    counselor=counselor,
                    session_date=session_date,
                    session_time=session_time,
                )
            record_obj.session_type = type_raw
            record_obj.concern_categories = concerns
            record_obj.session_notes = notes_raw
            record_obj.recommendations = recommendations
            record_obj.next_session_date = next_session_date
            record_obj.priority_level = priority_raw
            record_obj.status = status_raw
            try:
                record_obj.save()
            except ValidationError as exc:
                raise RowError(
                    ImportErrorCode.ROW_NOT_PROCESSED,
                    self._safe_validation_message(exc),
                )

        record.status = RecordStatus.SUCCESS
        record.mapped_to_model = "ConsultationRecord"
        record.mapped_to_id = record_obj.pk
        record.error_message = ""

    # ------------------------------------------------------------------ #

    @staticmethod
    def _safe_validation_message(exc):
        """Flatten a Django ValidationError into a short, internals-free line."""
        if hasattr(exc, "message_dict"):
            parts = []
            for field, messages in exc.message_dict.items():
                for message in messages:
                    parts.append(f"{field}: {message}")
            return "; ".join(parts)[:500]
        messages = getattr(exc, "messages", None) or ["The row is not valid."]
        return str(messages[0])[:500]

    def _resolve_counselor(self, student):
        """
        Server-controlled attribution for the session.

        The role matrix (FR-012 / FR-013 / FR-037) lets only an admin
        submit guidance records, so the uploader never has a guidance
        profile of their own to attribute to.  The student's assigned
        counselor is therefore taken from a record that already names
        them; if none exists the row is rejected rather than written with
        a fabricated counselor.
        """
        from apps.guidance.models import Intervention, RiskAlert

        alert = (
            RiskAlert.objects.filter(
                student=student, assigned_counselor__isnull=False
            )
            .order_by("-generated_at")
            .first()
        )
        if alert is not None:
            return alert.assigned_counselor

        intervention = (
            Intervention.objects.filter(student=student)
            .order_by("-plan_start_date")
            .first()
        )
        if intervention is not None:
            return intervention.assigned_counselor

        raise RowError(
            ImportErrorCode.NO_COUNSELOR,
            "No guidance counselor can be attributed to this record. Assign "
            "the student's counselor before importing.",
        )

    # ------------------------------------------------------------------ #

    @staticmethod
    def _resolve_student(student_id):
        from apps.accounts.models import StudentProfile

        try:
            return StudentProfile.objects.get(student_id=student_id)
        except StudentProfile.DoesNotExist:
            raise RowError(
                ImportErrorCode.INVALID_STUDENT,
                f"No student found with student_id {student_id!r}.",
            )
        except Exception:
            raise RowError(
                ImportErrorCode.INVALID_STUDENT, "Invalid student identifier."
            )

    def _resolve_date(self, raw, *, future_allowed):
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise RowError(
                ImportErrorCode.INVALID_SESSION_DATE,
                "Dates must use the YYYY-MM-DD format.",
            )
        if not future_allowed and parsed > timezone.localdate():
            raise RowError(
                ImportErrorCode.INVALID_SESSION_DATE,
                "session_date cannot be in the future.",
            )
        return parsed

    def _resolve_time(self, raw):
        for fmt in _TIME_FORMATS:
            try:
                return datetime.strptime(raw, fmt).time()
            except (ValueError, TypeError):
                continue
        raise RowError(
            ImportErrorCode.INVALID_SESSION_TIME,
            "session_time must use the 24-hour HH:MM format.",
        )

    @staticmethod
    def _resolve_choice(raw, valid, code, field_name):
        if raw not in valid:
            raise RowError(
                code,
                f"{field_name} must be one of: " + ", ".join(sorted(valid)) + ".",
            )
        return raw

    @staticmethod
    def _resolve_concerns(raw):
        parts = [raw]
        for sep in _CATEGORY_SEPARATORS:
            parts = [chunk for part in parts for chunk in part.split(sep)]
        cleaned = []
        for part in parts:
            value = part.strip().lower()
            if not value:
                continue
            if value not in _VALID_CONCERN_CATEGORIES:
                raise RowError(
                    ImportErrorCode.INVALID_CONCERN_CATEGORY,
                    f"Invalid concern category: {value!r}. Valid values: "
                    + ", ".join(sorted(_VALID_CONCERN_CATEGORIES))
                    + ".",
                )
            if value not in cleaned:
                cleaned.append(value)
        if not cleaned:
            raise RowError(
                ImportErrorCode.INVALID_CONCERN_LIST,
                "concern_categories must contain at least one valid category.",
            )
        return cleaned

    # ------------------------------------------------------------------ #

    def _fail_all(self, error):
        for record in self.records:
            record.status = RecordStatus.ERROR
            record.error_message = error.message
            record.mapped_to_model = ""
            record.mapped_to_id = None
            record.save()
        # TC-FAC-12/14: a header rejection fails the file before any row is
        # processed, so the per-row messages alone leave the history reading
        # "0 of 0 rows" with no reason.  Record the reason on the job itself.
        self.job.error_log = [{"code": error.code, "message": error.message}]
        recompute_job_counters(self.job, self.records)
