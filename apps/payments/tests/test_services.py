import threading
from datetime import timedelta

import pytest
from django.db import connection
from django.db.models import QuerySet
from django.utils import timezone

from apps.bookings.models import BookingStatus
from apps.bookings.state_machine import transition
from apps.bookings.tests.factories import BookingFactory
from apps.common.exceptions import (
    BusinessRuleViolation,
    Conflict,
    InvalidStateTransition,
    NotFound,
)
from apps.payments import services
from apps.payments.models import Payment, PaymentStatus
from apps.payments.services import apply_payment_result, create_payment
from apps.payments.tests.factories import PaymentFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def booking():
    return BookingFactory()


def pay(booking, outcome=None, **kwargs):
    return create_payment(user=booking.user, booking_id=booking.id, outcome=outcome, **kwargs)


def reload(obj):
    obj.refresh_from_db()
    return obj


# --- Outcomes ---


def test_success_outcome_confirms_booking(booking):
    payment, created = pay(booking, "SUCCESS")

    assert created is True
    assert payment.status == PaymentStatus.SUCCESS
    assert payment.reference.startswith("pay_")
    assert reload(booking).status == BookingStatus.CONFIRMED


def test_failed_outcome_fails_booking_with_reason(booking):
    payment, _ = pay(booking, "FAILED")

    assert payment.status == PaymentStatus.FAILED
    assert payment.failure_reason == "SIMULATED_DECLINE"
    assert reload(booking).status == BookingStatus.FAILED


def test_pending_outcome_leaves_both_pending(booking):
    payment, _ = pay(booking, "PENDING")

    assert reload(payment).status == PaymentStatus.PENDING
    assert reload(booking).status == BookingStatus.PENDING


def test_retry_after_failed_with_success_confirms_booking(booking):
    pay(booking, "FAILED")

    pay(booking, "SUCCESS")

    assert reload(booking).status == BookingStatus.CONFIRMED
    assert booking.payments.count() == 2


def test_payment_amount_equals_booking_amount(booking):
    payment, _ = pay(booking, "SUCCESS")

    assert payment.amount == booking.amount


@pytest.mark.parametrize(("roll", "expected"), [(0.1, "SUCCESS"), (0.95, "FAILED")])
def test_omitted_outcome_uses_success_rate(booking, monkeypatch, settings, roll, expected):
    settings.PAYMENT_SUCCESS_RATE = 0.8
    monkeypatch.setattr(services.random, "random", lambda: roll)

    payment, _ = pay(booking)

    assert payment.status == expected


# --- Rejections ---


@pytest.mark.parametrize("booking_status", [BookingStatus.CONFIRMED, BookingStatus.CANCELLED])
def test_paying_confirmed_or_cancelled_booking_is_not_payable(booking, booking_status):
    transition(booking, booking_status)

    with pytest.raises(Conflict) as exc_info:
        pay(booking, "SUCCESS")

    assert exc_info.value.code == "BOOKING_NOT_PAYABLE"
    assert exc_info.value.details == {"booking_status": booking_status}


def test_paying_while_pending_payment_exists_is_in_progress(booking):
    pay(booking, "PENDING")

    with pytest.raises(Conflict) as exc_info:
        pay(booking, "SUCCESS")

    assert exc_info.value.code == "PAYMENT_IN_PROGRESS"


def test_other_users_or_missing_booking_is_not_found(booking):
    other = BookingFactory()

    for booking_id in (other.id, 999999):
        with pytest.raises(NotFound) as exc_info:
            create_payment(user=booking.user, booking_id=booking_id, outcome="SUCCESS")
        assert exc_info.value.code == "BOOKING_NOT_FOUND"


def test_paying_past_appointment_is_rejected():
    booking = BookingFactory(appointment_at=timezone.now() - timedelta(hours=1))

    with pytest.raises(BusinessRuleViolation) as exc_info:
        pay(booking, "SUCCESS")

    assert exc_info.value.code == "APPOINTMENT_ALREADY_PASSED"


# --- Race branches (pre-check passes, DB constraint catches it) ---


