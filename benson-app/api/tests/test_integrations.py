from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from app.integrations.config import (
    GoogleAdsConfig,
    GoogleBusinessConfig,
    IntegrationConfigurationError,
    MetaConfig,
)
from app.integrations.google_ads import GoogleAdsAdapter, build_offline_conversion
from app.integrations.google_business import (
    GoogleBusinessProfileAdapter,
    build_local_post,
)
from app.integrations.meta_capi import MetaConversionsAdapter, build_meta_event
from app.integrations.models import ConsentStatus, IntegrationEvent
from app.integrations.privacy import ConsentRequired, normalize_email, sha256
from app.integrations.transport import AsyncJsonTransport


def event(consent: ConsentStatus = ConsentStatus.GRANTED) -> IntegrationEvent:
    return IntegrationEvent(
        event_id="lead-123-qualified",
        event_name="Lead",
        occurred_at=datetime(2026, 7, 16, 12, 30, tzinfo=UTC),
        source_url="https://bensonhomesolutions.com/contact",
        consent=consent,
        email=" First.Last+tag@Gmail.com ",
        phone=" +1 (541) 555-0100 ",
        first_name="Jane",
        last_name="Doe",
        city="Burns",
        state="OR",
        postal_code="97720",
        country_code="US",
        gclid="test-click",
        fbc="fb.1.click",
        fbp="fb.1.browser",
        value=Decimal("125.50"),
    )


def test_google_payload_hashes_and_minimizes_customer_data() -> None:
    payload = build_offline_conversion(event(), "customers/12/conversionActions/34")
    assert payload["orderId"] == sha256("lead-123-qualified")
    assert payload["conversionDateTime"] == "2026-07-16 12:30:00+00:00"
    assert payload["consent"] == {"adUserData": "GRANTED"}
    assert payload["gclid"] == "test-click"
    assert payload["userIdentifiers"] == [
        {"hashedEmail": sha256("firstlast@gmail.com")},
        {"hashedPhoneNumber": sha256("+1(541)555-0100")},
    ]
    assert "Jane" not in str(payload)
    assert normalize_email("A.B+tag@gmail.com") == "ab@gmail.com"


def test_ad_payloads_fail_closed_without_consent() -> None:
    denied = event(ConsentStatus.DENIED)
    with pytest.raises(ConsentRequired):
        build_offline_conversion(denied, "customers/12/conversionActions/34")
    with pytest.raises(ConsentRequired):
        build_meta_event(denied)


def test_meta_payload_uses_event_id_and_hashes_identifiers() -> None:
    payload = build_meta_event(event())
    assert payload["event_id"] == "lead-123-qualified"
    assert payload["action_source"] == "website"
    assert payload["user_data"]["em"] == [sha256("firstlast@gmail.com")]
    assert payload["user_data"]["fbc"] == "fb.1.click"
    assert payload["custom_data"] == {"value": 125.5, "currency": "USD"}


@pytest.mark.asyncio
async def test_adapters_are_disabled_and_dry_run_by_default() -> None:
    transport = AsyncMock()
    google = GoogleAdsAdapter(
        GoogleAdsConfig(False, True, None, None, None, "action"),
        AsyncMock(),
        transport,
    )
    meta = MetaConversionsAdapter(MetaConfig(False, True, None, None), transport)
    google_result = await google.publish(google.command(event()))
    meta_result = await meta.publish(meta.command(event()))
    assert google_result.dry_run and not google_result.accepted
    assert meta_result.dry_run and not meta_result.accepted
    transport.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_gbp_requires_user_oauth_for_live_publish() -> None:
    adapter = GoogleBusinessProfileAdapter(
        GoogleBusinessConfig(True, False, "account", "location", None), AsyncMock()
    )
    command = adapter.command(idempotency_key="post-1", summary="Project update")
    with pytest.raises(
        IntegrationConfigurationError, match="business-owner user OAuth"
    ):
        await adapter.publish(command)


def test_gbp_post_builder_rejects_non_https_links() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        build_local_post("Update", "http://example.com")


@pytest.mark.asyncio
async def test_transport_retries_transient_failure() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503 if attempts == 1 else 200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AsyncJsonTransport(
            client, max_attempts=2, timeout_seconds=1
        ).post("https://provider.example/events", payload={"data": []})
    assert result == {"ok": True}
    assert attempts == 2
