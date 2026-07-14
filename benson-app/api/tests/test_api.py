from pathlib import Path
from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.domain import Role
from app.main import app
from app.policy import ActionRisk, evaluate_agent_action
from app.quickbooks import SYNC_OWNERSHIP, SyncDirection, SyncEnvelope

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path) -> Iterator[Settings]:
    settings = Settings(
        database_path=tmp_path / "operations.sqlite3",
        upload_storage_path=tmp_path / "uploads",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.clear()


def test_health_is_benson_usd_oregon_profile() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["profile"] == {"currency": "USD", "state": "OR", "county": "Harney"}


def test_website_lead_rejects_missing_key() -> None:
    response = client.post("/api/v1/webhook-leads/incoming/benson-website/", json={})
    assert response.status_code == 401


def test_website_lead_returns_receipt_and_upload_handoff(isolated_settings: Settings) -> None:
    settings = isolated_settings
    response = client.post(
        "/api/v1/webhook-leads/incoming/benson-website/",
        headers={"X-Api-Key": settings.website_api_key},
        json={
            "contact_name": "Test Homeowner",
            "contact_phone": "458-555-0100",
            "qualification_notes": "window-door-replacements | standard | Burns",
        },
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "accepted"
    assert "/uploads/" in payload["upload_url"]
    session_id = payload["upload_session_id"]
    assert client.get(f"/uploads/{session_id}").status_code == 200
    upload = client.post(
        f"/uploads/{session_id}",
        files=[("files", ("window.jpg", b"jpeg-data", "image/jpeg"))],
    )
    assert upload.status_code == 200
    assert "Files attached" in upload.text


def test_dashboard_and_modules_are_role_scoped(isolated_settings: Settings) -> None:
    assert client.get("/api/v1/dashboard").json()["metrics"]["new_leads"] == 0
    field_groups = client.get("/api/v1/config/modules?role=field").json()["groups"]
    assert "delivery" in field_groups
    assert "finance" not in field_groups


def test_upload_validation_rejects_missing_session_and_unsafe_type() -> None:
    assert client.get("/uploads/missing").status_code == 404
    lead = client.post(
        "/api/v1/webhook-leads/incoming/benson-website/",
        headers={"X-Api-Key": "development-only"},
        json={
            "contact_name": "Test Homeowner",
            "contact_phone": "458-555-0100",
            "qualification_notes": "repair review",
        },
    ).json()
    response = client.post(
        f"/uploads/{lead['upload_session_id']}",
        files=[("files", ("payload.exe", b"unsafe", "application/octet-stream"))],
    )
    assert response.status_code == 415


def test_agent_rejects_field_financial_actions_without_calling_gateway() -> None:
    response = client.post(
        "/api/v1/agent/actions",
        json={"prompt": "Pay invoice", "role": "field", "tools": ["financial:pay"]},
    )
    assert response.status_code == 403


def test_agent_reports_gateway_failure_without_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ai_gateway import AiGatewayUnavailable

    monkeypatch.setattr(
        "app.main.run_agent_prompt",
        AsyncMock(side_effect=AiGatewayUnavailable("offline")),
    )
    response = client.post(
        "/api/v1/agent/actions",
        json={"prompt": "Summarize leads", "role": "owner", "tools": ["internal:read"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_quickbooks_contract_encodes_sync_ownership() -> None:
    envelope = SyncEnvelope(
        entity_type="invoice",
        entity_id="invoice-1",
        direction=SyncDirection.TO_QUICKBOOKS,
        idempotency_key="invoice-1-version-1",
        payload={"amount": "100.00"},
    )
    assert envelope.direction is SyncDirection.TO_QUICKBOOKS
    assert SYNC_OWNERSHIP["payment"] == "quickbooks_then_erp"


def test_agent_policy_requires_confirmation_for_external_and_money_actions() -> None:
    assert evaluate_agent_action(Role.OWNER, ActionRisk.INTERNAL).confirmation_required is False
    assert evaluate_agent_action(Role.OWNER, ActionRisk.EXTERNAL_SEND).confirmation_required is True
    assert (
        evaluate_agent_action(Role.ACCOUNTING, ActionRisk.FINANCIAL).confirmation_required is True
    )
    assert evaluate_agent_action(Role.FIELD, ActionRisk.FINANCIAL).allowed is False
