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

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import RequestFactory, SimpleTestCase
from rest_framework import status

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