from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth import (
    Principal,
    require_operations_staff,
)
from app.config import Settings
from app.domain import Role
from app.main import app
from app.object_storage import (
    delete_upload,
    detect_upload_type,
    read_upload,
    store_upload,
)
from app.policy import ActionRisk, evaluate_agent_action
from app.accounting_provider import SYNC_OWNERSHIP, SyncDirection, SyncEnvelope
from app.skill_registry import load_registry
from app.storage import operations_store


from tests.support import (
    STAFF_HEADERS,
    canonical_lead,
    client,
    post_signed_lead,
)


def test_staff_can_list_persisted_leads(isolated_settings: Settings) -> None:
    post_signed_lead(
        isolated_settings, canonical_lead(urgency="emergency"), key="urgent-1"
    )
    response = client.get("/api/benson/v1/leads?limit=500", headers=STAFF_HEADERS)
    assert response.status_code == 200
    assert response.json()["leads"][0]["priority"] == "urgent"


def test_staff_can_filter_open_update_and_audit_lead(
    isolated_settings: Settings,
) -> None:
    isolated_settings.estimator_pm_emails = "estimator@bensonhomesolutions.com"
    created = post_signed_lead(
        isolated_settings,
        canonical_lead(name="Filter Homeowner", urgency="emergency"),
        key="ops-1",
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
        client.patch(
            f"/api/benson/v1/leads/{lead_id}", headers=STAFF_HEADERS, json={}
        ).status_code
        == 400
    )
    unauthorized_assignee = client.patch(
        f"/api/benson/v1/leads/{lead_id}",
        headers=STAFF_HEADERS,
        json={"assigned_to": "outsider@example.com"},
    )
    assert unauthorized_assignee.status_code == 422
    assert (
        unauthorized_assignee.json()["detail"]
        == "Lead assignee must be an authorized staff member"
    )
    invalid = client.patch(
        f"/api/benson/v1/leads/{lead_id}",
        headers=STAFF_HEADERS,
        json={"status": "scheduled"},
    )
    assert invalid.status_code == 409
    assert "contacted to scheduled" in invalid.json()["detail"]


def test_spam_is_autofiltered_editable_and_soft_deletable(
    isolated_settings: Settings,
) -> None:
    created = post_signed_lead(
        isolated_settings,
        canonical_lead(
            name="SEO Vendor",
            message="We sell SEO services and backlinks for higher domain authority.",
            utm_source="cold-outreach",
        ),
        key="spam-1",
    ).json()
    lead_id = created["lead_id"]

    assert (
        client.get("/api/benson/v1/leads", headers=STAFF_HEADERS).json()["leads"] == []
    )
    spam = client.get("/api/benson/v1/leads?spam=spam", headers=STAFF_HEADERS).json()[
        "leads"
    ]
    assert spam[0]["id"] == lead_id
    assert spam[0]["source"] == "cold-outreach"
    assert spam[0]["is_spam"] is True
    assert "spam language" in spam[0]["spam_reason"]
    assert (
        operations_store(
            isolated_settings.resolved_database_url()
        ).notification_counts()
        == {}
    )

    corrected = client.patch(
        f"/api/benson/v1/leads/{lead_id}",
        headers=STAFF_HEADERS,
        json={
            "is_spam": False,
            "name": "Real Homeowner",
            "phone": "541-555-0199",
            "email": "real@example.com",
            "service_type": "Siding repair",
            "city": "Hines",
            "source": "Referral",
        },
    )
    assert corrected.status_code == 200
    assert corrected.json()["name"] == "Real Homeowner"
    assert corrected.json()["is_spam"] == 0
    active = client.get(
        "/api/benson/v1/leads?source=Referral&spam=active", headers=STAFF_HEADERS
    ).json()["leads"]
    assert [lead["id"] for lead in active] == [lead_id]

    deleted = client.delete(f"/api/benson/v1/leads/{lead_id}", headers=STAFF_HEADERS)
    assert deleted.status_code == 204
    assert (
        client.get(f"/api/benson/v1/leads/{lead_id}", headers=STAFF_HEADERS).status_code
        == 404
    )
    assert (
        client.get("/api/benson/v1/leads?spam=all", headers=STAFF_HEADERS).json()[
            "leads"
        ]
        == []
    )


def test_lead_workspace_denies_non_operations_roles(
    isolated_settings: Settings,
) -> None:
    lead_id = post_signed_lead(
        isolated_settings, canonical_lead(), key="role-scope"
    ).json()["lead_id"]
    field_principal = Principal(
        email="field@example.com", role=Role.FIELD, subject="field"
    )
    app.dependency_overrides[require_operations_staff] = lambda: (
        require_operations_staff(field_principal)
    )
    try:
        response = client.get(f"/api/benson/v1/leads/{lead_id}")
    finally:
        app.dependency_overrides.pop(require_operations_staff, None)
    assert response.status_code == 403


