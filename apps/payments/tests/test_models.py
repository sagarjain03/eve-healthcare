import pytest
from django.db import IntegrityError

from apps.accounts.tests.factories import UserFactory
from apps.bookings.tests.factories import BookingFactory
from apps.payments.models import PaymentStatus
from apps.payments.tests.factories import PaymentFactory

pytestmark = pytest.mark.django_db


def test_two_success_payments_for_one_booking_raise_integrity_error():
    booking = BookingFactory()
    PaymentFactory(booking=booking, status=PaymentStatus.SUCCESS)

    with pytest.raises(IntegrityError):
        PaymentFactory(booking=booking, status=PaymentStatus.SUCCESS)


def test_pending_and_success_payment_for_one_booking_raise_integrity_error():
    booking = BookingFactory()
    PaymentFactory(booking=booking, status=PaymentStatus.PENDING)

    with pytest.raises(IntegrityError):
        PaymentFactory(booking=booking, status=PaymentStatus.SUCCESS)


def test_multiple_failed_payments_for_one_booking_are_allowed():
    booking = BookingFactory()

    PaymentFactory.create_batch(3, booking=booking, status=PaymentStatus.FAILED)

    assert booking.payments.count() == 3


def test_same_user_same_idempotency_key_raises_integrity_error():
    first = PaymentFactory(idempotency_key="key-1", status=PaymentStatus.FAILED)
    other_booking = BookingFactory(user=first.user)

    with pytest.raises(IntegrityError):
        PaymentFactory(booking=other_booking, idempotency_key="key-1")


def test_different_users_can_use_the_same_idempotency_key():
    PaymentFactory(idempotency_key="shared-key")

    second = PaymentFactory(
        booking=BookingFactory(user=UserFactory()), idempotency_key="shared-key"
    )

    assert second.pk is not None
