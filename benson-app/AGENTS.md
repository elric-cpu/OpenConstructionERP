# Agent instructions (scope: this directory and subdirectories)

## Scope and layout

- This file governs the Benson Operations application in `benson-app/`.
- `api/` owns FastAPI endpoints, authorization, workflow rules, persistence, notifications, audit events, and private object-storage access.
- `web/` owns the authenticated React/Vite staff interface; follow `web/AGENTS.md` for frontend boundaries.
- `fcc-gateway/` owns the private IAM-authenticated Claude gateway.
- `skills/` contains the pinned construction-skill registry used by lead-scoped AI.
- `docs/` contains deployment and operational evidence; consult it only when the task requires it.

## Cross-stack contracts

- The browser may present capabilities but must not become the authority for roles, lead transitions, deletion, spam disposition, attachment access, or AI actions.
- Keep API contracts typed on both sides and update API tests plus Playwright coverage whenever a response or mutation shape changes.
- Preserve Google Workspace authentication, deny-by-default staff allowlisting, attributable audit history, idempotent lead intake, private uploads, and durable notification handling.

## Commands

- Full gate: `npm run verify`
- API gate: `npm run verify:api`
- Frontend format: `npm run format:check`
- Frontend lint: `npm run lint`
- Frontend types: `npm run typecheck`
- Frontend build: `npm run build`
- Browser tests: `npm run test:e2e`

## Frontend maintainability

- React/TypeScript source files are limited to 350 nonblank, noncomment lines; ESLint error.
- Functions/components are limited to 150 nonblank, noncomment lines; ESLint warning.
- Files above 500 lines must be decomposed when touched. Split API clients, orchestration hooks, forms, filters, panels, and presentation components by responsibility.
- Do not add lint disables or cosmetic wrapper components to evade these boundaries.

## Python maintainability

- Format Python at 88 characters and keep modules focused on one responsibility.
- Target 150–500 code lines per Python file; 550 nonblank, noncomment lines is the enforced hard ceiling.
- Generated migration files are the only file-size exception. Do not add legacy or convenience allowlists.
- When a file approaches the ceiling, split at natural API, persistence, domain, provider, or test boundaries.
- `tests/test_file_size.py` runs in the API suite and pre-commit hook; do not weaken or bypass it.

## Release safety

- Build immutable images and deploy candidate revisions at zero traffic until the approved UAT and cutover gates pass.
- Do not change public traffic, production website intake routing, or rollback retention merely because a candidate deploy succeeds.
- Preserve unrelated working-tree changes and leave `.serena/` untouched.
