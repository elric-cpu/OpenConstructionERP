import json
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.notifications import (
    DeliveryResult,
)
from app.signing import employee_invite_token
from app.storage import operations_store


from tests.support import (
    STAFF_HEADERS,
    client,
)


def test_owner_can_create_and_list_employee_foundation(
    isolated_settings: Settings,
) -> None:
    payload = {
        "name": "New Employee",
        "email": "new.employee@bensonhomesolutions.com",
        "start_date": "2026-08-03",
        "work_location": "Burns, Oregon",
        "classification": "employee",
        "role": "field",
        "federal_contract_applicability": "unknown",
    }

    created = client.post(
        "/api/benson/v1/employees", headers=STAFF_HEADERS, json=payload
    )

    assert created.status_code == 201
    assert created.json()["status"] == "draft"
    assert created.json()["email"] == payload["email"]
    listed = client.get("/api/benson/v1/employees", headers=STAFF_HEADERS)
    assert listed.status_code == 200
    assert [employee["id"] for employee in listed.json()] == [created.json()["id"]]
    assert (
        client.post(
            "/api/benson/v1/employees", headers=STAFF_HEADERS, json=payload
        ).status_code
        == 409
    )


def test_employee_foundation_is_owner_scoped_and_classification_safe(
    isolated_settings: Settings,
) -> None:
    isolated_settings.field_emails = "field@bensonhomesolutions.com"
    field_headers = {"X-Dev-Staff-Email": "field@bensonhomesolutions.com"}
    assert (
        client.get("/api/benson/v1/employees", headers=field_headers).status_code == 403
    )
    assert (
        client.get(
            "/api/benson/v1/onboarding/requirements", headers=field_headers
        ).status_code
        == 403
    )

    invalid = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Misclassified Worker",
            "email": "worker@example.com",
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "independent_contractor",
            "role": "field",
        },
    )
    assert invalid.status_code == 422


def test_owner_can_queue_secure_single_use_employee_invitation(
    isolated_settings: Settings,
) -> None:
    employee = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Invited Employee",
            "email": "invitee@bensonhomesolutions.com",
            "invite_delivery_email": "invitee.personal@example.com",
            "workspace_unlicensed_confirmed": True,
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "employee",
            "role": "field",
        },
    ).json()

    invitation = client.post(
        f"/api/benson/v1/employees/{employee['id']}/invite", headers=STAFF_HEADERS
    )

    assert invitation.status_code == 202
    assert invitation.json()["status"] == "pending_delivery"
    assert "token" not in invitation.text
    listed = client.get("/api/benson/v1/employees", headers=STAFF_HEADERS).json()
    assert listed[0]["status"] == "invited"
    claimed = operations_store(
        isolated_settings.resolved_database_url()
    ).claim_employee_notifications(limit=1)
    assert employee["workspace_license_policy"] == "no_paid_license"
    assert employee["workspace_account_status"] == "unlicensed_attested"
    assert claimed[0]["destination"] == "invitee.personal@example.com"
    assert "token" not in json.dumps(claimed[0]["payload"])
    assert "invite_url" not in claimed[0]["payload"]


def test_invitation_delivery_uses_durable_outbox(
    isolated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    employee = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Delivery Employee",
            "email": "delivery@bensonhomesolutions.com",
            "workspace_unlicensed_confirmed": True,
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "employee",
            "role": "office",
        },
    ).json()
    assert (
        client.post(
            f"/api/benson/v1/employees/{employee['id']}/invite", headers=STAFF_HEADERS
        ).status_code
        == 202
    )
    delivery = MagicMock(
        return_value=DeliveryResult(provider_message_id="invite-message-123")
    )
    monkeypatch.setattr("app.system_routes.deliver_notification", delivery)

    drained = client.post("/api/internal/v1/notifications/drain")

    assert drained.status_code == 200
    assert drained.json()["sent"] == 1
    assert delivery.call_args.args[0]["payload"]["kind"] == "employee_invitation"


def test_only_owner_can_invite_and_missing_employee_is_404(
    isolated_settings: Settings,
) -> None:
    isolated_settings.field_emails = "field@bensonhomesolutions.com"
    field_headers = {"X-Dev-Staff-Email": "field@bensonhomesolutions.com"}
    assert (
        client.post(
            "/api/benson/v1/employees/missing/invite", headers=field_headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/benson/v1/employees/missing/invite", headers=STAFF_HEADERS
        ).status_code
        == 404
    )


