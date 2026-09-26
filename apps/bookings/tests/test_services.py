from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.bookings.models import BookingStatus
from apps.bookings.services import cancel_booking, create_booking
from apps.bookings.tests.factories import BookingFactory
from apps.centres.tests.factories import CentreFactory, CentreTestFactory, DiagnosticTestFactory
from apps.common.exceptions import BusinessRuleViolation, DuplicateBooking

pytestmark = pytest.mark.django_db


def in_days(days: float):
    return timezone.now() + timedelta(days=days)


@pytest.fixture
def offering():
    return CentreTestFactory(price=Decimal("499.00"))


def book(user, offering, appointment_at=None):
    return create_booking(
        user=user,
        centre_id=offering.centre_id,
        test_id=offering.test_id,
        appointment_at=appointment_at or in_days(2),
    )


def test_create_booking_snapshots_price_and_starts_pending(offering):
    booking = book(UserFactory(), offering)

    assert booking.amount == Decimal("499.00")
    assert booking.status == BookingStatus.PENDING


@pytest.mark.parametrize("centre_state", ["inactive", "missing"])
def test_unavailable_centre_raises_centre_not_available(offering, centre_state):
    if centre_state == "inactive":
        offering.centre.is_active = False
        offering.centre.save()
        centre_id = offering.centre_id
    else:
        centre_id = 999999

    with pytest.raises(BusinessRuleViolation) as exc_info:
        create_booking(
            user=UserFactory(),
            centre_id=centre_id,
            test_id=offering.test_id,
            appointment_at=in_days(2),
        )

    assert exc_info.value.code == "CENTRE_NOT_AVAILABLE"


@pytest.mark.parametrize("case", ["not_offered", "inactive_offering", "inactive_test"])
def test_test_not_available_at_centre_raises_test_not_offered(case):
    centre = CentreFactory()
    if case == "not_offered":
        test = DiagnosticTestFactory()
    elif case == "inactive_offering":
        test = CentreTestFactory(centre=centre, is_active=False).test
    else:
        test = CentreTestFactory(centre=centre, test=DiagnosticTestFactory(is_active=False)).test

    with pytest.raises(BusinessRuleViolation) as exc_info:
        create_booking(
            user=UserFactory(), centre_id=centre.id, test_id=test.id, appointment_at=in_days(2)
        )

    assert exc_info.value.code == "TEST_NOT_OFFERED"


@pytest.mark.parametrize(
    ("days", "code"), [(-0.01, "APPOINTMENT_IN_PAST"), (91, "APPOINTMENT_TOO_FAR")]
)
def test_invalid_appointment_time_is_rejected(offering, days, code):
    with pytest.raises(BusinessRuleViolation) as exc_info:
        book(UserFactory(), offering, appointment_at=in_days(days))

    assert exc_info.value.code == code


def test_duplicate_active_booking_raises_duplicate_booking(offering):
    user, slot = UserFactory(), in_days(3)
    book(user, offering, slot)

    with pytest.raises(DuplicateBooking):
        book(user, offering, slot)


def test_duplicate_booking_race_is_caught_by_partial_unique(offering, monkeypatch):
    """Two requests pass the exists() pre-check at once; the partial unique index must win."""
    user, slot = UserFactory(), in_days(3)
    book(user, offering, slot)
    monkeypatch.setattr(QuerySet, "exists", lambda self: False)  # simulate the lost race

    with pytest.raises(DuplicateBooking):
        book(user, offering, slot)


def test_rebooking_same_slot_after_cancel_is_allowed(offering):
    user, slot = UserFactory(), in_days(3)
    first = book(user, offering, slot)
    cancel_booking(user=user, booking_id=first.id)

    second = book(user, offering, slot)

    assert second.id != first.id
    assert second.status == BookingStatus.PENDING


def test_db_constraint_rejects_duplicate_active_booking(offering):
    existing = BookingFactory(offering=offering)

    with pytest.raises(IntegrityError):
        BookingFactory(
            offering=offering, user=existing.user, appointment_at=existing.appointment_at
        )


def test_later_price_change_does_not_change_existing_booking_amount(offering):
    booking = book(UserFactory(), offering)

    offering.price = Decimal("999.00")
    offering.save()

    booking.refresh_from_db()
    assert booking.amount == Decimal("499.00")
