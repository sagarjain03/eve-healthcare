"""Payment provider webhook: HMAC signature check + idempotent event processing.

Flow (see Architecture §3.4):
1. Signature over the raw body is verified (401 if missing/wrong).
2. Payload is validated by the serializer (400).
3. process_webhook_event():
   - event_id already stored → DUPLICATE (no change)
   - unknown payment reference → 404; amount mismatch → 400 (nothing stored, provider can retry)
   - lock booking THEN payment (same order as create_payment → no deadlocks)
   - insert WebhookEvent (unique event_id is the idempotency guard)
   - apply via apply_payment_result, or IGNORE if the payment is already in / past that status
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.bookings.models import Booking
from apps.common.exceptions import BusinessRuleViolation, InvalidSignature, NotFound

from .models import Payment, PaymentStatus, WebhookEvent, WebhookEventStatus
from .services import ApplyResult, apply_payment_result

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Webhook-Signature"
SIGNATURE_PREFIX = "sha256="


class WebhookOutcome(StrEnum):
    PROCESSED = "PROCESSED"
    IGNORED = "IGNORED"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True)
class WebhookResult:
    event_id: str
    result: WebhookOutcome
    note: str = ""


# --- Signature ---


def compute_signature(body: bytes) -> str:
    """Return "sha256=<hex HMAC-SHA256 of body with WEBHOOK_SECRET>"."""
    digest = hmac.new(settings.WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify_signature(body: bytes, header: str | None) -> None:
    """Raise InvalidSignature (401) unless `header` is the correct signature for `body`."""
    if not header:
        raise InvalidSignature(f"Missing {SIGNATURE_HEADER} header.")
    # compare_digest takes constant time, so the signature can't be guessed byte by byte
    if not hmac.compare_digest(header.strip().encode(), compute_signature(body).encode()):
        logger.warning("Webhook signature mismatch")  # never log the secret or signature
        raise InvalidSignature()


# --- Processing ---


def _record_duplicate(event_id: str) -> bool:
    """Bump attempts on an already-stored event. True if the event existed."""
    return WebhookEvent.objects.filter(event_id=event_id).update(attempts=F("attempts") + 1) > 0


def _decide(payment: Payment, booking: Booking, new_status: str) -> tuple[WebhookOutcome, str]:
    if payment.status == new_status:
        return WebhookOutcome.IGNORED, "already_in_status"
    if payment.status != PaymentStatus.PENDING:  # SUCCESS / FAILED are terminal
        return WebhookOutcome.IGNORED, "terminal_payment"
    applied = apply_payment_result(payment=payment, booking=booking, new_status=new_status)
    note = "refund_required" if applied == ApplyResult.REFUND_REQUIRED else ""
    return WebhookOutcome.PROCESSED, note


def _log_result(result: WebhookResult, reference: str) -> None:
    extra = {
        "event_id": result.event_id,
        "payment_reference": reference,
        "result": result.result,
        "note": result.note,
    }
    if result.result == WebhookOutcome.IGNORED or result.note == "refund_required":
        logger.warning("Webhook event %s", result.result.lower(), extra=extra)
    else:
        logger.info("Webhook event %s", result.result.lower(), extra=extra)


def process_webhook_event(payload: dict) -> WebhookResult:
    """Apply one validated provider event exactly once.

    payload: {event_id, payment_reference, status (SUCCESS|FAILED), amount}.
    Raises NotFound (PAYMENT_NOT_FOUND) or BusinessRuleViolation (AMOUNT_MISMATCH) before
    anything is stored.
    """
    event_id = payload["event_id"]
    reference = payload["payment_reference"]
    new_status = payload["status"]
    amount = Decimal(str(payload["amount"]))

    if _record_duplicate(event_id):
        result = WebhookResult(event_id, WebhookOutcome.DUPLICATE)
        _log_result(result, reference)
        return result

    ids = Payment.objects.filter(reference=reference).values("id", "booking_id").first()
    if ids is None:
        raise NotFound("Payment not found.", code="PAYMENT_NOT_FOUND")

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=ids["booking_id"])
        payment = Payment.objects.select_for_update().get(pk=ids["id"])

        if amount != payment.amount:
            logger.warning(
                "Webhook amount mismatch",
                extra={
                    "event_id": event_id,
                    "payment_reference": reference,
                    "expected": str(payment.amount),
                    "received": str(amount),
                },
            )
            raise BusinessRuleViolation(
                "Amount does not match the payment amount.",
                details={"expected": str(payment.amount), "received": str(amount)},
                code="AMOUNT_MISMATCH",
            )

        try:
            with transaction.atomic():  # savepoint: a concurrent twin may insert first
                event = WebhookEvent.objects.create(
                    event_id=event_id,
                    payment_reference=reference,
                    payload={**payload, "amount": str(amount)},
                    status=WebhookEventStatus.PROCESSED,  # final status set below
                )
        except IntegrityError:
            _record_duplicate(event_id)
            result = WebhookResult(event_id, WebhookOutcome.DUPLICATE)
            _log_result(result, reference)
            return result

        outcome, note = _decide(payment, booking, new_status)
        event.status = (
            WebhookEventStatus.PROCESSED
            if outcome == WebhookOutcome.PROCESSED
            else WebhookEventStatus.IGNORED
        )
        event.note = note
        event.processed_at = timezone.now()
        event.save(update_fields=["status", "note", "processed_at"])

    result = WebhookResult(event_id, outcome, note)
    _log_result(result, reference)
    return result
