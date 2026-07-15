import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx2 import Response

from app.auth import Principal, require_operations_staff, require_owner, require_staff
from app.config import Settings, get_settings
from app.domain import Role
from app.main import app
from app.object_storage import delete_upload, detect_upload_type, read_upload, store_upload
from app.policy import ActionRisk, evaluate_agent_action
from app.accounting_provider import SYNC_OWNERSHIP, SyncDirection, SyncEnvelope
from app.signing import signature_for
from app.skill_registry import load_registry
from app.storage import operations_store

client = TestClient(app)
STAFF_HEADERS = {"X-Dev-Staff-Email": "office@bensonhomesolutions.com"}


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path) -> Iterator[Settings]:
    settings = Settings(
        environment="test",
        database_path=tmp_path / "operations.sqlite3",
        upload_storage_path=tmp_path / "uploads",
        ddc_registry_path=Path(__file__).resolve().parents[2] / "skills" / "registry.json",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    test_store = operations_store(settings.resolved_database_url())
    test_store.initialize_schema()
    yield settings
    app.dependency_overrides.clear()
    test_store.engine.dispose()
    operations_store.cache_clear()


def canonical_lead(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Test Homeowner",
        "phone": "458-555-0100",
        "email": "homeowner@example.com",
        "customer_type": "homeowner",
        "address": "123 Main St",
        "city": "Burns",
        "zip_code": "97720",
        "service_type": "window-door-replacements",
        "urgency": "standard",
        "message": "Two windows need review.",
        "form_context": "contact",
        "source_page": "/contact",
    }
    payload.update(overrides)
    return payload


def signed_headers(settings: Settings, body: bytes, key: str = "lead-test-1") -> dict[str, str]:
    timestamp = str(int(datetime.now(UTC).timestamp()))
    return {
        "content-type": "application/json",
        "Idempotency-Key": key,
        "X-Benson-Timestamp": timestamp,
        "X-Benson-Signature": signature_for(settings.website_signing_secret, timestamp, body),
    }


def post_signed_lead(
    settings: Settings, payload: dict[str, object], key: str = "lead-test-1"
) -> Response:
    body = json.dumps(payload, separators=(",", ":")).encode()
    return client.post(
        "/api/benson/v1/intake/leads", content=body, headers=signed_headers(settings, body, key)
    )


def test_health_is_benson_usd_oregon_profile() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["profile"] == {"currency": "USD", "state": "OR", "county": "Harney"}
    assert response.json()["storage"] == "sqlite"
    auth = client.get("/api/benson/v1/auth/config").json()
    assert auth["provider"] == "google_workspace"
    assert auth["hosted_domain"] == "bensonhomesolutions.com"


def test_production_configuration_fails_closed() -> None:
    with pytest.raises(ValueError, match="Production configuration is incomplete"):
        Settings(environment="production")


def test_signed_website_lead_is_durable_and_idempotent(isolated_settings: Settings) -> None:
    first = post_signed_lead(isolated_settings, canonical_lead())
    second = post_signed_lead(isolated_settings, canonical_lead())

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["lead_id"] == first.json()["lead_id"]
    assert (
        client.get("/api/v1/dashboard", headers=STAFF_HEADERS).json()["metrics"]["new_leads"] == 1
    )


def test_signed_intake_rejects_missing_bad_and_expired_signatures(
    isolated_settings: Settings,
) -> None:
    body = json.dumps(canonical_lead()).encode()
    assert client.post("/api/benson/v1/intake/leads", content=body).status_code == 401

    invalid = signed_headers(isolated_settings, body)
    invalid["X-Benson-Signature"] = "0" * 64
    assert (
        client.post("/api/benson/v1/intake/leads", content=body, headers=invalid).status_code == 401
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
        client.post("/api/benson/v1/intake/leads", content=body, headers=expired).status_code == 401
    )


def test_signed_intake_validates_idempotency_and_payload(isolated_settings: Settings) -> None:
    body = b"{}"
    headers = signed_headers(isolated_settings, body, key="")
    headers.pop("Idempotency-Key")
    assert (
        client.post("/api/benson/v1/intake/leads", content=body, headers=headers).status_code == 400
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
    field_principal = Principal(email="field@example.com", role=Role.FIELD, subject="field")
    app.dependency_overrides[require_staff] = lambda: field_principal
    try:
        groups = client.get("/api/v1/config/modules").json()["groups"]
    finally:
        app.dependency_overrides.pop(require_staff, None)
    assert "delivery" in groups
    assert "finance" not in groups


def test_production_google_auth_and_owner_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        environment="production",
        website_signing_secret="x" * 32,
        staff_google_audience="client.apps.googleusercontent.com",
        database_url="postgresql://user:pass@db/operations",
        upload_bucket="private-uploads",
        fcc_base_url="https://fcc.example.com",
        owner_emails="owner@bensonhomesolutions.com",
    )
    monkeypatch.setattr(
        "app.auth.id_token.verify_oauth2_token",
        MagicMock(
            return_value={
                "email": "owner@bensonhomesolutions.com",
                "email_verified": True,
                "hd": "bensonhomesolutions.com",
                "sub": "google-subject",
            }
        ),
    )
    principal = require_staff(authorization="Bearer valid", settings=settings)
    assert principal.role is Role.OWNER
    assert require_owner(principal) == principal
    with pytest.raises(HTTPException, match="Owner approval required"):
        require_owner(Principal(email="field@example.com", role=Role.FIELD, subject="field"))


@pytest.mark.parametrize(
    "claims",
    [
        {
            "email": "owner@bensonhomesolutions.com",
            "email_verified": False,
            "hd": "bensonhomesolutions.com",
        },
        {"email": "outsider@example.com", "email_verified": True, "hd": "example.com"},
    ],
)
def test_production_google_auth_rejects_untrusted_claims(
    claims: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        environment="production",
        website_signing_secret="x" * 32,
        staff_google_audience="client.apps.googleusercontent.com",
        database_url="postgresql://user:pass@db/operations",
        upload_bucket="private-uploads",
        fcc_base_url="https://fcc.example.com",
    )
    monkeypatch.setattr("app.auth.id_token.verify_oauth2_token", MagicMock(return_value=claims))
    with pytest.raises(HTTPException, match="Benson Workspace account required"):
        require_staff(authorization="Bearer invalid", settings=settings)


def test_production_google_auth_rejects_unlisted_workspace_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        environment="production",
        website_signing_secret="x" * 32,
        staff_google_audience="client.apps.googleusercontent.com",
        database_url="postgresql://user:pass@db/operations",
        upload_bucket="private-uploads",
        fcc_base_url="https://fcc.example.com",
        owner_emails="owner@bensonhomesolutions.com",
    )
    monkeypatch.setattr(
        "app.auth.id_token.verify_oauth2_token",
        MagicMock(
            return_value={
                "email": "unlisted@bensonhomesolutions.com",
                "email_verified": True,
                "hd": "bensonhomesolutions.com",
                "sub": "unlisted-subject",
            }
        ),
    )
    with pytest.raises(HTTPException, match="Staff account is not authorized"):
        require_staff(authorization="Bearer valid", settings=settings)
    with pytest.raises(HTTPException, match="Staff account is not authorized"):
        require_staff(
            x_dev_staff_email="unlisted@bensonhomesolutions.com",
            settings=Settings(),
        )


