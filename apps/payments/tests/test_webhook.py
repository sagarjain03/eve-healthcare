import json
import threading
import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.urls import resolve

from apps.bookings.models import BookingStatus
from apps.bookings.state_machine import transition
from apps.payments import webhook
from apps.payments.models import PaymentStatus, WebhookEvent, WebhookEventStatus
from apps.payments.tests.factories import PaymentFactory
from apps.payments.views import WebhookView
from apps.payments.webhook import compute_signature, process_webhook_event

WEBHOOK_URL = "/payments/webhook/"
TEST_SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def webhook_secret(settings):
    settings.WEBHOOK_SECRET = TEST_SECRET


@pytest.fixture
def payment(db):
    """A PENDING payment (e.g. created with outcome=PENDING), booking PENDING."""
    return PaymentFactory()


def event_for(payment, status="SUCCESS", event_id=None, amount=None) -> dict:
    return {
        "event_id": event_id or f"evt_{uuid.uuid4().hex}",
        "payment_reference": payment.reference,
        "status": status,
        "amount": str(amount if amount is not None else payment.amount),
    }


def post_webhook(client, payload, signature: str | None = "valid", **extra):
    body = json.dumps(payload).encode()
    headers = dict(extra)
    if signature == "valid":
        headers["HTTP_X_WEBHOOK_SIGNATURE"] = compute_signature(body)
    elif signature is not None:
        headers["HTTP_X_WEBHOOK_SIGNATURE"] = signature
    return client.post(WEBHOOK_URL, data=body, content_type="application/json", **headers)


def assert_error_shape(response, code: str | None = None) -> dict:
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    if code:
        assert body["error"]["code"] == code
    return body["error"]


def reload(obj):
    obj.refresh_from_db()
    return obj


# --- Signature ---


def test_missing_signature_returns_401(api_client, payment):
    response = post_webhook(api_client, event_for(payment), signature=None)

    assert response.status_code == 401
    assert_error_shape(response, "INVALID_SIGNATURE")
    assert not WebhookEvent.objects.exists()


def test_wrong_signature_returns_401(api_client, payment):
    response = post_webhook(api_client, event_for(payment), signature="sha256=" + "0" * 64)

    assert response.status_code == 401
    assert_error_shape(response, "INVALID_SIGNATURE")


def test_signature_of_a_different_body_returns_401(api_client, payment):
    other_body = json.dumps(event_for(payment, status="FAILED")).encode()

    response = post_webhook(api_client, event_for(payment), signature=compute_signature(other_body))

    assert response.status_code == 401
    assert_error_shape(response, "INVALID_SIGNATURE")
    assert reload(payment).status == PaymentStatus.PENDING


def test_valid_signature_returns_200(api_client, payment):
    response = post_webhook(api_client, event_for(payment))

    assert response.status_code == 200


# --- Payload validation (nothing stored) ---


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"event_id": None}, "event_id"),
        ({"payment_reference": "pay_not-hex"}, "payment_reference"),
        ({"status": "PENDING"}, "status"),
        ({"amount": "-5.00"}, "amount"),
    ],
)
def test_invalid_payload_returns_400_and_stores_nothing(api_client, payment, change, field):
    payload = {k: v for k, v in {**event_for(payment), **change}.items() if v is not None}

    response = post_webhook(api_client, payload)

    assert response.status_code == 400
    error = assert_error_shape(response, "VALIDATION_ERROR")
    assert field in error["details"]
    assert not WebhookEvent.objects.exists()


@pytest.mark.django_db
def test_unknown_payment_reference_returns_404_and_stores_nothing(api_client):
    payload = {
        "event_id": "evt_unknown",
        "payment_reference": "pay_" + "0" * 32,
        "status": "SUCCESS",
        "amount": "100.00",
    }

    response = post_webhook(api_client, payload)

    assert response.status_code == 404
    assert_error_shape(response, "PAYMENT_NOT_FOUND")
    assert not WebhookEvent.objects.exists()


def test_amount_mismatch_returns_400_and_changes_nothing(api_client, payment):
    response = post_webhook(api_client, event_for(payment, amount=Decimal("1.00")))

    assert response.status_code == 400
    error = assert_error_shape(response, "AMOUNT_MISMATCH")
    assert error["details"] == {"expected": str(payment.amount), "received": "1.00"}
    assert not WebhookEvent.objects.exists()
    assert reload(payment).status == PaymentStatus.PENDING


# --- Processing ---


def test_success_event_confirms_pending_payment(api_client, payment):
    payload = event_for(payment, "SUCCESS")

    response = post_webhook(api_client, payload)

    assert response.json() == {"event_id": payload["event_id"], "result": "PROCESSED", "note": ""}
    assert reload(payment).status == PaymentStatus.SUCCESS
    assert reload(payment.booking).status == BookingStatus.CONFIRMED
    event = WebhookEvent.objects.get()
    assert (event.status, event.attempts) == (WebhookEventStatus.PROCESSED, 1)
    assert event.processed_at is not None


def test_failed_event_fails_pending_payment(api_client, payment):
    response = post_webhook(api_client, event_for(payment, "FAILED"))

    assert response.json()["result"] == "PROCESSED"
    assert reload(payment).status == PaymentStatus.FAILED
    assert reload(payment.booking).status == BookingStatus.FAILED


def test_same_event_five_times_is_processed_once(api_client, payment):
    payload = event_for(payment, "SUCCESS")

    results = [post_webhook(api_client, payload).json()["result"] for _ in range(5)]

    assert results == ["PROCESSED"] + ["DUPLICATE"] * 4
    event = WebhookEvent.objects.get()
    assert event.attempts == 5
    booking = reload(payment.booking)
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.payments.count() == 1


