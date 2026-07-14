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
