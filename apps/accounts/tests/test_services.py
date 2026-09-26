import pytest

from apps.accounts.services import register_user
from apps.common.exceptions import EmailAlreadyExists

pytestmark = pytest.mark.django_db


def test_register_user_hashes_password_and_lowercases_email():
    user = register_user(email="  New@Example.COM ", password="StrongPass!123", full_name="New")

    assert user.email == "new@example.com"
    assert user.password != "StrongPass!123"
    assert user.check_password("StrongPass!123")


def test_register_user_duplicate_email_different_case_raises_email_already_exists():
    register_user(email="dup@example.com", password="StrongPass!123", full_name="One")

    with pytest.raises(EmailAlreadyExists):
        register_user(email="DUP@example.com", password="StrongPass!123", full_name="Two")
