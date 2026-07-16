# Estimate workflow evidence

Verified 2026-07-16 UTC against the Benson ERP rewrite. This is local
implementation evidence, not proof of a production deployment or the full ERP
completion definition.

## Implemented contract

- Estimates are linked to active persisted customers and contain ordered line
  items, decimal quantities, units, integer-cent unit prices, and server-owned
  64-bit totals. Browser totals are display-only.
- Drafts can be created and edited with a monotonically increasing version.
  Non-draft estimates are immutable.
- Server transitions are explicit: draft to ready; ready back to draft or sent;
  sent to accepted or declined. Void is owner/admin-only.
- Recording `sent` requires explicit confirmation that delivery occurred
  outside the ERP. The ERP does not send a message. Acceptance, decline, and
  void require a factual operator note.
- Archived-customer estimates cannot advance. Update audits record field names,
  line counts, and totals without duplicating scope text; decision notes are
  acknowledged but not copied into the audit payload. Authenticated staff can
  retrieve attributable lifecycle history through a protected endpoint.
- The migration `20260716_03_estimates.sql` is additive, uses foreign keys and
  64-bit cent columns, and contains no destructive data statements.

## Verification

- Ruff, strict mypy, frontend Prettier/ESLint/TypeScript, and Vite build passed.
- API: 92 tests passed at 87.06% aggregate coverage.
- Operations browser suite: 21 tests passed across desktop and mobile with one
  intentional desktop mobile-navigation skip.
- Estimate create, draft edit, server total display, ready, and confirmed sent
  flows passed with an axe serious/critical accessibility scan.

## Remaining release evidence

The estimate migration has not been applied to production. No real estimate was
sent, accepted, declined, or voided. A zero-traffic candidate, synthetic UAT,
backup/restore proof, monitoring, rollback rehearsal, and explicit production
cutover approval remain required.
