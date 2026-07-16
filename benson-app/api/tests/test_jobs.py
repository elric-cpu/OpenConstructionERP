import json
from typing import cast

from app.config import Settings
from app.storage import operations_store

from tests.support import STAFF_HEADERS, client


def accepted_estimate() -> dict[str, object]:
    customer = client.post(
        "/api/benson/v1/customers",
        headers=STAFF_HEADERS,
        json={
            "name": "Job Customer",
            "phone": "541-555-0189",
            "service_address": "20 Main Street",
            "city": "Burns",
            "state": "OR",
            "zip_code": "97720",
        },
    ).json()
    estimate = client.post(
        "/api/benson/v1/estimates",
        headers=STAFF_HEADERS,
        json={
            "customer_id": customer["id"],
            "title": "Documented window installation",
            "scope_notes": "Replace two south-facing windows.",
            "valid_until": "2026-09-30",
            "lines": [
                {
                    "description": "Window package",
                    "quantity": "2",
                    "unit": "each",
                    "unit_price_cents": 150_000,
                }
            ],
        },
    ).json()
    for payload in (
        {"status": "ready"},
        {"status": "sent", "external_delivery_confirmed": True},
        {"status": "accepted", "note": "Synthetic acceptance recorded."},
    ):
        response = client.post(
            f"/api/benson/v1/estimates/{estimate['id']}/transition",
            headers=STAFF_HEADERS,
            json=payload,
        )
        assert response.status_code == 200
    return cast(dict[str, object], response.json())


