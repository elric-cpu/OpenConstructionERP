from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.signing import employee_invite_token
from app.storage import operations_store


from tests.support import (
    STAFF_HEADERS,
    client,
)


def test_employee_tasks_are_generated_by_classification_and_applicability(
    isolated_settings: Settings,
) -> None:
    employee = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Federal Employee",
            "email": "federal.employee@bensonhomesolutions.com",
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "employee",
            "role": "field",
            "federal_contract_applicability": "unknown",
        },
    ).json()

    response = client.get(
        f"/api/benson/v1/employees/{employee['id']}/tasks", headers=STAFF_HEADERS
    )

    assert response.status_code == 200
    tasks = {task["requirement_id"]: task for task in response.json()}
    assert {"form-i9", "federal-w4", "oregon-w4", "payroll-enrollment"} <= tasks.keys()
    assert "contractor-w9" not in tasks
    assert "w2" not in tasks
    assert tasks["e-verify"]["status"] == "blocked"
    assert tasks["davis-bacon"]["status"] == "blocked"


def test_contractor_gets_separate_w9_task_only() -> None:
    contractor = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Independent Trade Partner",
            "email": "trade.partner@example.com",
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "independent_contractor",
            "role": "subcontractor",
        },
    ).json()

    tasks = client.get(
        f"/api/benson/v1/employees/{contractor['id']}/tasks", headers=STAFF_HEADERS
    ).json()

    assert [task["requirement_id"] for task in tasks] == ["contractor-w9"]


def test_activated_employee_tasks_are_the_default_view(
    isolated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_settings.staff_google_audience = "client.apps.googleusercontent.com"
    employee = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Tasks Employee",
            "email": "tasks.employee@bensonhomesolutions.com",
            "workspace_unlicensed_confirmed": True,
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "employee",
            "role": "field",
            "federal_contract_applicability": "not_applicable",
        },
    ).json()
    invitation = client.post(
        f"/api/benson/v1/employees/{employee['id']}/invite", headers=STAFF_HEADERS
    ).json()
    token = employee_invite_token(
        isolated_settings.employee_invite_signing_secret, invitation["id"]
    )
    monkeypatch.setattr(
        "app.auth.id_token.verify_oauth2_token",
        MagicMock(
            return_value={
                "email": "tasks.employee@bensonhomesolutions.com",
                "email_verified": True,
                "sub": "tasks-google-subject",
                "hd": "bensonhomesolutions.com",
            }
        ),
    )
    client.post(
        "/api/benson/v1/onboarding/activate",
        json={"token": token, "credential": "tasks-google-credential"},
    )

    response = client.get(
        "/api/benson/v1/onboarding/tasks",
        headers={"Authorization": "Bearer tasks-google-credential"},
    )

    assert response.status_code == 200
    assert response.json()["default_view"] == "tasks"
    assert response.json()["progress"] == {"completed": 0, "total": 8}
    assert response.json()["employee"]["id"] == employee["id"]


