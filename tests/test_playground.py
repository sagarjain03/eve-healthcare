import pytest


@pytest.mark.django_db
def test_playground_page_is_served_without_login(client):
    response = client.get("/playground/")

    assert response.status_code == 200
    assert b"API Playground" in response.content
    assert b"/payments/webhook/" in response.content