def test_staff_can_list_persisted_leads(isolated_settings: Settings) -> None:
    post_signed_lead(isolated_settings, canonical_lead(urgency="emergency"), key="urgent-1")
    response = client.get("/api/benson/v1/leads?limit=500", headers=STAFF_HEADERS)
    assert response.status_code == 200
    assert response.json()["leads"][0]["priority"] == "urgent"


def test_staff_can_filter_open_update_and_audit_lead(isolated_settings: Settings) -> None:
    created = post_signed_lead(
        isolated_settings, canonical_lead(name="Filter Homeowner", urgency="emergency"), key="ops-1"
    ).json()
    lead_id = created["lead_id"]
    filtered = client.get(
        "/api/benson/v1/leads?priority=urgent&query=Filter", headers=STAFF_HEADERS
    )
    assert [lead["id"] for lead in filtered.json()["leads"]] == [lead_id]

    updated = client.patch(
        f"/api/benson/v1/leads/{lead_id}",
        headers=STAFF_HEADERS,
        json={
            "status": "contacted",
            "assigned_to": "Estimator@BensonHomeSolutions.com",
            "note": "Left voicemail and requested measurements.",
        },
    )
    assert updated.status_code == 200
    detail = updated.json()
    assert detail["status"] == "contacted"
    assert detail["assigned_to"] == "estimator@bensonhomesolutions.com"
    assert detail["notes"][0]["body"] == "Left voicemail and requested measurements."
    assert {event["event"] for event in detail["audit_events"]} >= {
        "lead.accepted",
        "lead.updated",
        "lead.note_added",
    }
    assert client.get(f"/api/benson/v1/leads/{lead_id}").status_code == 503
    assert (
        client.patch(f"/api/benson/v1/leads/{lead_id}", headers=STAFF_HEADERS, json={}).status_code
        == 400
    )
    invalid = client.patch(
        f"/api/benson/v1/leads/{lead_id}",
        headers=STAFF_HEADERS,
        json={"status": "scheduled"},
    )
    assert invalid.status_code == 409
    assert "contacted to scheduled" in invalid.json()["detail"]


