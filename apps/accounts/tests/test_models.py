import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_create_user_hashes_password():
    user = User.objects.create_user(email="a@example.com", password="S3cret!pass", full_name="A")

    assert user.password != "S3cret!pass"
    assert user.check_password("S3cret!pass")


def test_create_user_lowercases_email():
    user = User.objects.create_user(email="Test@EXAMPLE.com", password="pw", full_name="T")

    assert user.email == "test@example.com"


def test_create_user_without_email_raises_value_error():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="pw", full_name="No Email")


def test_create_superuser_sets_staff_and_superuser_flags():
    admin = User.objects.create_superuser(email="admin@example.com", password="pw", full_name="Ad")

    assert admin.is_staff is True
    assert admin.is_superuser is True


def test_duplicate_email_with_different_case_raises_integrity_error():
    User.objects.create_user(email="dup@example.com", password="pw", full_name="One")

    with pytest.raises(IntegrityError):
        User.objects.create_user(email="DUP@Example.com", password="pw", full_name="Two")


def test_db_rejects_mixed_case_duplicate_email_when_save_is_bypassed():
    User.objects.create_user(email="a@x.com", password="pw", full_name="Lower")

    # bulk_create skips User.save(), so only the DB constraint can catch this
    with pytest.raises(IntegrityError):
        User.objects.bulk_create([User(email="A@x.com", full_name="Upper")])
