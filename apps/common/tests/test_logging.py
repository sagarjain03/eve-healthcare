import json
import logging
import sys

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.common.logging import JsonFormatter, RequestIdFilter, request_id_var
from apps.common.middleware import RequestIdMiddleware


def make_record(msg="Booking created", level=logging.INFO, exc_info=None, **extra):
    record = logging.LogRecord("apps.bookings.services", level, __file__, 1, msg, None, exc_info)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


# --- JsonFormatter ---


def test_json_formatter_outputs_one_json_object_with_extra_fields_and_request_id():
    token = request_id_var.set("req-123")
    try:
        line = JsonFormatter().format(make_record(booking_id=7, user_id=3))
    finally:
        request_id_var.reset(token)

    data = json.loads(line)
    assert data["message"] == "Booking created"
    assert data["level"] == "INFO"
    assert data["logger"] == "apps.bookings.services"
    assert data["request_id"] == "req-123"
    assert (data["booking_id"], data["user_id"]) == (7, 3)
    assert data["timestamp"].endswith("Z")
    assert "\n" not in line


def test_json_formatter_includes_exception_and_serializes_non_json_types():
    from decimal import Decimal

    try:
        raise ValueError("boom")
    except ValueError:
        record = make_record(level=logging.ERROR, exc_info=sys.exc_info(), amount=Decimal("1.50"))

    data = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in data["exc_info"]
    assert data["amount"] == "1.50"
    assert data["request_id"] is None  # outside a request


def test_request_id_filter_adds_placeholder_outside_requests():
    record = make_record()

    RequestIdFilter().filter(record)

    assert record.request_id == "-"


# --- RequestIdMiddleware ---


@pytest.fixture
def middleware_and_seen():
    seen = {}

    def view(request):
        seen["contextvar"] = request_id_var.get()
        seen["request"] = request.request_id
        return HttpResponse("ok")

    return RequestIdMiddleware(view), seen


def test_middleware_echoes_a_valid_incoming_request_id(middleware_and_seen):
    middleware, seen = middleware_and_seen

    response = middleware(RequestFactory().get("/", HTTP_X_REQUEST_ID="abc-123-XYZ"))

    assert response["X-Request-ID"] == "abc-123-XYZ"
    assert seen == {"contextvar": "abc-123-XYZ", "request": "abc-123-XYZ"}
    assert request_id_var.get() is None  # reset after the request


@pytest.mark.parametrize("bad", ["has spaces", "semi;colon", "x" * 65, "new\nline"])
def test_middleware_replaces_an_invalid_incoming_request_id(middleware_and_seen, bad):
    middleware, seen = middleware_and_seen

    response = middleware(RequestFactory().get("/", HTTP_X_REQUEST_ID=bad))

    assert response["X-Request-ID"] != bad
    assert len(response["X-Request-ID"]) == 32  # uuid4 hex
    assert seen["contextvar"] == response["X-Request-ID"]


def test_middleware_generates_a_request_id_when_missing(middleware_and_seen):
    middleware, _ = middleware_and_seen

    first = middleware(RequestFactory().get("/"))["X-Request-ID"]
    second = middleware(RequestFactory().get("/"))["X-Request-ID"]

    assert len(first) == 32
    assert first != second


@pytest.mark.django_db
def test_api_responses_carry_the_request_id_header(api_client):
    response = api_client.get("/health/", HTTP_X_REQUEST_ID="trace-42")

    assert response["X-Request-ID"] == "trace-42"
