import json

from app.config import Settings
from app.storage import operations_store

from tests.support import STAFF_HEADERS, canonical_lead, client, post_signed_lead


def customer_payload() -> dict[str, str]:
    return {
        "name": "Harney County Property Owner",
        "company": "High Desert Rentals",
        "phone": "541-555-0199",
        "email": "owner@example.com",
        "billing_address": "100 Main Street",
        "service_address": "200 Ranch Road",
        "city": "Burns",
        "state": "OR",
        "zip_code": "97720",
        "notes": "Prefers email for routine scheduling.",
    }


def test_staff_can_create_list_search_and_update_customers(
    isolated_settings: Settings,
) -> None:
    created = client.post(
        "/api/benson/v1/customers", headers=STAFF_HEADERS, json=customer_payload()
    )
    assert created.status_code == 201
    assert created.json()["status"] == "active"

    listed = client.get(
        "/api/benson/v1/customers?query=High%20Desert", headers=STAFF_HEADERS
    )
    assert [item["id"] for item in listed.json()] == [created.json()["id"]]

    updated = client.patch(
        f"/api/benson/v1/customers/{created.json()['id']}",
        headers=STAFF_HEADERS,
        json={
            "phone": "541-555-0123",
            "email": None,
            "notes": "Updated after verification.",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "541-555-0123"
    assert updated.json()["email"] is None

    store = operations_store(isolated_settings.resolved_database_url())
    with store.engine.connect() as db:
        events = db.exec_driver_sql(
            "SELECT event, actor, payload FROM audit_events "
            "WHERE subject_type = 'customer' ORDER BY occurred_at"
        ).mappings()
        recorded = list(events)
    assert [item["event"] for item in recorded] == [
        "customer.created",
        "customer.updated",
    ]
    assert recorded[-1]["actor"] == "office@bensonhomesolutions.com"
    delta = json.loads(recorded[-1]["payload"])["delta"]
    assert delta["phone"] == {"from": "[redacted]", "to": "[redacted]"}
    assert "541-555-0123" not in recorded[-1]["payload"]
    history = client.get(
        f"/api/benson/v1/customers/{created.json()['id']}/audit",
        headers=STAFF_HEADERS,
    )
    assert history.status_code == 200
    assert history.json()[0]["event"] == "customer.updated"
    assert history.json()[0]["payload"]["delta"]["phone"]["to"] == "[redacted]"


def test_staff_can_convert_a_lead_only_once(isolated_settings: Settings) -> None:
    lead = post_signed_lead(
        isolated_settings,
        canonical_lead(name="Converted Homeowner", city="Fields"),
        key="customer-conversion",
    ).json()
    client.patch(
        f"/api/benson/v1/leads/{lead['lead_id']}",
        headers=STAFF_HEADERS,
        json={"status": "contacted"},
    )
    client.patch(
        f"/api/benson/v1/leads/{lead['lead_id']}",
        headers=STAFF_HEADERS,
        json={"status": "qualified"},
    )

    converted = client.post(
        f"/api/benson/v1/customers/from-lead/{lead['lead_id']}",
        headers=STAFF_HEADERS,
    )
    assert converted.status_code == 201
    assert converted.json()["name"] == "Converted Homeowner"
    assert converted.json()["source_lead_id"] == lead["lead_id"]
    assert (
        client.post(
            f"/api/benson/v1/customers/from-lead/{lead['lead_id']}",
            headers=STAFF_HEADERS,
        ).status_code
        == 409
    )


def test_unqualified_lead_cannot_become_customer(
    isolated_settings: Settings,
) -> None:
    lead = post_signed_lead(
        isolated_settings,
        canonical_lead(name="Unqualified Lead"),
        key="unqualified-customer",
    ).json()
    response = client.post(
        f"/api/benson/v1/customers/from-lead/{lead['lead_id']}",
        headers=STAFF_HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Only qualified non-spam leads can become customers"
    )


def test_customer_access_is_fail_closed_and_archive_is_owner_only(
    isolated_settings: Settings,
) -> None:
    assert client.get("/api/benson/v1/customers").status_code == 503
    created = client.post(
        "/api/benson/v1/customers", headers=STAFF_HEADERS, json=customer_payload()
    ).json()

    isolated_settings.owner_emails = "owner@bensonhomesolutions.com"
    isolated_settings.office_emails = "office@bensonhomesolutions.com"
    assert (
        client.delete(
            f"/api/benson/v1/customers/{created['id']}", headers=STAFF_HEADERS
        ).status_code
        == 403
    )
    archived = client.delete(
        f"/api/benson/v1/customers/{created['id']}",
        headers={"X-Dev-Staff-Email": "owner@bensonhomesolutions.com"},
    )
    assert archived.status_code == 204
    assert (
        client.patch(
            f"/api/benson/v1/customers/{created['id']}",
            headers=STAFF_HEADERS,
            json={"name": "Must not change"},
        ).status_code
        == 404
    )
    assert client.get("/api/benson/v1/customers", headers=STAFF_HEADERS).json() == []
    all_customers = client.get(
        "/api/benson/v1/customers?include_archived=true", headers=STAFF_HEADERS
    ).json()
    assert all_customers[0]["status"] == "archived"
