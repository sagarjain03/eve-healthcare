import pytest
from django.core.management import call_command

from apps.bookings.models import BookingStatus
from apps.payments.models import PaymentStatus, WebhookEvent, WebhookEventStatus
from apps.payments.tests.factories import PaymentFactory

pytestmark = pytest.mark.django_db


def failed_event(payment, event_id="evt_failed", attempts=1, status="SUCCESS"):
    """A FAILED event as the webhook stores it after an unexpected error."""
    return WebhookEvent.objects.create(
        event_id=event_id,
        payment_reference=payment.reference,
        payload={
            "event_id": event_id,
            "payment_reference": payment.reference,
            "status": status,
            "amount": str(payment.amount),
        },
        status=WebhookEventStatus.FAILED,
        note="RuntimeError",
        attempts=attempts,
    )


def run(capsys, *args) -> str:
    call_command("reprocess_webhooks", *args)
    return capsys.readouterr().out


def reload(obj):
    obj.refresh_from_db()
    return obj


def test_command_retries_failed_events_and_succeeds(capsys):
    payment = PaymentFactory()
    event = failed_event(payment)

    out = run(capsys)

    event = reload(event)
    assert (event.status, event.attempts) == (WebhookEventStatus.PROCESSED, 2)
    assert reload(payment).status == PaymentStatus.SUCCESS
    assert reload(payment.booking).status == BookingStatus.CONFIRMED
    assert "retried: 1, succeeded: 1, still failing: 0, skipped (max attempts): 0" in out


def test_command_skips_events_at_max_attempts(capsys):
    payment = PaymentFactory()
    event = failed_event(payment, attempts=5)

    out = run(capsys, "--max-attempts", "5")

    assert reload(event).status == WebhookEventStatus.FAILED
    assert reload(payment).status == PaymentStatus.PENDING
    assert "skipped (max attempts): 1" in out


def test_dry_run_changes_nothing(capsys):
    payment = PaymentFactory()
    event = failed_event(payment)

    out = run(capsys, "--dry-run")

    event = reload(event)
    assert (event.status, event.attempts) == (WebhookEventStatus.FAILED, 1)
    assert reload(payment).status == PaymentStatus.PENDING
    assert "would retry evt_failed" in out
    assert out.strip().splitlines()[-1].startswith("[dry run] retried: 1")


def test_processed_event_is_never_rerun(capsys):
    payment = PaymentFactory()
    event = failed_event(payment)
    event.status = WebhookEventStatus.PROCESSED
    event.save()

    out = run(capsys)

    assert reload(event).attempts == 1
    assert reload(payment).status == PaymentStatus.PENDING
    assert "retried: 0" in out


def test_event_that_fails_again_stays_failed_with_more_attempts(capsys, monkeypatch):
    from apps.payments import webhook

    payment = PaymentFactory()
    event = failed_event(payment)

    def still_broken(**kwargs):
        raise RuntimeError("still down")

    monkeypatch.setattr(webhook, "apply_payment_result", still_broken)

    out = run(capsys)

    event = reload(event)
    assert (event.status, event.attempts) == (WebhookEventStatus.FAILED, 2)
    assert reload(payment).status == PaymentStatus.PENDING
    assert "still failing: 1" in out