def test_lead_workspace_denies_non_operations_roles(isolated_settings: Settings) -> None:
    lead_id = post_signed_lead(isolated_settings, canonical_lead(), key="role-scope").json()[
        "lead_id"
    ]
    field_principal = Principal(email="field@example.com", role=Role.FIELD, subject="field")
    app.dependency_overrides[require_operations_staff] = lambda: require_operations_staff(
        field_principal
    )
    try:
        response = client.get(f"/api/benson/v1/leads/{lead_id}")
    finally:
        app.dependency_overrides.pop(require_operations_staff, None)
    assert response.status_code == 403


def test_staff_attachment_download_is_authenticated(isolated_settings: Settings) -> None:
    created = post_signed_lead(isolated_settings, canonical_lead(), key="secure-file").json()
    client.post(
        f"/uploads/{created['upload_session_id']}",
        files=[("files", ("window.jpg", b"\xff\xd8\xffjpeg-data", "image/jpeg"))],
    )
    detail = client.get(f"/api/benson/v1/leads/{created['lead_id']}", headers=STAFF_HEADERS).json()
    attachment_id = detail["attachments"][0]["id"]
    assert "storage_key" not in detail["attachments"][0]
    assert client.get(f"/api/benson/v1/attachments/{attachment_id}").status_code == 503
    downloaded = client.get(f"/api/benson/v1/attachments/{attachment_id}", headers=STAFF_HEADERS)
    assert downloaded.content == b"\xff\xd8\xffjpeg-data"
    assert downloaded.headers["content-type"] == "image/jpeg"


def test_read_gcs_upload_uses_private_configured_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    client_mock = MagicMock()
    client_mock.bucket.return_value.blob.return_value.download_as_bytes.return_value = b"private"
    monkeypatch.setattr("app.object_storage.gcs.Client", MagicMock(return_value=client_mock))
    settings = Settings(upload_bucket="private-uploads")
    assert read_upload(settings, "gs://private-uploads/leads/1/file.pdf") == b"private"


def test_upload_validation_rejects_missing_session_and_spoofed_type(
    isolated_settings: Settings,
) -> None:
    assert client.get("/uploads/missing").status_code == 404
    lead = post_signed_lead(isolated_settings, canonical_lead(), key="upload-spoof").json()
    response = client.post(
        f"/uploads/{lead['upload_session_id']}",
        files=[("files", ("payload.jpg", b"not-an-image", "image/jpeg"))],
    )
    assert response.status_code == 415


def test_upload_session_enforces_cumulative_file_quota(isolated_settings: Settings) -> None:
    isolated_settings.upload_session_max_files = 1
    lead = post_signed_lead(isolated_settings, canonical_lead(), key="upload-quota").json()
    endpoint = f"/uploads/{lead['upload_session_id']}"
    file = [("files", ("window.jpg", b"\xff\xd8\xffjpeg-data", "image/jpeg"))]
    assert client.post(endpoint, files=file).status_code == 200
    assert client.post(endpoint, files=file).status_code == 413


def test_upload_type_detection() -> None:
    assert detect_upload_type(b"\xff\xd8\xffdata") == "image/jpeg"
    assert detect_upload_type(b"\x89PNG\r\n\x1a\ndata") == "image/png"
    assert detect_upload_type(b"RIFF0000WEBPdata") == "image/webp"
    assert detect_upload_type(b"%PDF-1.7") == "application/pdf"
    assert detect_upload_type(b"unknown") is None


