# Customer workflow evidence

Verified 2026-07-16 UTC against the Benson ERP rewrite. This is implementation
evidence for the customer vertical slice; it is not evidence that the full ERP
goal or production cutover is complete.

## Implemented contract

- PostgreSQL/SQLite `customers` storage with additive migration
  `20260716_02_customers.sql`; existing records are not rewritten or deleted.
- Authenticated operations staff can create, list, search, and edit active
  customer records. Missing SSO configuration and unlisted identities fail
  closed.
- Only qualified, scheduled, or closed non-spam leads can be converted. The
  unique source-lead constraint prevents duplicate conversion.
- Archive is owner/admin-only, audited, non-destructive, and makes the record
  immutable. Archived records remain available through an explicit server
  query for retention and recovery.
- Create, update, and archive events are attributable and queryable through the
  protected customer audit endpoint. Phone, email, addresses, and notes are
  redacted from update deltas rather than duplicated into the audit log.
- The responsive Customers workspace supports manual creation, guarded lead
  conversion, editing, phone/email actions, empty states, and owner-only archive
  controls.

## Verification

- Ruff formatting/lint and strict mypy: passed.
- API: 87 tests passed; 86.62% aggregate coverage.
- Frontend: Prettier, ESLint, TypeScript, and Vite production build passed.
- Playwright: 25 tests passed across desktop Chromium and Pixel 7 profiles;
  one desktop-only mobile-navigation interaction was intentionally skipped.
- Customer pages were scanned with axe; no serious or critical findings.
- `git diff --check`: required before publication.

## Not yet production evidence

The migration has not been applied to production and this slice has not been
deployed to a zero-traffic candidate. Production traffic must not change until
the candidate is deployed, synthetic customer UAT passes, monitoring and
rollback evidence are recorded, and cutover is explicitly approved.
