import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings

from tests.support import STAFF_HEADERS, client
from tests.test_schedule import (
    FIELD,
    OWNER,
    configure_roles,
    create_job,
    schedule_payload,
)


@pytest.mark.parametrize("terminal_status", ["completed", "cancelled"])
def test_terminal_job_retires_scheduled_entries_atomically(
    isolated_settings: Settings, terminal_status: str
) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    entry = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(job["id"]),
    ).json()
    if terminal_status == "completed":
        active = client.post(
            f"/api/benson/v1/jobs/{job['id']}/transition",
            headers=STAFF_HEADERS,
            json={"status": "active"},
        )
        assert active.status_code == 200
        headers = STAFF_HEADERS
    else:
        headers = {"X-Dev-Staff-Email": OWNER}
    terminal = client.post(
        f"/api/benson/v1/jobs/{job['id']}/transition",
        headers=headers,
        json={
            "status": terminal_status,
            "note": f"Synthetic job {terminal_status}.",
        },
    )
    assert terminal.status_code == 200

    entries = client.get(
        "/api/benson/v1/schedule",
        headers={"X-Dev-Staff-Email": FIELD},
        params={
            "start": "2026-08-01T00:00:00Z",
            "end": "2026-08-31T00:00:00Z",
        },
    ).json()
    assert entries[0]["id"] == entry["id"]
    assert entries[0]["status"] == "cancelled"
    assert entries[0]["version"] == 2
    history = client.get(
        f"/api/benson/v1/schedule/{entry['id']}/history",
        headers=STAFF_HEADERS,
    )
    assert history.status_code == 200
    assert f"job moved to {terminal_status}" in history.json()[0]["note"]
    audit = client.get(
        f"/api/benson/v1/schedule/{entry['id']}/audit",
        headers=STAFF_HEADERS,
    )
    assert audit.status_code == 200
    payload = audit.json()[0]["payload"]
    assert payload["reason"] == "job_terminal"
    assert payload["history_id"] == history.json()[0]["id"]
    assert "note" not in json.dumps(payload)

    replacement_job = create_job()
    replacement = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(replacement_job["id"]),
    )
    assert replacement.status_code == 201


def test_job_completion_retires_overdue_and_clock_active_scheduled_entries(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    now = datetime.now(UTC)
    zone = ZoneInfo("America/Los_Angeles")
    intervals = (
        (now - timedelta(hours=4), now - timedelta(hours=3)),
        (now - timedelta(minutes=30), now + timedelta(minutes=30)),
    )
    entry_ids = []
    for starts_at, ends_at in intervals:
        entry = client.post(
            "/api/benson/v1/schedule",
            headers=STAFF_HEADERS,
            json=schedule_payload(
                job["id"],
                starts_at=starts_at.astimezone(zone).isoformat(),
                ends_at=ends_at.astimezone(zone).isoformat(),
            ),
        )
        assert entry.status_code == 201
        entry_ids.append(entry.json()["id"])
    active = client.post(
        f"/api/benson/v1/jobs/{job['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "active"},
    )
    assert active.status_code == 200
    completed = client.post(
        f"/api/benson/v1/jobs/{job['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "completed", "note": "Clock-state closeout."},
    )
    assert completed.status_code == 200
    entries = client.get(
        "/api/benson/v1/schedule",
        headers={"X-Dev-Staff-Email": FIELD},
        params={
            "start": (now - timedelta(days=1)).isoformat(),
            "end": (now + timedelta(days=1)).isoformat(),
        },
    ).json()
    retired = {entry["id"]: entry for entry in entries if entry["id"] in entry_ids}
    assert set(retired) == set(entry_ids)
    assert {entry["status"] for entry in retired.values()} == {"cancelled"}
    assert {entry["version"] for entry in retired.values()} == {2}


def test_in_progress_schedule_blocks_job_terminal_transition(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    entry = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(job["id"]),
    ).json()
    active = client.post(
        f"/api/benson/v1/jobs/{job['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "active"},
    )
    assert active.status_code == 200
    started = client.post(
        f"/api/benson/v1/schedule/{entry['id']}/transition",
        headers={"X-Dev-Staff-Email": FIELD},
        json={"expected_version": 1, "status": "in_progress"},
    )
    assert started.status_code == 200
    blocked = client.post(
        f"/api/benson/v1/jobs/{job['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "completed", "note": "Too early."},
    )
    assert blocked.status_code == 409
    assert "in-progress schedule entry" in blocked.json()["detail"]

    finished = client.post(
        f"/api/benson/v1/schedule/{entry['id']}/transition",
        headers={"X-Dev-Staff-Email": FIELD},
        json={
            "expected_version": 2,
            "status": "completed",
            "note": "Synthetic field completion.",
        },
    )
    assert finished.status_code == 200
    completed = client.post(
        f"/api/benson/v1/jobs/{job['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "completed", "note": "Closeout verified."},
    )
    assert completed.status_code == 200


def test_job_close_and_schedule_start_cannot_both_win(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    job = create_job()
    entry = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(job["id"]),
    ).json()
    active = client.post(
        f"/api/benson/v1/jobs/{job['id']}/transition",
        headers=STAFF_HEADERS,
        json={"status": "active"},
    )
    assert active.status_code == 200

    def close_job() -> int:
        return client.post(
            f"/api/benson/v1/jobs/{job['id']}/transition",
            headers=STAFF_HEADERS,
            json={"status": "completed", "note": "Concurrent closeout."},
        ).status_code

    def start_entry() -> int:
        return client.post(
            f"/api/benson/v1/schedule/{entry['id']}/transition",
            headers={"X-Dev-Staff-Email": FIELD},
            json={"expected_version": 1, "status": "in_progress"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        close_future = executor.submit(close_job)
        start_future = executor.submit(start_entry)
        outcomes = sorted((close_future.result(), start_future.result()))
    assert outcomes == [200, 409]
    jobs = client.get("/api/benson/v1/jobs", headers=STAFF_HEADERS).json()
    final_job = next(item for item in jobs if item["id"] == job["id"])
    entries = client.get(
        "/api/benson/v1/schedule",
        headers={"X-Dev-Staff-Email": FIELD},
        params={
            "start": "2026-08-01T00:00:00Z",
            "end": "2026-08-31T00:00:00Z",
        },
    ).json()
    final_entry = next(item for item in entries if item["id"] == entry["id"])
    assert (final_job["status"], final_entry["status"]) in {
        ("completed", "cancelled"),
        ("active", "in_progress"),
    }