def test_gcs_upload_and_delete_use_private_configured_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_mock = MagicMock()
    blob = client_mock.bucket.return_value.blob.return_value
    monkeypatch.setattr("app.object_storage.gcs.Client", MagicMock(return_value=client_mock))
    settings = Settings(upload_bucket="private-uploads")
    storage_key, digest = store_upload(
        settings,
        lead_id="lead-1",
        original_name="photo.jpg",
        content_type="image/jpeg",
        content=b"\xff\xd8\xffphoto",
    )
    assert storage_key.startswith("gs://private-uploads/leads/lead-1/")
    assert len(digest) == 64
    blob.upload_from_string.assert_called_once_with(b"\xff\xd8\xffphoto", content_type="image/jpeg")
    delete_upload(settings, storage_key)
    blob.delete.assert_called_once()


def test_skill_catalog_is_pinned_and_role_scoped() -> None:
    response = client.get("/api/benson/v1/ai/skills", headers=STAFF_HEADERS)
    assert response.status_code == 200
    assert response.json()["source_commit"].startswith("34e0d783")
    assert any(skill["id"] == "estimate-builder" for skill in response.json()["skills"])
    catalog = load_registry(str(Path(__file__).resolve().parents[2] / "skills" / "registry.json"))
    assert catalog.get("missing") is None
    assert catalog.get("estimate-builder") is not None


def test_ai_skill_creates_owner_approved_persisted_proposal(
    isolated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = AsyncMock(return_value={"output_text": "Draft estimate"})
    monkeypatch.setattr("app.main.run_agent_prompt", gateway)
    run = client.post(
        "/api/benson/v1/ai/runs",
        headers=STAFF_HEADERS,
        json={
            "skill_id": "estimate-builder",
            "prompt": "Draft from supplied scope",
            "record_context": {"scope": "two windows"},
        },
    )
    assert run.status_code == 200
    assert run.json()["status"] == "confirmation_required"
    assert gateway.await_args is not None
    assert '"scope": "two windows"' in gateway.await_args.args[1]
    proposal_id = run.json()["proposal_id"]
    approved = client.post(
        f"/api/benson/v1/ai/proposals/{proposal_id}/approve",
        headers=STAFF_HEADERS,
        json={"comment": "Owner reviewed"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert (
        client.post(
            f"/api/benson/v1/ai/proposals/{proposal_id}/reject",
            headers=STAFF_HEADERS,
            json={},
        ).status_code
        == 409
    )


def test_ai_skill_rejects_unknown_skill_and_gateway_failure_has_no_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = client.post(
        "/api/benson/v1/ai/runs",
        headers=STAFF_HEADERS,
        json={"skill_id": "missing", "prompt": "No"},
    )
    assert missing.status_code == 404
    from app.ai_gateway import AiGatewayUnavailable

    monkeypatch.setattr(
        "app.main.run_agent_prompt", AsyncMock(side_effect=AiGatewayUnavailable("offline"))
    )
    failed = client.post(
        "/api/benson/v1/ai/runs",
        headers=STAFF_HEADERS,
        json={"skill_id": "historical-cost-analyzer", "prompt": "Summarize supplied costs"},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["proposal_id"] is None


def test_accounting_provider_contract_encodes_sync_ownership() -> None:
    envelope = SyncEnvelope(
        entity_type="invoice",
        entity_id="invoice-1",
        direction=SyncDirection.TO_PROVIDER,
        idempotency_key="invoice-1-version-1",
        payload={"amount": "100.00"},
    )
    assert envelope.direction is SyncDirection.TO_PROVIDER
    assert SYNC_OWNERSHIP["payment"] == "provider_then_erp"


def test_agent_policy_requires_confirmation_for_external_and_money_actions() -> None:
    assert evaluate_agent_action(Role.OWNER, ActionRisk.INTERNAL).confirmation_required is False
    assert evaluate_agent_action(Role.OWNER, ActionRisk.EXTERNAL_SEND).confirmation_required is True
    assert (
        evaluate_agent_action(Role.ACCOUNTING, ActionRisk.FINANCIAL).confirmation_required is True
    )
    assert evaluate_agent_action(Role.FIELD, ActionRisk.FINANCIAL).allowed is False
