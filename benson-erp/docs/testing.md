# Testing and release gates

The repository separates fast unit checks from PostgreSQL integration tests and
real-stack browser acceptance tests. CI treats all three as release-blocking.

## Backend

Run static checks and the full PostgreSQL suite:

```bash
uv run ruff check .
uv run mypy apps/api/app
RUN_POSTGRES_TESTS=1 \
DATABASE_URL=postgresql+asyncpg://benson_app:benson-app-development-only@127.0.0.1:55432/benson_erp \
TEST_DATABASE_OWNER_URL=postgresql+asyncpg://benson:benson-development-only@127.0.0.1:55432/benson_erp \
uv run pytest apps/api/tests
uv run alembic check
```

The URLs above are development-only. The owner URL is used only to clean up
database-trigger-protected immutable records created by integration tests.
Never expose or reuse either credential outside the local Compose environment.

## Frontend

```bash
cd apps/web
npm run lint
npm run build
npm run test
npm run typecheck:e2e
```

The lint configuration enforces the Benson frontend maintainability limits:
350 nonblank, noncomment lines per source file and a warning at 150 lines per
function or component.

## Real-stack browser acceptance

The Lead-to-Project acceptance suite runs against PostgreSQL, the FastAPI
service, MinIO, Redis, and the actual Vite application. It does not mock API
responses. Start the Compose stack and create a dedicated test tenant with the
supported administrator command. Use an ephemeral password and never commit it.

```bash
docker compose up -d --build
docker compose run --rm -T \
  -e DATABASE_URL=postgresql+asyncpg://benson:benson-development-only@postgres:5432/benson_erp \
  api benson-erp create-admin \
  --organization "Benson E2E" \
  --slug benson-e2e \
  --email e2e@bensonhomesolutions.com \
  --google-domain bensonhomesolutions.com
```

The command prompts twice for the password. Then run:

```bash
cd apps/web
npx playwright install
E2E_BASE_URL=http://benson-ai:5173 \
E2E_ORGANIZATION=benson-e2e \
E2E_EMAIL=e2e@bensonhomesolutions.com \
E2E_PASSWORD='use-the-ephemeral-password' \
npm run test:e2e
```

The suite covers desktop Chromium, Firefox, WebKit, and mobile Chromium. It
proves the connected Lead → Customer and Property → Estimate → Proposal →
Acceptance → Contract and Project workflow, immutable proposal download,
client-safe proposal fields, project budget creation, and mobile viewport fit.
It also proves Employee Draft → Manager Approval → durable mock Directory
identity creation and Project → Schedule Activity → conflict-checked Employee
Assignment. It also takes a daily time operation offline, verifies visible
IndexedDB queue state, restores connectivity, and proves one server record is
created. The mock is limited to non-production Compose environments.
Failed runs retain screenshots and traces under `test-results/`.

Employee activation also has focused backend coverage for inspect, completion,
single use, least-privilege membership, real login, worker idempotency, and
secret exclusion from audit/outbox payloads. The frontend activation tests
cover fragment-token removal, generic missing/rejected-token errors, password
confirmation, and success routing. These focused checks do not replace
the remaining two-user browser gate: manager approval and mock delivery →
employee activation/login → self-certification → manager approval → payroll
lock/export/import/reconciliation.

## CI evidence

The `e2e` GitHub Actions job provisions a fresh Compose environment, applies
migrations, generates a temporary administrator password, executes every
browser project, uploads traces and service logs, and destroys the environment.
It depends on the backend, frontend, and container jobs, so it cannot run as a
substitute for those earlier gates.
