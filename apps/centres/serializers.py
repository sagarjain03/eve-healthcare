from decimal import Decimal

from rest_framework import serializers

from .models import CentreTest, DiagnosticCentre, DiagnosticTest


class DiagnosticTestSerializer(serializers.ModelSerializer):
    # Declared explicitly to drop DRF's exact-match UniqueValidator: it would miss "cbc" vs
    # "CBC" (code is uppercased on save). The DB enforces uniqueness; the service maps it to 409.
    code = serializers.CharField(max_length=30)

    class Meta:
        model = DiagnosticTest
        fields = ("id", "code", "name", "description", "sample_type", "is_active")


class CentreListSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticCentre
        fields = ("id", "name", "address", "city", "pincode", "is_active")


class OfferingSerializer(serializers.ModelSerializer):
    test_code = serializers.CharField(source="test.code", read_only=True)
    test_name = serializers.CharField(source="test.name", read_only=True)
    sample_type = serializers.CharField(source="test.sample_type", read_only=True)

    class Meta:
        model = CentreTest
        fields = ("test_id", "test_code", "test_name", "sample_type", "price", "is_active")
        read_only_fields = fields


class CentreDetailSerializer(CentreListSerializer):
    tests = OfferingSerializer(many=True, source="offerings", read_only=True)

    class Meta(CentreListSerializer.Meta):
        fields = (*CentreListSerializer.Meta.fields, "tests")


class CentreWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticCentre
        fields = ("id", "name", "address", "city", "pincode", "is_active")
        read_only_fields = ("id",)


class OfferingWriteSerializer(serializers.Serializer):
    test_id = serializers.PrimaryKeyRelatedField(
        queryset=DiagnosticTest.objects.all(), source="test"
    )
    price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01")
    )
    is_active = serializers.BooleanField(default=True)
