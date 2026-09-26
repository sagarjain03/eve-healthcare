import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.centres.models import CentreTest
from apps.centres.tests.factories import CentreFactory, CentreTestFactory, DiagnosticTestFactory

pytestmark = pytest.mark.django_db

CENTRES_URL = "/centres/"
TESTS_URL = "/tests/"


def centre_url(centre_id) -> str:
    return f"{CENTRES_URL}{centre_id}/"


def offering_url(centre_id) -> str:
    return f"{CENTRES_URL}{centre_id}/tests/"


def centre_payload(**overrides) -> dict:
    return {
        "name": "New Lab",
        "address": "1 Ring Road",
        "city": "Delhi",
        "pincode": "110002",
        **overrides,
    }


def assert_error_shape(response, code: str | None = None) -> dict:
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    if code:
        assert body["error"]["code"] == code
    return body["error"]


def result_ids(response) -> list[int]:
    return [item["id"] for item in response.json()["results"]]


# --- Public reads ---


def test_list_centres_without_token_returns_paginated_results(api_client):
    CentreFactory.create_batch(2)

    response = api_client.get(CENTRES_URL)

    assert response.status_code == 200
    body = response.json()
    assert {"count", "next", "previous", "results"} <= set(body)
    assert body["count"] == 2


def test_inactive_centre_hidden_from_public_but_visible_to_admin(api_client, admin_client):
    active = CentreFactory()
    inactive = CentreFactory(is_active=False)

    public_list = api_client.get(CENTRES_URL)
    public_detail = api_client.get(centre_url(inactive.id))
    admin_list = admin_client.get(CENTRES_URL)
    admin_detail = admin_client.get(centre_url(inactive.id))

    assert result_ids(public_list) == [active.id]
    assert public_detail.status_code == 404
    assert_error_shape(public_detail, "NOT_FOUND")
    assert set(result_ids(admin_list)) == {active.id, inactive.id}
    assert admin_detail.status_code == 200


def test_centre_detail_shows_only_active_offerings_with_prices(api_client):
    centre = CentreFactory()
    visible = CentreTestFactory(centre=centre, price="350.00")
    CentreTestFactory(centre=centre, is_active=False)
    CentreTestFactory(centre=centre, test=DiagnosticTestFactory(is_active=False))

    response = api_client.get(centre_url(centre.id))

    assert response.status_code == 200
    assert response.json()["tests"] == [
        {
            "test_id": visible.test.id,
            "test_code": visible.test.code,
            "test_name": visible.test.name,
            "sample_type": visible.test.sample_type,
            "price": "350.00",
            "is_active": True,
        }
    ]


def test_filter_by_city_is_case_insensitive(api_client):
    delhi = CentreFactory(city="Delhi")
    CentreFactory(city="Mumbai")

    response = api_client.get(CENTRES_URL, {"city": "delhi"})

    assert result_ids(response) == [delhi.id]


def test_filter_by_test_id_or_code_returns_each_centre_once(api_client):
    cbc = DiagnosticTestFactory(code="CBC")
    offers_cbc = CentreFactory()
    CentreTestFactory(centre=offers_cbc, test=cbc)
    CentreTestFactory(centre=offers_cbc)  # a second offering must not duplicate the centre
    inactive_offering = CentreFactory()
    CentreTestFactory(centre=inactive_offering, test=cbc, is_active=False)
    CentreTestFactory(centre=CentreFactory())  # offers something else

    by_id = api_client.get(CENTRES_URL, {"test": cbc.id})
    by_code = api_client.get(CENTRES_URL, {"test": "cbc"})

    assert result_ids(by_id) == [offers_cbc.id]
    assert result_ids(by_code) == [offers_cbc.id]


def test_unknown_centre_returns_404(api_client):
    response = api_client.get(centre_url(999999))

    assert response.status_code == 404
    assert_error_shape(response, "NOT_FOUND")


# --- Centre writes ---


def test_anonymous_create_centre_returns_401(api_client):
    response = api_client.post(CENTRES_URL, centre_payload(), format="json")

    assert response.status_code == 401
    assert_error_shape(response, "NOT_AUTHENTICATED")


def test_normal_user_create_centre_returns_403(auth_client):
    response = auth_client.post(CENTRES_URL, centre_payload(), format="json")

    assert response.status_code == 403
    assert_error_shape(response, "PERMISSION_DENIED")


def test_admin_create_centre_returns_201(admin_client):
    response = admin_client.post(CENTRES_URL, centre_payload(), format="json")

    assert response.status_code == 201
    assert response.json()["name"] == "New Lab"
    assert response.json()["is_active"] is True


def test_admin_create_duplicate_centre_different_case_returns_409(admin_client):
    CentreFactory(name="New Lab", city="Delhi")

    response = admin_client.post(
        CENTRES_URL, centre_payload(name="NEW LAB", city="delhi"), format="json"
    )

    assert response.status_code == 409
    assert_error_shape(response, "CENTRE_ALREADY_EXISTS")


def test_admin_deactivate_centre_with_patch(admin_client):
    centre = CentreFactory()

    response = admin_client.patch(centre_url(centre.id), {"is_active": False}, format="json")

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_invalid_pincode_returns_400(admin_client):
    response = admin_client.post(CENTRES_URL, centre_payload(pincode="12AB"), format="json")

    assert response.status_code == 400
    error = assert_error_shape(response, "VALIDATION_ERROR")
    assert "pincode" in error["details"]


