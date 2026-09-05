# Phased delivery backlog

Each item is complete only with schema/migration, service authorization, audit, API/OpenAPI, responsive UI, loading/error/offline states where applicable, tests, and documentation.

## Gate 1 — Foundation and vertical slice 1

1. Platform: configuration validation, PostgreSQL sessions and RLS, organizations, users, memberships, RBAC, sessions/MFA seams, audit, outbox/jobs, file metadata/storage, observability, migration and tenant test harness.
2. CRM: leads with website/manual intake, qualification stages, deduplication, follow-up, and conversion.
3. Records: customer and property creation/reuse during lead conversion.
4. Estimating: hierarchical sections/lines, decimal cost math, markup-or-margin pricing, approval and immutable proposal version.
5. Proposal: branded HTML/PDF, internal-field suppression, acceptance audit and idempotency.
6. Project: atomic accepted-proposal conversion to contract, initial budget, project, audit, and outbox event.
7. E2E: Lead → Customer → Property → Estimate → Proposal → Project, including Tenant A/B and client-margin denial.

## Gate 2 — Vertical slice 2

Employee approval and date-effective employment; Google identity provisioning saga; native schedule; offline daily time; employee certification; supervisor approval; locked payroll period; preview; generic CSV/XLSX provider mappings; immutable export; import/reconciliation; federal charge codes and floor-check reporting. Complete adversarial, calculation, and E2E coverage before procurement or advanced modules.

Current checkpoint: employee drafts, manager approval, tenant-scoped
audit/outbox records, idempotent Cloud Identity user creation, native
project/employee scheduling, single-use ERP activation with SMTP/mock delivery,
least-privilege employee membership and login, manager reissue/status controls,
offline daily time, permission-compatible self-service entry, employee
certification,
supervisor approval, immutable corrections, payroll periods, validation/lock,
versioned mappings and rates, immutable CSV/XLSX/JSON artifacts, controlled
provider-result import, persisted reconciliation exceptions, and project labor
cost posting, canonical federal charge codes, date-effective billing rates and
qualifications, inclusive floor-check reporting, and immutable federal labor
invoice support are implemented. Adjustment exports, provider-specific
transmission/result connectors, certified payroll, and browser acceptance for
activation/login → employee certification → supervisor approval → payroll
lock/export/import/reconciliation remain before Gate 2 is complete.
Cross-browser acceptance for employee approval/identity creation, dispatch, and
offline time queue/reconnect sync is complete across Chromium, Firefox, WebKit,
and mobile Chromium. Activation has focused PostgreSQL service coverage and
frontend component coverage; it is not counted as cross-browser complete until
the full two-user journey passes.

## Later phases

3. Cost catalog, assemblies, documents, contracts.
4. Schedule, tasks, daily logs, equipment, field PWA.
5. Bids, POs, receipts, bills, budgets, job cost, invoices, payments, WIP.
6. Change orders, selections, safety, quality, punch, closeout, warranty.
7. Google/Firebase/website/accounting integrations, then Business Profile and Meta after provider approval.
8. Restoration, government contracting, rural logistics, geographic intelligence.
9. Semantic search and human-reviewed AI, followed by CAD/BIM/takeoff/4D/5D and marketplace APIs.

## First vertical-slice specification

### Invariants

- A lead belongs to exactly one tenant and may reference or create one customer/property pair.
- Conversion is idempotent and atomic; retrying cannot duplicate customers, properties, or projects.
- Estimate quantities, unit costs, markups, margins, taxes, and totals use decimal arithmetic and retain calculation inputs.
- Pricing mode is explicit: markup is `direct_cost × (1 + rate)`; margin is `direct_cost ÷ (1 - rate)`.
- Approval freezes an estimate version. Proposal rendering exposes price and scope but never cost or margin without an explicit permission.
- Proposal acceptance creates an immutable acceptance record. Project creation links lead, customer, property, estimate, proposal, contract, initial budget, actor, and correlation ID.

### API journey

`POST /api/v1/leads` → `POST /leads/{id}/qualify` → `POST /leads/{id}/convert` → `POST /estimates` → section/line mutations with `If-Match` → `POST /estimates/{id}/approve` → `POST /estimates/{id}/proposals` → `POST /proposals/{id}/accept` → `POST /proposals/{id}/create-project`.

### Acceptance tests

- Reuse an existing customer/property without duplication; create missing records atomically.
- Reject cross-tenant IDs, unauthorized transitions, stale versions, invalid pricing rates, and duplicate acceptance.
- Prove direct-cost, markup, margin, tax, and rounded totals from source lines.
- Verify client output omits unit cost, internal notes, labor cost, overhead detail, profit, and margin.
- Simulate an outbox dispatch retry without duplicating the project or document.
- Complete the workflow on desktop and mobile viewports with keyboard and screen-reader labels.
