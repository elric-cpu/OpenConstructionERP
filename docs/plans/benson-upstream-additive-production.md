# Upstream-Additive Benson ERP Integration and Production Plan

## Summary

Rebuild the Benson release line from OpenConstructionERP `v12.9.0` commit `19bd8e0856b549e40472e2b57a6c82b8a0722a73`, then add Benson capabilities as modules and edition overlays. The current fork cannot be the baseline: compared with `v12.9.0`, it lacks 609 upstream paths, 18 backend modules, and 17 frontend feature directories.

The implementation begins by saving this plan as `docs/plans/benson-upstream-additive-production.md`. The existing separate-app production runbook becomes superseded until the integrated application passes parity.

## Preservation and Architecture Contract

- Preserve every upstream file, migration, module, API operation, UI route, command, task, exported symbol, and test unless covered by the English-language exception.
- Prefer new `benson_*` modules, manifests, event handlers, adapters, regional profiles, and frontend features. Existing upstream files may only receive reviewed additive registration hooks.
- Keep `benson-app/` and `benson-erp/` intact as reference implementations until every Benson capability is represented and acceptance-tested in the integrated application.
- Generate a three-way capability matrix covering upstream `v12.9.0`, `benson-app/`, and `benson-erp/`. Every feature must map to an integrated module, an acceptance test, or an explicit future item; nothing may silently disappear.
- Create automated parity manifests for:
  - 7,564 upstream tracked paths and 183 backend module directories;
  - Alembic revisions and heads;
  - OpenAPI operation IDs, CLI commands, Celery tasks, permissions, and module manifests;
  - frontend feature directories, routes, navigation entries, and TypeScript/Python exports.
- CI must reject deleted upstream paths, missing symbols, reduced route/module inventories, migration loss, or disabled capabilities.
- Future upstream upgrades use review branches pinned to stable releases. They never auto-merge or auto-deploy.

## Integration Changes

1. Archive the current fork tip `0072bc061` with a permanent tag and create a clean integration branch from `v12.9.0`; do not merge the unrelated current histories.
2. Port Benson identity, CRM, estimating, documents, scheduling, offline timekeeping, employee onboarding, federal labor, payroll, reconciliation, MFA, audit, and worker behavior into upstream’s module-loader and frontend feature architecture.
3. Use upstream services where capabilities overlap. Benson modules extend them through manifests, hooks, events, and provider adapters instead of replacing upstream modules.
4. Add a Benson edition configuration:
   - `OE_EDITION=benson`
   - `OE_SUPPORTED_LOCALES=en`
   - `OE_DEFAULT_LOCALE=en-US`
   - `OE_DEFAULT_REGION=benson_eastern_oregon`
5. Keep upstream locale sources for clean synchronization, but the Benson production artifact must compile, expose, and accept only English. Hide language switching and translation administration in the Benson edition, reject unsupported locale changes, and assert that non-English chunks are absent from the artifact.
6. Add an `Eastern Oregon` regional profile that extends the upstream US pack:
   - USD, imperial units, `en-US`, Oregon state context;
   - Eastern Oregon as the organization operating region;
   - county, local jurisdiction, and IANA timezone required per project;
   - no hard-coded county whitelist and no universal Pacific-time assumption;
   - other upstream regional modules remain preserved but are not active for the Benson tenant.
7. Fix the known release blockers during integration:
   - SPA fallback must serve browser routes while retaining API/health/metrics 404 behavior;
   - remove all high-severity npm advisories;
   - retain the 350-line frontend file and 150-line component/function standards.
8. Replace the separate-app deployment documentation with an integrated-app runbook and update the codebase map and architecture documentation to identify the upstream baseline, Benson modules, English build, and Eastern Oregon profile.

## Verification and Release

- Run the complete upstream backend, frontend, PostgreSQL, migration, module-loader, browser, security, and packaging suites unchanged.
- Run all Benson tests plus cross-role acceptance journeys for lead-to-project, onboarding, activation, schedule, offline time, federal labor, payroll, reconciliation, MFA, and immutable documents.
- Prove parity mechanically:
  - upstream modules, routes, commands, tasks, exports, migrations, and UI navigation are subsets of the integrated inventories;
  - no upstream test is removed or skipped;
  - only English is present in the Benson artifact;
  - project jurisdiction and timezone behavior works across Eastern Oregon boundaries.
- Build one immutable integrated image from a clean, green commit.
- Provision the fresh `benson_erp_v2` database, Redis, private GCS, secrets, migration/bootstrap jobs, and worker/scheduler pools.
- Deploy a zero-traffic candidate while the existing revision retains 100% traffic.
- Smoke-test all upstream and Benson module families, not only the Benson vertical slices.
- Enable Resend and Google Directory only after candidate smoke tests.
- Cutover requires authorization naming the exact revision, digest, green CI run, parity report, smoke record, and rollback revision.
- Retain the previous revision and database for seven days.

## Assumptions and Locked Decisions

- The production product is one integrated application, not two linked applications and not a Benson-only subset.
- OpenConstructionERP `v12.9.0` is the initial pinned baseline; later stable releases are reviewed individually.
- “English only” applies to Benson runtime behavior and build artifacts; upstream locale source remains available solely for clean upstream synchronization.
- Eastern Oregon is an operating profile, while county, jurisdiction, and timezone remain project-specific.
- Aside from the language presentation exception, subtractive upstream changes are prohibited.
- Plan Mode prevents writing the requested file now; the first execution action is to save this plan verbatim at the path above.