def test_accepted_estimate_becomes_one_audited_job(
    isolated_settings: Settings,
) -> None:
    estimate = accepted_estimate()
    created = client.post(
        f"/api/benson/v1/jobs/from-estimate/{estimate['id']}",
        headers=STAFF_HEADERS,
        json={
            "target_start": "2026-08-03",
            "target_completion": "2026-08-07",
        },
    )
    assert created.status_code == 201
    job = created.json()
    assert job["status"] == "planned"
    assert job["contract_value_cents"] == 300_000
    assert job["scope_snapshot"] == "Replace two south-facing windows."
    assert job["site_address"] == "20 Main Street"
    assert (
        client.post(
            f"/api/benson/v1/jobs/from-estimate/{estimate['id']}",
            headers=STAFF_HEADERS,
            json={},
        ).status_code
        == 409
    )

    updated = client.patch(
        f"/api/benson/v1/jobs/{job['id']}",
        headers=STAFF_HEADERS,
        json={"title": "Revised installation plan", "assigned_to": None},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Revised installation plan"
    history = client.get(
        f"/api/benson/v1/jobs/{job['id']}/audit", headers=STAFF_HEADERS
    )
    assert history.status_code == 200
    assert [event["event"] for event in reversed(history.json())] == [
        "job.created_from_estimate",
        "job.updated",
    ]
    store = operations_store(isolated_settings.resolved_database_url())
    with store.engine.connect() as db:
        payloads = list(
            db.exec_driver_sql(
                "SELECT payload FROM audit_events WHERE subject_type = 'job'"
            ).scalars()
        )
    assert "scope_snapshot" not in json.dumps(payloads)


def test_job_transitions_require_notes_and_owner_cancellation(
    isolated_settings: Settings,
) -> None:
    isolated_settings.owner_emails = "owner@bensonhomesolutions.com"
    isolated_settings.office_emails = "office@bensonhomesolutions.com"
    job = client.post(
        f"/api/benson/v1/jobs/from-estimate/{accepted_estimate()['id']}",
        headers=STAFF_HEADERS,
        json={},
    ).json()
    assert (
        client.post(
            f"/api/benson/v1/jobs/{job['id']}/transition",
            headers=STAFF_HEADERS,
            json={"status": "on_hold"},
        ).status_code
        == 422
    )
    active = client.post(
        f"/api/benson/v1/jobs/{job['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "active"},
    )
    assert active.status_code == 200
    completed = client.post(
        f"/api/benson/v1/jobs/{job['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "completed", "note": "Synthetic closeout verified."},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    history = client.get(
        f"/api/benson/v1/jobs/{job['id']}/audit", headers=STAFF_HEADERS
    ).json()
    assert history[0]["payload"]["note"] == "Synthetic closeout verified."
    assert (
        client.patch(
            f"/api/benson/v1/jobs/{job['id']}",
            headers=STAFF_HEADERS,
            json={"title": "Too late"},
        ).status_code
        == 404
    )

    cancel_job = client.post(
        f"/api/benson/v1/jobs/from-estimate/{accepted_estimate()['id']}",
        headers=STAFF_HEADERS,
        json={},
    ).json()
    denied = client.post(
        f"/api/benson/v1/jobs/{cancel_job['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "cancelled", "note": "Synthetic cancellation."},
    )
    assert denied.status_code == 403
    approved = client.post(
        f"/api/benson/v1/jobs/{cancel_job['id']}/transition",
        headers={"X-Dev-Staff-Email": "owner@bensonhomesolutions.com"},
        json={"status": "cancelled", "note": "Owner approved synthetic test."},
    )
    assert approved.status_code == 200


def test_job_rejects_nonaccepted_estimate_and_invalid_dates() -> None:
    customer = client.post(
        "/api/benson/v1/customers",
        headers=STAFF_HEADERS,
        json={"name": "Draft Customer", "phone": "541-555-0190"},
    ).json()
    estimate = client.post(
        "/api/benson/v1/estimates",
        headers=STAFF_HEADERS,
        json={
            "customer_id": customer["id"],
            "title": "Draft only",
            "valid_until": "2026-09-30",
            "lines": [
                {
                    "description": "Labor",
                    "quantity": "1",
                    "unit": "hour",
                    "unit_price_cents": 10_000,
                }
            ],
        },
    ).json()
    assert (
        client.post(
            f"/api/benson/v1/jobs/from-estimate/{estimate['id']}",
            headers=STAFF_HEADERS,
            json={},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/benson/v1/jobs/from-estimate/{estimate['id']}",
            headers=STAFF_HEADERS,
            json={
                "target_start": "2026-08-10",
                "target_completion": "2026-08-01",
            },
        ).status_code
        == 422
    )


def test_job_partial_date_updates_and_assignment_scope(
    isolated_settings: Settings,
) -> None:
    isolated_settings.owner_emails = "owner@bensonhomesolutions.com"
    isolated_settings.office_emails = "office@bensonhomesolutions.com"
    isolated_settings.field_emails = (
        "field@bensonhomesolutions.com,other@bensonhomesolutions.com"
    )
    estimate = accepted_estimate()
    created = client.post(
        f"/api/benson/v1/jobs/from-estimate/{estimate['id']}",
        headers=STAFF_HEADERS,
        json={
            "target_completion": "2026-08-10",
            "assigned_to": "field@bensonhomesolutions.com",
        },
    )
    assert created.status_code == 201
    job = created.json()
    changed = client.patch(
        f"/api/benson/v1/jobs/{job['id']}",
        headers=STAFF_HEADERS,
        json={"target_start": "2026-08-01"},
    )
    assert changed.status_code == 200
    assert changed.json()["target_start"] == "2026-08-01"
    rejected = client.patch(
        f"/api/benson/v1/jobs/{job['id']}",
        headers=STAFF_HEADERS,
        json={"assigned_to": "external@example.com"},
    )
    assert rejected.status_code == 422

    field_headers = {"X-Dev-Staff-Email": "field@bensonhomesolutions.com"}
    other_headers = {"X-Dev-Staff-Email": "other@bensonhomesolutions.com"}
    assert [
        item["id"]
        for item in client.get("/api/benson/v1/jobs", headers=field_headers).json()
    ] == [job["id"]]
    assert client.get("/api/benson/v1/jobs", headers=other_headers).json() == []
    assert (
        client.post(
            f"/api/benson/v1/jobs/{job['id']}/transition",
            headers=other_headers,
            json={"status": "active"},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/benson/v1/jobs/{job['id']}/audit", headers=other_headers
        ).status_code
        == 404
    )
    started = client.post(
        f"/api/benson/v1/jobs/{job['id']}/transition",
        headers=field_headers,
        json={"status": "active"},
    )
    assert started.status_code == 200


def test_accounting_can_read_but_cannot_mutate_jobs(
    isolated_settings: Settings,
) -> None:
    job = client.post(
        f"/api/benson/v1/jobs/from-estimate/{accepted_estimate()['id']}",
        headers=STAFF_HEADERS,
        json={},
    ).json()
    isolated_settings.accounting_emails = "books@bensonhomesolutions.com"
    accounting = {"X-Dev-Staff-Email": "books@bensonhomesolutions.com"}
    assert client.get("/api/benson/v1/jobs", headers=accounting).status_code == 200
    assert (
        client.patch(
            f"/api/benson/v1/jobs/{job['id']}",
            headers=accounting,
            json={"title": "Unauthorized"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/benson/v1/jobs/{job['id']}/transition",
            headers=accounting,
            json={"status": "active"},
        ).status_code
        == 403
    )


def test_job_routes_fail_closed_for_unauthenticated_users() -> None:
    assert client.get("/api/benson/v1/jobs").status_code == 503
