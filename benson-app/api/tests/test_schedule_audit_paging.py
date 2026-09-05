import json
from datetime import UTC, datetime

from app.config import Settings
from app.storage import operations_store
from app.storage_schema import audit_events

from tests.support import STAFF_HEADERS, client
from tests.test_schedule import FIELD, configure_roles, create_job, schedule_payload


def test_schedule_audit_is_bounded_deterministic_and_pageable(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    entry = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(create_job()["id"]),
    ).json()
    occurred_at = datetime(2030, 1, 1, tzinfo=UTC)
    event_ids = [f"00000000-0000-0000-0000-{index:012x}" for index in range(1, 106)]
    store = operations_store(isolated_settings.resolved_database_url())
    with store.engine.begin() as db:
        db.execute(
            audit_events.insert(),
            [
                {
                    "id": event_id,
                    "event": "schedule.synthetic_page_test",
                    "actor": "office@bensonhomesolutions.com",
                    "subject_type": "schedule_entry",
                    "subject_id": entry["id"],
                    "payload": json.dumps({"sequence": index}),
                    "occurred_at": occurred_at,
                }
                for index, event_id in enumerate(event_ids, start=1)
            ],
        )

    url = f"/api/benson/v1/schedule/{entry['id']}/audit"
    first_page = client.get(
        url,
        headers={"X-Dev-Staff-Email": FIELD},
    )
    assert first_page.status_code == 200
    assert len(first_page.json()) == 100
    assert [event["id"] for event in first_page.json()[:3]] == list(
        reversed(event_ids[-3:])
    )
    second_page = client.get(
        url,
        headers={"X-Dev-Staff-Email": FIELD},
        params={"limit": 3, "offset": 100},
    )
    assert second_page.status_code == 200
    assert [event["id"] for event in second_page.json()] == list(
        reversed(event_ids[:5])
    )[:3]


def test_schedule_audit_rejects_out_of_bound_paging(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    entry = client.post(
        "/api/benson/v1/schedule",
        headers=STAFF_HEADERS,
        json=schedule_payload(create_job()["id"]),
    ).json()
    url = f"/api/benson/v1/schedule/{entry['id']}/audit"
    for params in (
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"offset": 10_001},
    ):
        response = client.get(url, headers=STAFF_HEADERS, params=params)
        assert response.status_code == 422
