"""
Tests for the cross-cutting API exception handler.

Covers the one behaviour added to ``core.exceptions``: a
``django.core.exceptions.ValidationError`` raised on a mutating request is
reported as a 400 in the project's frozen error envelope, with its field
detail preserved - instead of escaping as an HTTP 500.

The scoping is asserted as deliberately: a ``ValidationError`` on a safe
method is *not* reclassified, so a server fault on a read is not disguised as
a client error.
"""

from unittest import mock

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.utils import OperationalError
from django.test import RequestFactory, SimpleTestCase, TestCase
from rest_framework import status
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError as DRFValidationError,
)
from rest_framework.test import APIClient

from core.exceptions import custom_exception_handler, drf_validation_error_from


class DjangoValidationErrorTranslationTests(SimpleTestCase):
    """The exception -> DRF exception conversion."""

    def test_field_keyed_error_dict_keeps_its_field_names(self):
        converted = drf_validation_error_from(
            DjangoValidationError({"target_review_date": "Too early."})
        )
        self.assertEqual(
            converted.detail,
            {"target_review_date": ["Too early."]},
        )

    def test_non_field_error_list_is_preserved(self):
        converted = drf_validation_error_from(
            DjangoValidationError(["Something is structurally wrong."])
        )
        self.assertEqual(converted.detail, ["Something is structurally wrong."])

    def test_multiple_messages_for_one_field_become_a_list(self):
        converted = drf_validation_error_from(
            DjangoValidationError({"options": ["First problem.", "Second problem."]})
        )
        self.assertEqual(
            converted.detail,
            {"options": ["First problem.", "Second problem."]},
        )


