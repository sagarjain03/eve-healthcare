from django.conf import settings
from django.db import models

from apps.centres.models import DiagnosticCentre, DiagnosticTest
from apps.common.models import TimeStampedModel


class BookingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


ACTIVE_STATUSES = (BookingStatus.PENDING, BookingStatus.CONFIRMED)


class Booking(TimeStampedModel):
    """A user's appointment for a test at a centre. Status changes only via state_machine."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings"
    )
    centre = models.ForeignKey(
        DiagnosticCentre, on_delete=models.PROTECT, related_name="bookings"
    )
    test = models.ForeignKey(DiagnosticTest, on_delete=models.PROTECT, related_name="bookings")
    appointment_at = models.DateTimeField(db_index=True)
    # Snapshot of CentreTest.price at booking time; later price changes don't affect it
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING,
        db_index=True,
    )

    class Meta:
        db_table = "bookings"
        ordering = ("-created_at",)
        constraints = (
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="booking_amount_positive"
            ),
            # Only one ACTIVE booking per slot; cancelled/failed ones don't block re-booking
            models.UniqueConstraint(
                fields=("user", "centre", "test", "appointment_at"),
                condition=models.Q(status__in=ACTIVE_STATUSES),
                name="booking_active_unique",
            ),
        )
        indexes = (models.Index(fields=("user", "-created_at"), name="booking_user_created_idx"),)

    def __str__(self) -> str:
        return f"Booking #{self.pk} ({self.status})"
