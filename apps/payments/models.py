from django.conf import settings
from django.db import models

from apps.bookings.models import Booking
from apps.common.models import TimeStampedModel


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"


class Payment(TimeStampedModel):
    """One payment attempt for a booking. Status changes only via services.apply_payment_result."""

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="payments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments"
    )
    # "pay_" + uuid4 hex, generated in the service
    reference = models.CharField(max_length=40, unique=True, editable=False)
    # Copied from booking.amount (itself a snapshot of the centre price)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )
    idempotency_key = models.CharField(max_length=100, null=True, blank=True)
    failure_reason = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "payments"
        ordering = ("-created_at",)
        constraints = (
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="payment_amount_positive"
            ),
            # At most one in-flight or successful payment per booking; FAILED retries are fine
            models.UniqueConstraint(
                fields=("booking",),
                condition=models.Q(status__in=(PaymentStatus.PENDING, PaymentStatus.SUCCESS)),
                name="payment_one_active_per_booking",
            ),
            models.UniqueConstraint(
                fields=("user", "idempotency_key"),
                condition=models.Q(idempotency_key__isnull=False),
                name="payment_idempotency_key_unique",
            ),
        )

    def __str__(self) -> str:
        return f"{self.reference} ({self.status})"
