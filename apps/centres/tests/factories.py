from decimal import Decimal

import factory

from apps.centres.models import CentreTest, DiagnosticCentre, DiagnosticTest


class CentreFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DiagnosticCentre

    name = factory.Sequence(lambda n: f"Centre {n}")
    address = factory.Sequence(lambda n: f"{n} Main Road")
    city = "Delhi"
    pincode = "110001"


class DiagnosticTestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DiagnosticTest

    code = factory.Sequence(lambda n: f"T{n}")
    name = factory.Sequence(lambda n: f"Test {n}")
    sample_type = "Blood"


class CentreTestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CentreTest

    centre = factory.SubFactory(CentreFactory)
    test = factory.SubFactory(DiagnosticTestFactory)
    price = Decimal("499.00")
