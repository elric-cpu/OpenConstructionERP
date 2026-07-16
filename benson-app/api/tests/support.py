import base64
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from httpx2 import Response

from app.config import Settings
from app.main import app
from app.signing import signature_for

client = TestClient(app)
STAFF_HEADERS = {"X-Dev-Staff-Email": "office@bensonhomesolutions.com"}


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


def signed_headers(
    settings: Settings, body: bytes, key: str = "lead-test-1"
) -> dict[str, str]:
    timestamp = str(int(datetime.now(UTC).timestamp()))
    return {
        "content-type": "application/json",
        "Idempotency-Key": key,
        "X-Benson-Timestamp": timestamp,
        "X-Benson-Signature": signature_for(
            settings.website_signing_secret, timestamp, body
        ),
    }


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "website_signing_secret": "x" * 32,
        "employee_invite_signing_secret": "i" * 32,
        "employee_document_encryption_key": base64.b64encode(b"p" * 32).decode(),
        "staff_google_audience": "client.apps.googleusercontent.com",
        "database_url": "postgresql://user:pass@db/operations",
        "upload_bucket": "private-uploads",
        "fcc_base_url": "https://fcc.example.com",
        "notification_worker_audience": "https://operations.example.com",
        "notification_worker_email": "worker@example.iam.gserviceaccount.com",
        "resend_api_key": "resend-key",
        "twilio_account_sid": "AC123",
        "twilio_api_key_sid": "SK123",
        "twilio_api_key_secret": "twilio-secret",
        "twilio_from_number": "+15415550100",
        "sms_to": "+15415550101",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def post_signed_lead(
    settings: Settings,
    payload: dict[str, object],
    key: str = "lead-test-1",
) -> Response:
    body = json.dumps(payload, separators=(",", ":")).encode()
    return client.post(
        "/api/benson/v1/intake/leads",
        content=body,
        headers=signed_headers(settings, body, key),
    )
