# Benson ERP agent instructions

- This subtree is the ground-up Benson Construction ERP production application.
- `apps/api` owns FastAPI, authorization, tenancy, persistence, migrations, providers, and workers.
- `apps/web` owns the authenticated React/Vite staff application.
- Preserve PostgreSQL row-level tenant isolation, immutable financial artifacts, audited transitions, outbox idempotency, secure sessions, and production fail-closed configuration.
- Keep React/TypeScript source files at or below 350 nonblank, noncomment lines and functions/components at or below 150.
- Apply schema changes only through Alembic. The runtime database role must not receive schema DDL privileges.
- Build one immutable image for the API, SPA, jobs, and worker pools. Never deploy `latest`.
- Run the backend, frontend, PostgreSQL/Alembic, production-image, and Playwright gates before release.
