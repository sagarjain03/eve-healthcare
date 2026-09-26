from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler


class DomainError(Exception):
    """Base for business errors raised by services; mapped to the standard error shape."""

    status_code = 400
    code = "BAD_REQUEST"
    message = "Bad request."

    def __init__(
        self, message: str | None = None, details: dict | None = None, code: str | None = None
    ):
        self.message = message or self.message
        self.details = details or {}
        self.code = code or self.code  # optional per-raise code, e.g. "TEST_NOT_OFFERED"
        super().__init__(self.message)


class NotFound(DomainError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Not found."


class Conflict(DomainError):
    status_code = 409
    code = "CONFLICT"
    message = "Conflict."


class InvalidStateTransition(Conflict):
    code = "INVALID_STATE_TRANSITION"
    message = "Invalid state transition."


class EmailAlreadyExists(Conflict):
    code = "EMAIL_ALREADY_EXISTS"
    message = "A user with this email already exists."


class CentreAlreadyExists(Conflict):
    code = "CENTRE_ALREADY_EXISTS"
    message = "A centre with this name already exists in this city."


class TestCodeAlreadyExists(Conflict):
    code = "TEST_CODE_ALREADY_EXISTS"
    message = "A test with this code already exists."


class DuplicateBooking(Conflict):
    code = "DUPLICATE_BOOKING"
    message = "You already have an active booking for this test, centre and time."


class BusinessRuleViolation(DomainError):
    status_code = 400
    code = "BUSINESS_RULE_VIOLATION"
    message = "Business rule violated."


class InvalidSignature(DomainError):
    status_code = 401
    code = "INVALID_SIGNATURE"
    message = "Invalid signature."


def _error_body(code: str, message: str, details) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def custom_exception_handler(exc, context):
    """Convert domain and DRF exceptions into {"error": {code, message, details}}."""
    if isinstance(exc, DomainError):
        return Response(_error_body(exc.code, exc.message, exc.details), status=exc.status_code)

    # DRF converts these internally, but we read default_code from exc, so convert up front
    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf_exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, drf_exceptions.ValidationError):
        details = response.data if isinstance(response.data, dict) else {"non_field_errors": response.data}
        response.data = _error_body("VALIDATION_ERROR", "Invalid input.", details)
    else:
        code = getattr(exc, "default_code", "error").upper()
        response.data = _error_body(code, str(response.data.get("detail", exc)), {})
    return response
