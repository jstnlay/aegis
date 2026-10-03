"""
Cross-cutting exception handling for the DRF API.

Every API failure leaves through ``custom_exception_handler`` and is rendered
with the project's one frozen error envelope::

    {"success": False, "error": {"code", "message", "details"}}

``django.core.exceptions.ValidationError`` is *not* a DRF ``APIException``, so
DRF's own ``exception_handler`` ignores it. Models in this project validate
inside ``save()`` via ``full_clean()``, so an invariant failure on a mutating
request is the caller's bad input - but it escaped as HTTP 500 instead of a 400.

The conversion below is deliberately narrow:

* it matches exactly one exception type, so no unrelated failure is
  reclassified;
* it is limited to unsafe HTTP methods, so a ``ValidationError`` escaping on a
  read keeps reporting as a server fault rather than being disguised as a
  client error;
* it converts into a DRF ``ValidationError`` rather than building a response
  by hand, so the existing envelope, status-code mapping and field detail in
  ``error.details`` are unchanged.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.views import exception_handler

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def drf_validation_error_from(exc):
    """Translate a Django ``ValidationError`` into a DRF ``ValidationError``.

    ``exc.message_dict`` is ``{field: [message, ...]}`` and is ``None`` unless
    the error was raised with a field-keyed dict. It maps directly onto the
    shape DRF's own validators produce, so field detail survives into
    ``error.details``; a non-field error keeps its flat message list.

    ``exc.messages`` is deliberately not used for the field-keyed case: it
    flattens every field into one list and would discard the attribution.
    """
    message_dict = getattr(exc, "message_dict", None)
    if message_dict is not None:
        detail = {field: list(messages) for field, messages in message_dict.items()}
    else:
        detail = list(exc.messages)
    return DRFValidationError(detail)


def _is_mutating_request(context):
    """True when the request that raised is an unsafe (write) method."""
    request = context.get("request")
    method = getattr(request, "method", None)
    return bool(method) and method.upper() not in SAFE_METHODS


def custom_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError) and _is_mutating_request(context):
        exc = drf_validation_error_from(exc)

    response = exception_handler(exc, context)

    if response is not None:
        error_data = {
            "success": False,
            "error": {
                "code": _get_error_code(response.status_code),
                "message": _get_error_message(response),
                "details": response.data if isinstance(response.data, dict) else {"detail": response.data},
            },
        }
        response.data = error_data

    return response


def _get_error_code(status_code):
    codes = {
        400: "VALIDATION_ERROR",
        401: "AUTHENTICATION_REQUIRED",
        403: "PERMISSION_DENIED",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "FILE_TOO_LARGE",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_SERVER_ERROR",
    }
    return codes.get(status_code, "ERROR")


def _get_error_message(response):
    if isinstance(response.data, dict):
        return response.data.get("detail", "An error occurred.")
    return "An error occurred."
