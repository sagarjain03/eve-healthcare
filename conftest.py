"""Shared pytest fixtures (root-level so they apply to tests/ and apps/*/tests/)."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def _clear_cache():
    # Throttle counters live in the cache; don't let them leak between tests
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


def _client_for(user) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def admin_user(db):
    return UserFactory(is_staff=True)


@pytest.fixture
def auth_client(user):
    return _client_for(user)


@pytest.fixture
def admin_client(admin_user):
    return _client_for(admin_user)
