import httpx
import pytest

from app.ai_gateway import AiGatewayUnavailable, run_agent_prompt
from app.config import Settings


@pytest.mark.asyncio
async def test_agent_gateway_uses_fcc_responses_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer freecc"
        return httpx.Response(200, json={"output_text": "Ready"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await run_agent_prompt(
            Settings(), "Summarize", "Use supplied records", client=client
        )
    assert result["output_text"] == "Ready"


@pytest.mark.asyncio
async def test_agent_gateway_normalizes_transport_failures() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AiGatewayUnavailable):
            await run_agent_prompt(Settings(), "Summarize", "Use supplied records", client=client)


@pytest.mark.asyncio
async def test_production_agent_gateway_uses_cloud_run_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.ai_gateway.id_token.fetch_id_token", lambda _request, audience: f"id:{audience}"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer id:https://fcc.example.com"
        return httpx.Response(200, json={"output_text": "Private gateway ready"})

    settings = Settings(
        environment="production",
        website_signing_secret="x" * 32,
        staff_google_audience="client.apps.googleusercontent.com",
        database_url="postgresql://user:pass@db/operations",
        upload_bucket="private-uploads",
        fcc_base_url="https://fcc.example.com",
        notification_worker_audience="https://operations.example.com",
        notification_worker_email="worker@example.iam.gserviceaccount.com",
        resend_api_key="resend-key",
        twilio_account_sid="AC123",
        twilio_api_key_sid="SK123",
        twilio_api_key_secret="twilio-secret",
        twilio_from_number="+15415550100",
        sms_to="+15415550101",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await run_agent_prompt(
            settings, "Summarize", "Use supplied records", client=client
        )
    assert result["output_text"] == "Private gateway ready"


@pytest.mark.asyncio
async def test_agent_gateway_parses_fcc_streaming_response() -> None:
    body = "\n".join(
        [
            "event: response.created",
            'data: {"type":"response.created","response":{"status":"in_progress"}}',
            "",
            "event: response.completed",
            'data: {"type":"response.completed","response":{"id":"resp-1","status":"completed","output":[{"type":"reasoning","content":[]},{"type":"message","content":[{"type":"output_text","text":"Fact-scoped draft"}]}]}}',
            "",
        ]
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await run_agent_prompt(
            Settings(), "Summarize", "Use supplied records", client=client
        )
    assert result["status"] == "completed"
    assert result["output_text"] == "Fact-scoped draft"
