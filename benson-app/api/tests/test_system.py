import json
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.auth import (
    Principal,
    require_identity_provisioning_worker,
    require_notification_worker,
    require_staff,
)
from app.config import Settings
from app.domain import Role
from app.main import app
from app.notifications import (
    DeliveryResult,
    NotificationDeliveryError,
    deliver_notification,
)
from app.signing import employee_invite_token, signature_for
from app.storage import operations_store


from tests.support import (
    STAFF_HEADERS,
    canonical_lead,
    client,
    post_signed_lead,
    production_settings,
    signed_headers,
)


def test_health_is_benson_usd_oregon_profile() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["profile"] == {
        "currency": "USD",
        "state": "OR",
        "county": "Harney",
    }
    assert response.json()["storage"] == "sqlite"
    auth = client.get("/api/benson/v1/auth/config").json()
    assert auth["provider"] == "google_workspace"
    assert auth["hosted_domain"] == "bensonhomesolutions.com"


def test_production_configuration_fails_closed() -> None:
    with pytest.raises(ValueError, match="Production configuration is incomplete"):
        Settings(environment="production")

    sms_disabled = production_settings(
        twilio_account_sid="",
        twilio_api_key_sid="",
        twilio_api_key_secret="",
        twilio_from_number="",
        sms_to="",
    )
    assert sms_disabled.sms_enabled_default is False
    directory_disabled = production_settings(
        identity_provisioning_enabled=False,
        identity_worker_audience=None,
        identity_worker_email="",
        google_directory_credentials_json="",
        google_directory_admin="",
        google_paid_license_skus="",
        google_paid_license_skus_approved=False,
    )
    assert directory_disabled.identity_provisioning_enabled is False
    with pytest.raises(ValueError, match="BENSON_TWILIO"):
        production_settings(
            sms_enabled_default=True,
            twilio_account_sid="",
            twilio_api_key_sid="",
            twilio_api_key_secret="",
            twilio_from_number="",
            sms_to="",
        )


def test_disabled_identity_provisioning_worker_fails_closed() -> None:
    settings = production_settings(identity_provisioning_enabled=False)

    with pytest.raises(HTTPException, match="Identity provisioning is disabled"):
        require_identity_provisioning_worker(
            authorization="Bearer ignored", settings=settings
        )


def test_signed_website_lead_is_durable_and_idempotent(
    isolated_settings: Settings,
) -> None:
    first = post_signed_lead(isolated_settings, canonical_lead())
    second = post_signed_lead(isolated_settings, canonical_lead())

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["lead_id"] == first.json()["lead_id"]
    assert (
        client.get("/api/v1/dashboard", headers=STAFF_HEADERS).json()["metrics"][
            "new_leads"
        ]
        == 1
    )
    assert operations_store(
        isolated_settings.resolved_database_url()
    ).notification_counts() == {"pending": 1}


def test_idempotency_key_reuse_with_different_payload_is_rejected(
    isolated_settings: Settings,
) -> None:
    assert (
        post_signed_lead(
            isolated_settings, canonical_lead(), key="same-key"
        ).status_code
        == 201
    )
    conflict = post_signed_lead(
        isolated_settings,
        canonical_lead(message="A different project description."),
        key="same-key",
    )
    assert conflict.status_code == 409
    assert "different lead payload" in conflict.json()["detail"]


