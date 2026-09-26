from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

from apps.common.models import TimeStampedModel

pincode_validator = RegexValidator(r"^\d{6}$", "Pincode must be exactly 6 digits.")


class DiagnosticCentre(TimeStampedModel):
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, db_index=True)
    pincode = models.CharField(max_length=6, validators=[pincode_validator])
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "diagnostic_centres"
        constraints = (
            models.UniqueConstraint(
                Lower("name"), Lower("city"), name="centre_name_city_ci_unique"
            ),
        )

    def __str__(self) -> str:
        return f"{self.name} ({self.city})"


class DiagnosticTest(TimeStampedModel):
    """Global test catalog entry (e.g. CBC). Price lives on CentreTest."""

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    sample_type = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "diagnostic_tests"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class CentreTest(TimeStampedModel):
    """A test offered at a centre, with that centre's price."""

    centre = models.ForeignKey(DiagnosticCentre, on_delete=models.CASCADE, related_name="offerings")
    test = models.ForeignKey(DiagnosticTest, on_delete=models.PROTECT, related_name="offerings")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "centre_tests"
        constraints = (
            models.UniqueConstraint(fields=("centre", "test"), name="centre_test_unique"),
            models.CheckConstraint(
                condition=models.Q(price__gt=0), name="centre_test_price_positive"
            ),
        )

    def __str__(self) -> str:
        return f"{self.test.code} @ {self.centre.name}: {self.price}"
