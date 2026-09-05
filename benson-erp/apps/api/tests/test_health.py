import json
import logging
import uuid

import pytest
from app.core.health import ReadinessResult
from app.core.observability import JsonFormatter, correlation_scope
from app.main import app
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr


@pytest.mark.asyncio
async def test_liveness() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://benson-ai") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_request_correlation_and_metrics() -> None:
    correlation_id = str(uuid.uuid4())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://benson-ai",
    ) as client:
        response = await client.get(
            "/health/live",
            headers={"X-Correlation-ID": correlation_id},
        )
        invalid_response = await client.get(
            "/health/live",
            headers={"X-Correlation-ID": "unsafe-value"},
        )
        metrics = await client.get("/metrics")

    assert response.headers["X-Correlation-ID"] == correlation_id
    assert uuid.UUID(invalid_response.headers["X-Correlation-ID"])
    assert metrics.status_code == 200
    assert "benson_http_requests_total" in metrics.text
    assert 'route="/health/live"' in metrics.text


@pytest.mark.asyncio
async def test_cors_allows_and_exposes_correlation_header() -> None:
    origin = app.state.settings.cors_origins.split(",")[0]
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://benson-ai",
    ) as client:
        preflight = await client.options(
            "/health/live",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Correlation-ID",
            },
        )
        response = await client.get("/health/live", headers={"Origin": origin})

    assert preflight.status_code == 200
    assert "x-correlation-id" in preflight.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-expose-headers"].lower() == "x-correlation-id"


@pytest.mark.asyncio
async def test_metrics_token_is_enforced_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app.state.settings,
        "metrics_bearer_token",
        SecretStr("collector-secret"),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://benson-ai",
    ) as client:
        denied = await client.get("/metrics")
        allowed = await client.get(
            "/metrics",
            headers={"Authorization": "Bearer collector-secret"},
        )

    assert denied.status_code == 401
    assert denied.headers["WWW-Authenticate"] == "Bearer"
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_readiness_reports_dependency_state(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unavailable(*args: object) -> ReadinessResult:
        return ReadinessResult(
            ready=False,
            checks={"database": "ok", "redis": "unavailable"},
        )

    monkeypatch.setattr("app.main.check_readiness", unavailable)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://benson-ai",
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "ok", "redis": "unavailable"},
    }


def test_json_logging_includes_correlation_and_redacts_unlisted_extras() -> None:
    formatter = JsonFormatter("test-service", "test")
    record = logging.LogRecord(
        "benson.test",
        logging.INFO,
        __file__,
        1,
        "completed",
        (),
        None,
    )
    record.http_status = 200
    record.secret = "must-not-appear"
    correlation_id = str(uuid.uuid4())

    with correlation_scope(correlation_id):
        payload = json.loads(formatter.format(record))

    assert payload["correlation_id"] == correlation_id
    assert payload["http_status"] == 200
    assert "must-not-appear" not in formatter.format(record)
