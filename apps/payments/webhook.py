"""Payment provider webhook: HMAC signature check + idempotent event processing.

Flow (see Architecture §3.4):
1. Signature over the raw body is verified (401 if missing/wrong).
2. Payload is validated by the serializer (400).
3. process_webhook_event():
   - event_id already PROCESSED/IGNORED → DUPLICATE (no change); a FAILED one is re-processed
   - unknown payment reference → 404; amount mismatch → 400 (nothing stored, provider can retry)
   - lock booking THEN payment (same order as create_payment → no deadlocks)
   - insert (or re-use the FAILED) WebhookEvent (unique event_id is the idempotency guard)
   - apply via apply_payment_result, or IGNORE if the payment is already in / past that status
   - an UNEXPECTED error rolls everything back, is recorded as a FAILED event in its own
     transaction, and returns 500 so the provider retries (or `reprocess_webhooks` does)
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
from apps.common.exceptions import (
    BusinessRuleViolation,
    DomainError,
    InvalidSignature,
    NotFound,
    WebhookProcessingError,
)

from .models import Payment, PaymentStatus, WebhookEvent, WebhookEventStatus
from .services import ApplyResult, apply_payment_result

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Webhook-Signature"
SIGNATURE_PREFIX = "sha256="
FINAL_EVENT_STATUSES = (WebhookEventStatus.PROCESSED, WebhookEventStatus.IGNORED)


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
    """Bump attempts on an already-final (PROCESSED/IGNORED) event. True if there was one."""
    updated = WebhookEvent.objects.filter(
        event_id=event_id, status__in=FINAL_EVENT_STATUSES
    ).update(attempts=F("attempts") + 1)
    return updated > 0


def _record_failure(event_id: str, reference: str, stored_payload: dict, exc: Exception) -> None:
    """Store/update the event as FAILED in its own transaction (the processing one rolled back)."""
    with transaction.atomic():
        event, created = WebhookEvent.objects.select_for_update().get_or_create(
            event_id=event_id,
            defaults={
                "payment_reference": reference,
                "payload": stored_payload,
                "status": WebhookEventStatus.FAILED,
                "note": type(exc).__name__,
            },
        )
        if not created:
            event.status = WebhookEventStatus.FAILED
            event.note = type(exc).__name__
            event.attempts = F("attempts") + 1
            event.save(update_fields=["status", "note", "attempts"])
    logger.error(
        "Webhook event processing failed; will be retried",
        exc_info=exc,
        extra={"event_id": event_id, "payment_reference": reference},
    )


def _decide(payment: Payment, booking: Booking, new_status: str) -> tuple[WebhookOutcome, str]:
    """Apply the result, or IGNORE if the payment already has / is past that status."""
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


def _claim_event(event_id: str, reference: str, stored_payload: dict) -> WebhookEvent | None:
    """Return the event row to process (new, or a FAILED one being retried), or None if another
    request already finished this event_id (→ DUPLICATE). Caller holds the booking lock."""
    event = WebhookEvent.objects.select_for_update().filter(event_id=event_id).first()
    if event is not None:
        if event.status in FINAL_EVENT_STATUSES:
            return None
        event.attempts += 1  # retrying a FAILED event
        return event
    try:
        with transaction.atomic():  # savepoint: a concurrent twin may insert first
            return WebhookEvent.objects.create(
                event_id=event_id,
                payment_reference=reference,
                payload=stored_payload,
                status=WebhookEventStatus.PROCESSED,  # final status set by the caller
            )
    except IntegrityError:
        return None


def _process_locked(
    event_id: str, reference: str, new_status: str, amount: Decimal, ids: dict, stored: dict
) -> WebhookResult:
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

        event = _claim_event(event_id, reference, stored)
        if event is None:
            _record_duplicate(event_id)
            return WebhookResult(event_id, WebhookOutcome.DUPLICATE)

        outcome, note = _decide(payment, booking, new_status)
        event.status = (
            WebhookEventStatus.PROCESSED
            if outcome == WebhookOutcome.PROCESSED
            else WebhookEventStatus.IGNORED
        )
        event.note = note
        event.processed_at = timezone.now()
        event.save(update_fields=["status", "note", "attempts", "processed_at"])
    return WebhookResult(event_id, outcome, note)


def process_webhook_event(payload: dict) -> WebhookResult:
    """Apply one validated provider event exactly once.

    payload: {event_id, payment_reference, status (SUCCESS|FAILED), amount}.
    Raises NotFound (PAYMENT_NOT_FOUND) or BusinessRuleViolation (AMOUNT_MISMATCH) before
    anything is stored. An unexpected error is recorded as a FAILED event and re-raised as
    WebhookProcessingError (500) so the provider retries.
    """
    event_id = payload["event_id"]
    reference = payload["payment_reference"]
    new_status = payload["status"]
    amount = Decimal(str(payload["amount"]))
    stored = {**payload, "amount": str(amount)}  # JSON-safe copy for the events table

    if _record_duplicate(event_id):
        result = WebhookResult(event_id, WebhookOutcome.DUPLICATE)
        _log_result(result, reference)
        return result

    ids = Payment.objects.filter(reference=reference).values("id", "booking_id").first()
    if ids is None:
        raise NotFound("Payment not found.", code="PAYMENT_NOT_FOUND")

    try:
        result = _process_locked(event_id, reference, new_status, amount, ids, stored)
    except DomainError:
        raise  # expected 4xx: nothing stored, provider fixes and resends
    except Exception as exc:
        _record_failure(event_id, reference, stored, exc)
        raise WebhookProcessingError() from exc

    _log_result(result, reference)
    return result
