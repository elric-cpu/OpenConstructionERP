from io import BytesIO
from typing import Any, cast

from PIL import Image

from app.config import Settings
from tests.support import STAFF_HEADERS, client
from tests.test_jobs import accepted_estimate

FIELD = "field@bensonhomesolutions.com"
OTHER_FIELD = "other@bensonhomesolutions.com"
OWNER = "owner@bensonhomesolutions.com"


def configure_roles(settings: Settings) -> None:
    settings.owner_emails = OWNER
    settings.office_emails = "office@bensonhomesolutions.com"
    settings.field_emails = f"{FIELD},{OTHER_FIELD}"


def assigned_job(assignee: str = FIELD) -> dict[str, Any]:
    estimate = accepted_estimate()
    response = client.post(
        f"/api/benson/v1/jobs/from-estimate/{estimate['id']}",
        headers=STAFF_HEADERS,
        json={"assigned_to": assignee},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def report_payload(job_id: str) -> dict[str, object]:
    return {
        "job_id": job_id,
        "service_date": "2026-08-03",
        "workforce_total": 3,
        "workforce_hours": "24 crew-hours (not certified payroll)",
        "weather": "Clear, 72 F",
        "completed_work": "Installed the west elevation windows.",
        "materials": "Six windows and flashing tape",
        "equipment": "Two ladders",
        "delays": "",
        "issues": "One sill required repair.",
        "safety_observations": ["Ladder tie-offs were in place."],
    }


def create_report(job_id: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    response = client.post(
        "/api/benson/v1/field-records",
        headers=headers or {"X-Dev-Staff-Email": FIELD},
        json=report_payload(job_id),
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_field_staff_are_scoped_to_explicit_job_assignment(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    own_job = assigned_job()
    other_job = assigned_job(OTHER_FIELD)
    report = create_report(own_job["id"])

    hidden = client.post(
        "/api/benson/v1/field-records",
        headers={"X-Dev-Staff-Email": FIELD},
        json=report_payload(other_job["id"]),
    )
    assert hidden.status_code == 404
    assert (
        client.get(
            f"/api/benson/v1/field-records/{report['id']}",
            headers={"X-Dev-Staff-Email": OTHER_FIELD},
        ).status_code
        == 404
    )
    listed = client.get(
        "/api/benson/v1/field-records",
        headers={"X-Dev-Staff-Email": FIELD},
    )
    assert [item["id"] for item in listed.json()] == [report["id"]]


def test_submission_is_immutable_and_correction_creates_linked_revision(
    isolated_settings: Settings,
) -> None:
    configure_roles(isolated_settings)
    report = create_report(assigned_job()["id"])
    submitted = client.post(
        f"/api/benson/v1/field-records/{report['id']}/submit",
        headers={"X-Dev-Staff-Email": FIELD},
        params={"expected_version": 1},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"

    immutable_payload = report_payload(report["job_id"])
    immutable_payload.pop("job_id")
    immutable_payload.pop("service_date")
    immutable = client.put(
        f"/api/benson/v1/field-records/{report['id']}",
        headers={"X-Dev-Staff-Email": FIELD},
        json={"expected_version": 2, **immutable_payload},
    )
    assert immutable.status_code == 409
    correction = client.post(
        f"/api/benson/v1/field-records/{report['id']}/correction",
        headers=STAFF_HEADERS,
        json={"expected_version": 2, "reason": "Clarify the sill repair."},
    )
    assert correction.status_code == 200
    assert correction.json()["status"] == "correction_required"
    revision = client.post(
        f"/api/benson/v1/field-records/{report['id']}/revisions",
        headers={"X-Dev-Staff-Email": FIELD},
        params={"expected_version": 3},
    )
    assert revision.status_code == 201
    assert revision.json()["revision"] == 2
    assert revision.json()["previous_revision_id"] == report["id"]

    corrected = client.post(
        f"/api/benson/v1/field-records/{revision.json()['id']}/submit",
        headers={"X-Dev-Staff-Email": FIELD},
        params={"expected_version": 1},
    )
    assert corrected.json()["status"] == "corrected"
    old = client.get(
        f"/api/benson/v1/field-records/{report['id']}",
        headers=STAFF_HEADERS,
    )
    assert old.json()["status"] == "superseded"


def test_stale_update_is_rejected_and_audited(isolated_settings: Settings) -> None:
    configure_roles(isolated_settings)
    report = create_report(assigned_job()["id"])
    payload = report_payload(report["job_id"])
    payload.pop("job_id")
    payload.pop("service_date")
    first = client.put(
        f"/api/benson/v1/field-records/{report['id']}",
        headers={"X-Dev-Staff-Email": FIELD},
        json={"expected_version": 1, **payload, "weather": "Cloudy"},
    )
    assert first.status_code == 200
    stale = client.put(
        f"/api/benson/v1/field-records/{report['id']}",
        headers={"X-Dev-Staff-Email": FIELD},
        json={"expected_version": 1, **payload},
    )
    assert stale.status_code == 409
    audit = client.get(
        f"/api/benson/v1/field-records/{report['id']}/audit",
        headers={"X-Dev-Staff-Email": FIELD},
    ).json()
    assert [event["event"] for event in audit] == [
        "field_report.updated",
        "field_report.created",
    ]
    assert audit[0]["actor"] == FIELD


def test_photo_is_decoded_reencoded_and_private(isolated_settings: Settings) -> None:
    configure_roles(isolated_settings)
    report = create_report(assigned_job()["id"])
    source = BytesIO()
    image = Image.new("RGB", (24, 24), "red")
    exif = Image.Exif()
    exif[0x010E] = "private camera note"
    image.save(source, format="JPEG", exif=exif)
    uploaded = client.post(
        f"/api/benson/v1/field-records/{report['id']}/photos",
        headers={"X-Dev-Staff-Email": FIELD},
        data={"stage": "during"},
        files={"photo": ("site.jpg", source.getvalue(), "image/jpeg")},
    )
    assert uploaded.status_code == 201, uploaded.text
    photo = uploaded.json()
    assert photo["sha256"]
    assert "storage_key" not in photo
    assert (
        client.get(
            f"/api/benson/v1/field-records/{report['id']}/photos/{photo['id']}/download",
            headers={"X-Dev-Staff-Email": OTHER_FIELD},
        ).status_code
        == 404
    )
    downloaded = client.get(
        f"/api/benson/v1/field-records/{report['id']}/photos/{photo['id']}/download",
        headers={"X-Dev-Staff-Email": FIELD},
    )
    assert downloaded.status_code == 200
    with Image.open(BytesIO(downloaded.content)) as sanitized:
        assert not sanitized.getexif()
