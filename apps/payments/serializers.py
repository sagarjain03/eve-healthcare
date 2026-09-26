from decimal import Decimal

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


class WebhookPayloadSerializer(serializers.Serializer):
    event_id = serializers.CharField(min_length=1, max_length=100)
    payment_reference = serializers.RegexField(
        r"^pay_[0-9a-f]{32}$", error_messages={"invalid": "Invalid payment reference format."}
    )
    # A webhook reports a final result; PENDING is not a valid webhook status
    status = serializers.ChoiceField(choices=(PaymentStatus.SUCCESS, PaymentStatus.FAILED))
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))


class WebhookResponseSerializer(serializers.Serializer):
    event_id = serializers.CharField()
    result = serializers.ChoiceField(choices=("PROCESSED", "IGNORED", "DUPLICATE"))
    note = serializers.CharField(allow_blank=True)


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
            "refund_required",
            "booking_status",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
