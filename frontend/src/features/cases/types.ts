// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Cases (playbooks) - data model.
//
// A "case" is a cross-module, end-to-end guided scenario. The platform already
// explains each module on its own (Module Guides, the How-it-works hub, the
// journey map); a case is the missing worked example that walks a user THROUGH
// several modules in order, telling them WHAT to do and WHY at each step, with
// a "Go" button that drops them into the real module.
//
// i18n convention: every user-facing string on a Playbook / PlaybookStep is a
// key PLUS an inline English default (the same key + defaultValue pattern used
// by ModuleGuide and the *Guide.ts files). Playbook CONTENT strings live ONLY
// in the data files - they are NEVER added to en.ts. Only the framework chrome
// (page title, runner buttons, labels) is seeded into en.ts. Translators pick
// the inline-default content keys up later.

/**
 * One step of a playbook: a single thing the user does, in one module.
 *
 * `to` is a real app route and MAY contain a `:projectId` slot
 * (e.g. `/projects/:projectId/boq`). When the user has picked a sample project
 * the slot is filled in; when they have not, the `/projects/:projectId`
 * prefix is stripped so the module opens unscoped (see `resolveStepRoute`).
 *
 * `moduleLabel` is the short module name shown as a chip on the step
 * (e.g. "BOQ"). Pass `moduleLabelKey` to reuse an existing translated
 * sidebar/nav key (e.g. `boq.title`) so the chip is localized for free;
 * when omitted the plain `moduleLabel` renders.
 *
 * `spotlightSelector` is an optional CSS selector reserved for a future
 * in-module highlight (it mirrors ModuleGuide's spotlight contract). It is
 * carried on the model now so data files can declare it without a later
 * schema change.
 */
export interface PlaybookStep {
  /** Stable id, unique within the playbook. Progress is keyed by this, so
   *  do NOT reuse or renumber ids once a case has shipped. */
  id: string;
  /** i18n key for the step title (the short imperative, e.g. "Build the BOQ"). */
  titleKey: string;
  /** Inline English default for the step title. */
  titleDefault: string;
  /** i18n key for the "what you do" copy. */
  whatKey: string;
  /** Inline English default for the "what you do" copy. */
  whatDefault: string;
  /** i18n key for the "why" copy. */
  whyKey: string;
  /** Inline English default for the "why" copy. */
  whyDefault: string;
  /** Short module name shown as a chip on the step (English fallback). */
  moduleLabel: string;
  /** Optional existing nav/title i18n key to localize the module chip. */
  moduleLabelKey?: string;
  /** Target route. May contain a `:projectId` slot for project scoping. */
  to: string;
  /** Optional lucide-react icon name for the step (resolved by the runner). */
  icon?: string;
  /** Optional CSS selector for a future in-module spotlight highlight. */
  spotlightSelector?: string;
}

/**
 * A complete case: an ordered set of steps spanning several modules.
 *
 * Drop a new one into `features/cases/data/<slug>.playbook.ts` as the file's
 * default export; it is auto-discovered (no central registry to edit). `order`
 * controls where the card sits in the list (ascending).
 */
export interface Playbook {
  /** Stable id, unique across all playbooks (matches the file slug). */
  id: string;
  /** Sort order in the case list (ascending). Lower shows first. */
  order: number;
  /** i18n key for the case title. */
  titleKey: string;
  /** Inline English default for the case title. */
  titleDefault: string;
  /** i18n key for the one-line case description. */
  descKey: string;
  /** Inline English default for the case description. */
  descDefault: string;
  /** Rough time-to-complete in minutes, shown on the card. */
  estMinutes: number;
  /** Optional lucide-react icon name for the case card (resolved by the page). */
  icon?: string;
  /** Ordered steps. At least one is required for the case to be useful. */
  steps: PlaybookStep[];
}

/**
 * Per-run progress for one playbook (optionally scoped to a sample project).
 * Persisted in localStorage by `useCasesStore`, keyed by `runKey`.
 */
export interface PlaybookProgress {
  /** Ids of completed steps. Order is irrelevant; membership is what counts. */
  completedStepIds: string[];
  /** Index of the step the runner is focused on. */
  currentStepIndex: number;
}
