from rest_framework import serializers

from apps.centres.models import DiagnosticCentre, DiagnosticTest

from .models import Booking


class BookingCreateSerializer(serializers.Serializer):
    """Only these fields are accepted; any `amount`/`status` sent by the client is ignored."""

    centre_id = serializers.IntegerField(min_value=1)
    test_id = serializers.IntegerField(min_value=1)
    appointment_at = serializers.DateTimeField()


class BookingCentreSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticCentre
        fields = ("id", "name", "city")


class BookingTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticTest
        fields = ("id", "code", "name")


class BookingSerializer(serializers.ModelSerializer):
    centre = BookingCentreSerializer(read_only=True)
    test = BookingTestSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = (
            "id",
            "status",
            "amount",
            "appointment_at",
            "centre",
            "test",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