def test_staff_attachment_download_is_authenticated(
    isolated_settings: Settings,
) -> None:
    created = post_signed_lead(
        isolated_settings, canonical_lead(), key="secure-file"
    ).json()
    client.post(
        f"/uploads/{created['upload_session_id']}",
        files=[("files", ("window.jpg", b"\xff\xd8\xffjpeg-data", "image/jpeg"))],
    )
    detail = client.get(
        f"/api/benson/v1/leads/{created['lead_id']}", headers=STAFF_HEADERS
    ).json()
    attachment_id = detail["attachments"][0]["id"]
    assert "storage_key" not in detail["attachments"][0]
    assert client.get(f"/api/benson/v1/attachments/{attachment_id}").status_code == 503
    downloaded = client.get(
        f"/api/benson/v1/attachments/{attachment_id}", headers=STAFF_HEADERS
    )
    assert downloaded.content == b"\xff\xd8\xffjpeg-data"
    assert downloaded.headers["content-type"] == "image/jpeg"


def test_read_gcs_upload_uses_private_configured_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_mock = MagicMock()
    client_mock.bucket.return_value.blob.return_value.download_as_bytes.return_value = (
        b"private"
    )
    monkeypatch.setattr(
        "app.object_storage.gcs.Client", MagicMock(return_value=client_mock)
    )
    settings = Settings(upload_bucket="private-uploads")
    assert read_upload(settings, "gs://private-uploads/leads/1/file.pdf") == b"private"


def test_upload_validation_rejects_missing_session_and_spoofed_type(
    isolated_settings: Settings,
) -> None:
    assert client.get("/uploads/missing").status_code == 404
    lead = post_signed_lead(
        isolated_settings, canonical_lead(), key="upload-spoof"
    ).json()
    response = client.post(
        f"/uploads/{lead['upload_session_id']}",
        files=[("files", ("payload.jpg", b"not-an-image", "image/jpeg"))],
    )
    assert response.status_code == 415


def test_upload_session_enforces_cumulative_file_quota(
    isolated_settings: Settings,
) -> None:
    isolated_settings.upload_session_max_files = 1
    lead = post_signed_lead(
        isolated_settings, canonical_lead(), key="upload-quota"
    ).json()
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
    monkeypatch.setattr(
        "app.object_storage.gcs.Client", MagicMock(return_value=client_mock)
    )
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
    blob.upload_from_string.assert_called_once_with(
        b"\xff\xd8\xffphoto", content_type="image/jpeg"
    )
    delete_upload(settings, storage_key)
    blob.delete.assert_called_once()


def test_skill_catalog_is_pinned_and_role_scoped() -> None:
    response = client.get("/api/benson/v1/ai/skills", headers=STAFF_HEADERS)
    assert response.status_code == 200
    assert response.json()["source_commit"].startswith("34e0d783")
    assert any(skill["id"] == "estimate-builder" for skill in response.json()["skills"])
    catalog = load_registry(
        str(Path(__file__).resolve().parents[2] / "skills" / "registry.json")
    )
    assert catalog.get("missing") is None
    assert catalog.get("estimate-builder") is not None


def test_ai_skill_creates_owner_approved_persisted_proposal(
    isolated_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = AsyncMock(return_value={"output_text": "Draft estimate"})
    monkeypatch.setattr("app.ai_routes.run_agent_prompt", gateway)
    lead_id = post_signed_lead(isolated_settings, canonical_lead()).json()["lead_id"]
    run = client.post(
        "/api/benson/v1/ai/runs",
        headers=STAFF_HEADERS,
        json={
            "skill_id": "estimate-builder",
            "prompt": "Draft from supplied scope",
            "lead_id": lead_id,
        },
    )
    assert run.status_code == 200
    assert run.json()["status"] == "confirmation_required"
    assert gateway.await_args is not None
    model_prompt = gateway.await_args.args[1]
    assert '"project_description": "Two windows need review."' in model_prompt
    assert "homeowner@example.com" not in model_prompt
    assert "458-555-0100" not in model_prompt
    assert "Test Homeowner" not in model_prompt
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
    isolated_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead_id = post_signed_lead(isolated_settings, canonical_lead()).json()["lead_id"]
    missing = client.post(
        "/api/benson/v1/ai/runs",
        headers=STAFF_HEADERS,
        json={"skill_id": "missing", "prompt": "No", "lead_id": lead_id},
    )
    assert missing.status_code == 404
    from app.ai_gateway import AiGatewayUnavailable

    monkeypatch.setattr(
        "app.ai_routes.run_agent_prompt",
        AsyncMock(side_effect=AiGatewayUnavailable("offline")),
    )
    failed = client.post(
        "/api/benson/v1/ai/runs",
        headers=STAFF_HEADERS,
        json={
            "skill_id": "historical-cost-analyzer",
            "prompt": "Summarize supplied costs",
            "lead_id": lead_id,
        },
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
    assert (
        evaluate_agent_action(Role.OWNER, ActionRisk.INTERNAL).confirmation_required
        is False
    )
    assert (
        evaluate_agent_action(
            Role.OWNER, ActionRisk.EXTERNAL_SEND
        ).confirmation_required
        is True
    )
    assert (
        evaluate_agent_action(
            Role.ACCOUNTING, ActionRisk.FINANCIAL
        ).confirmation_required
        is True
    )
    assert evaluate_agent_action(Role.FIELD, ActionRisk.FINANCIAL).allowed is False
