# Job workflow evidence

This evidence covers the Jobs vertical slice. It does not establish completion
of schedules, field records, change orders, invoicing, or the full ERP.

## Implemented contract

- One accepted estimate can create at most one job.
- The job snapshots the accepted estimate scope and total; later job planning
  cannot rewrite the accepted source or contract value.
- Archived customers and non-accepted estimates cannot start jobs.
- Planning captures target dates, site address, and assigned staff identity.
- Server transitions permit planned, active, on-hold, completed, and cancelled
  states through an explicit state machine.
- On-hold, completed, and cancelled states require a factual operator note.
- Cancellation requires owner or administrator authority.
- Accounting staff can read job records but cannot mutate delivery state;
  operations staff plan jobs and field-capable staff advance delivery state.
- Audit payloads record identifiers, state deltas, and required factual status
  notes; they do not copy accepted scope text or customer contact fields.

## Persistence and migration

`20260716_04_jobs.sql` creates the additive `jobs` table with unique estimate
lineage, integer-cent contract value, guarded statuses, ordered target dates,
and foreign keys to accepted source records. It contains no destructive SQL.

## Automated verification

- Full API suite: 99 passed with 87.27% aggregate coverage.
- Ruff formatting and lint, strict mypy, Prettier, ESLint, TypeScript, and the
  production web build passed.
- Desktop/mobile Playwright: 33 passed and 1 intentionally skipped, including
  accepted-estimate conversion, plan edit, start/completion, field scoping,
  accounting read-only access, and accessibility checks.
- Focused API tests cover duplicate rejection, hold/resume, completion,
  cancellation authorization, invalid dates, assignment validation, scoped
  field access, accounting restrictions, audit deltas, and fail-closed auth.

## Release evidence still required

- Fork PR 7 merged at `85d1f070`; Cloud Build
  `f7ea81ce-5338-4cb7-8abc-f9aba9e31fab` produced immutable digest
  `sha256:5433f75254ac9296000fdf3e7440dafe9c3b842f10f9178acf27404ab6c43ae4`.
- Cloud Run revision `benson-operations-00015-mon`, tagged
  `jobs-candidate`, returned a healthy PostgreSQL readiness response at zero
  traffic. Production remained 100% on `benson-operations-full-erp2-20260716`.
- Authenticated human UAT against the candidate revision.
- Backup/restore evidence and approved production cutover.
