import json
from typing import cast

from app.config import Settings
from app.storage import operations_store

from tests.support import STAFF_HEADERS, client


def create_customer() -> dict[str, object]:
    response = client.post(
        "/api/benson/v1/customers",
        headers=STAFF_HEADERS,
        json={
            "name": "Estimate Customer",
            "phone": "541-555-0188",
            "email": "estimate@example.com",
            "city": "Burns",
            "state": "OR",
            "zip_code": "97720",
        },
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def estimate_payload(customer_id: str) -> dict[str, object]:
    return {
        "customer_id": customer_id,
        "title": "Replace south-facing windows",
        "scope_notes": "Final dimensions require field verification.",
        "valid_until": "2026-08-31",
        "lines": [
            {
                "description": "High-desert rated window",
                "quantity": "2.50",
                "unit": "each",
                "unit_price_cents": 125_000,
            },
            {
                "description": "Documented installation",
                "quantity": "8.00",
                "unit": "hour",
                "unit_price_cents": 8_500,
            },
        ],
    }


def test_staff_create_edit_and_list_server_totaled_estimate(
    isolated_settings: Settings,
) -> None:
    customer = create_customer()
    created = client.post(
        "/api/benson/v1/estimates",
        headers=STAFF_HEADERS,
        json=estimate_payload(str(customer["id"])),
    )
    assert created.status_code == 201
    assert created.json()["status"] == "draft"
    assert created.json()["subtotal_cents"] == 380_500
    assert created.json()["total_cents"] == 380_500
    assert created.json()["version"] == 1

    updated = client.patch(
        f"/api/benson/v1/estimates/{created.json()['id']}",
        headers=STAFF_HEADERS,
        json={
            "title": "Updated window replacement",
            "lines": [
                {
                    "description": "Window package",
                    "quantity": "3",
                    "unit": "each",
                    "unit_price_cents": 100_001,
                }
            ],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["total_cents"] == 300_003
    assert updated.json()["version"] == 2
    listed = client.get("/api/benson/v1/estimates", headers=STAFF_HEADERS)
    assert [item["number"] for item in listed.json()] == [created.json()["number"]]

    store = operations_store(isolated_settings.resolved_database_url())
    with store.engine.connect() as db:
        events = list(
            db.exec_driver_sql(
                "SELECT event, payload FROM audit_events "
                "WHERE subject_type = 'estimate' ORDER BY occurred_at"
            ).mappings()
        )
    assert [event["event"] for event in events] == [
        "estimate.created",
        "estimate.updated",
    ]
    assert "scope_notes" not in json.dumps([dict(event) for event in events])
    history = client.get(
        f"/api/benson/v1/estimates/{created.json()['id']}/audit",
        headers=STAFF_HEADERS,
    )
    assert history.status_code == 200
    assert history.json()[0]["event"] == "estimate.updated"


def test_estimate_transitions_require_real_delivery_confirmation(
    isolated_settings: Settings,
) -> None:
    customer = create_customer()
    estimate = client.post(
        "/api/benson/v1/estimates",
        headers=STAFF_HEADERS,
        json=estimate_payload(str(customer["id"])),
    ).json()
    ready = client.post(
        f"/api/benson/v1/estimates/{estimate['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "ready"},
    )
    assert ready.status_code == 200
    assert (
        client.post(
            f"/api/benson/v1/estimates/{estimate['id']}/transition",
            headers=STAFF_HEADERS,
            json={"status": "sent"},
        ).status_code
        == 409
    )
    sent = client.post(
        f"/api/benson/v1/estimates/{estimate['id']}/transition",
        headers=STAFF_HEADERS,
        json={
            "status": "sent",
            "external_delivery_confirmed": True,
            "note": "Hand-delivered synthetic UAT copy.",
        },
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert (
        client.post(
            f"/api/benson/v1/estimates/{estimate['id']}/transition",
            headers=STAFF_HEADERS,
            json={"status": "accepted"},
        ).status_code
        == 422
    )
    accepted = client.post(
        f"/api/benson/v1/estimates/{estimate['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "accepted", "note": "Synthetic customer acceptance."},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    with operations_store(
        isolated_settings.resolved_database_url()
    ).engine.connect() as db:
        audit_payloads = " ".join(
            row[0]
            for row in db.exec_driver_sql(
                "SELECT payload FROM audit_events WHERE subject_type = 'estimate'"
            )
        )
    assert "Synthetic customer acceptance" not in audit_payloads
    assert (
        client.patch(
            f"/api/benson/v1/estimates/{estimate['id']}",
            headers=STAFF_HEADERS,
            json={"title": "Must not change"},
        ).status_code
        == 404
    )


def test_estimate_workflow_is_fail_closed_and_void_is_owner_only(
    isolated_settings: Settings,
) -> None:
    assert client.get("/api/benson/v1/estimates").status_code == 503
    customer = create_customer()
    estimate = client.post(
        "/api/benson/v1/estimates",
        headers=STAFF_HEADERS,
        json=estimate_payload(str(customer["id"])),
    ).json()
    isolated_settings.owner_emails = "owner@bensonhomesolutions.com"
    isolated_settings.office_emails = "office@bensonhomesolutions.com"
    denied = client.post(
        f"/api/benson/v1/estimates/{estimate['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "void"},
    )
    assert denied.status_code == 403
    voided = client.post(
        f"/api/benson/v1/estimates/{estimate['id']}/transition",
        headers={"X-Dev-Staff-Email": "owner@bensonhomesolutions.com"},
        json={"status": "void", "note": "Duplicate synthetic estimate."},
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "void"


def test_archived_customer_estimate_cannot_advance(
    isolated_settings: Settings,
) -> None:
    customer = create_customer()
    estimate = client.post(
        "/api/benson/v1/estimates",
        headers=STAFF_HEADERS,
        json=estimate_payload(str(customer["id"])),
    ).json()
    operations_store(isolated_settings.resolved_database_url()).archive_customer(
        str(customer["id"]), actor="owner@bensonhomesolutions.com"
    )
    response = client.post(
        f"/api/benson/v1/estimates/{estimate['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "ready"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == ("An archived customer estimate cannot advance")