def test_delete_centre_returns_405(admin_client):
    centre = CentreFactory()

    response = admin_client.delete(centre_url(centre.id))

    assert response.status_code == 405
    assert_error_shape(response, "METHOD_NOT_ALLOWED")


# --- Offerings ---


def test_admin_add_offering_returns_201_then_200_on_price_update(admin_client):
    centre, test = CentreFactory(), DiagnosticTestFactory()

    created = admin_client.post(
        offering_url(centre.id), {"test_id": test.id, "price": "500.00"}, format="json"
    )
    updated = admin_client.post(
        offering_url(centre.id), {"test_id": test.id, "price": "650.50"}, format="json"
    )

    assert created.status_code == 201
    assert created.json()["price"] == "500.00"
    assert updated.status_code == 200
    assert updated.json()["price"] == "650.50"
    assert CentreTest.objects.filter(centre=centre, test=test).count() == 1


@pytest.mark.parametrize(
    ("payload_overrides", "field"),
    [
        ({"price": "0"}, "price"),
        ({"price": "-5.00"}, "price"),
        ({"test_id": 999999}, "test_id"),
    ],
)
def test_invalid_offering_returns_400(admin_client, payload_overrides, field):
    centre, test = CentreFactory(), DiagnosticTestFactory()
    payload = {"test_id": test.id, "price": "100.00", **payload_overrides}

    response = admin_client.post(offering_url(centre.id), payload, format="json")

    assert response.status_code == 400
    error = assert_error_shape(response, "VALIDATION_ERROR")
    assert field in error["details"]


def test_offering_for_inactive_test_returns_400(admin_client):
    centre, test = CentreFactory(), DiagnosticTestFactory(is_active=False)

    response = admin_client.post(
        offering_url(centre.id), {"test_id": test.id, "price": "100.00"}, format="json"
    )

    assert response.status_code == 400
    assert_error_shape(response, "BUSINESS_RULE_VIOLATION")


def test_normal_user_add_offering_returns_403(auth_client):
    centre, test = CentreFactory(), DiagnosticTestFactory()

    response = auth_client.post(
        offering_url(centre.id), {"test_id": test.id, "price": "100.00"}, format="json"
    )

    assert response.status_code == 403
    assert_error_shape(response, "PERMISSION_DENIED")


# --- Tests catalog ---


def test_list_tests_is_public_and_hides_inactive(api_client):
    active = DiagnosticTestFactory()
    DiagnosticTestFactory(is_active=False)

    response = api_client.get(TESTS_URL)

    assert response.status_code == 200
    assert result_ids(response) == [active.id]


def test_search_tests_by_name(api_client):
    cbc = DiagnosticTestFactory(code="CBC", name="Complete Blood Count")
    DiagnosticTestFactory(code="LIPID", name="Lipid Profile")

    response = api_client.get(TESTS_URL, {"search": "blood"})

    assert result_ids(response) == [cbc.id]


def test_normal_user_create_test_returns_403(auth_client):
    response = auth_client.post(TESTS_URL, {"code": "NEW", "name": "New Test"}, format="json")

    assert response.status_code == 403
    assert_error_shape(response, "PERMISSION_DENIED")


def test_admin_create_test_returns_201_with_uppercase_code(admin_client):
    response = admin_client.post(TESTS_URL, {"code": "vitb12", "name": "Vitamin B12"}, format="json")

    assert response.status_code == 201
    assert response.json()["code"] == "VITB12"


def test_page_size_is_capped_at_100(api_client):
    DiagnosticTestFactory.create_batch(105)

    response = api_client.get(TESTS_URL, {"page_size": 1000})

    assert response.json()["count"] == 105
    assert len(response.json()["results"]) == 100


def test_admin_create_duplicate_test_code_different_case_returns_409(admin_client):
    DiagnosticTestFactory(code="CBC")

    response = admin_client.post(
        TESTS_URL, {"code": "cbc", "name": "Complete Blood Count"}, format="json"
    )

    assert response.status_code == 409
    assert_error_shape(response, "TEST_CODE_ALREADY_EXISTS")


# --- Query counts (no N+1) ---


def test_centre_detail_query_count_is_constant(api_client, django_assert_max_num_queries):
    centre = CentreFactory()
    CentreTestFactory.create_batch(10, centre=centre)

    with django_assert_max_num_queries(2):  # centre + prefetched offerings (joined with test)
        response = api_client.get(centre_url(centre.id))

    assert len(response.json()["tests"]) == 10


def test_tests_list_query_count_is_constant(api_client):
    DiagnosticTestFactory()
    with CaptureQueriesContext(connection) as one_row:
        api_client.get(TESTS_URL)

    DiagnosticTestFactory.create_batch(15)
    with CaptureQueriesContext(connection) as many_rows:
        response = api_client.get(TESTS_URL)

    assert response.json()["count"] == 16
    assert len(many_rows) == len(one_row)


def test_centre_list_query_count_is_constant(api_client, django_assert_max_num_queries):
    for centre in CentreFactory.create_batch(10):
        CentreTestFactory.create_batch(3, centre=centre)

    with django_assert_max_num_queries(2):  # count + page
        response = api_client.get(CENTRES_URL)

    assert response.json()["count"] == 10
