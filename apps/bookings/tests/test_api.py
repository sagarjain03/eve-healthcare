from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.state_machine import transition
from apps.bookings.tests.factories import BookingFactory
from apps.centres.tests.factories import CentreTestFactory

pytestmark = pytest.mark.django_db

BOOKINGS_URL = "/bookings/"


def booking_url(booking_id) -> str:
    return f"{BOOKINGS_URL}{booking_id}/"


def cancel_url(booking_id) -> str:
    return f"{BOOKINGS_URL}{booking_id}/cancel/"


def future_iso(days: float = 2) -> str:
    return (timezone.now() + timedelta(days=days)).isoformat()


def assert_error_shape(response, code: str | None = None) -> dict:
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    if code:
        assert body["error"]["code"] == code
    return body["error"]


def result_ids(response) -> list[int]:
    return [item["id"] for item in response.json()["results"]]


@pytest.fixture
def offering():
    return CentreTestFactory(price="499.00")


# --- Auth ---


@pytest.mark.parametrize("method", ["get", "post"])
def test_unauthenticated_requests_return_401(api_client, method):
    response = getattr(api_client, method)(BOOKINGS_URL)

    assert response.status_code == 401
    assert_error_shape(response, "NOT_AUTHENTICATED")


# --- Create ---


def test_create_booking_uses_server_price_and_ignores_client_amount_and_status(
    auth_client, offering
):
    payload = {
        "centre_id": offering.centre_id,
        "test_id": offering.test_id,
        "appointment_at": future_iso(),
        "amount": "1.00",
        "status": "CONFIRMED",
    }

    response = auth_client.post(BOOKINGS_URL, payload, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == "499.00"
    assert body["status"] == "PENDING"
    assert body["centre"]["id"] == offering.centre_id
    assert body["test"]["code"] == offering.test.code


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"appointment_at": "not-a-date"}, "appointment_at"),
        ({"centre_id": "abc"}, "centre_id"),
        ({"test_id": "xyz"}, "test_id"),
        ({"centre_id": None}, "centre_id"),
    ],
)
def test_create_booking_with_invalid_fields_returns_400(auth_client, offering, overrides, field):
    payload = {
        "centre_id": offering.centre_id,
        "test_id": offering.test_id,
        "appointment_at": future_iso(),
        **overrides,
    }

    response = auth_client.post(BOOKINGS_URL, payload, format="json")

    assert response.status_code == 400
    error = assert_error_shape(response, "VALIDATION_ERROR")
    assert field in error["details"]


def test_create_booking_with_missing_fields_returns_400(auth_client):
    response = auth_client.post(BOOKINGS_URL, {}, format="json")

    assert response.status_code == 400
    error = assert_error_shape(response, "VALIDATION_ERROR")
    assert {"centre_id", "test_id", "appointment_at"} <= set(error["details"])


def test_create_booking_business_rule_error_has_standard_shape(auth_client, offering):
    payload = {
        "centre_id": offering.centre_id,
        "test_id": offering.test_id,
        "appointment_at": future_iso(-1),
    }

    response = auth_client.post(BOOKINGS_URL, payload, format="json")

    assert response.status_code == 400
    assert_error_shape(response, "APPOINTMENT_IN_PAST")


def test_create_duplicate_booking_returns_409(auth_client, offering):
    payload = {
        "centre_id": offering.centre_id,
        "test_id": offering.test_id,
        "appointment_at": future_iso(),
    }
    auth_client.post(BOOKINGS_URL, payload, format="json")

    response = auth_client.post(BOOKINGS_URL, payload, format="json")

    assert response.status_code == 409
    assert_error_shape(response, "DUPLICATE_BOOKING")


# --- Timezones ---


