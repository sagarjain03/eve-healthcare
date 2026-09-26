from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.centres.tests.factories import CentreFactory, CentreTestFactory, DiagnosticTestFactory

pytestmark = pytest.mark.django_db


def test_test_code_is_saved_uppercase():
    test = DiagnosticTestFactory(code=" cbc ")

    test.refresh_from_db()
    assert test.code == "CBC"


def test_duplicate_centre_test_offering_raises_integrity_error():
    offering = CentreTestFactory()

    with pytest.raises(IntegrityError):
        CentreTestFactory(centre=offering.centre, test=offering.test)


@pytest.mark.parametrize("price", [Decimal(0), Decimal("-10.00")])
def test_non_positive_price_raises_integrity_error(price):
    with pytest.raises(IntegrityError):
        CentreTestFactory(price=price)


def test_same_centre_name_and_city_different_case_raises_integrity_error():
    CentreFactory(name="City Lab", city="Delhi")

    with pytest.raises(IntegrityError):
        CentreFactory(name="CITY LAB", city="delhi")
