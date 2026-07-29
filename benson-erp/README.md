# Benson Construction ERP

An open, modular, self-hosted construction operating system. The repository is a modular monolith: one FastAPI deployment, one React application, one PostgreSQL database, and independently owned business modules.

## Current milestone

The staff ERP includes the connected lead-to-project workflow, employee
identity and activation, native scheduling, offline certified time, payroll
export/reconciliation, and federal labor accounting. See
[docs/backlog.md](docs/backlog.md) for the precise completed and remaining
boundaries.

## Local development

1. Copy `.env.example` to `.env` and replace every development secret.
2. Run `docker compose up --build`.
3. Open the API documentation at `http://benson-ai:8000/docs` and the web app at `http://benson-ai:5173`.

Production configuration is fail-closed and must never reuse the example credentials.
The Git-to-Cloud Run release procedure is documented in
[DEPLOYMENT.md](DEPLOYMENT.md).

## Database and first administrator

Apply migrations with the database-owner URL, then create the first tenant administrator through the supported command (not direct SQL):

```bash
MIGRATION_DATABASE_URL=postgresql+asyncpg://... alembic upgrade head
benson-erp create-admin \
  --organization "Benson Enterprises" \
  --slug benson-enterprises \
  --email administrator@example.com
```

The administrator command prompts for a password without echoing it and hashes it with Argon2id. Replace the example email with the authorized administrator's real work email.

See [Security configuration](docs/security-configuration.md) for production secrets, MFA, session policy, recovery codes, and incident-response actions.

## Operations

API liveness is available at `http://benson-ai:8000/health/live`, dependency
readiness at `http://benson-ai:8000/health/ready`, and Prometheus-compatible
metrics at `http://benson-ai:8000/metrics`. See
[Observability and health](docs/observability.md) for structured log,
correlation-ID, tracing, metrics, and alerting guidance.

## Verification

Unit, PostgreSQL integration, migration, frontend, and real-stack Playwright
commands are documented in [Testing and release gates](docs/testing.md).