def test_in_progress_race_is_caught_by_one_active_constraint(booking, monkeypatch):
    PaymentFactory(booking=booking)  # PENDING payment already exists
    monkeypatch.setattr(QuerySet, "exists", lambda self: False)  # pre-check misses it

    with pytest.raises(Conflict) as exc_info:
        pay(booking, "SUCCESS")

    assert exc_info.value.code == "PAYMENT_IN_PROGRESS"


def test_already_paid_race_is_caught_by_one_active_constraint(booking, monkeypatch):
    # A concurrent request's SUCCESS payment committed after our status check
    PaymentFactory(booking=booking, status=PaymentStatus.SUCCESS)
    real_exists = QuerySet.exists
    # Only the in-progress pre-check misses; the "is it already paid?" lookup stays real
    monkeypatch.setattr(
        QuerySet,
        "exists",
        lambda self: False if self.query.where and "PENDING" in str(self.query) else
        real_exists(self),
    )

    with pytest.raises(Conflict) as exc_info:
        pay(booking, "SUCCESS")

    assert exc_info.value.code == "BOOKING_NOT_PAYABLE"


def test_idempotency_key_race_returns_the_winning_payment(booking, monkeypatch):
    winner = PaymentFactory(booking=booking, status=PaymentStatus.FAILED, idempotency_key="k-r")
    transition(booking, BookingStatus.FAILED)
    real_find = services._find_idempotent_replay
    calls = []

    def find_once_missing(*args):
        calls.append(args)
        return None if len(calls) == 1 else real_find(*args)  # 1st lookup loses the race

    monkeypatch.setattr(services, "_find_idempotent_replay", find_once_missing)

    payment, created = pay(booking, "SUCCESS", idempotency_key="k-r")

    assert (payment.pk, created) == (winner.pk, False)
    assert booking.payments.count() == 1


# --- Concurrency ---


@pytest.mark.django_db(transaction=True)
def test_concurrent_payments_for_same_booking_only_one_succeeds():
    booking = BookingFactory()
    threads_count = 5
    barrier = threading.Barrier(threads_count)
    created, rejected, errors = [], [], []

    def worker():
        try:
            barrier.wait()
            create_payment(user=booking.user, booking_id=booking.id, outcome="SUCCESS")
            created.append(True)
        except Conflict as exc:
            rejected.append(exc.code)
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
    assert len(created) == 1  # the booking row lock serializes the requests
    assert rejected == ["BOOKING_NOT_PAYABLE"] * (threads_count - 1)
    assert Payment.objects.filter(booking=booking).count() == 1
    assert reload(booking).status == BookingStatus.CONFIRMED


# --- apply_payment_result ---


def test_apply_same_status_twice_is_noop(booking):
    payment = PaymentFactory(booking=booking)
    apply_payment_result(payment=payment, booking=booking, new_status=PaymentStatus.SUCCESS)

    apply_payment_result(payment=payment, booking=booking, new_status=PaymentStatus.SUCCESS)

    assert reload(payment).status == PaymentStatus.SUCCESS
    assert reload(booking).status == BookingStatus.CONFIRMED


def test_apply_failed_after_success_raises_invalid_transition(booking):
    payment = PaymentFactory(booking=booking)
    apply_payment_result(payment=payment, booking=booking, new_status=PaymentStatus.SUCCESS)

    with pytest.raises(InvalidStateTransition) as exc_info:
        apply_payment_result(payment=payment, booking=booking, new_status=PaymentStatus.FAILED)

    assert exc_info.value.details == {"from": "SUCCESS", "to": "FAILED", "object": "payment"}
    assert reload(booking).status == BookingStatus.CONFIRMED


# --- Idempotency ---


def test_same_key_same_booking_returns_original_payment(booking):
    first, first_created = pay(booking, "SUCCESS", idempotency_key="k-1")

    second, second_created = pay(booking, "SUCCESS", idempotency_key="k-1")

    assert (first_created, second_created) == (True, False)
    assert second.pk == first.pk
    assert Payment.objects.filter(booking=booking).count() == 1


def test_same_key_different_booking_is_rejected(booking):
    pay(booking, "SUCCESS", idempotency_key="k-2")
    other = BookingFactory(user=booking.user)

    with pytest.raises(Conflict) as exc_info:
        pay(other, "SUCCESS", idempotency_key="k-2")

    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"
