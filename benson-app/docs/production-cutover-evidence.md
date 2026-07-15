# Benson Operations production cutover evidence

Last updated: 2026-07-15 UTC. This record covers the isolated production candidate. It is not authorization to switch the public website or `erp.bensonhomesolutions.com` before every open gate below passes.

## Verified candidate

- Cloud Run service: `benson-operations`, revision `benson-operations-00003-xt7`
- Image: `sha256:2ca1707b9f58974314635b6b8d93df788bc0e8c47fc5615222a8edb53c71e6d9`
- Dedicated runtime identity: `benson-operations@civic-wall-494004-b3.iam.gserviceaccount.com`
- Database: regional-HA PostgreSQL 16 instance `benson-operations-postgres`, PITR enabled, deletion protection enabled, 90 retained backups
- Uploads: private uniform-access bucket `benson-operations-private-uploads-1048944000089`, public access prevention, versioning, and 90-day soft delete
- AI: private IAM-authenticated service `benson-fcc-gateway`, pinned gateway source and container image
- Identity: Google Workspace OAuth client `1048944000089-77cgutagg3qlp4ghn59kojgglgb6h41h.apps.googleusercontent.com`; server roles fail closed

The live candidate returned HTTP 200 from `/api/health`, reported `environment=production` and `storage=postgresql`, rejected unauthenticated staff lead access with HTTP 401, and rejected unauthenticated notification-worker access with HTTP 401.

## Verification gates

- `npm run verify`: 35 API tests passed at 92.41% coverage; Ruff, strict mypy, Prettier, ESLint, TypeScript, and the production build passed; Playwright passed 9 tests with 1 intentional skip.
- Scheduler identity probe: `benson-notifications-drain` called the private worker contract with its exact OIDC service identity and received HTTP 200 after audience normalization.
- Durable delivery: lead acceptance and email/emergency-SMS outbox rows share one transaction; idempotent intake does not duplicate jobs; provider failures remain retryable with bounded exponential backoff and stale-lock recovery.
- Resend provider probe: controlled message accepted with a provider message ID.
- Twilio provider probe: credentials authenticate, but the account is `Trial`; delivery is not production-ready because Twilio rejects arbitrary SMS with error `572006` and requires predefined trial templates.
- Signed intake probe: first request HTTP 201, exact replay HTTP 200 with `duplicate=true` and the same lead ID.
- Upload probe: controlled PDF accepted; unauthenticated application download returned HTTP 401; direct public object request returned HTTP 403.
- Synthetic intake, upload, outbox, audit, and object artifacts were removed after the probe. The target returned to exactly 9 leads and zero outbox jobs.
- Rollback rehearsal: traffic moved 100% from revision `00003-xt7` to `00002-sk9`, health returned HTTP 200, traffic restored 100% to `00003-xt7`, and health again returned HTTP 200. The notification scheduler was paused during the older revision and resumed after restoration.

## Monitoring

- External 60-second uptime check: `benson-operations-health-sFoZ-vqnIxc`, Oregon, Virginia, and Europe
- Alert policy: `Benson Operations unavailable` (`5110565086227570806`)
- Log metric: `benson_operations_notification_delivery_failures`
- Alert policy: `Benson notification delivery failures` (`17727204473347113289`)
- Email channel: `Benson Operations alerts` (`12660752846837039647`)
- Durable worker: `benson-notifications-drain`, every minute, dedicated identity `benson-notification-scheduler@civic-wall-494004-b3.iam.gserviceaccount.com`

## Nine-lead reconciliation

The guarded migration tool refuses any accepted source count other than 9 and any target that is neither empty nor the already reconciled set. It preserves source timestamps and payloads, records `lead.migrated` audit events, and intentionally sends no historical notifications.

- Accepted legacy CRM leads: 9
- Accepted legacy webhook records: 9
- Target leads after migration: 9
- ID fingerprint: `8f136c99af2678e0bd569305d6d53dfb2522d205147766473330f6e88baf4416`
- Content fingerprint: `6062c920bdafbcc2f94ba5b61f058e5fea41c69c29cc9e19bad55d3d847de6e3`
- Content reconciliation: true
- Historical notifications enqueued: 0

## Open cutover gates

1. Upgrade/configure the Twilio account so a controlled SMS receives a provider message ID; then re-run the emergency delivery probe.
2. Complete authenticated Google Workspace staff UAT against the live nine-lead queue. The configured inference browser was unavailable (`App not found`), so automated database reconciliation is not being mislabeled as human UAT.
3. During an approved 8–10 PM Pacific window: freeze legacy writes, run the final guarded reconciliation, switch every website form directly with no dual-write, switch domain/traffic, and run post-cutover smoke/rollback verification.
4. Preserve the legacy system as a no-write rollback/archive surface for 30 days and retain backups/export for 90 days.

Accounting, jobs, estimating, portals, and the rest of full lead-to-cash remain outside this launch scope.
