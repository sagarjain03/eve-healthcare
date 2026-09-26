from rest_framework import exceptions as drf_exceptions

from apps.common.exceptions import InvalidStateTransition, NotFound, custom_exception_handler


def test_domain_not_found_returns_404_with_standard_shape():
    response = custom_exception_handler(NotFound("x"), {})

    assert response.status_code == 404
    assert response.data == {"error": {"code": "NOT_FOUND", "message": "x", "details": {}}}


def test_invalid_state_transition_returns_409():
    response = custom_exception_handler(InvalidStateTransition(), {})

    assert response.status_code == 409
    assert response.data["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_drf_validation_error_puts_field_errors_in_details():
    exc = drf_exceptions.ValidationError({"email": ["bad"]})

    response = custom_exception_handler(exc, {})

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert response.data["error"]["message"] == "Invalid input."
    assert "email" in response.data["error"]["details"]


def test_drf_not_authenticated_returns_401_with_code():
    response = custom_exception_handler(drf_exceptions.NotAuthenticated(), {})

    assert response.status_code == 401
    assert response.data["error"]["code"] == "NOT_AUTHENTICATED"
    assert set(response.data["error"]) == {"code", "message", "details"}


def test_unknown_exception_returns_none():
    assert custom_exception_handler(ValueError("boom"), {}) is None
