# Agent instructions (scope: this directory and subdirectories)

## Scope and layout

- This file governs the Benson Operations React/Vite frontend in `benson-app/web/`.
- `src/App.tsx` owns shell-level composition only; `src/LeadWorkspace.tsx` owns lead-workspace composition only.
- Put shared API request code in an API client module, reusable state orchestration in hooks, shared contracts in `types.ts`, and each substantial panel/form/filter in its own component.

## Commands

- Install: `npm ci`
- Format: `npm run format:check`
- Lint: `npm run lint`
- Types: `npm run typecheck`
- Build: `npm run build`
- Browser tests: `npm run test:e2e`

## Component boundaries

- Maximum frontend source file size: 350 nonblank, noncomment lines; ESLint error.
- Maximum function/component size: 150 nonblank, noncomment lines; ESLint warning.
- Files above 500 lines must be refactored when touched for feature work.
- Split by behavior and ownership, not merely to reduce line count. Prefer modules such as `operations-api`, `useOperationsData`, `LeadQueue`, `LeadFilters`, `LeadDetailsForm`, `LeadWorkflowPanel`, `LeadNotes`, `LeadAttachments`, `LeadAssistant`, and `LeadAuditTrail` when those responsibilities exist.
- Preserve accessible names, authenticated request handling, abort behavior, empty-state honesty, and desktop/mobile Playwright coverage during extraction.

## Do not

- Do not silence `max-lines` with file-level disables or generated wrapper components.
- Do not move server authorization or workflow rules into the browser.
- Do not expose private attachment storage keys or persist Google credentials outside session storage.
