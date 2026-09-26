from django.core.management.base import BaseCommand

from apps.common.exceptions import DomainError
from apps.payments.models import WebhookEvent, WebhookEventStatus
from apps.payments.webhook import process_webhook_event


class Command(BaseCommand):
    help = (
        "Re-run FAILED webhook events from their stored payload. The signature was verified "
        "when the event was received. PROCESSED/IGNORED events are never re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-attempts",
            type=int,
            default=5,
            help="Skip events that already have this many attempts (default 5).",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Only list what would be retried."
        )

    def handle(self, *args, max_attempts: int, dry_run: bool, **options):
        failed = WebhookEvent.objects.filter(status=WebhookEventStatus.FAILED).order_by(
            "received_at"
        )
        retried = succeeded = still_failing = skipped = 0

        for event in failed:
            if event.attempts >= max_attempts:
                skipped += 1
                self.stdout.write(f"  skip  {event.event_id} (attempts={event.attempts})")
                continue
            if dry_run:
                retried += 1
                self.stdout.write(f"  would retry {event.event_id} (attempts={event.attempts})")
                continue

            retried += 1
            try:
                result = process_webhook_event(event.payload)
            except DomainError as exc:  # includes WebhookProcessingError (recorded as FAILED)
                still_failing += 1
                self.stdout.write(f"  fail  {event.event_id}: {exc.code}")
            else:
                succeeded += 1
                self.stdout.write(f"  ok    {event.event_id}: {result.result} {result.note}")

        prefix = "[dry run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}retried: {retried}, succeeded: {succeeded}, "
                f"still failing: {still_failing}, skipped (max attempts): {skipped}"
            )
        )
