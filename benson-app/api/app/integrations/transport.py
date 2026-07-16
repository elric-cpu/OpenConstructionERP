import asyncio
from collections.abc import Mapping
from typing import Any

import httpx


class ProviderDeliveryError(RuntimeError):
    pass


class AsyncJsonTransport:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        timeout_seconds: float = 10,
        max_attempts: int = 3,
    ) -> None:
        self._client = client
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts

    async def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    response = await client.post(
                        url,
                        headers=headers,
                        params=params,
                        json=payload,
                        timeout=self._timeout,
                    )
                    if response.status_code not in {429, 500, 502, 503, 504}:
                        response.raise_for_status()
                        result = response.json()
                        if not isinstance(result, dict):
                            raise ProviderDeliveryError(
                                "Provider response was not an object"
                            )
                        return result
                except (httpx.HTTPError, ValueError) as error:
                    if attempt == self._max_attempts:
                        raise ProviderDeliveryError(
                            "Provider request failed"
                        ) from error
                if attempt < self._max_attempts:
                    await asyncio.sleep(0.25 * (2 ** (attempt - 1)))
            raise ProviderDeliveryError("Provider retries exhausted")
        finally:
            if owns_client:
                await client.aclose()
