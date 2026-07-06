// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// PlaybookRunner - the stepper that drives one case.
//
// Shows the ordered steps as a vertical list with a progress strip, the
// focused step's "what you do" + "why", a "Go" button that drops the user into
// the real module (scoped to a chosen sample project when one is picked), and
// mark-done / reset controls. Progress and the sample-project choice are owned
// by useCasesStore and persist across reloads.

import { useCallback, useEffect, useMemo, useRef, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import { ArrowLeft, ArrowRight, Check, RotateCcw, CheckCircle2 } from 'lucide-react';
import { Button, Badge } from '@/shared/ui';
import { projectsApi, type Project } from '@/features/projects/api';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import type { Playbook, PlaybookStep } from './types';
import { tintFor, CATEGORY_BY_ID } from './categories';
import { iconFor } from './icons';
import { CaseArt } from './CaseArt';
import { StepScene } from './StepScene';
import { useCasesStore, EMPTY_PROGRESS } from './useCasesStore';
import {
  clampStepIndex,
  completedCount,
  isPlaybookDone,
  isStepDone,
  nextStepIndex,
  progressPct,
  resolveStepRoute,
  runKey,
  toggleStep,
} from './progress';

/** Returns true for seeded sample projects (they carry `metadata.demo_id`). */
function isDemoProject(p: Project): boolean {
  return Boolean((p.metadata as Record<string, unknown> | null)?.demo_id);
}

export interface PlaybookRunnerProps {
  playbook: Playbook;
  /** Optional handler for the "All cases" back control. */
  onBack?: () => void;
}

export function PlaybookRunner({ playbook, onBack }: PlaybookRunnerProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const stepRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const toggleStepDone = useCasesStore((s) => s.toggleStepDone);
  const setCurrentStep = useCasesStore((s) => s.setCurrentStep);
  const reset = useCasesStore((s) => s.reset);
  const setSelectedProject = useCasesStore((s) => s.setSelectedProject);

  /* ── Sample-project picker ────────────────────────────────────────────── */
  const { data: projects } = useQuery({
    queryKey: ['projects'],
    queryFn: projectsApi.list,
    retry: false,
    staleTime: 5 * 60_000,
  });

  // Sample (seeded) projects first so they are the obvious thing to learn on,
  // then the rest, each group alphabetical.
  const sortedProjects = useMemo(() => {
    const list = [...(projects ?? [])];
    return list.sort((a, b) => {
      const ad = isDemoProject(a) ? 0 : 1;
      const bd = isDemoProject(b) ? 0 : 1;
      if (ad !== bd) return ad - bd;
      return a.name.localeCompare(b.name);
    });
  }, [projects]);

  const selectedRaw = useCasesStore((s) => s.selected[playbook.id]) ?? '';
  const projectsLoaded = projects !== undefined;
  // Validate the persisted selection against the live list. A stale id (the
  // sample project was deleted or re-seeded) resolves to null, so "Go" never
  // navigates into a dead /projects/<id> route and the picker shows the truth.
  const selectedProject = useMemo(
    () => (selectedRaw ? (sortedProjects.find((p) => p.id === selectedRaw) ?? null) : null),
    [sortedProjects, selectedRaw],
  );
  // Until the list loads, trust the stored id so progress keeps its run key;
  // once loaded, only a project that still exists scopes the run.
  const projectId = selectedProject?.id ?? (projectsLoaded ? null : selectedRaw || null);

  // Drop a persisted selection that no longer resolves to a live project, so the
  // store does not keep a dead id and the picker settles on "no sample project".
  useEffect(() => {
    if (projectsLoaded && selectedRaw && !selectedProject) {
      setSelectedProject(playbook.id, '');
    }
  }, [projectsLoaded, selectedRaw, selectedProject, setSelectedProject, playbook.id]);

  /* ── Progress for the active run ──────────────────────────────────────── */
  const key = runKey(playbook.id, projectId);
  const progress = useCasesStore((s) => s.runs[key]) ?? EMPTY_PROGRESS;
  const total = playbook.steps.length;
  const currentIndex = clampStepIndex(progress.currentStepIndex, total);
  const doneCount = completedCount(progress, playbook);
  const pct = progressPct(progress, playbook);
  const allDone = isPlaybookDone(progress, playbook);

  const selectStep = useCallback(
    (index: number) => setCurrentStep(playbook.id, projectId, index, total),
    [setCurrentStep, playbook.id, projectId, total],
  );

  const handleGo = useCallback(
    (step: PlaybookStep) => {
      // Scope the chosen sample project so unscoped module pages (Takeoff,
      // Validation, Reports) also follow it, exactly as the journey map does.
      if (projectId && selectedProject) {
        useProjectContextStore.getState().setActiveProject(projectId, selectedProject.name);
      }
      navigate(resolveStepRoute(step.to, projectId));
    },
    [navigate, projectId, selectedProject],
  );

  const handleToggle = useCallback(
    (step: PlaybookStep) => {
      const updated = toggleStep(progress, step.id);
      toggleStepDone(playbook.id, projectId, step.id);
      // When the step was just completed, advance focus to the next gap so the
      // user keeps moving without an extra click.
      if (isStepDone(updated, step.id)) {
        setCurrentStep(playbook.id, projectId, nextStepIndex(updated, playbook), total);
      }
    },
    [progress, toggleStepDone, setCurrentStep, playbook, projectId, total],
  );

  const onStepKeyDown = useCallback(
    (e: KeyboardEvent, index: number) => {
      let target: number | null = null;
      if (e.key === 'ArrowDown') target = clampStepIndex(index + 1, total);
      else if (e.key === 'ArrowUp') target = clampStepIndex(index - 1, total);
      else if (e.key === 'Home') target = 0;
      else if (e.key === 'End') target = total - 1;
      if (target === null) return;
      e.preventDefault();
      selectStep(target);
      // Move real DOM focus too, so keyboard users land on the step they just
      // navigated to instead of being stranded on the previous row.
      stepRefs.current[target]?.focus();
    },
    [selectStep, total],
  );

  const title = t(playbook.titleKey, { defaultValue: playbook.titleDefault });
  const desc = t(playbook.descKey, { defaultValue: playbook.descDefault });
  const selectId = `cases-run-on-${playbook.id}`;
  const progressLabel = t('cases.steps_progress', {
    defaultValue: '{{done}} of {{total}} steps',
    done: doneCount,
    total,
  });

  // Visual identity + the focused step, resolved once for the detail stage.
  const tint = tintFor(playbook.category);
  const cat = CATEGORY_BY_ID[playbook.category];
  const PlaybookIcon = iconFor(playbook.icon);
  const currentStep = playbook.steps[currentIndex];
  const CurIcon = iconFor(currentStep?.icon);
  const curDone = currentStep ? isStepDone(progress, currentStep.id) : false;
  const curTitle = currentStep ? t(currentStep.titleKey, { defaultValue: currentStep.titleDefault }) : '';
  const curModule = currentStep
    ? currentStep.moduleLabelKey
      ? t(currentStep.moduleLabelKey, { defaultValue: currentStep.moduleLabel })
      : currentStep.moduleLabel
    : '';

  return (
    <div className="space-y-5 animate-fade-in">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div>
        <button
          type="button"
          onClick={onBack ?? (() => navigate('/cases'))}
          className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1.5 py-1 text-xs font-medium text-content-secondary transition-colors hover:text-content-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
        >
          <ArrowLeft size={14} />
          {t('cases.back_to_list', { defaultValue: 'All cases' })}
        </button>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-4">
            <div
              className="mt-0.5 flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-border-light bg-gradient-to-b from-white to-slate-50 ring-1 ring-inset ring-slate-900/[0.04] sm:h-24 sm:w-24"
              aria-hidden="true"
            >
              <CaseArt id={playbook.id} fallbackIcon={PlaybookIcon} fallbackClass={tint.text} />
            </div>
            <div className="min-w-0">
              <h1 className="text-2xl font-semibold tracking-tight text-content-primary">{title}</h1>
              <p className="mt-1 max-w-2xl text-sm leading-relaxed text-content-secondary">{desc}</p>
              <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                <span
                  className={clsx(
                    'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-2xs font-medium',
                    tint.chip,
                  )}
                >
                  <PlaybookIcon size={11} strokeWidth={2} aria-hidden="true" />
                  {t(cat.labelKey, { defaultValue: cat.labelDefault })}
                </span>
                <span className="text-2xs font-medium text-content-tertiary">
                  {t('cases.card.minutes', {
                    defaultValue: 'about {{count}} min',
                    count: playbook.estMinutes,
                  })}
                </span>
                <span className="text-2xs font-medium text-content-tertiary">{progressLabel}</span>
              </div>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            icon={<RotateCcw size={13} />}
            onClick={() => reset(playbook.id, projectId)}
            disabled={doneCount === 0 && progress.currentStepIndex === 0}
            title={t('cases.reset_hint', {
              defaultValue: 'Clear progress for this case and start over',
            })}
          >
            {t('cases.reset', { defaultValue: 'Reset progress' })}
          </Button>
        </div>
      </div>

      {/* ── Work area: a compact step rail beside the focused step ───────── */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)] lg:items-start">
        {/* Rail: progress, sample project, and the ordered step list */}
        <aside className="space-y-4 lg:sticky lg:top-4">
          {/* Progress */}
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={doneCount}
            aria-valuetext={progressLabel}
            aria-label={t('cases.progress_label', { defaultValue: 'Case progress' })}
            aria-live="polite"
          >
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <span className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
                {t('cases.progress_label', { defaultValue: 'Case progress' })}
              </span>
              <span className="text-2xs font-medium tabular-nums text-content-secondary">
                {progressLabel}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-secondary">
              <div
                className="h-full rounded-full bg-oe-blue transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>

          {/* Sample-project picker (compact) */}
          <div className="rounded-xl border border-border-light bg-surface-secondary/40 p-2.5">
            <label
              htmlFor={selectId}
              className="mb-1 block text-2xs font-semibold uppercase tracking-wide text-content-tertiary"
            >
              {t('cases.run_on', { defaultValue: 'Run on' })}
            </label>
            <select
              id={selectId}
              value={selectedRaw}
              onChange={(e) => setSelectedProject(playbook.id, e.target.value)}
              className="h-8 w-full rounded-lg border border-border bg-surface-primary px-2.5 text-xs text-content-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
            >
              <option value="">
                {t('cases.run_on_none', { defaultValue: 'No sample project (just open the module)' })}
              </option>
              {sortedProjects.map((p) => {
                const label = isDemoProject(p)
                  ? t('cases.run_on_sample_option', { defaultValue: '{{name}} (sample)', name: p.name })
                  : p.name;
                return (
                  <option key={p.id} value={p.id}>
                    {label}
                  </option>
                );
              })}
            </select>
          </div>

          {/* Step list: compact, selectable rows (detail shows in the stage) */}
          <ol className="space-y-1.5" aria-label={title}>
            {playbook.steps.map((step, i) => {
              const done = isStepDone(progress, step.id);
              const isCurrent = i === currentIndex;
              const stepTitle = t(step.titleKey, { defaultValue: step.titleDefault });
              return (
                <li key={step.id}>
                  <button
                    type="button"
                    ref={(el) => {
                      stepRefs.current[i] = el;
                    }}
                    onClick={() => selectStep(i)}
                    onKeyDown={(e) => onStepKeyDown(e, i)}
                    aria-current={isCurrent ? 'step' : undefined}
                    className={clsx(
                      'flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40',
                      isCurrent
                        ? 'border-oe-blue/50 bg-oe-blue/[0.06]'
                        : 'border-transparent hover:bg-surface-secondary/60',
                    )}
                  >
                    <span
                      className={clsx(
                        'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-2xs font-bold transition-colors',
                        done
                          ? 'bg-oe-blue text-white'
                          : isCurrent
                            ? 'bg-oe-blue/15 text-oe-blue ring-1 ring-inset ring-oe-blue/30'
                            : 'bg-surface-secondary text-content-tertiary',
                      )}
                      aria-hidden="true"
                    >
                      {done ? <Check size={13} strokeWidth={2.5} /> : i + 1}
                    </span>
                    <span
                      className={clsx(
                        'min-w-0 flex-1 truncate text-xs font-medium',
                        isCurrent
                          ? 'text-content-primary'
                          : done
                            ? 'text-content-secondary'
                            : 'text-content-primary',
                      )}
                    >
                      {stepTitle}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </aside>

        {/* Stage: the focused step in full ────────────────────────────────── */}
        <section className="min-w-0">
          {currentStep && (
            <div className="rounded-2xl border border-border-light bg-surface-primary p-5 shadow-xs sm:p-6">
              {/* Line-art visual of what this step does */}
              <StepScene
                icon={currentStep.icon}
                title={curTitle}
                className="mb-4 h-32 w-full sm:h-36"
              />
              {/* Eyebrow: step counter + module chip */}
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <span className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
                  {t('cases.step_counter', {
                    defaultValue: 'Step {{n}} of {{total}}',
                    n: currentIndex + 1,
                    total,
                  })}
                </span>
                <span className="inline-flex shrink-0 items-center gap-1 rounded-md border border-border-light bg-surface-secondary px-2 py-1 text-2xs font-medium text-content-secondary">
                  <CurIcon size={12} strokeWidth={2} aria-hidden="true" />
                  {curModule}
                </span>
              </div>

              {/* Title with status badge */}
              <div className="flex items-start gap-3">
                <span
                  className={clsx(
                    'flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold',
                    curDone
                      ? 'bg-oe-blue text-white'
                      : 'bg-oe-blue/15 text-oe-blue ring-1 ring-inset ring-oe-blue/30',
                  )}
                  aria-hidden="true"
                >
                  {curDone ? <Check size={17} strokeWidth={2.5} /> : currentIndex + 1}
                </span>
                <h2 className="mt-1 text-lg font-semibold leading-snug text-content-primary">
                  {curTitle}
                </h2>
              </div>

              {/* What + Why */}
              <div className="mt-4 space-y-4">
                <div>
                  <p className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
                    {t('cases.step.what', { defaultValue: 'What you do' })}
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-content-secondary">
                    {t(currentStep.whatKey, { defaultValue: currentStep.whatDefault })}
                  </p>
                </div>
                <div>
                  <p className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
                    {t('cases.step.why', { defaultValue: 'Why' })}
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-content-secondary">
                    {t(currentStep.whyKey, { defaultValue: currentStep.whyDefault })}
                  </p>
                </div>
              </div>

              {/* Primary actions */}
              <div className="mt-5 flex flex-wrap items-center gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  icon={<ArrowRight size={13} />}
                  iconPosition="right"
                  onClick={() => handleGo(currentStep)}
                  aria-label={t('cases.step.go_to', {
                    defaultValue: 'Go to {{module}}',
                    module: curModule,
                  })}
                >
                  {t('cases.step.go_to_module', {
                    defaultValue: 'Open {{module}}',
                    module: curModule,
                  })}
                </Button>
                <Button
                  variant={curDone ? 'ghost' : 'secondary'}
                  size="sm"
                  icon={curDone ? <RotateCcw size={13} /> : <Check size={13} />}
                  onClick={() => handleToggle(currentStep)}
                >
                  {curDone
                    ? t('cases.step.mark_undone', { defaultValue: 'Mark not done' })
                    : t('cases.step.mark_done', { defaultValue: 'Mark done' })}
                </Button>
              </div>

              {/* Step-to-step navigation */}
              <div className="mt-5 flex items-center justify-between gap-2 border-t border-border-light pt-3">
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<ArrowLeft size={13} />}
                  onClick={() => selectStep(clampStepIndex(currentIndex - 1, total))}
                  disabled={currentIndex === 0}
                >
                  {t('cases.prev_step', { defaultValue: 'Previous' })}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<ArrowRight size={13} />}
                  iconPosition="right"
                  onClick={() => selectStep(clampStepIndex(currentIndex + 1, total))}
                  disabled={currentIndex === total - 1}
                >
                  {t('cases.next_step', { defaultValue: 'Next' })}
                </Button>
              </div>
            </div>
          )}
        </section>
      </div>

      {/* ── Completion note ─────────────────────────────────────────────── */}
      {allDone && (
        <div
          role="status"
          className="flex items-start gap-3 rounded-xl border border-semantic-success/40 bg-semantic-success-bg px-4 py-3 animate-card-in"
        >
          <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-semantic-success" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-content-primary">
              {t('cases.all_done_title', { defaultValue: 'Case complete' })}
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-content-secondary">
              {t('cases.all_done_body', {
                defaultValue:
                  'You have stepped through every part of this case. Reset it to run again, or pick another case.',
              })}
            </p>
          </div>
          <Badge variant="success" size="sm">
            {pct}%
          </Badge>
        </div>
      )}
    </div>
  );
}