def test_intake_enqueues_email_only_when_emergency_sms_is_disabled(
    isolated_settings: Settings,
) -> None:
    first = post_signed_lead(
        isolated_settings,
        canonical_lead(urgency="emergency"),
        key="emergency-notifications",
    )
    duplicate = post_signed_lead(
        isolated_settings,
        canonical_lead(urgency="emergency"),
        key="emergency-notifications",
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert operations_store(
        isolated_settings.resolved_database_url()
    ).notification_counts() == {"pending": 1}


def test_public_gateway_alias_preserves_signed_intake_contract(
    isolated_settings: Settings,
) -> None:
    payload = canonical_lead(
        metadata={"geo_coordinates": {"latitude": 43.5862, "longitude": -118.4967}}
    )
    body = json.dumps(payload, separators=(",", ":")).encode()

    response = client.post(
        "/api/v1/intake/leads",
        content=body,
        headers=signed_headers(isolated_settings, body, "public-gateway-alias"),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "accepted"


def test_owner_can_enable_and_disable_twilio_messaging(
    isolated_settings: Settings,
) -> None:
    initial = client.get("/api/benson/v1/settings/notifications", headers=STAFF_HEADERS)
    assert initial.status_code == 200
    assert initial.json() == {
        "email_enabled": True,
        "sms_enabled": False,
        "sms_configured": False,
    }
    assert (
        client.patch(
            "/api/benson/v1/settings/notifications",
            headers=STAFF_HEADERS,
            json={"sms_enabled": True},
        ).status_code
        == 409
    )

    isolated_settings.twilio_account_sid = "AC123"
    isolated_settings.twilio_api_key_sid = "SK123"
    isolated_settings.twilio_api_key_secret = SecretStr("twilio-secret")
    isolated_settings.twilio_from_number = "+15415550100"
    isolated_settings.sms_to = "+15415550101"
    enabled = client.patch(
        "/api/benson/v1/settings/notifications",
        headers=STAFF_HEADERS,
        json={"sms_enabled": True},
    )
    assert enabled.status_code == 200
    assert enabled.json()["sms_enabled"] is True

    post_signed_lead(
        isolated_settings, canonical_lead(urgency="emergency"), key="sms-on"
    )
    assert operations_store(
        isolated_settings.resolved_database_url()
    ).notification_counts() == {"pending": 3}

    disabled = client.patch(
        "/api/benson/v1/settings/notifications",
        headers=STAFF_HEADERS,
        json={"sms_enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["sms_enabled"] is False
    assert operations_store(
        isolated_settings.resolved_database_url()
    ).notification_counts() == {
        "disabled": 2,
        "pending": 1,
    }


def test_notification_settings_require_owner(isolated_settings: Settings) -> None:
    isolated_settings.field_emails = "field@bensonhomesolutions.com"
    response = client.get(
        "/api/benson/v1/settings/notifications",
        headers={"X-Dev-Staff-Email": "field@bensonhomesolutions.com"},
    )
    assert response.status_code == 403


def test_notification_worker_delivers_claimed_outbox(
    isolated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    post_signed_lead(isolated_settings, canonical_lead(), key="notification-delivery")
    delivery = MagicMock(
        return_value=DeliveryResult(provider_message_id="provider-123")
    )
    monkeypatch.setattr("app.system_routes.deliver_notification", delivery)

    response = client.post("/api/internal/v1/notifications/drain")

    assert response.status_code == 200
    assert response.json() == {
        "claimed": 1,
        "sent": 1,
        "failed": 0,
        "outbox": {"sent": 1},
    }
    delivery.assert_called_once()


def test_notification_worker_persists_retry_after_provider_failure(
    isolated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    post_signed_lead(isolated_settings, canonical_lead(), key="notification-retry")
    monkeypatch.setattr(
        "app.system_routes.deliver_notification",
        MagicMock(side_effect=NotificationDeliveryError("provider unavailable")),
    )

    response = client.post("/api/internal/v1/notifications/drain")

    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert response.json()["outbox"] == {"pending": 1}


def test_production_notification_worker_requires_exact_service_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = production_settings()
    verify = MagicMock(
        return_value={
            "email": "worker@example.iam.gserviceaccount.com",
            "email_verified": True,
        }
    )
    monkeypatch.setattr("app.auth.id_token.verify_oauth2_token", verify)
    assert require_notification_worker(
        authorization="Bearer valid", settings=settings
    ) == ("worker@example.iam.gserviceaccount.com")
    assert verify.call_args.args[2] == "https://operations.example.com"
    monkeypatch.setattr(
        "app.auth.id_token.verify_oauth2_token",
        MagicMock(
            return_value={"email": "attacker@example.com", "email_verified": True}
        ),
    )
    with pytest.raises(HTTPException, match="Notification worker is not authorized"):
        require_notification_worker(authorization="Bearer valid", settings=settings)


@pytest.mark.parametrize(
    ("channel", "provider_body", "expected_url"),
    [
        ("email", {"id": "email-123"}, "https://api.resend.com/emails"),
        (
            "sms",
            {"sid": "sms-123"},
            "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json",
        ),
    ],
)
def test_notification_provider_contracts(
    channel: str,
    provider_body: dict[str, str],
    expected_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock()
    response.json.return_value = provider_body
    post = MagicMock(return_value=response)
    monkeypatch.setattr("app.notifications.httpx.post", post)
    item = {
        "id": "outbox-123",
        "channel": channel,
        "destination": "office@example.com" if channel == "email" else "+15415550101",
        "payload": canonical_lead(urgency="emergency"),
    }

    result = deliver_notification(item, production_settings())

    assert result.provider_message_id == next(iter(provider_body.values()))
    assert post.call_args.args[0] == expected_url
    response.raise_for_status.assert_called_once()


def test_notification_provider_invalid_json_is_a_delivery_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock()
    response.json.side_effect = ValueError("invalid json")
    monkeypatch.setattr(
        "app.notifications.httpx.post", MagicMock(return_value=response)
    )
    with pytest.raises(NotificationDeliveryError, match="invalid json"):
        deliver_notification(
            {
                "id": "outbox-invalid-json",
                "channel": "email",
                "destination": "office@example.com",
                "payload": canonical_lead(),
            },
            production_settings(),
        )


def test_invitation_email_derives_token_only_at_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock()
    response.json.return_value = {"id": "invite-email-123"}
    post = MagicMock(return_value=response)
    monkeypatch.setattr("app.notifications.httpx.post", post)
    settings = production_settings()
    invite_id = "7e805943-3810-40c6-abed-e5da24f2c223"
    payload = {
        "kind": "employee_invitation",
        "name": "New Employee",
        "invite_base_url": "https://erp.bensonhomesolutions.com",
        "invite_id": invite_id,
        "expires_at": "2026-08-03T00:00:00+00:00",
    }

    result = deliver_notification(
        {
            "id": "outbox-invite",
            "channel": "email",
            "destination": "new.employee@bensonhomesolutions.com",
            "payload": payload,
        },
        settings,
    )

    expected_token = employee_invite_token(
        settings.employee_invite_signing_secret, invite_id
    )
    assert result.provider_message_id == "invite-email-123"
    assert expected_token in post.call_args.kwargs["json"]["text"]
    assert "token" not in json.dumps(payload)


def test_signed_intake_rejects_missing_bad_and_expired_signatures(
    isolated_settings: Settings,
) -> None:
    body = json.dumps(canonical_lead()).encode()
    assert client.post("/api/benson/v1/intake/leads", content=body).status_code == 401

    invalid = signed_headers(isolated_settings, body)
    invalid["X-Benson-Signature"] = "0" * 64
    assert (
        client.post(
            "/api/benson/v1/intake/leads", content=body, headers=invalid
        ).status_code
        == 401
    )

    timestamp = "1"
    expired = {
        "Idempotency-Key": "expired",
        "X-Benson-Timestamp": timestamp,
        "X-Benson-Signature": signature_for(
            isolated_settings.website_signing_secret, timestamp, body
        ),
    }
    assert (
        client.post(
            "/api/benson/v1/intake/leads", content=body, headers=expired
        ).status_code
        == 401
    )


def test_signed_intake_validates_idempotency_and_payload(
    isolated_settings: Settings,
) -> None:
    body = b"{}"
    headers = signed_headers(isolated_settings, body, key="")
    headers.pop("Idempotency-Key")
    assert (
        client.post(
            "/api/benson/v1/intake/leads", content=body, headers=headers
        ).status_code
        == 400
    )

    headers = signed_headers(isolated_settings, body)
    response = client.post("/api/benson/v1/intake/leads", content=body, headers=headers)
    assert response.status_code == 422


def test_signed_lead_upload_handoff(isolated_settings: Settings) -> None:
    response = post_signed_lead(isolated_settings, canonical_lead(), key="upload-lead")
    assert response.status_code == 201
    session_id = response.json()["upload_session_id"]
    assert client.get(f"/uploads/{session_id}").status_code == 200
    upload = client.post(
        f"/uploads/{session_id}",
        files=[("files", ("window.jpg", b"\xff\xd8\xffjpeg-data", "image/jpeg"))],
    )
    assert upload.status_code == 200
    assert "Files attached" in upload.text


def test_staff_endpoints_require_auth_and_scope_modules() -> None:
    assert client.get("/api/v1/dashboard").status_code == 503
    field_principal = Principal(
        email="field@example.com", role=Role.FIELD, subject="field"
    )
    app.dependency_overrides[require_staff] = lambda: field_principal
    try:
        groups = client.get("/api/v1/config/modules").json()["groups"]
    finally:
        app.dependency_overrides.pop(require_staff, None)
    assert "delivery" in groups
    assert "finance" not in groups


def test_authenticated_staff_directory_uses_names_and_roles(
    isolated_settings: Settings,
) -> None:
    isolated_settings.owner_emails = "elric@bensonhomesolutions.com"
    isolated_settings.office_emails = "office@bensonhomesolutions.com"
    isolated_settings.staff_display_names = "elric@bensonhomesolutions.com=Elric,office@bensonhomesolutions.com=Benson Office"

    response = client.get("/api/benson/v1/staff", headers=STAFF_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "staff": [
            {
                "email": "elric@bensonhomesolutions.com",
                "display_name": "Elric",
                "role": "owner",
            },
            {
                "email": "office@bensonhomesolutions.com",
                "display_name": "Benson Office",
                "role": "office",
            },
        ]
    }
    assert client.get("/api/benson/v1/staff").status_code == 503
