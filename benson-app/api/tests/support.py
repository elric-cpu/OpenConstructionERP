import base64
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from httpx2 import Response

from app.config import Settings
from app.directory_provider import DirectoryIdentity
from app.identity_provisioning_worker import IdentityProvisioningWorker
from app.main import app
from app.signing import signature_for
from app.storage import operations_store

client = TestClient(app)
STAFF_HEADERS = {"X-Dev-Staff-Email": "office@bensonhomesolutions.com"}


class VerifiedTestDirectoryProvider:
    def create_identity(self, **values: object) -> DirectoryIdentity:
        return self._identity(values, "directory_created")

    def verify_identity(self, **values: object) -> DirectoryIdentity:
        return self._identity(values, "no_paid_license")

    def suspend_identity(self, **values: object) -> DirectoryIdentity:
        identity = self._identity(values, "directory_suspended")
        return DirectoryIdentity(
            external_user_id=identity.external_user_id,
            primary_email=identity.primary_email,
            org_unit_path=identity.org_unit_path,
            suspended=True,
            verification_status="verified",
            provider_code=identity.provider_code,
        )

    @staticmethod
    def _identity(values: dict[str, object], code: str) -> DirectoryIdentity:
        return DirectoryIdentity(
            external_user_id="test-directory-user",
            primary_email=str(values["primary_email"]),
            org_unit_path=str(values.get("org_unit_path", "")),
            suspended=False,
            verification_status="verified",
            provider_code=code,
        )


def provision_test_identity(settings: Settings, employee_id: str) -> None:
    result = IdentityProvisioningWorker(
        operations_store(settings.resolved_database_url()).engine,
        VerifiedTestDirectoryProvider(),
        settings.employee_document_key_bytes(),
    ).process_one(worker="test-identity-worker")
    assert result is not None
    assert result["employee_id"] == employee_id
    assert result["status"] == "verified"


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
        "identity_provisioning_enabled": True,
        "identity_worker_audience": "https://operations.example.com",
        "identity_worker_email": "identity-worker@example.iam.gserviceaccount.com",
        "google_directory_credentials_json": '{"type":"service_account"}',
        "google_directory_admin": "workspace-admin@bensonhomesolutions.com",
        "google_paid_license_skus": "test-paid-sku",
        "google_paid_license_skus_approved": True,
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
