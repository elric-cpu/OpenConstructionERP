# Benson ERP handoff — 2026-07-20

## Implemented in this turn

- Employee creation now always creates an identity-provisioning command.
- When Directory automation is disabled, the command is `manual_setup_required`.
- Employee link-only invitations are rejected; contractor invitations retain their existing path.
- Owner-only manual setup and credential reissue endpoints require a fresh temporary password, account-created attestation, no-paid-license attestation, reason, and evidence reference.
- Temporary passwords are sealed at rest, included only in the credentialed invitation email, and scrubbed from outbox/command storage after successful delivery or terminal failure.
- The active employee review UI now exposes the manual Google Admin setup/reissue workflow.
- The Jobs tab now has a visible `+ New job` action for planners, using accepted estimates and preserving the server-side acceptance invariant.

## Verification

- Python compileall: passed.
- Ruff format/check: passed.
- Mypy: passed.
- Web typecheck, lint, and production build: passed.
- Full `npm run verify`: started successfully through formatting, lint, typecheck, and build; API pytest entered the suite but stalled in the local sandbox during the asset tests. It was stopped rather than reported as green.
- Direct system Python pytest is not valid here because it has Pydantic v1; the project requires the `uv` environment with Pydantic v2.

## Deployment state

No production deployment or production data mutation was performed. The working tree contains uncommitted changes and the full API gate is not green, so there is no immutable, tested digest eligible for the documented zero-traffic production candidate flow yet.

An isolated Cloud Run staging deploy was attempted on 2026-07-20. The configured project is `civic-wall-494004-b3`, but the available local gcloud credential for `elric@bensonhomesolutions.com` is expired and no active service-account credential or ADC was available. Authenticate gcloud, then resume with the documented immutable build and `--no-traffic` staging deployment.

## Next operator loop

1. Diagnose the API test stall in a network-enabled/dev-container environment and add focused tests for manual setup, reissue, password scrubbing, and employee invite rejection.
2. Complete parity review against `upstream/main` and run the full verification suite to completion.
3. Commit the verified revision, build/tag by full SHA, deploy the same digest to isolated staging, then deploy production at zero traffic.
4. After the production candidate is healthy, use the manual Google Admin workflow to create/reset the two affected employee identities, revoke the old invitations, and send fresh credentialed invitations.
5. Change public traffic only after the production smoke and identity checks pass.
