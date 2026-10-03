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

``error.message`` is a human-readable *summary* and is always a non-empty
``str``; ``error.details`` is the machine-readable payload and keeps whatever
shape DRF produced, so a client's field-error map is untouched. The two are
derived independently because ``response.data`` takes four different shapes
depending on how the failure was raised - see ``_message_from_detail``.
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


#: How many field errors are named in a synthesized summary message before the
#: remainder is counted. The full set is always in ``error.details``; this only
#: bounds the one-line summary so a 20-field payload cannot produce a paragraph.
MAX_SUMMARIZED_FIELDS = 3

#: Keys DRF uses for errors that are not attributed to a serializer field.
NON_FIELD_KEYS = ("detail", "non_field_errors")

#: Field names that mean nothing to a human reader. DRF emits them when a
#: nested serializer or a non-form payload fails, and echoing them back would
#: replace a real message with a meaningless label.
_OPAQUE_FIELD_NAMES = frozenset(
    {"non_field_errors", "__all__", "detail", "object", "root"}
)


def _stringify(value):
    """Coerce a DRF detail node to a plain ``str``.

    ``ErrorDetail`` subclasses ``str`` so it serializes correctly, but the
    envelope contract declares ``message`` as a string, so it is normalized to
    one explicitly rather than relying on JSON coercion.
    """
    if isinstance(value, str):
        return str(value)
    return ""


def _join_messages(messages):
    """Join the string entries of a DRF detail list, dropping empties."""
    parts = [text for text in (_stringify(item) for item in messages) if text]
    return " ".join(parts)


def _summarize_field_errors(data):
    """Build a summary from a serializer's field-keyed error mapping.

    Returns ``None`` when the mapping holds nothing nameable, so the caller can
    fall back rather than emitting a vague message.
    """
    named = []
    opaque_texts = []
    overflow = 0

    for field, errors in data.items():
        name = str(field)
        if isinstance(errors, (list, tuple)):
            text = _join_messages(errors)
        else:
            text = _stringify(errors)
        if not text:
            continue
        if name in _OPAQUE_FIELD_NAMES:
            opaque_texts.append(text)
        elif len(named) < MAX_SUMMARIZED_FIELDS:
            named.append(f"{name}: {text}")
        else:
            overflow += 1

    if not named and not opaque_texts:
        return None

    fragments = named + opaque_texts
    if overflow:
        fragments.append(f"(+{overflow} more)")
    return "; ".join(fragments)


def _message_from_detail(detail):
    """Best-effort human message from any shape ``response.data`` can take.

    DRF produces four distinct shapes, and all four reach this handler:

    * a bare string / ``ErrorDetail`` - ``PermissionDenied``, ``NotFound``;
    * a list of messages - ``ValidationError("...")``, because DRF keeps a
      list ``exc.detail`` un-wrapped rather than nesting it under ``detail``;
    * a dict with a string or list ``detail`` - ``ValidationError({...})``;
    * a field-keyed mapping - every serializer ``is_valid`` failure.
    """
    if isinstance(detail, str):
        return _stringify(detail)
    if isinstance(detail, (list, tuple)):
        return _join_messages(detail)
    if isinstance(detail, dict):
        for key in NON_FIELD_KEYS:
            if key in detail:
                nested = _message_from_detail(detail[key])
                if nested:
                    return nested
        return _summarize_field_errors(detail) or ""
    return ""


#: Used only when the response body carries no usable text at all, so the
#: envelope can never ship an empty ``message`` string.
_FALLBACK_MESSAGES = {
    400: "The request could not be processed.",
    401: "Authentication is required.",
    403: "You do not have permission to perform this action.",
    404: "The requested resource was not found.",
    405: "That method is not allowed for this resource.",
    409: "The request conflicts with the current state.",
    413: "The uploaded file is too large.",
    429: "Too many requests. Please try again later.",
    500: "An unexpected server error occurred.",
}


def _get_error_message(response):
    """Always returns a non-empty, human-readable ``str``.

    The message is a *summary*; ``error.details`` keeps the machine-readable
    field mapping, and its shape is unchanged by this function.
    """
    message = _message_from_detail(response.data)
    return message or _FALLBACK_MESSAGES.get(
        response.status_code, "An error occurred."
    )
