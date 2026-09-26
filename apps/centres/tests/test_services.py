from decimal import Decimal

import pytest

from apps.centres.services import upsert_offering
from apps.centres.tests.factories import CentreFactory, DiagnosticTestFactory
from apps.common.exceptions import BusinessRuleViolation

pytestmark = pytest.mark.django_db


def test_upsert_offering_creates_then_updates_price():
    centre, test = CentreFactory(), DiagnosticTestFactory()

    offering, created = upsert_offering(centre=centre, test=test, price=Decimal("300.00"))
    assert created is True
    assert offering.price == Decimal("300.00")

    updated, created = upsert_offering(centre=centre, test=test, price=Decimal("450.00"))
    assert created is False
    assert updated.pk == offering.pk
    assert updated.price == Decimal("450.00")


def test_upsert_offering_with_inactive_test_raises_business_rule_violation():
    test = DiagnosticTestFactory(is_active=False)

    with pytest.raises(BusinessRuleViolation):
        upsert_offering(centre=CentreFactory(), test=test, price=Decimal("100.00"))
