from typing import Any, cast

import httpx

from .config import Settings


class AiGatewayUnavailable(RuntimeError):
    pass


async def run_agent_prompt(
    settings: Settings,
    prompt: str,
    system: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=settings.ai_timeout_seconds)
    try:
        response = await http.post(
            f"{str(settings.fcc_base_url).rstrip('/')}/v1/responses",
            headers={"authorization": f"Bearer {settings.fcc_auth_token}"},
            json={
                "model": settings.fcc_model,
                "input": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_output_tokens": 1800,
            },
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())
    except (httpx.HTTPError, ValueError) as error:
        raise AiGatewayUnavailable("Benson AI gateway is temporarily unavailable") from error
    finally:
        if owns_client:
            await http.aclose()
