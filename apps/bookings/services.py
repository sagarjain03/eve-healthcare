import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.centres.models import CentreTest, DiagnosticCentre
from apps.common.exceptions import BusinessRuleViolation, DuplicateBooking, NotFound

from . import state_machine
from .models import ACTIVE_STATUSES, Booking, BookingStatus

logger = logging.getLogger(__name__)


def _validate_appointment_time(appointment_at: datetime) -> None:
    now = timezone.now()
    if appointment_at <= now:
        raise BusinessRuleViolation(
            "Appointment time must be in the future.", code="APPOINTMENT_IN_PAST"
        )
    max_days = settings.MAX_BOOKING_DAYS_AHEAD
    if appointment_at > now + timedelta(days=max_days):
        raise BusinessRuleViolation(
            f"Appointments can be booked at most {max_days} days ahead.",
            code="APPOINTMENT_TOO_FAR",
        )


@transaction.atomic
def create_booking(
    *, user: User, centre_id: int, test_id: int, appointment_at: datetime
) -> Booking:
    """Create a PENDING booking.

    Rules: centre must be active; the test must be actively offered there; the time must be
    in the future and within MAX_BOOKING_DAYS_AHEAD; no duplicate active booking for the same
    slot (409). Amount is copied from the offering price — never taken from the client.
    """
    centre = DiagnosticCentre.objects.filter(pk=centre_id, is_active=True).first()
    if centre is None:
        raise BusinessRuleViolation(
            "Centre does not exist or is not active.", code="CENTRE_NOT_AVAILABLE"
        )

    offering = (
        CentreTest.objects.select_related("test")
        .filter(centre=centre, test_id=test_id, is_active=True, test__is_active=True)
        .first()
    )
    if offering is None:
        raise BusinessRuleViolation(
            "This test is not offered at this centre.", code="TEST_NOT_OFFERED"
        )

    _validate_appointment_time(appointment_at)

    slot = {"user": user, "centre": centre, "test": offering.test, "appointment_at": appointment_at}
    if Booking.objects.filter(**slot, status__in=ACTIVE_STATUSES).exists():
        raise DuplicateBooking()

    try:
        with transaction.atomic():  # savepoint: a concurrent duplicate hits the partial unique
            booking = Booking.objects.create(**slot, amount=offering.price)
    except IntegrityError as exc:
        raise DuplicateBooking() from exc

    logger.info("Booking created", extra={"booking_id": booking.id, "user_id": user.id})
    return booking


@transaction.atomic
def cancel_booking(*, user: User, booking_id: int) -> Booking:
    """Cancel the user's own booking.

    Other users' bookings are reported as not found (404) so their existence isn't leaked.
    Past appointments can't be cancelled; CANCELLED -> CANCELLED is rejected by the
    state machine (409).
    """
    try:
        booking = Booking.objects.select_for_update().filter(user=user).get(id=booking_id)
    except Booking.DoesNotExist as exc:
        raise NotFound("Booking not found.", code="BOOKING_NOT_FOUND") from exc

    if booking.appointment_at <= timezone.now():
        raise BusinessRuleViolation(
            "Cannot cancel a booking whose appointment time has passed.",
            code="APPOINTMENT_ALREADY_PASSED",
        )

    state_machine.transition(booking, BookingStatus.CANCELLED)
    logger.info("Booking cancelled", extra={"booking_id": booking.id, "user_id": user.id})
    return booking
