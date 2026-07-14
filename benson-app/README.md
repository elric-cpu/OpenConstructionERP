# Benson Operations

Benson Home Solutions' focused construction operating system. This application is a full Benson-specific rewrite maintained in a sparse branch of the OpenConstructionERP repository so upstream history, AGPL attribution, and selected reference implementations remain available without shipping the global 161-module product.

## Operating profile

- English, USD, imperial units, United States, Oregon, Harney County
- Current release: durable website CRM intake, private customer uploads, staff lead queue, Google Workspace roles, immutable audit events, and confirmation-gated AI drafts
- Planned modules: estimating, jobs, schedules, field records, documents, procurement, equipment, quality, safety, service, invoicing, and customer/subcontractor portals
- QuickBooks Online remains the planned accounting system of record; this release defines ownership policy but does not yet sync accounting data
- AI drafts route through the configured Free Claude Code gateway; this release does not execute mutations or external sends

## Development

```bash
cd api
uv sync --extra dev
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

cd ../web
npm ci
npm run dev -- --host 0.0.0.0
```

Use `benson-ai` rather than `localhost` when sharing local URLs.

Copy `api/.env.example` to `api/.env` and replace every placeholder before a shared deployment. Production starts fail closed unless PostgreSQL, a private Google Cloud Storage bucket, the website HMAC secret, and the Google Workspace OAuth client ID are configured. SQLite and local private-file storage remain development-only fallbacks.

## Website intake contract

The public website sends leads to `POST /api/benson/v1/intake/leads`. Every request carries an independent idempotency key plus a timestamped HMAC-SHA256 signature over the exact JSON body. The ERP persists the lead before returning success and issues a durable, expiring upload session for customer photos and PDFs. Staff lead, dashboard, module, and AI routes require a verified `@bensonhomesolutions.com` Google identity; roles are assigned by server configuration, never by browser claims.

The previous OpenConstructionERP webhook is not exposed by Benson Operations. New website code must use the signed intake route.

## Construction AI skills

`skills/registry.json` is the reviewed metadata allowlist. It pins the DDC reference collection to commit `34e0d78332ce6a510706703dcb61793ee85e4aed` and exposes only the Benson-approved subset, scoped by role and action risk. The full 221 source instructions are retained in the shared `ddc-construction-ops` reference gateway for review, but this release deliberately uses server-owned prompts instead of executing arbitrary upstream skill text. The Free Claude Code gateway creates drafts and proposals only.

## Verification

```bash
cd web
npm ci
npx playwright install chromium
cd ..
npm run verify
```

The API gate runs Ruff formatting and linting, strict mypy, and pytest with an 80% coverage floor. The web gate runs Prettier, ESLint, TypeScript, a production Vite build, and local Playwright against desktop Chrome and Pixel 7 viewports. Browser checks cover the mobile navigation rail, overflow, empty-state honesty, and serious/critical axe accessibility findings.

## License

AGPL-3.0-or-later. See the repository root for upstream copyright and attribution.
