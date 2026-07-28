# Benson Operations production cutover evidence

Last updated: 2026-07-16 UTC. Overall release decision: **NO-GO**.

This document separates live observed state and historical recovery evidence
from the evidence still required for the next full-ERP candidate. It is not
authorization to deploy a candidate, apply migrations, change traffic, enable a
provider, move money, or send an employee invitation.

## Live observed state

Read-only Google Cloud inspection on 2026-07-16 established:

- `erp.bensonhomesolutions.com` is ready and maps to Cloud Run service
  `benson-operations` in `us-west1`.
- `benson-operations` sends 100% of traffic to historical revision
  `benson-operations-full-erp2-20260716`. The current repository commit is not
  deployed as the serving production revision.
- Zero-traffic module candidates remain tagged on the same service, including
  `estimates-candidate`, `jobs-candidate`, and `schedule-candidate`. None is the
  complete candidate required by this plan.
- Runtime identity is
  `benson-operations@civic-wall-494004-b3.iam.gserviceaccount.com`.
- Scheduler `benson-notifications-drain` is enabled every minute, targets the
  canonical `benson-operations` service URL, uses the matching origin as its
  OIDC audience, and authenticates as the dedicated scheduler identity.
- Regional PostgreSQL instance `benson-operations-postgres` is runnable with
  backups and deletion protection. The private operations upload and cutover
  archive buckets enforce uniform access and public-access prevention.
- No isolated staging Cloud Run service or staging Cloud SQL instance was
  visible. Production module tags are not a substitute for isolated staging.
- The separate `openconstructionerp` service still exists, but it is not the
  current target of the ERP domain mapping.

## Current repository and CI evidence

- The sequential SQL bundle covers the logistics foundation, customers,
  estimates, jobs, schedule, field records, change orders, and onboarding
  completion.
- The release Dockerfile now installs the API from `uv.lock`, pins base images
  by digest, and includes the complete migration bundle.
- `Benson Rewrite Verify` validates migration ordering and additive safety,
  publishes a checksum artifact tied to the commit SHA, builds the runtime
  image, and verifies its migration and application contents.
- Root CI run `29514349987` is red for upstream source/environment failures,
  including frontend heap exhaustion under an unsupported Node version,
  forbidden zero-width characters in locale sources, fuzzy-search behavior,
  and cross-platform embedded-PostgreSQL setup. These failures are not waived
  or hidden by the Benson workflow.
- Full-suite run `29536920627` was still active when inspected; its Windows job
  failed before collection because embedded PostgreSQL attempted to create an
  already-existing temporary parent directory.
- No immutable image digest has been built or approved from the current complete
  branch. No migration in this branch has been applied by this workstream.

## Historical recovery evidence requiring revalidation

The following evidence predates the next full-scope candidate and may support,
but cannot satisfy, its gates:

- Regional-HA PostgreSQL 16, PITR, retained backups, and deletion protection
  were previously verified for `benson-operations-postgres`.
- Private upload and archive buckets were previously verified with versioning,
  uniform access, public-access prevention, and retention controls.
- Uptime check `benson-operations-health-sFoZ-vqnIxc`, alert policy
  `Benson Operations unavailable`, notification-failure metric and alert, and
  email channel `Benson Operations alerts` were previously configured.
- Protected exports `legacy/precutover-20260715T0509Z.sql.gz` and
  `operations/postmigration-20260715T0510Z.sql.gz` were retained for 90 days.
- The nine-lead migration previously reconciled source and target counts and
  hashes without enqueuing historical notifications. A final write-freeze export
  and delta reconciliation remain required.
- A prior rollback rehearsal restored health after moving traffic between older
  Operations revisions. The new digest requires a fresh rehearsal and evidence.

## G1–G8 acceptance ledger

| Gate | Required evidence | Current status |
| --- | --- | --- |
| G1 — merged source | Clean signed commit, reviewed PR, current main integration, required checks green | **NO-GO:** current work is not merged and root CI is red |
| G2 — complete local gate | Ruff, mypy, pytest/coverage, Prettier, ESLint, TypeScript, build, Playwright, desktop/mobile accessibility | **NO-GO:** no complete current-SHA evidence bundle |
| G3 — migration and restore | CI checksums, staging application, migration history, backup restore, counts/hashes/ledger reconciliation | **NO-GO:** checksums are defined; staging apply and restore are absent |
| G4 — isolated staging UAT | Dedicated database/storage/test OU, payment-provider test mode, accounting-provider sandbox, non-delivering providers, both full UAT journeys | **NO-GO:** isolated staging is not provisioned |
| G5 — external review | Security, privacy, accessibility, operations, and qualified HR/legal approvals with no unresolved high severity | **NO-GO:** approvals are not recorded |
| G6 — immutable candidate | One merged image digest, unchanged staging regression, zero-traffic production deploy, IAM/secrets/monitoring/rollback proof | **NO-GO:** no current digest or candidate exists |
| G7 — production cutover | Approved 8–10 PM Pacific window, write freeze, final exports, guarded delta, no dual-write, 100% traffic and smoke evidence | **NO-GO:** G1–G6 are incomplete |
| G8 — first real invitation | Successful production smoke, verified Directory identity and no-paid-license state, reachable delivery email, HR/legal and audit approval | **NO-GO:** G7 is incomplete; no invitation may be sent |

Authorization to shift general ERP traffic and send one real invitation becomes
actionable only when the corresponding gates are recorded as PASS. It does not
waive earlier gates or authorize additional invitations.

## Provider and cutover stop conditions

- Twilio is disabled. The known account was previously Trial-limited, and this
  release does not mount Twilio secrets, send SMS, or use SMS as an onboarding
  fallback.
- Payment processing remains test-only and accounting export remains sandbox-only until their
  authoritative workflows, signed events, reconciliation, and approvals pass.
- Stop before traffic change if the serving service, image digest, migrations,
  scheduler audience/identity, secret versions, monitoring, backups, or rollback
  revision differs from the release record.
- Stop before the real invitation if production smoke, Directory/license
  verification, delivery-address validation, HR/legal approval, or invitation
  audit controls fail.
- On a critical smoke failure, pause workers and providers, restore traffic to
  the retained compatible revision, and reconcile all writes accepted after the
  freeze point.
