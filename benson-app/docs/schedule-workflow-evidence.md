# Schedule workflow evidence

This evidence covers the Schedule vertical slice. It does not establish
completion of field records, change orders, invoicing, accounting, or the full
ERP.

## Required contract

- Every schedule entry belongs to a persisted job that is not on hold,
  completed, or cancelled.
- Entries store timezone-aware start and end instants and reject zero-length or
  reversed intervals. UTC instants remain authoritative while a validated IANA
  timezone preserves the intended local scheduling context. Inputs must resolve
  to that zone without silently accepting nonexistent or ambiguous local times,
  and event duration is bounded.
- Event types are limited to site visit, work, inspection, and delivery.
- Delivery status follows an explicit scheduled, in-progress, completed, or
  cancelled state machine.
- Only owner, administrator, office, and project-management roles can create,
  edit, reassign, or cancel entries.
- Staff whose sole role is field can list only entries assigned to their exact
  identity. Any configured delivery-capable staff member may start or complete
  only their own assigned entry. Accounting staff have no Schedule access until
  a separate, data-minimized finance contract exists.
- Assignees must be configured active, delivery-capable staff; arbitrary
  external addresses are rejected.
- Overlapping active entries for one assignee are rejected, including
  concurrent requests.
- Updates and transitions use an expected version so stale writes fail rather
  than overwrite newer work.
- Typed mutation contracts reject unknown or server-owned fields. List queries
  use bounded date windows and pagination rather than unbounded enumeration.
- Audit payloads record identifiers, time/status deltas, versions, and required
  reason references without copying estimate scope, contract value, customer
  contact data, or protected factual notes.

## Automated verification completed

- The additive PostgreSQL migration includes foreign keys, interval and status
  checks, active-entry conflict enforcement, and no destructive SQL.
- API coverage includes the role matrix, assignment IDOR, inactive and terminal
  jobs, invalid and DST-adjacent intervals, conflicts, concurrent conflicts,
  stale writes, state transitions, protected notes, bounded audit pagination,
  and terminal-job retirement of future, current, and overdue scheduled work.
- A PostgreSQL 16 test launches the job-close and schedule-start operations in
  separate spawned processes against an isolated schema. It proves the shared
  advisory lock permits exactly one winner and always removes its schema.
- Ruff formatting and lint, strict mypy across 76 source files, and the full API
  suite passed. The final PostgreSQL-enabled gate ran 118 tests with 87.69%
  aggregate coverage.
- Prettier, ESLint, TypeScript, and the production Vite build passed.
- Desktop Chrome and Pixel 7 Playwright passed 39 tests with one intentional
  mobile-only duplicate skip. Coverage includes keyboard operation, honest
  empty states, navigation and role boundaries, conflict recovery, assigned
  field delivery, and serious or critical axe findings.

## Release gates remaining

- Build the exact merged revision and deploy its immutable image digest as a
  PostgreSQL Cloud Run candidate at zero traffic.
- Complete authenticated human Schedule UAT and retain its evidence.
- Prove backup and restore for the candidate data model, document rollback, and
  obtain explicit approval before changing production traffic.
- Schedule notifications remain outside this slice. No provider call or
  customer communication is triggered by a Schedule write.
