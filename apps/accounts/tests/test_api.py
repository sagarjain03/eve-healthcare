import pytest

from apps.accounts.tests.factories import DEFAULT_PASSWORD

pytestmark = pytest.mark.django_db

SIGNUP_URL = "/auth/signup/"
LOGIN_URL = "/auth/login/"
REFRESH_URL = "/auth/token/refresh/"
ME_URL = "/auth/me/"


def signup_payload(**overrides) -> dict:
    return {
        "email": "new@example.com",
        "password": "StrongPass!123",
        "full_name": "New User",
        **overrides,
    }


def assert_error_shape(response, code: str | None = None) -> dict:
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    if code:
        assert body["error"]["code"] == code
    return body["error"]


# --- Signup ---


def test_signup_success_returns_201_without_password(api_client):
    response = api_client.post(SIGNUP_URL, signup_payload(), format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert "password" not in body


def test_signup_duplicate_email_returns_409(api_client, user):
    payload = signup_payload(email=user.email.upper())

    response = api_client.post(SIGNUP_URL, payload, format="json")

    assert response.status_code == 409
    assert_error_shape(response, "EMAIL_ALREADY_EXISTS")


def test_signup_invalid_email_returns_400(api_client):
    response = api_client.post(SIGNUP_URL, signup_payload(email="not-an-email"), format="json")

    assert response.status_code == 400
    error = assert_error_shape(response, "VALIDATION_ERROR")
    assert "email" in error["details"]


def test_signup_common_password_returns_400(api_client):
    response = api_client.post(SIGNUP_URL, signup_payload(password="password"), format="json")

    assert response.status_code == 400
    error = assert_error_shape(response, "VALIDATION_ERROR")
    assert "password" in error["details"]


def test_signup_missing_full_name_returns_400(api_client):
    payload = signup_payload()
    del payload["full_name"]

    response = api_client.post(SIGNUP_URL, payload, format="json")

    assert response.status_code == 400
    error = assert_error_shape(response, "VALIDATION_ERROR")
    assert "full_name" in error["details"]


def test_signup_ignores_garbage_authorization_header(api_client):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer garbage.token.value")

    response = api_client.post(SIGNUP_URL, signup_payload(), format="json")

    assert response.status_code == 201


# --- Login ---


def test_login_success_returns_access_and_refresh(api_client, user):
    response = api_client.post(
        LOGIN_URL, {"email": user.email, "password": DEFAULT_PASSWORD}, format="json"
    )

    assert response.status_code == 200
    assert {"access", "refresh"} <= set(response.json())


def test_login_with_mixed_case_email_succeeds(api_client, user):
    response = api_client.post(
        LOGIN_URL, {"email": user.email.upper(), "password": DEFAULT_PASSWORD}, format="json"
    )

    assert response.status_code == 200


def test_login_wrong_password_returns_401(api_client, user):
    response = api_client.post(
        LOGIN_URL, {"email": user.email, "password": "WrongPass!999"}, format="json"
    )

    assert response.status_code == 401
    assert_error_shape(response)


# --- Refresh ---


def test_refresh_with_valid_token_returns_new_access(api_client, user):
    login = api_client.post(
        LOGIN_URL, {"email": user.email, "password": DEFAULT_PASSWORD}, format="json"
    )

    response = api_client.post(REFRESH_URL, {"refresh": login.json()["refresh"]}, format="json")

    assert response.status_code == 200
    assert "access" in response.json()


def test_refresh_with_garbage_token_returns_401(api_client):
    response = api_client.post(REFRESH_URL, {"refresh": "garbage"}, format="json")

    assert response.status_code == 401
    assert_error_shape(response)


# --- Me ---


def test_me_with_token_returns_current_user(auth_client, user):
    response = auth_client.get(ME_URL)

    assert response.status_code == 200
    assert response.json()["email"] == user.email


def test_me_without_token_returns_401(api_client):
    response = api_client.get(ME_URL)

    assert response.status_code == 401
    assert_error_shape(response, "NOT_AUTHENTICATED")


def test_me_with_invalid_token_returns_401(api_client):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer invalid.token.value")

    response = api_client.get(ME_URL)

    assert response.status_code == 401
    assert_error_shape(response)


# --- Throttling ---


def test_login_is_throttled_after_10_attempts_per_minute(api_client, user):
    payload = {"email": user.email, "password": "WrongPass!999"}
    for _ in range(10):
        assert api_client.post(LOGIN_URL, payload, format="json").status_code == 401

    response = api_client.post(LOGIN_URL, payload, format="json")

    assert response.status_code == 429
    assert_error_shape(response, "THROTTLED")