class CustomExceptionHandlerTests(SimpleTestCase):
    """The handler's request-method scoping and envelope output."""

    def setUp(self):
        self.factory = RequestFactory()

    def _context(self, method):
        return {"request": getattr(self.factory, method.lower())("/")}

    def test_validation_error_on_post_becomes_400_in_the_envelope(self):
        response = custom_exception_handler(
            DjangoValidationError({"options": "Needs at least 2 options."}),
            self._context("POST"),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(
            response.data["error"]["details"],
            {"options": ["Needs at least 2 options."]},
        )

    def test_each_unsafe_method_is_converted(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                response = custom_exception_handler(
                    DjangoValidationError({"order": "Already used."}),
                    self._context(method),
                )
                self.assertEqual(
                    response.status_code, status.HTTP_400_BAD_REQUEST
                )
                self.assertEqual(
                    response.data["error"]["details"],
                    {"order": ["Already used."]},
                )

    def test_validation_error_on_a_safe_method_is_not_reclassified(self):
        """A read-path invariant failure stays a server fault, not a 400."""
        response = custom_exception_handler(
            DjangoValidationError({"options": "Broken on read."}),
            self._context("GET"),
        )

        self.assertIsNone(response)

    def test_context_without_a_request_is_not_converted(self):
        response = custom_exception_handler(
            DjangoValidationError({"options": "No request in context."}),
            {},
        )

        self.assertIsNone(response)

    def test_unrelated_exceptions_are_untouched(self):
        """Only Django ValidationError is reclassified."""
        response = custom_exception_handler(
            RuntimeError("boom"), self._context("POST")
        )

        self.assertIsNone(response)


class ErrorMessageSummaryTests(SimpleTestCase):
    """``error.message`` must be a useful string for every response shape.

    ``error.details`` always keeps DRF's own structure. These tests pin only the
    summary, which is what a client renders when it has no field-level form to
    attach the detail to. Before this was fixed, every 400 rendered as
    "An error occurred." because the handler only ever looked for a string
    ``detail`` key.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def _message(self, exc, method="POST"):
        response = custom_exception_handler(
            exc, {"request": getattr(self.factory, method.lower())("/")}
        )
        self.assertIsNotNone(response, "handler returned no response")
        return response.data["error"]["message"]

    def test_message_is_always_a_plain_string(self):
        for exc in (
            DRFValidationError({"student": ["This field is required."]}),
            DRFValidationError("Assessment is already published."),
            DRFValidationError(["First problem."]),
            PermissionDenied(),
            NotFound("No Assessment matches the given query."),
        ):
            with self.subTest(exc=type(exc).__name__):
                message = self._message(exc)
                self.assertIsInstance(message, str)
                self.assertNotIsInstance(message, list)
                self.assertTrue(message.strip(), "message was blank")

    def test_serializer_field_errors_name_the_field_and_the_reason(self):
        message = self._message(
            DRFValidationError(
                {
                    "student": ["This field is required."],
                    "score": ["Must be between 0 and 100."],
                }
            )
        )

        self.assertIn("student", message)
        self.assertIn("This field is required.", message)
        self.assertIn("score", message)
        self.assertIn("Must be between 0 and 100.", message)

    def test_action_error_string_survives_drfs_list_wrapping(self):
        """DRF leaves a list ``exc.detail`` un-wrapped, so there is no
        ``detail`` key to read. The text must still reach the message."""
        message = self._message(DRFValidationError("Assessment is already published."))

        self.assertEqual(message, "Assessment is already published.")

    def test_zero_question_publish_error_is_reported_verbatim(self):
        message = self._message(
            DRFValidationError(
                {"detail": "Cannot publish assessment without questions."}
            )
        )

        self.assertEqual(message, "Cannot publish assessment without questions.")

    def test_non_field_errors_are_not_echoed_as_a_field_name(self):
        message = self._message(
            DRFValidationError({"non_field_errors": ["Ordering is inconsistent."]})
        )

        self.assertEqual(message, "Ordering is inconsistent.")
        self.assertNotIn("non_field_errors", message)

    def test_field_summary_is_bounded_but_details_stay_complete(self):
        detail = {f"field_{index}": ["is invalid"] for index in range(7)}
        response = custom_exception_handler(
            DRFValidationError(detail), {"request": self.factory.post("/")}
        )

        message = response.data["error"]["message"]
        self.assertIn("(+4 more)", message)
        # Bounding the summary must never truncate the machine-readable payload.
        self.assertEqual(
            set(response.data["error"]["details"]), set(detail)
        )

    def test_permission_denied_keeps_drfs_own_text(self):
        self.assertEqual(
            self._message(PermissionDenied()),
            "You do not have permission to perform this action.",
        )

    def test_status_fallback_when_the_body_has_no_usable_text(self):
        # An empty field map carries no usable text, so the message falls back
        # to the status-appropriate default rather than shipping "".
        response = custom_exception_handler(
            DRFValidationError({}), {"request": self.factory.post("/")}
        )
        self.assertEqual(
            response.data["error"]["message"],
            "The request could not be processed.",
        )

    def test_details_are_unchanged_by_the_message_fix(self):
        """The summary is derived independently; field attribution survives."""
        response = custom_exception_handler(
            DRFValidationError({"order": ["Already used."]}),
            {"request": self.factory.post("/")},
        )

        self.assertEqual(
            response.data["error"]["details"], {"order": ["Already used."]}
        )
        self.assertEqual(response.data["error"]["message"], "order: Already used.")

class HealthProbeTests(TestCase):
    """
    The probes a deployment calls without a token.

    They must answer anonymously, they must not leak anything about the
    deployment, and readiness must fail when the database does.
    """

    def setUp(self):
        self.client = APIClient()

    def test_liveness_answers_without_a_token(self):
        response = self.client.get("/api/v1/health/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readiness_reports_the_database(self):
        response = self.client.get("/api/v1/ready/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"status": "ok", "database": True})

    def test_readiness_fails_when_the_database_does_not_answer(self):
        broken = mock.MagicMock()
        broken.cursor.side_effect = OperationalError("no route to host")

        with mock.patch("core.health.connection", broken):
            response = self.client.get("/api/v1/ready/")

        self.assertEqual(
            response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE
        )
        self.assertEqual(
            response.json(), {"status": "unavailable", "database": False}
        )

    def test_probe_failure_does_not_leak_the_database_error(self):
        broken = mock.MagicMock()
        broken.cursor.side_effect = OperationalError("password=hunter2 host=db.internal")

        with mock.patch("core.health.connection", broken):
            response = self.client.get("/api/v1/ready/")

        body = response.content.decode()
        self.assertNotIn("hunter2", body)
        self.assertNotIn("db.internal", body)
