import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory

from apps.common.permissions import IsAdminOrReadOnly

User = get_user_model()
factory = APIRequestFactory()
permission = IsAdminOrReadOnly()


def test_get_allowed_for_anonymous_user():
    request = factory.get("/")
    request.user = AnonymousUser()

    assert permission.has_permission(request, None) is True


@pytest.mark.django_db
def test_post_denied_for_normal_user():
    request = factory.post("/")
    request.user = User.objects.create_user(email="u@example.com", password="pw", full_name="U")

    assert permission.has_permission(request, None) is False


@pytest.mark.django_db
def test_post_allowed_for_staff_user():
    request = factory.post("/")
    request.user = User.objects.create_user(
        email="s@example.com", password="pw", full_name="S", is_staff=True
    )

    assert permission.has_permission(request, None) is True