def test_new_event_with_status_payment_already_has_is_ignored(api_client, payment):
    post_webhook(api_client, event_for(payment, "SUCCESS"))

    response = post_webhook(api_client, event_for(payment, "SUCCESS"))

    assert response.json()["result"] == "IGNORED"
    assert response.json()["note"] == "already_in_status"
    assert WebhookEvent.objects.filter(status=WebhookEventStatus.IGNORED).count() == 1


def test_failed_after_success_is_ignored_and_booking_stays_confirmed(api_client, payment):
    post_webhook(api_client, event_for(payment, "SUCCESS"))

    response = post_webhook(api_client, event_for(payment, "FAILED"))

    assert response.status_code == 200
    assert (response.json()["result"], response.json()["note"]) == ("IGNORED", "terminal_payment")
    assert reload(payment).status == PaymentStatus.SUCCESS
    assert reload(payment.booking).status == BookingStatus.CONFIRMED


def test_success_after_failed_is_ignored_and_booking_stays_failed(api_client, payment):
    post_webhook(api_client, event_for(payment, "FAILED"))

    response = post_webhook(api_client, event_for(payment, "SUCCESS"))

    assert (response.json()["result"], response.json()["note"]) == ("IGNORED", "terminal_payment")
    assert reload(payment).status == PaymentStatus.FAILED
    assert reload(payment.booking).status == BookingStatus.FAILED


def test_success_for_cancelled_booking_flags_refund_and_keeps_booking_cancelled(
    api_client, payment
):
    transition(payment.booking, BookingStatus.CANCELLED)

    response = post_webhook(api_client, event_for(payment, "SUCCESS"))

    assert (response.json()["result"], response.json()["note"]) == ("PROCESSED", "refund_required")
    payment = reload(payment)
    assert payment.status == PaymentStatus.SUCCESS
    assert payment.refund_required is True
    assert reload(payment.booking).status == BookingStatus.CANCELLED
    assert WebhookEvent.objects.get().note == "refund_required"


def test_failed_for_cancelled_booking_keeps_booking_cancelled(api_client, payment):
    transition(payment.booking, BookingStatus.CANCELLED)

    response = post_webhook(api_client, event_for(payment, "FAILED"))

    assert response.json()["result"] == "PROCESSED"
    assert reload(payment).status == PaymentStatus.FAILED
    assert reload(payment).refund_required is False
    assert reload(payment.booking).status == BookingStatus.CANCELLED


def test_no_jwt_needed_and_garbage_authorization_header_is_ignored(api_client, payment):
    response = post_webhook(
        api_client, event_for(payment), HTTP_AUTHORIZATION="Bearer garbage.token.value"
    )

    assert response.status_code == 200
    assert response.json()["result"] == "PROCESSED"


def test_webhook_is_not_throttled(api_client, payment):
    statuses = {post_webhook(api_client, event_for(payment)).status_code for _ in range(30)}

    assert statuses == {200}
    assert WebhookEvent.objects.count() == 30


def test_webhook_url_routes_to_webhook_view_not_payment_detail():
    assert resolve(WEBHOOK_URL).func.view_class is WebhookView


# --- Unexpected failures + retries ---


def fail_once(monkeypatch):
    """Make apply_payment_result raise on its first call only (e.g. a transient DB hiccup)."""
    real_apply = webhook.apply_payment_result
    calls = []

    def flaky(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("transient failure")
        return real_apply(**kwargs)

    monkeypatch.setattr(webhook, "apply_payment_result", flaky)


def test_unexpected_error_returns_500_stores_failed_event_and_changes_nothing(
    api_client, payment, monkeypatch
):
    fail_once(monkeypatch)

    response = post_webhook(api_client, event_for(payment, "SUCCESS"))

    assert response.status_code == 500
    assert_error_shape(response, "INTERNAL_ERROR")
    event = WebhookEvent.objects.get()
    assert (event.status, event.note, event.attempts) == (
        WebhookEventStatus.FAILED,
        "RuntimeError",
        1,
    )
    assert reload(payment).status == PaymentStatus.PENDING
    assert reload(payment.booking).status == BookingStatus.PENDING


def test_resending_a_failed_event_processes_it(api_client, payment, monkeypatch):
    fail_once(monkeypatch)
    payload = event_for(payment, "SUCCESS")
    post_webhook(api_client, payload)

    response = post_webhook(api_client, payload)

    assert response.status_code == 200
    assert response.json()["result"] == "PROCESSED"
    event = WebhookEvent.objects.get()
    assert (event.status, event.attempts) == (WebhookEventStatus.PROCESSED, 2)
    assert reload(payment.booking).status == BookingStatus.CONFIRMED

    # ...and after that it's a normal duplicate again
    assert post_webhook(api_client, payload).json()["result"] == "DUPLICATE"


# --- Concurrency ---


@pytest.mark.django_db(transaction=True)
def test_same_event_sent_concurrently_is_processed_exactly_once():
    payment = PaymentFactory()
    payload = {
        "event_id": "evt_concurrent",
        "payment_reference": payment.reference,
        "status": "SUCCESS",
        "amount": payment.amount,
    }
    threads_count = 5
    barrier = threading.Barrier(threads_count)
    results, errors = [], []

    def worker():
        try:
            barrier.wait()
            results.append(process_webhook_event(payload).result)
        except Exception as exc:  # noqa: BLE001 — a thread's exception would vanish; assert below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(results) == ["DUPLICATE"] * 4 + ["PROCESSED"]
    event = WebhookEvent.objects.get()
    assert event.attempts == threads_count
    assert reload(payment).status == PaymentStatus.SUCCESS
    assert reload(payment.booking).status == BookingStatus.CONFIRMED