def test_employee_evidence_is_encrypted_versioned_and_reviewed(
    isolated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_settings.staff_google_audience = "client.apps.googleusercontent.com"
    email = "evidence.employee@bensonhomesolutions.com"
    employee = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Evidence Employee",
            "email": email,
            "workspace_unlicensed_confirmed": True,
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "employee",
            "role": "field",
            "federal_contract_applicability": "not_applicable",
        },
    ).json()
    invitation = client.post(
        f"/api/benson/v1/employees/{employee['id']}/invite", headers=STAFF_HEADERS
    ).json()
    token = employee_invite_token(
        isolated_settings.employee_invite_signing_secret, invitation["id"]
    )
    monkeypatch.setattr(
        "app.auth.id_token.verify_oauth2_token",
        MagicMock(
            return_value={
                "email": email,
                "email_verified": True,
                "sub": "evidence-subject",
                "hd": "bensonhomesolutions.com",
            }
        ),
    )
    credential_headers = {"Authorization": "Bearer employee-google-credential"}
    assert (
        client.post(
            "/api/benson/v1/onboarding/activate",
            json={"token": token, "credential": "employee-google-credential"},
        ).status_code
        == 200
    )
    tasks = client.get(
        "/api/benson/v1/onboarding/tasks", headers=credential_headers
    ).json()["tasks"]
    task = next(item for item in tasks if item["requirement_id"] == "federal-w4")
    plaintext = b"%PDF-1.7\nconfidential withholding values\n%%EOF"

    uploaded = client.post(
        f"/api/benson/v1/onboarding/tasks/{task['id']}/evidence",
        headers=credential_headers,
        files={"file": ("w4.pdf", plaintext, "application/pdf")},
    )

    assert uploaded.status_code == 201
    document = uploaded.json()
    assert document["version"] == 1
    assert document["data_classification"] == "highly_restricted"
    internal = operations_store(
        isolated_settings.resolved_database_url()
    ).get_employee_document(document["id"])
    assert internal is not None
    stored = Path(internal["storage_key"]).read_bytes()
    assert plaintext not in stored
    assert b"confidential withholding values" not in stored
    downloaded = client.get(
        f"/api/benson/v1/onboarding/documents/{document['id']}",
        headers=credential_headers,
    )
    assert downloaded.status_code == 200
    assert downloaded.content == plaintext

    completed = client.patch(
        f"/api/benson/v1/employees/{employee['id']}/tasks/{task['id']}",
        headers=STAFF_HEADERS,
        json={"decision": "complete", "comment": "Reviewed signed withholding form."},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


def test_rejected_evidence_preserves_versions_and_blocks_cross_task_actions(
    isolated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_settings.staff_google_audience = "client.apps.googleusercontent.com"
    email = "revision.employee@bensonhomesolutions.com"
    employee = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Revision Employee",
            "email": email,
            "workspace_unlicensed_confirmed": True,
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "employee",
            "role": "field",
            "federal_contract_applicability": "unknown",
        },
    ).json()
    invitation = client.post(
        f"/api/benson/v1/employees/{employee['id']}/invite", headers=STAFF_HEADERS
    ).json()
    token = employee_invite_token(
        isolated_settings.employee_invite_signing_secret, invitation["id"]
    )
    monkeypatch.setattr(
        "app.auth.id_token.verify_oauth2_token",
        MagicMock(
            return_value={
                "email": email,
                "email_verified": True,
                "sub": "revision-subject",
                "hd": "bensonhomesolutions.com",
            }
        ),
    )
    employee_headers = {"Authorization": "Bearer revision-google-credential"}
    client.post(
        "/api/benson/v1/onboarding/activate",
        json={"token": token, "credential": "revision-google-credential"},
    )
    tasks = client.get(
        "/api/benson/v1/onboarding/tasks", headers=employee_headers
    ).json()["tasks"]
    w4 = next(item for item in tasks if item["requirement_id"] == "federal-w4")
    blocked = next(item for item in tasks if item["requirement_id"] == "e-verify")
    assert (
        client.post(
            f"/api/benson/v1/onboarding/tasks/{blocked['id']}/evidence",
            headers=employee_headers,
            files={"file": ("blocked.pdf", b"%PDF-blocked", "application/pdf")},
        ).status_code
        == 409
    )
    first = client.post(
        f"/api/benson/v1/onboarding/tasks/{w4['id']}/evidence",
        headers=employee_headers,
        files={"file": ("w4-v1.pdf", b"%PDF-first", "application/pdf")},
    ).json()
    rejected = client.patch(
        f"/api/benson/v1/employees/{employee['id']}/tasks/{w4['id']}",
        headers=STAFF_HEADERS,
        json={"decision": "reject", "comment": "Signature is missing."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    second = client.post(
        f"/api/benson/v1/onboarding/tasks/{w4['id']}/evidence",
        headers=employee_headers,
        files={"file": ("w4-v2.pdf", b"%PDF-second", "application/pdf")},
    ).json()
    assert second["version"] == 2
    documents = client.get(
        "/api/benson/v1/onboarding/documents", headers=employee_headers
    ).json()
    by_id = {item["id"]: item for item in documents}
    assert by_id[first["id"]]["status"] == "superseded"
    assert by_id[second["id"]]["status"] == "active"
    assert (
        client.patch(
            f"/api/benson/v1/employees/{employee['id']}/tasks/{blocked['id']}",
            headers=STAFF_HEADERS,
            json={"decision": "complete", "comment": "Attempt without applicability."},
        ).status_code
        == 409
    )
    not_applicable = client.patch(
        f"/api/benson/v1/employees/{employee['id']}/tasks/{blocked['id']}",
        headers=STAFF_HEADERS,
        json={
            "decision": "not_applicable",
            "comment": "Contract clause does not apply.",
        },
    )
    assert not_applicable.status_code == 200
    assert not_applicable.json()["status"] == "not_applicable"


def test_compliance_matrix_is_explicitly_pending_review() -> None:
    response = client.get(
        "/api/benson/v1/onboarding/requirements", headers=STAFF_HEADERS
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "pending_qualified_hr_legal_review"
    requirements = {item["id"]: item for item in body["requirements"]}
    assert {
        "form-i9",
        "e-verify",
        "federal-w4",
        "oregon-w4",
        "davis-bacon",
        "contractor-w9",
    } <= requirements.keys()
    assert all(
        item["legal_review_status"] == "pending" for item in requirements.values()
    )
