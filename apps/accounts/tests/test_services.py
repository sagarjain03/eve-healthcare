import pytest
from django.db.models import QuerySet

from apps.accounts.services import register_user
from apps.common.exceptions import EmailAlreadyExists

pytestmark = pytest.mark.django_db


def test_register_user_hashes_password_and_lowercases_email():
    user = register_user(email="  New@Example.COM ", password="StrongPass!123", full_name="New")

    assert user.email == "new@example.com"
    assert user.password != "StrongPass!123"
    assert user.check_password("StrongPass!123")


def test_register_user_race_is_caught_by_db_constraint(monkeypatch):
    """Two signups pass the exists() pre-check at once; the unique index must still win."""
    register_user(email="race@example.com", password="StrongPass!123", full_name="First")
    monkeypatch.setattr(QuerySet, "exists", lambda self: False)  # simulate the lost race

    with pytest.raises(EmailAlreadyExists):
        register_user(email="RACE@example.com", password="StrongPass!123", full_name="Second")


def test_register_user_duplicate_email_different_case_raises_email_already_exists():
    register_user(email="dup@example.com", password="StrongPass!123", full_name="One")

    with pytest.raises(EmailAlreadyExists):
        register_user(email="DUP@example.com", password="StrongPass!123", full_name="Two")
