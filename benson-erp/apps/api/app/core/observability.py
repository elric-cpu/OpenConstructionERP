import json
import logging
import secrets
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import Settings

CORRELATION_HEADER = "X-Correlation-ID"
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_LOG_FIELDS = (
    "duration_ms",
    "event_id",
    "http_method",
    "http_route",
    "http_status",
    "outcome",
    "tenant_id",
)

HTTP_REQUESTS = Counter(
    "benson_http_requests_total",
    "Completed HTTP requests.",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "benson_http_request_duration_seconds",
    "HTTP request duration.",
    ("method", "route"),
)
HTTP_IN_PROGRESS = Gauge(
    "benson_http_requests_in_progress",
    "HTTP requests currently in progress.",
    ("method",),
)


def correlation_id() -> str | None:
    return _correlation_id.get()


def correlation_uuid() -> uuid.UUID:
    current = correlation_id()
    return uuid.UUID(current) if current else uuid.uuid4()


def parse_or_create_correlation_id(value: str | None) -> str:
    if value:
        try:
            return str(uuid.UUID(value))
        except ValueError:
            pass
    return str(uuid.uuid4())


@contextmanager
def correlation_scope(value: str) -> Iterator[None]:
    token: Token[str | None] = _correlation_id.set(parse_or_create_correlation_id(value))
    try:
        yield
    finally:
        _correlation_id.reset(token)


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str, environment: str) -> None:
        super().__init__()
        self.service_name = service_name
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "environment": self.environment,
        }
        current_correlation_id = correlation_id()
        if current_correlation_id:
            payload["correlation_id"] = current_correlation_id
        span = trace.get_current_span()
        span_context = span.get_span_context()
        if span_context.is_valid:
            payload["trace_id"] = format(span_context.trace_id, "032x")
            payload["span_id"] = format(span_context.span_id, "016x")
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for field in _LOG_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(settings.otel_service_name, settings.environment))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    for logger_name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.disabled = False

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True


def configure_tracing(app: FastAPI, engine: AsyncEngine, settings: Settings) -> None:
    provider = configure_tracer(settings)
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health/live,health/ready,metrics",
        tracer_provider=provider,
    )
    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine,
        tracer_provider=provider,
    )


def configure_tracer(settings: Settings) -> TracerProvider:
    provider = TracerProvider(
        resource=Resource.create(
            {
                SERVICE_NAME: settings.otel_service_name,
                DEPLOYMENT_ENVIRONMENT: settings.environment,
            }
        ),
        sampler=ParentBased(TraceIdRatioBased(settings.otel_trace_sample_ratio)),
    )
    if settings.otel_exporter_otlp_endpoint:
        exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            headers=_parse_headers(settings.otel_exporter_otlp_headers),
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


async def metrics_response(request: Request) -> Response:
    configured_token = request.app.state.settings.metrics_bearer_token
    if configured_token is not None:
        supplied = request.headers.get("Authorization", "")
        expected = f"Bearer {configured_token.get_secret_value()}"
        if not secrets.compare_digest(supplied, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Metrics authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_correlation_id = parse_or_create_correlation_id(
            request.headers.get(CORRELATION_HEADER)
        )
        method = request.method
        started = time.perf_counter()
        HTTP_IN_PROGRESS.labels(method=method).inc()
        with correlation_scope(request_correlation_id):
            try:
                response = await call_next(request)
            except Exception:
                route_path, duration = self._record(request, method, 500, started)
                logging.getLogger("benson.http").exception(
                    "request_failed",
                    extra={
                        "duration_ms": round(duration * 1000, 3),
                        "http_method": method,
                        "http_route": route_path,
                        "http_status": 500,
                    },
                )
                raise
            finally:
                HTTP_IN_PROGRESS.labels(method=method).dec()
            response.headers[CORRELATION_HEADER] = request_correlation_id
            route_path, duration = self._record(
                request,
                method,
                response.status_code,
                started,
            )
            logging.getLogger("benson.http").info(
                "request_completed",
                extra={
                    "duration_ms": round(duration * 1000, 3),
                    "http_method": method,
                    "http_route": route_path,
                    "http_status": response.status_code,
                },
            )
            return response

    @staticmethod
    def _record(
        request: Request,
        method: str,
        status: int,
        started: float,
    ) -> tuple[str, float]:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        duration = time.perf_counter() - started
        HTTP_REQUESTS.labels(method=method, route=route_path, status=str(status)).inc()
        HTTP_DURATION.labels(method=method, route=route_path).observe(duration)
        return route_path, duration


def _parse_headers(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    headers: dict[str, str] = {}
    for item in value.split(","):
        key, separator, header_value = item.partition("=")
        if not separator or not key.strip():
            raise ValueError("OTLP headers must use comma-separated key=value pairs")
        headers[key.strip()] = header_value.strip()
    return headers
