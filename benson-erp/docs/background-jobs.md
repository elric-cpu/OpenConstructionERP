# Background jobs

## Delivery contract

Business transactions write domain state and an `outbox_events` row in the
same PostgreSQL transaction. Celery Beat runs the dispatcher every two seconds.
The dispatcher enumerates organizations, establishes PostgreSQL tenant context,
and leases ready rows with `FOR UPDATE SKIP LOCKED`. It then publishes only the
tenant ID and event ID to Redis. A Celery worker reloads the authoritative event
under the same tenant context before running registered handlers.

Delivery is at least once. The platform does not claim exactly-once delivery:
an external provider can accept a request immediately before a worker loses its
acknowledgement. Every provider-facing handler must therefore use the event
idempotency key or a provider idempotency key derived from it. Internal handlers
write `inbox_receipts` in the same transaction as their effects; the unique
tenant/event/handler constraint prevents duplicate internal effects.

## Event states

- `PENDING`: committed and eligible for dispatch.
- `LEASED`: exclusively leased by a dispatcher.
- `PROCESSING`: locked by a worker and executing handlers.
- `RETRY`: failed and delayed until `next_attempt_at`.
- `PUBLISHED`: every registered handler completed and receipts were committed.
- `DEAD_LETTER`: the configured attempt limit was reached.

Attempts are counted when a lease is acquired. Retry delay is exponential:
`base_seconds * 2^(attempt_count - 1)`, capped by
`WORKER_RETRY_MAX_SECONDS`. Expired leases are eligible for safe redelivery.
The last exception class and message are retained on the event; secrets and
request payloads must not be placed in exception messages.

## Local operation

Run migrations before starting the application services:

```bash
docker compose run --rm \
  -e MIGRATION_DATABASE_URL=postgresql+asyncpg://DATABASE_OWNER@postgres:5432/benson_erp \
  api alembic -c /app/alembic.ini upgrade head
docker compose up --build api worker scheduler web
```

Use a secret-managed owner credential for `MIGRATION_DATABASE_URL`; the API
runtime role is intentionally unable to create tables, types, or policies.

Inspect worker and scheduler health:

```bash
docker compose ps
docker compose logs --tail=100 worker scheduler
docker compose exec worker celery -A app.workers.celery_app:celery_app inspect ping
```

For deterministic PostgreSQL tests, stop `worker` and `scheduler` first so the
test process is the only dispatcher:

```bash
docker compose stop worker scheduler
RUN_POSTGRES_TESTS=1 pytest -m postgres
```

## Recovery and dead letters

Operational recovery is database-backed: restarting Redis, Beat, or workers
does not lose committed events. An operator should first correct the underlying
provider, configuration, or handler defect. Dead-letter replay must create an
audited administration action that clears the dead-letter timestamp, resets
the event to `RETRY`, and assigns a new `next_attempt_at`; direct production
database edits are prohibited. That administration workflow is a subsequent
platform slice. Until it exists, dead-letter events are inspectable but are not
replayable through the application.

## Adding a handler

Register a stable handler name for an explicit event type in
`app.workers.registry`. A handler receives the tenant-scoped SQLAlchemy session
and immutable outbox event. Keep database effects inside that session. External
calls need a durable provider idempotency key and should store the provider
reference for reconciliation. Add tests for success, duplicate delivery,
provider failure, retry exhaustion, and cross-tenant denial.
