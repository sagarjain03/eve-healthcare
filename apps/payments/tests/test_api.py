import pytest

from apps.bookings.tests.factories import BookingFactory
from apps.payments.models import Payment
from apps.payments.tests.factories import PaymentFactory

pytestmark = pytest.mark.django_db

PAYMENTS_URL = "/payments/"


def payment_url(reference: str) -> str:
    return f"{PAYMENTS_URL}{reference}/"


def assert_error_shape(response, code: str | None = None) -> dict:
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    if code:
        assert body["error"]["code"] == code
    return body["error"]


@pytest.fixture
def booking(user):
    return BookingFactory(user=user)


# --- Auth ---


@pytest.mark.parametrize("method", ["get", "post"])
def test_unauthenticated_requests_return_401(api_client, method):
    response = getattr(api_client, method)(PAYMENTS_URL)

    assert response.status_code == 401
    assert_error_shape(response, "NOT_AUTHENTICATED")


# --- Create ---


def test_successful_payment_returns_201_and_confirms_booking(auth_client, booking):
    response = auth_client.post(
        PAYMENTS_URL, {"booking_id": booking.id, "outcome": "SUCCESS"}, format="json"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["reference"].startswith("pay_")
    assert body["status"] == "SUCCESS"
    assert body["booking_status"] == "CONFIRMED"
    assert body["booking_id"] == booking.id


def test_client_sent_amount_and_status_are_ignored(auth_client, booking):
    response = auth_client.post(
        PAYMENTS_URL,
        {"booking_id": booking.id, "outcome": "FAILED", "amount": "1.00", "status": "SUCCESS"},
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["amount"] == str(booking.amount)
    assert response.json()["status"] == "FAILED"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"booking_id": 1, "outcome": "MAYBE"}, "outcome"),
        ({"outcome": "SUCCESS"}, "booking_id"),
        ({"booking_id": "abc", "outcome": "SUCCESS"}, "booking_id"),
    ],
)
def test_invalid_payload_returns_400(auth_client, payload, field):
    response = auth_client.post(PAYMENTS_URL, payload, format="json")

    assert response.status_code == 400
    error = assert_error_shape(response, "VALIDATION_ERROR")
    assert field in error["details"]


def test_paying_confirmed_booking_returns_409(auth_client, booking):
    auth_client.post(PAYMENTS_URL, {"booking_id": booking.id, "outcome": "SUCCESS"}, format="json")

    response = auth_client.post(
        PAYMENTS_URL, {"booking_id": booking.id, "outcome": "SUCCESS"}, format="json"
    )

    assert response.status_code == 409
    error = assert_error_shape(response, "BOOKING_NOT_PAYABLE")
    assert error["details"] == {"booking_status": "CONFIRMED"}


def test_paying_other_users_booking_returns_404(auth_client):
    other = BookingFactory()

    response = auth_client.post(
        PAYMENTS_URL, {"booking_id": other.id, "outcome": "SUCCESS"}, format="json"
    )

    assert response.status_code == 404
    assert_error_shape(response, "BOOKING_NOT_FOUND")


# --- Idempotency-Key ---


def test_idempotency_key_replay_returns_200_with_same_reference(auth_client, booking):
    payload = {"booking_id": booking.id, "outcome": "SUCCESS"}
    headers = {"Idempotency-Key": "order-123"}

    first = auth_client.post(PAYMENTS_URL, payload, format="json", headers=headers)
    replay = auth_client.post(PAYMENTS_URL, payload, format="json", headers=headers)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["reference"] == first.json()["reference"]
    assert Payment.objects.filter(booking=booking).count() == 1


def test_idempotency_key_too_long_returns_400(auth_client, booking):
    response = auth_client.post(
        PAYMENTS_URL,
        {"booking_id": booking.id, "outcome": "SUCCESS"},
        format="json",
        headers={"Idempotency-Key": "x" * 101},
    )

    assert response.status_code == 400
    error = assert_error_shape(response, "VALIDATION_ERROR")
    assert "Idempotency-Key" in error["details"]


# --- Read ---


def test_get_my_payment_returns_200(auth_client, booking):
    payment = PaymentFactory(booking=booking)

    response = auth_client.get(payment_url(payment.reference))

    assert response.status_code == 200
    assert response.json()["reference"] == payment.reference


def test_get_other_users_payment_returns_404(auth_client):
    other = PaymentFactory()

    response = auth_client.get(payment_url(other.reference))

    assert response.status_code == 404
    assert_error_shape(response, "PAYMENT_NOT_FOUND")


def test_get_unknown_reference_returns_404(auth_client):
    response = auth_client.get(payment_url("pay_" + "0" * 32))

    assert response.status_code == 404
    assert_error_shape(response, "PAYMENT_NOT_FOUND")


def test_list_returns_only_my_payments_and_filters_by_booking(auth_client, user, booking):
    mine = PaymentFactory(booking=booking)
    mine_other_booking = PaymentFactory(booking=BookingFactory(user=user))
    PaymentFactory()  # someone else's

    all_mine = auth_client.get(PAYMENTS_URL)
    filtered = auth_client.get(PAYMENTS_URL, {"booking": booking.id})

    assert {p["reference"] for p in all_mine.json()["results"]} == {
        mine.reference,
        mine_other_booking.reference,
    }
    assert [p["reference"] for p in filtered.json()["results"]] == [mine.reference]


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_update_and_delete_are_not_allowed(auth_client, booking, method):
    payment = PaymentFactory(booking=booking)

    response = getattr(auth_client, method)(payment_url(payment.reference))

    assert response.status_code == 405
    assert_error_shape(response, "METHOD_NOT_ALLOWED")


# --- Throttling ---


def test_payment_creation_is_throttled_after_20_per_minute(auth_client):
    payload = {"booking_id": 999999, "outcome": "SUCCESS"}  # cheap 404s still count
    for _ in range(20):
        assert auth_client.post(PAYMENTS_URL, payload, format="json").status_code == 404

    response = auth_client.post(PAYMENTS_URL, payload, format="json")

    assert response.status_code == 429
    assert_error_shape(response, "THROTTLED")
