import logging
from decimal import Decimal

from django.db import IntegrityError, models, transaction

from apps.common.exceptions import (
    BusinessRuleViolation,
    CentreAlreadyExists,
    TestCodeAlreadyExists,
)

from .models import CentreTest, DiagnosticCentre, DiagnosticTest

logger = logging.getLogger(__name__)


def _save_or_conflict(instance: models.Model, conflict: type[Exception], **fields) -> models.Model:
    """Apply fields and save; a unique-constraint violation becomes a 409 domain error."""
    for name, value in fields.items():
        setattr(instance, name, value)
    try:
        with transaction.atomic():  # savepoint so the outer transaction survives the error
            instance.save()
    except IntegrityError as exc:
        raise conflict() from exc
    return instance


def create_centre(**fields) -> DiagnosticCentre:
    """Create a centre. Name + city is unique case-insensitively (409 on duplicate)."""
    return _save_or_conflict(DiagnosticCentre(), CentreAlreadyExists, **fields)


def update_centre(centre: DiagnosticCentre, **fields) -> DiagnosticCentre:
    """Update given centre fields (e.g. is_active=False to deactivate); 409 on duplicate."""
    return _save_or_conflict(centre, CentreAlreadyExists, **fields)


def create_test(**fields) -> DiagnosticTest:
    """Create a catalog test. Code is stored uppercase and unique (409 on duplicate)."""
    return _save_or_conflict(DiagnosticTest(), TestCodeAlreadyExists, **fields)


def update_test(test: DiagnosticTest, **fields) -> DiagnosticTest:
    """Update given catalog test fields; 409 if the new code is taken."""
    return _save_or_conflict(test, TestCodeAlreadyExists, **fields)


def upsert_offering(
    *, centre: DiagnosticCentre, test: DiagnosticTest, price: Decimal, is_active: bool = True
) -> tuple[CentreTest, bool]:
    """Add a test to a centre or update its price. Inactive tests can't be offered."""
    if not test.is_active:
        raise BusinessRuleViolation(f"Test {test.code} is inactive and cannot be offered.")
    with transaction.atomic():
        offering, created = CentreTest.objects.update_or_create(
            centre=centre, test=test, defaults={"price": price, "is_active": is_active}
        )
    logger.info(
        "Offering %s",
        "created" if created else "updated",
        extra={"centre_id": centre.id, "test_id": test.id, "offering_id": offering.id},
    )
    return offering, created