def test_invitation_requires_unlicensed_workspace_attestation() -> None:
    employee = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Pending Workspace Employee",
            "email": "pending.workspace@bensonhomesolutions.com",
            "invite_delivery_email": "pending@example.com",
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "employee",
            "role": "field",
        },
    ).json()

    response = client.post(
        f"/api/benson/v1/employees/{employee['id']}/invite", headers=STAFF_HEADERS
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Confirm the Workspace account exists without a paid license before inviting"
    )


def test_invited_employee_activates_with_matching_verified_google_identity(
    isolated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_settings.staff_google_audience = "client.apps.googleusercontent.com"
    employee = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Portal Employee",
            "email": "portal.employee@bensonhomesolutions.com",
            "workspace_unlicensed_confirmed": True,
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "employee",
            "role": "field",
        },
    ).json()
    invitation = client.post(
        f"/api/benson/v1/employees/{employee['id']}/invite", headers=STAFF_HEADERS
    ).json()
    token = employee_invite_token(
        isolated_settings.employee_invite_signing_secret, invitation["id"]
    )
    verify = MagicMock(
        return_value={
            "email": "portal.employee@bensonhomesolutions.com",
            "email_verified": True,
            "sub": "employee-google-subject",
            "hd": "bensonhomesolutions.com",
        }
    )
    monkeypatch.setattr("app.auth.id_token.verify_oauth2_token", verify)

    activated = client.post(
        "/api/benson/v1/onboarding/activate",
        json={
            "token": token,
            "credential": "google-credential-value",
        },
    )

    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    me = client.get(
        "/api/benson/v1/onboarding/me",
        headers={"Authorization": "Bearer google-credential-value"},
    )
    assert me.status_code == 200
    assert me.json()["id"] == employee["id"]
    session = client.get(
        "/api/benson/v1/session",
        headers={"Authorization": "Bearer google-credential-value"},
    )
    assert session.status_code == 200
    assert session.json()["kind"] == "employee"
    assert session.json()["default_view"] == "tasks"
    assert (
        client.post(
            "/api/benson/v1/onboarding/activate",
            json={
                "token": token,
                "credential": "google-credential-value",
            },
        ).status_code
        == 409
    )


def test_owner_session_defaults_to_operations() -> None:
    session = client.get("/api/benson/v1/session", headers=STAFF_HEADERS)

    assert session.status_code == 200
    assert session.json() == {
        "kind": "staff",
        "email": "office@bensonhomesolutions.com",
        "role": "owner",
        "default_view": "overview",
        "employee": None,
    }


def test_invitation_rejects_wrong_google_account(
    isolated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_settings.staff_google_audience = "client.apps.googleusercontent.com"
    employee = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Exact Identity",
            "email": "right@bensonhomesolutions.com",
            "workspace_unlicensed_confirmed": True,
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "employee",
            "role": "office",
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
                "email": "wrong@bensonhomesolutions.com",
                "email_verified": True,
                "sub": "wrong-sub",
                "hd": "bensonhomesolutions.com",
            }
        ),
    )

    response = client.post(
        "/api/benson/v1/onboarding/activate",
        json={"token": token, "credential": "google-credential-value"},
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"] == "Invitation does not match the signed-in account"
    )


def test_employee_requires_managed_workspace_email() -> None:
    response = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Personal Email Employee",
            "email": "personal@example.com",
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "employee",
            "role": "field",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Employees must use an @bensonhomesolutions.com Workspace email"
    )


def test_invitation_activation_requires_managed_hosted_domain(
    isolated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_settings.staff_google_audience = "client.apps.googleusercontent.com"
    employee = client.post(
        "/api/benson/v1/employees",
        headers=STAFF_HEADERS,
        json={
            "name": "Managed Identity",
            "email": "managed@bensonhomesolutions.com",
            "workspace_unlicensed_confirmed": True,
            "start_date": "2026-08-03",
            "work_location": "Burns, Oregon",
            "classification": "employee",
            "role": "field",
        },
    ).json()
    invitation = client.post(
        f"/api/benson/v1/employees/{employee['id']}/invite",
        headers=STAFF_HEADERS,
    ).json()
    token = employee_invite_token(
        isolated_settings.employee_invite_signing_secret, invitation["id"]
    )
    monkeypatch.setattr(
        "app.auth.id_token.verify_oauth2_token",
        MagicMock(
            return_value={
                "email": "managed@bensonhomesolutions.com",
                "email_verified": True,
                "sub": "unmanaged-subject",
            }
        ),
    )

    response = client.post(
        "/api/benson/v1/onboarding/activate",
        json={"token": token, "credential": "google-credential-value"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Managed Benson Workspace account required"
