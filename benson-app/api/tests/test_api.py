from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.policy import ActionRisk, evaluate_agent_action
from app.domain import Role

client = TestClient(app)


def test_health_is_benson_usd_oregon_profile():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["profile"] == {"currency": "USD", "state": "OR", "county": "Harney"}


def test_website_lead_rejects_missing_key():
    response = client.post("/api/v1/webhook-leads/incoming/benson-website/", json={})
    assert response.status_code == 401


def test_website_lead_returns_receipt_and_upload_handoff():
    settings = get_settings()
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


def test_agent_policy_requires_confirmation_for_external_and_money_actions():
    assert evaluate_agent_action(Role.OWNER, ActionRisk.INTERNAL).confirmation_required is False
    assert evaluate_agent_action(Role.OWNER, ActionRisk.EXTERNAL_SEND).confirmation_required is True
    assert evaluate_agent_action(Role.ACCOUNTING, ActionRisk.FINANCIAL).confirmation_required is True
    assert evaluate_agent_action(Role.FIELD, ActionRisk.FINANCIAL).allowed is False
