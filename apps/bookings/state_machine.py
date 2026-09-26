"""Booking state machine — the ONLY place allowed to change `booking.status`.

Rules in plain English:
- A new booking starts as PENDING (waiting for payment).
- PENDING can become CONFIRMED (payment succeeded), FAILED (payment failed) or CANCELLED.
- FAILED can be retried: it can become CONFIRMED, FAILED again (another failed attempt),
  or CANCELLED.
- CONFIRMED can only be CANCELLED (a late "failed" payment event can't un-confirm it).
- CANCELLED is final: nothing can change it.
Anything else raises InvalidStateTransition, which the API returns as 409.
"""

import logging

from apps.common.exceptions import InvalidStateTransition

from .models import Booking, BookingStatus

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    BookingStatus.PENDING: {BookingStatus.CONFIRMED, BookingStatus.FAILED, BookingStatus.CANCELLED},
    BookingStatus.FAILED: {BookingStatus.CONFIRMED, BookingStatus.FAILED, BookingStatus.CANCELLED},
    BookingStatus.CONFIRMED: {BookingStatus.CANCELLED},
    BookingStatus.CANCELLED: set(),
}


def can_transition(current: str, new: str) -> bool:
    return new in ALLOWED_TRANSITIONS.get(current, set())


def transition(booking: Booking, new_status: str) -> Booking:
    """Move a booking to `new_status` or raise InvalidStateTransition (409)."""
    old_status = booking.status
    if not can_transition(old_status, new_status):
        raise InvalidStateTransition(
            f"Cannot move booking from {old_status} to {new_status}.",
            details={"from": old_status, "to": new_status},
        )
    booking.status = new_status
    booking.save(update_fields=["status", "updated_at"])
    logger.info(
        "Booking status changed",
        extra={"booking_id": booking.id, "from": old_status, "to": new_status},
    )
    return booking
