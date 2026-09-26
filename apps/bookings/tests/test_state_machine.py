from itertools import product

import pytest

from apps.bookings.models import BookingStatus
from apps.bookings.state_machine import ALLOWED_TRANSITIONS, can_transition, transition
from apps.bookings.tests.factories import BookingFactory
from apps.common.exceptions import InvalidStateTransition

pytestmark = pytest.mark.django_db

ALL_PAIRS = list(product(BookingStatus.values, repeat=2))
ALLOWED = [(old, new) for old, new in ALL_PAIRS if new in ALLOWED_TRANSITIONS[old]]
DISALLOWED = [(old, new) for old, new in ALL_PAIRS if new not in ALLOWED_TRANSITIONS[old]]


def test_transition_table_matches_the_documented_rules():
    assert set(ALLOWED) == {
        ("PENDING", "CONFIRMED"),
        ("PENDING", "FAILED"),
        ("PENDING", "CANCELLED"),
        ("FAILED", "CONFIRMED"),
        ("FAILED", "FAILED"),
        ("FAILED", "CANCELLED"),
        ("CONFIRMED", "CANCELLED"),
    }


@pytest.mark.parametrize(("old", "new"), ALLOWED)
def test_allowed_transition_updates_status(old, new):
    booking = BookingFactory(status=old)

    transition(booking, new)

    booking.refresh_from_db()
    assert booking.status == new
    assert can_transition(old, new) is True


@pytest.mark.parametrize(("old", "new"), DISALLOWED)
def test_disallowed_transition_raises_and_keeps_status(old, new):
    booking = BookingFactory(status=old)

    with pytest.raises(InvalidStateTransition) as exc_info:
        transition(booking, new)

    assert exc_info.value.status_code == 409
    assert exc_info.value.details == {"from": old, "to": new}
    booking.refresh_from_db()
    assert booking.status == old
