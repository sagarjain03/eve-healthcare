import logging
import random
import uuid
from enum import StrEnum

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import state_machine
from apps.bookings.models import Booking, BookingStatus
from apps.common.exceptions import (
    BusinessRuleViolation,
    Conflict,
    InvalidStateTransition,
    NotFound,
)

from .models import Payment, PaymentStatus

logger = logging.getLogger(__name__)

# SUCCESS and FAILED are final; a retry is a NEW payment row
PAYMENT_TRANSITIONS: dict[str, set[str]] = {
    PaymentStatus.PENDING: {PaymentStatus.SUCCESS, PaymentStatus.FAILED},
    PaymentStatus.SUCCESS: set(),
    PaymentStatus.FAILED: set(),
}

# Payment result -> booking status it drives
BOOKING_STATUS_FOR_PAYMENT = {
    PaymentStatus.SUCCESS: BookingStatus.CONFIRMED,
    PaymentStatus.FAILED: BookingStatus.FAILED,
}

PAYABLE_BOOKING_STATUSES = (BookingStatus.PENDING, BookingStatus.FAILED)
SIMULATED_DECLINE = "SIMULATED_DECLINE"


def _new_reference() -> str:
    """Public payment id: "pay_" + 32 hex chars (unguessable, URL-safe)."""
    return f"pay_{uuid.uuid4().hex}"


class ApplyResult(StrEnum):
    APPLIED = "APPLIED"  # payment updated (and booking, unless it was cancelled)
    NO_CHANGE = "NO_CHANGE"  # payment already had this status
    REFUND_REQUIRED = "REFUND_REQUIRED"  # SUCCESS for a cancelled booking


def apply_payment_result(
    *,
    payment: Payment,
    booking: Booking,
    new_status: str,
    failure_reason: str = SIMULATED_DECLINE,
) -> ApplyResult:
    """The SINGLE place that maps a payment result onto its booking.

    Caller must hold row locks on both (booking first, then payment). Re-applying the current
    status is a no-op. SUCCESS confirms the booking; FAILED marks it FAILED (user may retry).
    The payment always follows the provider; a CANCELLED booking stays cancelled — a SUCCESS
    for it is flagged `refund_required` instead.
    """
    old_status = payment.status
    if old_status == new_status:
        return ApplyResult.NO_CHANGE
    if new_status not in PAYMENT_TRANSITIONS[old_status]:
        raise InvalidStateTransition(
            f"Cannot move payment from {old_status} to {new_status}.",
            details={"from": old_status, "to": new_status, "object": "payment"},
        )

    payment.status = new_status
    payment.failure_reason = failure_reason if new_status == PaymentStatus.FAILED else ""
    log_extra = {
        "payment_reference": payment.reference,
        "booking_id": booking.id,
        "from": old_status,
        "to": new_status,
    }

    if booking.status == BookingStatus.CANCELLED:
        payment.refund_required = new_status == PaymentStatus.SUCCESS
        payment.save(update_fields=["status", "failure_reason", "refund_required", "updated_at"])
        if payment.refund_required:
            logger.warning("Payment succeeded for a cancelled booking; refund required",
                           extra=log_extra)
            return ApplyResult.REFUND_REQUIRED
        logger.info("Payment result applied; booking stays cancelled", extra=log_extra)
        return ApplyResult.APPLIED

    payment.save(update_fields=["status", "failure_reason", "updated_at"])
    state_machine.transition(booking, BOOKING_STATUS_FOR_PAYMENT[new_status])
    logger.info("Payment result applied", extra=log_extra)
    return ApplyResult.APPLIED


def _find_idempotent_replay(user: User, idempotency_key: str, booking_id: int) -> Payment | None:
    """Return the payment already created with this key, or None. Key reuse for another
    booking is a client bug → 409."""
    existing = Payment.objects.filter(user=user, idempotency_key=idempotency_key).first()
    if existing is not None and existing.booking_id != booking_id:
        raise Conflict(
            "This Idempotency-Key was already used for a different booking.",
            code="IDEMPOTENCY_KEY_REUSED",
        )
    return existing


def _decide_outcome(outcome: str | None) -> str:
    """Use the requested outcome, or pick SUCCESS/FAILED with PAYMENT_SUCCESS_RATE."""
    if outcome is not None:
        return outcome
    success = random.random() < settings.PAYMENT_SUCCESS_RATE
    return PaymentStatus.SUCCESS if success else PaymentStatus.FAILED


def _create_payment_locked(
    *, user: User, booking_id: int, outcome: str | None, idempotency_key: str | None
) -> Payment:
    """Lock the user's booking, check it can be paid, create the payment, apply the outcome."""
    try:
        booking = Booking.objects.select_for_update().filter(user=user).get(id=booking_id)
    except Booking.DoesNotExist as exc:
        raise NotFound("Booking not found.", code="BOOKING_NOT_FOUND") from exc

    if booking.status not in PAYABLE_BOOKING_STATUSES:
        raise Conflict(
            f"Booking is {booking.status} and cannot be paid.",
            details={"booking_status": booking.status},
            code="BOOKING_NOT_PAYABLE",
        )
    if booking.appointment_at <= timezone.now():
        raise BusinessRuleViolation(
            "Cannot pay for a booking whose appointment time has passed.",
            code="APPOINTMENT_ALREADY_PASSED",
        )
    if booking.payments.filter(status=PaymentStatus.PENDING).exists():
        raise Conflict("A payment for this booking is already in progress.",
                       code="PAYMENT_IN_PROGRESS")

    decided = _decide_outcome(outcome)
    payment = Payment.objects.create(
        booking=booking,
        user=user,
        reference=_new_reference(),
        amount=booking.amount,
        idempotency_key=idempotency_key,
    )
    if decided != PaymentStatus.PENDING:
        apply_payment_result(payment=payment, booking=booking, new_status=decided)
    return payment


def create_payment(
    *,
    user: User,
    booking_id: int,
    outcome: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[Payment, bool]:
    """Simulate paying for the user's own booking. Returns (payment, created).

    - Only PENDING/FAILED bookings with a future appointment can be paid.
    - outcome SUCCESS/FAILED is applied at once; PENDING leaves the result to the webhook;
      no outcome → random using PAYMENT_SUCCESS_RATE.
    - Same Idempotency-Key + same booking → the original payment (created=False).
    - The booking row is locked, so concurrent pays for one booking are serialized.
    """
    if idempotency_key:
        existing = _find_idempotent_replay(user, idempotency_key, booking_id)
        if existing is not None:
            return existing, False

    try:
        with transaction.atomic():
            payment = _create_payment_locked(
                user=user, booking_id=booking_id, outcome=outcome, idempotency_key=idempotency_key
            )
    except IntegrityError as exc:
        # A concurrent request won the race; map the violated constraint to a clean response
        constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
        if constraint == "payment_idempotency_key_unique" and idempotency_key:
            existing = _find_idempotent_replay(user, idempotency_key, booking_id)
            if existing is not None:
                return existing, False
        if constraint == "payment_one_active_per_booking":
            if Payment.objects.filter(booking_id=booking_id, status=PaymentStatus.SUCCESS).exists():
                raise Conflict("Booking is already paid.", code="BOOKING_NOT_PAYABLE") from exc
            raise Conflict(
                "A payment for this booking is already in progress.", code="PAYMENT_IN_PROGRESS"
            ) from exc
        raise

    logger.info(
        "Payment created",
        extra={
            "payment_reference": payment.reference,
            "booking_id": booking_id,
            "user_id": user.id,
            "status": payment.status,
        },
    )
    return payment, True
