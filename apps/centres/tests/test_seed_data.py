import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.centres.models import CentreTest, DiagnosticCentre, DiagnosticTest

pytestmark = pytest.mark.django_db


def counts() -> tuple[int, int, int, int]:
    return (
        get_user_model().objects.filter(is_staff=True).count(),
        DiagnosticTest.objects.count(),
        DiagnosticCentre.objects.count(),
        CentreTest.objects.count(),
    )


def test_seed_data_is_idempotent(monkeypatch, capsys):
    monkeypatch.setenv("SEED_ADMIN_EMAIL", "seed-admin@eve.local")

    call_command("seed_data")
    first = counts()
    call_command("seed_data")

    assert first == (1, 8, 4, 25)
    assert counts() == first
    assert "0 created, 8 already existed" in capsys.readouterr().out
    admin = get_user_model().objects.get(email="seed-admin@eve.local")
    assert admin.is_staff and admin.is_superuser
