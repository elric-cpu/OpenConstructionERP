// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Cases - progress store.
//
// A thin zustand store over the pure helpers in ./progress. It owns the
// per-run progress map plus the per-case sample-project selection, and persists
// both to localStorage so a half-finished case (and the project you were
// learning it on) survive reloads and a hop into a module and back. All real
// logic lives in ./progress (pure, tested); this layer only reads/writes and
// persists.

import { create } from 'zustand';
import type { PlaybookProgress } from './types';
import {
  clampStepIndex,
  emptyProgress,
  runKey,
  toggleStep as toggleStepProgress,
} from './progress';

const RUNS_KEY = 'oe_cases_progress';
const SELECTED_KEY = 'oe_cases_selected';

/** Stable, frozen fallback used by selectors for a run that has no progress
 *  yet. Frozen so an accidental mutation throws instead of corrupting shared
 *  state; the pure helpers never mutate, they return new objects. */
export const EMPTY_PROGRESS: PlaybookProgress = Object.freeze(emptyProgress());

type RunMap = Record<string, PlaybookProgress>;
type SelectedMap = Record<string, string>;

function readRuns(): RunMap {
  try {
    const raw = localStorage.getItem(RUNS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return {};
    const out: RunMap = {};
    for (const [k, value] of Object.entries(parsed as Record<string, unknown>)) {
      const v = value as Partial<PlaybookProgress> | null;
      if (v && Array.isArray(v.completedStepIds)) {
        out[k] = {
          completedStepIds: v.completedStepIds.filter(
            (id): id is string => typeof id === 'string',
          ),
          currentStepIndex: typeof v.currentStepIndex === 'number' ? v.currentStepIndex : 0,
        };
      }
    }
    return out;
  } catch {
    return {};
  }
}

function readSelected(): SelectedMap {
  try {
    const raw = localStorage.getItem(SELECTED_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return {};
    const out: SelectedMap = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof v === 'string') out[k] = v;
    }
    return out;
  } catch {
    return {};
  }
}

function persistRuns(runs: RunMap) {
  try {
    localStorage.setItem(RUNS_KEY, JSON.stringify(runs));
  } catch {
    /* localStorage unavailable (private mode / quota) - non-fatal. */
  }
}

function persistSelected(selected: SelectedMap) {
  try {
    localStorage.setItem(SELECTED_KEY, JSON.stringify(selected));
  } catch {
    /* non-fatal */
  }
}

interface CasesState {
  /** Progress per run key (playbookId or `playbookId::projectId`). */
  runs: RunMap;
  /** Sample project chosen per playbook id (empty / absent = none). */
  selected: SelectedMap;
  /** Toggle a step's done flag for a run. */
  toggleStepDone: (playbookId: string, projectId: string | null, stepId: string) => void;
  /** Move the runner's focus to a step index (clamped to the step count). */
  setCurrentStep: (
    playbookId: string,
    projectId: string | null,
    index: number,
    total: number,
  ) => void;
  /** Clear all progress for a run. */
  reset: (playbookId: string, projectId?: string | null) => void;
  /** Set (or clear, with '') the sample project for a playbook. */
  setSelectedProject: (playbookId: string, projectId: string) => void;
}

export const useCasesStore = create<CasesState>((set, get) => ({
  runs: readRuns(),
  selected: readSelected(),

  toggleStepDone: (playbookId, projectId, stepId) => {
    const key = runKey(playbookId, projectId);
    const current = get().runs[key] ?? emptyProgress();
    const next = toggleStepProgress(current, stepId);
    const runs = { ...get().runs, [key]: next };
    persistRuns(runs);
    set({ runs });
  },

  setCurrentStep: (playbookId, projectId, index, total) => {
    const key = runKey(playbookId, projectId);
    const current = get().runs[key] ?? emptyProgress();
    const clamped = clampStepIndex(index, total);
    if (get().runs[key] && current.currentStepIndex === clamped) return;
    const runs = { ...get().runs, [key]: { ...current, currentStepIndex: clamped } };
    persistRuns(runs);
    set({ runs });
  },

  reset: (playbookId, projectId) => {
    const key = runKey(playbookId, projectId);
    if (!(key in get().runs)) return;
    const runs = { ...get().runs };
    delete runs[key];
    persistRuns(runs);
    set({ runs });
  },

  setSelectedProject: (playbookId, projectId) => {
    const selected = { ...get().selected };
    if (projectId) selected[playbookId] = projectId;
    else delete selected[playbookId];
    persistSelected(selected);
    set({ selected });
  },
}));
