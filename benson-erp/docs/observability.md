# Observability and health

## Request correlation

Every HTTP response includes `X-Correlation-ID`. A caller may provide a UUID in
that header; malformed values are replaced with a generated UUID so untrusted
text cannot enter structured logs. The request correlation ID is stored on
audit and outbox records created by that request and is propagated in Celery
task arguments. This provides one join key across API logs, traces, audit
history, outbox delivery, and worker logs.

Do not log authorization headers, cookies, request bodies, signed URLs,
integration credentials, personal tax data, wage data, or document contents.
The JSON formatter emits only explicitly allowlisted structured fields.

## JSON logs

API, worker, and scheduler processes emit one JSON object per line to standard
output. Common fields are:

- `timestamp`, `severity`, `logger`, `message`
- `service`, `environment`, `correlation_id`
- OpenTelemetry `trace_id` and `span_id` while a span is active
- allowlisted HTTP, tenant, event, duration, and outcome fields

Google Cloud Run collects standard output in Cloud Logging. Filter on
`jsonPayload.correlation_id` for a business action or `jsonPayload.trace_id`
for its distributed trace. Set `LOG_LEVEL` to `INFO` in normal production
operation; use `DEBUG` only for a bounded incident window.

## Health contracts

- `GET /health/live` proves the API process can serve requests. It does not
  contact dependencies and is suitable for liveness/restart decisions.
- `GET /health/ready` probes PostgreSQL and Redis concurrently with a bounded
  timeout. It returns `200` and `status=ready` only when both are available;
  otherwise it returns `503` with generic `ok` or `unavailable` states.
- Docker Compose marks the API healthy from readiness and validates Celery
  worker responsiveness with `inspect ping`.

Readiness responses never include connection strings, hostnames, exception
messages, credentials, or stack traces.

## Prometheus metrics

When `METRICS_ENABLED=true`, `GET /metrics` exposes Prometheus text format:

- `benson_http_requests_total`
- `benson_http_request_duration_seconds`
- `benson_http_requests_in_progress`

Routes use FastAPI templates such as `/api/v1/leads/{lead_id}` rather than raw
paths, preventing customer IDs from becoming high-cardinality labels. Restrict
the production metrics endpoint to the monitoring collector with load-balancer
or service-level access policy; it is not a public reporting API. Production
also requires `METRICS_BEARER_TOKEN`, supplied to the collector through Secret
Manager and sent as an `Authorization: Bearer` header.

## OpenTelemetry

FastAPI and SQLAlchemy are instrumented. Celery producer/consumer propagation is
enabled for workers and scheduled jobs. Configure:

```text
OTEL_SERVICE_NAME=benson-erp-api
OTEL_EXPORTER_OTLP_ENDPOINT=https://collector.example/v1/traces
OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20...
OTEL_TRACE_SAMPLE_RATIO=0.1
```

Without an OTLP endpoint, spans remain local/no-export and application startup
continues. Production should send OTLP/HTTP to a trusted collector that exports
to Cloud Trace or another OpenTelemetry-compatible backend. Store exporter
credentials in Secret Manager, not `.env` or source control.

## Local checks

```bash
curl --fail http://benson-ai:8000/health/live
curl --fail http://benson-ai:8000/health/ready
curl --fail http://benson-ai:8000/metrics
docker compose exec worker \
  celery -A app.workers.celery_app:celery_app inspect ping --timeout=5
docker compose logs --tail=100 api worker scheduler
```

Alert in production on sustained readiness failure, HTTP 5xx rate, latency
percentiles, worker unavailability, outbox dead letters, repeated authentication
failures, and backup/restore failures. Alert thresholds and Cloud Monitoring
resources belong to the Google Cloud infrastructure slice.
