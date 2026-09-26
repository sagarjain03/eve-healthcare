"""Every non-2xx response must use {"error": {"code", "message", "details"}}."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.db import DatabaseError
from rest_framework_simplejwt.tokens import AccessToken

from apps.bookings import views as booking_views
from apps.common import exceptions
from apps.common import views as common_views

pytestmark = pytest.mark.django_db

CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")
APPS_DIR = Path(__file__).resolve().parent.parent / "apps"


def assert_error_shape(response, status: int, code: str) -> dict:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    return body["error"]


# --- Django-level handlers (DEBUG=False) ---


@pytest.mark.parametrize("url", ["/nope/", "/bookings/abc/", "/payments/pay_not-a-ref/"])
def test_unmatched_url_returns_json_404(api_client, settings, url):
    settings.DEBUG = False

    response = api_client.get(url)

    assert_error_shape(response, 404, "NOT_FOUND")


def test_unexpected_exception_returns_json_500_without_traceback(
    auth_client, settings, monkeypatch
):
    settings.DEBUG = False

    def boom(**kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(booking_views, "create_booking", boom)
    auth_client.raise_request_exception = False  # let Django's handler500 answer

    response = auth_client.post(
        "/bookings/",
        {"centre_id": 1, "test_id": 1, "appointment_at": "2030-01-01T09:00:00Z"},
        format="json",
    )

    error = assert_error_shape(response, 500, "INTERNAL_ERROR")
    assert error["message"] == "An unexpected error occurred."
    assert "secret internal detail" not in response.content.decode()
    assert "Traceback" not in response.content.decode()


def test_health_returns_503_with_standard_shape_when_db_is_down(api_client, monkeypatch):
    def broken_cursor():
        raise DatabaseError("connection refused")

    monkeypatch.setattr(common_views.connection, "cursor", broken_cursor)

    response = api_client.get("/health/")

    assert_error_shape(response, 503, "DATABASE_UNAVAILABLE")


# --- DRF-level errors ---


def test_method_not_allowed_returns_405(auth_client):
    response = auth_client.delete("/bookings/")

    assert_error_shape(response, 405, "METHOD_NOT_ALLOWED")


def test_unsupported_media_type_returns_415(auth_client):
    response = auth_client.post("/bookings/", data="centre_id=1", content_type="text/plain")

    assert_error_shape(response, 415, "UNSUPPORTED_MEDIA_TYPE")


def test_malformed_json_returns_400_parse_error(auth_client):
    response = auth_client.post("/bookings/", data="{not json", content_type="application/json")

    assert_error_shape(response, 400, "PARSE_ERROR")


def test_throttled_response_includes_retry_info(api_client, user):
    payload = {"email": user.email, "password": "wrong-password"}
    for _ in range(10):
        api_client.post("/auth/login/", payload, format="json")

    response = api_client.post("/auth/login/", payload, format="json")

    error = assert_error_shape(response, 429, "THROTTLED")
    assert "available in" in error["message"]
    assert error["details"]["wait"] > 0


def test_out_of_range_page_returns_404(api_client):
    response = api_client.get("/centres/", {"page": 999})

    assert_error_shape(response, 404, "NOT_FOUND")


def test_expired_access_token_returns_401(api_client, user):
    token = AccessToken.for_user(user)
    token.set_exp(from_time=datetime.now(UTC) - timedelta(hours=2), lifetime=timedelta(minutes=1))
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = api_client.get("/auth/me/")

    assert_error_shape(response, 401, "TOKEN_NOT_VALID")


# --- Code format ---


def _all_subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _all_subclasses(sub)


def test_every_domain_error_class_code_is_upper_snake_case():
    classes = [exceptions.DomainError, *_all_subclasses(exceptions.DomainError)]

    bad = {cls.__name__: cls.code for cls in classes if not CODE_PATTERN.match(cls.code)}

    assert len(classes) > 5
    assert bad == {}


def test_every_code_passed_in_app_code_is_upper_snake_case():
    """Codes given per raise via code="..." (not only class attributes)."""
    sources = [p for p in APPS_DIR.rglob("*.py") if "tests" not in p.parts]
    codes = {
        match
        for path in sources
        for match in re.findall(r'code\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"))
    }

    assert codes  # sanity: the scan found something
    assert {c for c in codes if not CODE_PATTERN.match(c)} == set()
