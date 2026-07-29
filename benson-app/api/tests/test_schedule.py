import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

from app.config import Settings

from tests.support import STAFF_HEADERS, client
from tests.test_jobs import accepted_estimate

FIELD = "field@bensonhomesolutions.com"
OTHER_FIELD = "other@bensonhomesolutions.com"
OWNER = "owner@bensonhomesolutions.com"
ACCOUNTING = "accounting@bensonhomesolutions.com"


def configure_roles(settings: Settings) -> None:
    settings.owner_emails = OWNER
    settings.office_emails = "office@bensonhomesolutions.com"
    settings.estimator_pm_emails = "pm@bensonhomesolutions.com"
    settings.field_emails = f"{FIELD},{OTHER_FIELD}"
    settings.accounting_emails = ACCOUNTING


def create_job() -> dict[str, Any]:
    estimate = accepted_estimate()
    response = client.post(
        f"/api/benson/v1/jobs/from-estimate/{estimate['id']}",
        headers=STAFF_HEADERS,
        json={},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def schedule_payload(
    job_id: str,
    *,
    assignee: str = FIELD,
    starts_at: str = "2026-08-03T09:00:00-07:00",
    ends_at: str = "2026-08-03T11:00:00-07:00",
) -> dict[str, object]:
    return {
        "job_id": job_id,
        "event_type": "work",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "timezone": "America/Los_Angeles",
        "assigned_to": assignee,
    }


def test_planner_creates_lists_and_audits_safe_schedule_projection(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    created = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(job["id"]),
    )
    assert created.status_code == 201, created.text
    entry = created.json()
    assert entry["status"] == "scheduled"
    assert entry["version"] == 1
    assert entry["starts_at"] == "2026-08-03T16:00:00Z"
    assert entry["timezone"] == "America/Los_Angeles"
    assert "contract_value_cents" not in entry
    assert "scope_snapshot" not in entry

    listed = client.get(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        params={
            "start": "2026-08-01T00:00:00Z",
            "end": "2026-08-31T00:00:00Z",
        },
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [entry["id"]]
    audit = client.get(
        f"/api/benson/v1/schedule/{entry['id']}/audit", headers=STAFF_HEADERS
    )
    assert audit.status_code == 200
    payload = json.dumps(audit.json())
    assert job["customer_name"] not in payload
    assert job["site_address"] not in payload
    assert "scope_snapshot" not in payload


def test_overlap_is_rejected_atomically_and_back_to_back_is_allowed(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    payload = schedule_payload(job["id"])
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: client.post(
                    "/api/benson/v1/schedule", headers=STAFF_HEADERS, json=payload
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [201, 409]

    adjacent = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(
            job["id"],
            starts_at="2026-08-03T11:00:00-07:00",
            ends_at="2026-08-03T12:00:00-07:00",
        ),
    )
    assert adjacent.status_code == 201


def test_cas_updates_validate_conflicts_and_active_assignees(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    entry = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(job["id"]),
    ).json()
    updated = client.patch(
        f"/api/benson/v1/schedule/{entry['id']}",
        headers=STAFF_HEADERS,
        json={
            "expected_version": 1,
            "event_type": "inspection",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    moved = client.patch(
        f"/api/benson/v1/schedule/{entry['id']}",
        headers=STAFF_HEADERS,
        json={
            "expected_version": 2,
            "starts_at": "2026-08-04T09:00:00-07:00",
            "ends_at": "2026-08-04T10:00:00-07:00",
        },
    )
    assert moved.status_code == 200
    assert moved.json()["version"] == 3
    stale = client.patch(
        f"/api/benson/v1/schedule/{entry['id']}",
        headers=STAFF_HEADERS,
        json={"expected_version": 1, "event_type": "delivery"},
    )
    assert stale.status_code == 409
    unauthorized_assignee = client.patch(
        f"/api/benson/v1/schedule/{entry['id']}",
        headers=STAFF_HEADERS,
        json={
            "expected_version": 3,
            "assigned_to": "outsider@example.com",
        },
    )
    assert unauthorized_assignee.status_code == 422
    reassigned = client.patch(
        f"/api/benson/v1/schedule/{entry['id']}",
        headers=STAFF_HEADERS,
        json={"expected_version": 3, "assigned_to": OWNER},
    )
    assert reassigned.status_code == 200
    audit = client.get(
        f"/api/benson/v1/schedule/{entry['id']}/audit", headers=STAFF_HEADERS
    ).json()
    assert audit[0]["payload"]["changes"]["assigned_to"] == {
        "from": FIELD,
        "to": OWNER,
    }
    assert audit[1]["payload"]["changes"]["starts_at"] == {
        "from": "2026-08-03T16:00:00+00:00",
        "to": "2026-08-04T16:00:00+00:00",
    }


def test_field_scope_and_transition_authorization(isolated_settings: Settings) -> None:
    configure_roles(isolated_settings)
    first_job = create_job()
    second_job = create_job()
    first = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(first_job["id"]),
    ).json()
    client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(
            second_job["id"],
            assignee=OTHER_FIELD,
            starts_at="2026-08-04T09:00:00-07:00",
            ends_at="2026-08-04T11:00:00-07:00",
        ),
    ).raise_for_status()
    field_headers = {"X-Dev-Staff-Email": FIELD}
    listed = client.get(
        "/api/benson/v1/schedule",
        headers=field_headers,
        params={
            "start": "2026-08-01T00:00:00Z",
            "end": "2026-08-31T00:00:00Z",
        },
    )
    assert [item["id"] for item in listed.json()] == [first["id"]]
    assert (
        client.get(
            "/api/benson/v1/schedule",
            headers={"X-Dev-Staff-Email": ACCOUNTING},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/benson/v1/schedule/{first['id']}",
            headers=field_headers,
            json={"expected_version": 1, "event_type": "inspection"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/benson/v1/schedule/{first['id']}/transition",
            headers={"X-Dev-Staff-Email": OTHER_FIELD},
            json={"expected_version": 1, "status": "in_progress"},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/benson/v1/schedule/{first['id']}/audit",
            headers={"X-Dev-Staff-Email": OTHER_FIELD},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/benson/v1/schedule/{first['id']}/transition",
            headers=STAFF_HEADERS,
            json={"expected_version": 1, "status": "in_progress"},
        ).status_code
        == 404
    )
    started = client.post(
        f"/api/benson/v1/schedule/{first['id']}/transition",
        headers=field_headers,
        json={"expected_version": 1, "status": "in_progress"},
    )
    assert started.status_code == 200
    completed = client.post(
        f"/api/benson/v1/schedule/{first['id']}/transition",
        headers=field_headers,
        json={
            "expected_version": 2,
            "status": "completed",
            "note": "Synthetic field completion.",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["version"] == 3
    history = client.get(
        f"/api/benson/v1/schedule/{first['id']}/history", headers=STAFF_HEADERS
    )
    assert history.status_code == 200
    assert history.json()[0]["note"] == "Synthetic field completion."
    assert (
        client.get(
            f"/api/benson/v1/schedule/{first['id']}/history",
            headers=field_headers,
        ).status_code
        == 403
    )
    audit = client.get(
        f"/api/benson/v1/schedule/{first['id']}/audit", headers=field_headers
    )
    assert "Synthetic field completion." not in audit.text
    assert "note" not in audit.text


def test_owner_can_deliver_when_exactly_assigned_and_completion_frees_time(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    entry = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(job["id"], assignee=OWNER),
    ).json()
    owner_headers = {"X-Dev-Staff-Email": OWNER}
    started = client.post(
        f"/api/benson/v1/schedule/{entry['id']}/transition",
        headers=owner_headers,
        json={"expected_version": 1, "status": "in_progress"},
    )
    assert started.status_code == 200
    assert (
        client.post(
            f"/api/benson/v1/schedule/{entry['id']}/transition",
            headers=owner_headers,
            json={"expected_version": 2, "status": "completed"},
        ).status_code
        == 422
    )
    completed = client.post(
        f"/api/benson/v1/schedule/{entry['id']}/transition",
        headers=owner_headers,
        json={
            "expected_version": 2,
            "status": "completed",
            "note": "Synthetic owner completion.",
        },
    )
    assert completed.status_code == 200
    replacement = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(job["id"], assignee=OWNER),
    )
    assert replacement.status_code == 201


def test_same_version_concurrent_transition_has_one_winner(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    entry = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(create_job()["id"]),
    ).json()
    field_headers = {"X-Dev-Staff-Email": FIELD}
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: client.post(
                    f"/api/benson/v1/schedule/{entry['id']}/transition",
                    headers=field_headers,
                    json={"expected_version": 1, "status": "in_progress"},
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 409]


def test_schedule_ids_and_all_unapproved_viewers_fail_closed(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    assert (
        client.get(
            "/api/benson/v1/schedule",
            headers={"X-Dev-Staff-Email": ACCOUNTING},
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/benson/v1/schedule",
            headers={"X-Dev-Staff-Email": "unknown@bensonhomesolutions.com"},
        ).status_code
        == 403
    )
    assert client.get("/api/benson/v1/schedule").status_code == 503
    assert (
        client.post(
            "/api/benson/v1/schedule/not-a-uuid/transition",
            headers=STAFF_HEADERS,
            json={"expected_version": 1, "status": "cancelled", "note": "x"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/benson/v1/schedule/00000000-0000-0000-0000-000000000000/history",
            headers=STAFF_HEADERS,
        ).status_code
        == 404
    )


def test_planner_cancellation_requires_note_and_stale_versions_conflict(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    entry = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(create_job()["id"]),
    ).json()
    missing_note = client.post(
        f"/api/benson/v1/schedule/{entry['id']}/transition",
        headers=STAFF_HEADERS,
        json={"expected_version": 1, "status": "cancelled"},
    )
    assert missing_note.status_code == 422
    cancelled = client.post(
        f"/api/benson/v1/schedule/{entry['id']}/transition",
        headers=STAFF_HEADERS,
        json={
            "expected_version": 1,
            "status": "cancelled",
            "note": "Synthetic planner cancellation.",
        },
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["version"] == 2
    stale = client.post(
        f"/api/benson/v1/schedule/{entry['id']}/transition",
        headers=STAFF_HEADERS,
        json={
            "expected_version": 1,
            "status": "cancelled",
            "note": "Stale synthetic request.",
        },
    )
    assert stale.status_code == 409


def test_timezone_dst_extra_fields_duration_and_window_are_rejected(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    invalid_payloads = [
        schedule_payload(
            job["id"],
            starts_at="2026-08-03T09:00:00Z",
            ends_at="2026-08-03T10:00:00Z",
        ),
        schedule_payload(
            job["id"],
            starts_at="2026-03-08T02:30:00-08:00",
            ends_at="2026-03-08T03:30:00-07:00",
        ),
        schedule_payload(
            job["id"],
            starts_at="2026-08-03T09:00:00-07:00",
            ends_at="2026-08-04T10:00:00-07:00",
        ),
    ]
    invalid_payloads.append({**schedule_payload(job["id"]), "private": "nope"})
    for payload in invalid_payloads:
        assert (
            client.post(
                "/api/benson/v1/schedule", headers=STAFF_HEADERS, json=payload
            ).status_code
            == 422
        )
    too_wide = client.get(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        params={
            "start": "2026-01-01T00:00:00Z",
            "end": "2027-01-01T00:00:00Z",
        },
    )
    assert too_wide.status_code == 422


def test_on_hold_job_cannot_be_scheduled(isolated_settings: Settings) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    held = client.post(
        f"/api/benson/v1/jobs/{job['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "on_hold", "note": "Synthetic schedule hold."},
    )
    assert held.status_code == 200
    response = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(job["id"]),
    )
    assert response.status_code == 409
