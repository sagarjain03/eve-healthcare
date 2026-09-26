from rest_framework import serializers

from .models import Payment, PaymentStatus


class PaymentCreateSerializer(serializers.Serializer):
    """Only these fields are accepted; any `amount`/`status` sent by the client is ignored."""

    booking_id = serializers.IntegerField(min_value=1)
    outcome = serializers.ChoiceField(
        choices=PaymentStatus.choices,
        required=False,
        help_text="SUCCESS / FAILED apply immediately; PENDING waits for the webhook; "
        "omit for a random result (PAYMENT_SUCCESS_RATE).",
    )


class PaymentSerializer(serializers.ModelSerializer):
    booking_status = serializers.CharField(source="booking.status", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "reference",
            "booking_id",
            "amount",
            "status",
            "failure_reason",
            "booking_status",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
