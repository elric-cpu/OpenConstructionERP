from io import BytesIO
from typing import Any, cast

from PIL import Image

from app.config import Settings
from tests.support import STAFF_HEADERS, client
from tests.test_jobs import accepted_estimate

OWNER = "owner@bensonhomesolutions.com"
ACCOUNTING = "accounting@bensonhomesolutions.com"


def configure_roles(settings: Settings) -> None:
    settings.owner_emails = OWNER
    settings.office_emails = "office@bensonhomesolutions.com"
    settings.accounting_emails = ACCOUNTING


def create_job() -> dict[str, Any]:
    estimate = accepted_estimate()
    response = client.post(
        f"/api/benson/v1/jobs/from-estimate/{estimate['id']}",
        headers=STAFF_HEADERS,
        json={},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def order_payload(job_id: str, *, price: int = 125_000) -> dict[str, object]:
    return {
        "job_id": job_id,
        "title": "Repair concealed sill damage",
        "schedule_impact_days": 2,
        "internal_notes": "Synthetic UAT change.",
        "customer_explanation": "Replace concealed damaged framing before installation.",
        "lines": [
            {
                "description": "Framing repair",
                "quantity": "2.5",
                "unit": "hour",
                "unit_price_cents": price,
            }
        ],
    }


def create_order(job_id: str) -> dict[str, Any]:
    response = client.post(
        "/api/benson/v1/change-orders",
        headers=STAFF_HEADERS,
        json=order_payload(job_id),
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def transition(
    order: dict[str, Any], target: str, headers: dict[str, str] = STAFF_HEADERS
) -> dict[str, Any]:
    response = client.post(
        f"/api/benson/v1/change-orders/{order['id']}/transition",
        headers=headers,
        json={
            "expected_version": order["version"],
            "status": target,
            "note": "Synthetic decision evidence." if target != "submitted" else "",
        },
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def test_approval_atomically_updates_contract_and_billing_eligibility(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    original_contract = job["contract_value_cents"]
    order = create_order(job["id"])
    assert order["subtotal_cents"] == 312_500
    assert order["estimate_id"] == job["estimate_id"]
    assert order["customer_id"] == job["customer_id"]

    before_approval = client.get("/api/benson/v1/jobs", headers=STAFF_HEADERS).json()[0]
    assert before_approval["billing_eligible_cents"] == original_contract
    submitted = transition(order, "submitted")
    denied = client.post(
        f"/api/benson/v1/change-orders/{order['id']}/transition",
        headers=STAFF_HEADERS,
        json={
            "expected_version": submitted["version"],
            "status": "approved",
            "note": "Office cannot approve.",
        },
    )
    assert denied.status_code == 403
    approved = transition(submitted, "approved", {"X-Dev-Staff-Email": OWNER})
    assert approved["status"] == "approved"
    job_after = client.get("/api/benson/v1/jobs", headers=STAFF_HEADERS).json()[0]
    assert job_after["contract_value_cents"] == original_contract + 312_500
    assert job_after["approved_change_order_cents"] == 312_500
    assert job_after["billing_eligible_cents"] == original_contract + 312_500
    job_audit = client.get(
        f"/api/benson/v1/jobs/{job['id']}/audit", headers=STAFF_HEADERS
    ).json()
    assert job_audit[0]["event"] == "job.change_order_approved"


def test_submitted_revision_is_immutable_and_stale_writes_conflict(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    order = create_order(create_job()["id"])
    updated = client.patch(
        f"/api/benson/v1/change-orders/{order['id']}",
        headers=STAFF_HEADERS,
        json={"expected_version": 1, "schedule_impact_days": 3},
    )
    assert updated.status_code == 200
    stale = client.patch(
        f"/api/benson/v1/change-orders/{order['id']}",
        headers=STAFF_HEADERS,
        json={"expected_version": 1, "schedule_impact_days": 4},
    )
    assert stale.status_code == 409
    submitted = transition(updated.json(), "submitted")
    immutable = client.patch(
        f"/api/benson/v1/change-orders/{order['id']}",
        headers=STAFF_HEADERS,
        json={"expected_version": submitted["version"], "schedule_impact_days": 4},
    )
    assert immutable.status_code == 409
    assert (
        client.get(
            f"/api/benson/v1/change-orders/{order['id']}",
            headers={"X-Dev-Staff-Email": ACCOUNTING},
        ).status_code
        == 403
    )


def test_approved_correction_uses_linked_revision_and_contract_delta(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    original = job["contract_value_cents"]
    approved = transition(
        transition(create_order(job["id"]), "submitted"),
        "approved",
        {"X-Dev-Staff-Email": OWNER},
    )
    revision_response = client.post(
        f"/api/benson/v1/change-orders/{approved['id']}/revisions",
        headers=STAFF_HEADERS,
        json={"expected_version": approved["version"], "reason": "Correct quantity."},
    )
    assert revision_response.status_code == 201
    revision = revision_response.json()
    assert revision["previous_revision_id"] == approved["id"]
    assert revision["revision"] == 2
    changed = client.patch(
        f"/api/benson/v1/change-orders/{revision['id']}",
        headers=STAFF_HEADERS,
        json={
            "expected_version": 1,
            "lines": order_payload(job["id"], price=100_000)["lines"],
        },
    ).json()
    corrected = transition(
        transition(changed, "submitted"),
        "approved",
        {"X-Dev-Staff-Email": OWNER},
    )
    assert corrected["subtotal_cents"] == 250_000
    current_job = client.get("/api/benson/v1/jobs", headers=STAFF_HEADERS).json()[0]
    assert current_job["contract_value_cents"] == original + 250_000
    assert current_job["approved_change_order_cents"] == 250_000


def test_private_evidence_is_sanitized_and_locked_after_submission(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    order = create_order(create_job()["id"])
    source = BytesIO()
    image = Image.new("RGB", (20, 20), "blue")
    exif = Image.Exif()
    exif[0x010E] = "private evidence note"
    image.save(source, format="JPEG", exif=exif)
    uploaded = client.post(
        f"/api/benson/v1/change-orders/{order['id']}/evidence",
        headers=STAFF_HEADERS,
        files={"evidence": ("damage.jpg", source.getvalue(), "image/jpeg")},
    )
    assert uploaded.status_code == 201, uploaded.text
    evidence = uploaded.json()
    assert "storage_key" not in evidence
    download = client.get(
        f"/api/benson/v1/change-orders/{order['id']}/evidence/{evidence['id']}/download",
        headers=STAFF_HEADERS,
    )
    assert download.status_code == 200
    with Image.open(BytesIO(download.content)) as sanitized:
        assert not sanitized.getexif()
    submitted = transition(order, "submitted")
    locked = client.post(
        f"/api/benson/v1/change-orders/{submitted['id']}/evidence",
        headers=STAFF_HEADERS,
        files={"evidence": ("more.jpg", source.getvalue(), "image/jpeg")},
    )
    assert locked.status_code == 409


def test_void_and_reject_do_not_change_job_totals(isolated_settings: Settings) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    order = create_order(job["id"])
    rejected = transition(
        transition(order, "submitted"),
        "rejected",
        {"X-Dev-Staff-Email": OWNER},
    )
    assert rejected["status"] == "rejected"
    unchanged = client.get("/api/benson/v1/jobs", headers=STAFF_HEADERS).json()[0]
    assert unchanged["contract_value_cents"] == job["contract_value_cents"]
    assert unchanged["approved_change_order_cents"] == 0
    assert unchanged["billing_eligible_cents"] == job["contract_value_cents"]


def test_change_order_access_is_fail_closed_and_missing_ids_are_not_found(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    assert client.get("/api/benson/v1/change-orders").status_code == 503
    assert (
        client.get(
            "/api/benson/v1/change-orders/00000000-0000-0000-0000-000000000000",
            headers=STAFF_HEADERS,
        ).status_code
        == 404
    )