def test_naive_appointment_time_is_interpreted_as_utc(auth_client, offering):
    naive = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0, tzinfo=None)

    response = auth_client.post(
        BOOKINGS_URL,
        {
            "centre_id": offering.centre_id,
            "test_id": offering.test_id,
            "appointment_at": naive.isoformat(),  # no offset
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["appointment_at"] == naive.isoformat() + "Z"


def test_offset_appointment_time_is_stored_in_utc(auth_client, offering):
    ist = timezone.get_fixed_timezone(330)  # +05:30
    local = (datetime.now(ist) + timedelta(days=2)).replace(hour=9, minute=0, second=0,
                                                            microsecond=0)

    response = auth_client.post(
        BOOKINGS_URL,
        {
            "centre_id": offering.centre_id,
            "test_id": offering.test_id,
            "appointment_at": local.isoformat(),  # e.g. 2026-09-29T09:00:00+05:30
        },
        format="json",
    )

    assert response.status_code == 201
    expected_utc = local.astimezone(UTC).replace(tzinfo=None).isoformat() + "Z"
    assert response.json()["appointment_at"] == expected_utc  # 09:00 IST == 03:30Z
    booking = Booking.objects.get(pk=response.json()["id"])
    assert booking.appointment_at == local


# --- List / retrieve ---


def test_list_returns_only_my_bookings(auth_client, user):
    mine = BookingFactory(user=user)
    BookingFactory()  # someone else's

    response = auth_client.get(BOOKINGS_URL)

    assert response.status_code == 200
    assert result_ids(response) == [mine.id]


def test_list_filter_by_status(auth_client, user):
    pending = BookingFactory(user=user)
    BookingFactory(user=user, status=BookingStatus.CANCELLED)

    response = auth_client.get(BOOKINGS_URL, {"status": "PENDING"})

    assert result_ids(response) == [pending.id]


def test_list_filter_with_invalid_status_returns_400(auth_client):
    response = auth_client.get(BOOKINGS_URL, {"status": "WRONG"})

    assert response.status_code == 400
    error = assert_error_shape(response, "VALIDATION_ERROR")
    assert "status" in error["details"]


def test_get_other_users_booking_returns_404(auth_client):
    other = BookingFactory()

    response = auth_client.get(booking_url(other.id))

    assert response.status_code == 404
    assert_error_shape(response, "BOOKING_NOT_FOUND")


def test_get_nonexistent_booking_returns_404(auth_client):
    response = auth_client.get(booking_url(999999))

    assert response.status_code == 404
    assert_error_shape(response, "BOOKING_NOT_FOUND")


def test_get_my_booking_returns_200(auth_client, user):
    booking = BookingFactory(user=user)

    response = auth_client.get(booking_url(booking.id))

    assert response.status_code == 200
    assert response.json()["id"] == booking.id


# --- Cancel ---


def test_cancel_pending_booking_then_cancel_again_returns_409(auth_client, user):
    booking = BookingFactory(user=user)

    first = auth_client.post(cancel_url(booking.id))
    second = auth_client.post(cancel_url(booking.id))

    assert first.status_code == 200
    assert first.json()["status"] == "CANCELLED"
    assert second.status_code == 409
    error = assert_error_shape(second, "INVALID_STATE_TRANSITION")
    assert error["details"] == {"from": "CANCELLED", "to": "CANCELLED"}


def test_cancel_confirmed_booking_returns_200(auth_client, user):
    booking = BookingFactory(user=user)
    transition(booking, BookingStatus.CONFIRMED)

    response = auth_client.post(cancel_url(booking.id))

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_cancel_other_users_booking_returns_404(auth_client):
    other = BookingFactory()

    response = auth_client.post(cancel_url(other.id))

    assert response.status_code == 404
    assert_error_shape(response, "BOOKING_NOT_FOUND")
    other.refresh_from_db()
    assert other.status == BookingStatus.PENDING


def test_cancel_past_appointment_returns_400(auth_client, user):
    booking = BookingFactory(user=user, appointment_at=timezone.now() - timedelta(hours=1))

    response = auth_client.post(cancel_url(booking.id))

    assert response.status_code == 400
    assert_error_shape(response, "APPOINTMENT_ALREADY_PASSED")


# --- Not allowed methods ---


@pytest.mark.parametrize("method", ["patch", "put", "delete"])
def test_update_and_delete_are_not_allowed(auth_client, user, method):
    booking = BookingFactory(user=user)

    response = getattr(auth_client, method)(
        booking_url(booking.id), {"status": "CONFIRMED"}, format="json"
    )

    assert response.status_code == 405
    assert_error_shape(response, "METHOD_NOT_ALLOWED")


# --- Query count (no N+1) ---


def test_list_query_count_is_constant(auth_client, user):
    BookingFactory(user=user)
    with CaptureQueriesContext(connection) as one_booking:
        auth_client.get(BOOKINGS_URL)

    BookingFactory.create_batch(9, user=user)
    with CaptureQueriesContext(connection) as ten_bookings:
        response = auth_client.get(BOOKINGS_URL)

    assert response.json()["count"] == 10
    assert len(ten_bookings) == len(one_booking)
