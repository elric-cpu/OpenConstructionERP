// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// PlaybookRunner - the case detail page that drives one case.
//
// Layout, top to bottom: a compact header (title + one-line description + meta
// on the left, a small framed case image on the right), a slim control bar (the
// progress track, the sample-project picker and reset, all on one line), a
// compact "The process" step strip (the ordered steps as small clickable
// filmstrip cards), and the stage - the selected step in full. The stage is the
// star: it shows the step as an IN -> ACTION -> OUT flow (what data goes in, the
// action scene in the middle, what comes out) so the user sees exactly what the
// step consumes and produces, then a What / Why caption and the module actions.
//
// The selected step is a single source of truth: `useCasesStore`'s per-run
// current step index. Clicking a process card, using Prev/Next, or marking a
// step done all write that one index, and the strip, the highlight and the stage
// all read back from it, so everything stays in sync. Progress and the
// sample-project choice are owned by useCasesStore and persist across reloads.

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type KeyboardEvent,
  type ReactElement,
} from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowLeft,
  ArrowRight,
  ArrowDown,
  Check,
  RotateCcw,
  CheckCircle2,
  LogIn,
  LogOut,
} from "lucide-react";
import { Button, Badge } from "@/shared/ui";
import { projectsApi, type Project } from "@/features/projects/api";
import { useProjectContextStore } from "@/stores/useProjectContextStore";
import type { Playbook, PlaybookStep } from "./types";
import { tintFor, CATEGORY_BY_ID } from "./categories";
import { iconFor } from "./icons";
import { CaseArt } from "./CaseArt";
import { StepScene } from "./StepScene";
import { StepProcessScene, hasProcessScene } from "./processScenes";
import { useCasesStore, EMPTY_PROGRESS } from "./useCasesStore";
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
} from "./progress";

/** Returns true for seeded sample projects (they carry `metadata.demo_id`). */
function isDemoProject(p: Project): boolean {
  return Boolean((p.metadata as Record<string, unknown> | null)?.demo_id);
}

/** One side (In / Out) of the step's data flow: a titled column of chips. The
 *  In dots are quiet (raw material); the Out dots are green (the payoff), so the
 *  eye reads left-to-right from what you start with to what you end up with. */
function FlowSide({
  label,
  items,
  tone,
}: {
  label: string;
  items: string[];
  tone: "in" | "out";
}): ReactElement {
  const Icon = tone === "in" ? LogIn : LogOut;
  return (
    <div className="flex flex-1 flex-col rounded-xl border border-border-light bg-surface-secondary/40 p-4">
      <p className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-content-secondary">
        <Icon size={16} strokeWidth={2.2} aria-hidden="true" />
        {label}
      </p>
      <ul className="flex-1 space-y-2">
        {items.map((text, i) => (
          <li
            key={i}
            className="flex items-start gap-2.5 text-sm leading-snug text-content-secondary"
          >
            <span
              className={clsx(
                "mt-[7px] h-2 w-2 shrink-0 rounded-full",
                tone === "in" ? "bg-content-quaternary" : "bg-semantic-success",
              )}
              aria-hidden="true"
            />
            <span className="min-w-0">{text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The connector between flow columns: points right on desktop (In -> Out reads
 *  left to right) and down when the columns stack on narrow screens. */
function FlowConnector(): ReactElement {
  return (
    <div
      className="flex shrink-0 items-center justify-center text-content-tertiary"
      aria-hidden="true"
    >
      <ArrowRight size={18} strokeWidth={2.2} className="hidden lg:block" />
      <ArrowDown size={16} strokeWidth={2.2} className="lg:hidden" />
    </div>
  );
}

/** The small filmstrip thumbnail for one step in the process strip: the step's
 *  bespoke process scene when it has one, otherwise its icon scene, framed to
 *  match the stage so the strip reads as a row of pictures of the actual work. */
function StepThumb({ step }: { step: PlaybookStep }): ReactElement {
  // A compact, wide 16:9 banner: small enough that the numbered title beside it
  // stays the prominent element and the strip reads as an ordered process.
  const cls = "aspect-[16/9] w-full";
  return step.scene && hasProcessScene(step.scene) ? (
    <StepProcessScene
      sceneId={step.scene}
      rounded="rounded-lg"
      className={cls}
    />
  ) : (
    <StepScene icon={step.icon} rounded="rounded-lg" className={cls} />
  );
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
  const stageRef = useRef<HTMLElement | null>(null);

  const toggleStepDone = useCasesStore((s) => s.toggleStepDone);
  const setCurrentStep = useCasesStore((s) => s.setCurrentStep);
  const reset = useCasesStore((s) => s.reset);
  const setSelectedProject = useCasesStore((s) => s.setSelectedProject);

  /* ── Sample-project picker ────────────────────────────────────────────── */
  const { data: projects } = useQuery({
    queryKey: ["projects"],
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

  const selectedRaw = useCasesStore((s) => s.selected[playbook.id]) ?? "";
  const projectsLoaded = projects !== undefined;
  // Validate the persisted selection against the live list. A stale id (the
  // sample project was deleted or re-seeded) resolves to null, so "Go" never
  // navigates into a dead /projects/<id> route and the picker shows the truth.
  const selectedProject = useMemo(
    () =>
      selectedRaw
        ? (sortedProjects.find((p) => p.id === selectedRaw) ?? null)
        : null,
    [sortedProjects, selectedRaw],
  );
  // Until the list loads, trust the stored id so progress keeps its run key;
  // once loaded, only a project that still exists scopes the run.
  const projectId =
    selectedProject?.id ?? (projectsLoaded ? null : selectedRaw || null);

  // Drop a persisted selection that no longer resolves to a live project, so the
  // store does not keep a dead id and the picker settles on "no sample project".
  useEffect(() => {
    if (projectsLoaded && selectedRaw && !selectedProject) {
      setSelectedProject(playbook.id, "");
    }
  }, [
    projectsLoaded,
    selectedRaw,
    selectedProject,
    setSelectedProject,
    playbook.id,
  ]);

  /* ── Progress for the active run ──────────────────────────────────────── */
  const key = runKey(playbook.id, projectId);
  const progress = useCasesStore((s) => s.runs[key]) ?? EMPTY_PROGRESS;
  const total = playbook.steps.length;
  const currentIndex = clampStepIndex(progress.currentStepIndex, total);
  const doneCount = completedCount(progress, playbook);
  const pct = progressPct(progress, playbook);
  const allDone = isPlaybookDone(progress, playbook);

  // Single writer for the selected step: clamps, dedupes and persists the index.
  const selectStep = useCallback(
    (index: number) => setCurrentStep(playbook.id, projectId, index, total),
    [setCurrentStep, playbook.id, projectId, total],
  );

  const handleGo = useCallback(
    (step: PlaybookStep) => {
      // Scope the chosen sample project so unscoped module pages (Takeoff,
      // Validation, Reports) also follow it, exactly as the journey map does.
      if (projectId && selectedProject) {
        useProjectContextStore
          .getState()
          .setActiveProject(projectId, selectedProject.name);
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
        setCurrentStep(
          playbook.id,
          projectId,
          nextStepIndex(updated, playbook),
          total,
        );
      }
    },
    [progress, toggleStepDone, setCurrentStep, playbook, projectId, total],
  );

  const onStepKeyDown = useCallback(
    (e: KeyboardEvent, index: number) => {
      let target: number | null = null;
      // The strip is a single sequence, so both axes walk it.
      if (e.key === "ArrowDown" || e.key === "ArrowRight")
        target = clampStepIndex(index + 1, total);
      else if (e.key === "ArrowUp" || e.key === "ArrowLeft")
        target = clampStepIndex(index - 1, total);
      else if (e.key === "Home") target = 0;
      else if (e.key === "End") target = total - 1;
      if (target === null) return;
      e.preventDefault();
      selectStep(target);
      // Move real DOM focus too, so keyboard users land on the step they just
      // navigated to instead of being stranded on the previous card.
      stepRefs.current[target]?.focus();
    },
    [selectStep, total],
  );

  // Pointer taps on a process card should reveal the stage below, so the switch
  // is visible even when the stage sits under the fold (mobile / short
  // viewports). Only scroll when little to none of the stage is on screen; when
  // it is already visible (desktop) the viewport stays put. Keyboard activation
  // reports `detail === 0` and is skipped, so arrowing through the cards never
  // yanks focus out of view.
  const revealStage = useCallback(() => {
    const el = stageRef.current;
    if (!el) return;
    if (el.getBoundingClientRect().top > window.innerHeight - 120) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  // Resolve a flow item list (input / output) to display strings once.
  const resolveFlow = useCallback(
    (step: PlaybookStep | undefined, side: "inputs" | "outputs"): string[] =>
      (step?.[side] ?? []).map((it) =>
        it.labelKey ? t(it.labelKey, { defaultValue: it.label }) : it.label,
      ),
    [t],
  );

  const title = t(playbook.titleKey, { defaultValue: playbook.titleDefault });
  const desc = t(playbook.descKey, { defaultValue: playbook.descDefault });
  const selectId = `cases-run-on-${playbook.id}`;
  const progressLabel = t("cases.steps_progress", {
    defaultValue: "{{done}} of {{total}} steps",
    done: doneCount,
    total,
  });

  // Visual identity + the focused step, resolved once for the detail stage.
  const tint = tintFor(playbook.category);
  const cat = CATEGORY_BY_ID[playbook.category];
  const PlaybookIcon = iconFor(playbook.icon);
  const resetButton = (
    <Button
      variant="ghost"
      size="sm"
      icon={<RotateCcw size={13} />}
      onClick={() => reset(playbook.id, projectId)}
      disabled={doneCount === 0 && progress.currentStepIndex === 0}
      title={t("cases.reset_hint", {
        defaultValue: "Clear progress for this case and start over",
      })}
    >
      {t("cases.reset", { defaultValue: "Reset progress" })}
    </Button>
  );
  const currentStep = playbook.steps[currentIndex];
  const CurIcon = iconFor(currentStep?.icon);
  const curDone = currentStep ? isStepDone(progress, currentStep.id) : false;
  const curTitle = currentStep
    ? t(currentStep.titleKey, { defaultValue: currentStep.titleDefault })
    : "";
  const curModule = currentStep
    ? currentStep.moduleLabelKey
      ? t(currentStep.moduleLabelKey, { defaultValue: currentStep.moduleLabel })
      : currentStep.moduleLabel
    : "";
  const curInputs = resolveFlow(currentStep, "inputs");
  const curOutputs = resolveFlow(currentStep, "outputs");
  const hasFlow = curInputs.length > 0 || curOutputs.length > 0;

  const StageScene =
    currentStep?.scene && hasProcessScene(currentStep.scene) ? (
      <StepProcessScene
        sceneId={currentStep.scene}
        title={curTitle}
        className="aspect-[10/7] w-full"
      />
    ) : (
      <StepScene
        icon={currentStep?.icon}
        title={curTitle}
        className="aspect-[10/7] w-full"
      />
    );

  return (
    <div className="space-y-5 animate-fade-in">
      {/* ── Back ────────────────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={onBack ?? (() => navigate("/cases"))}
        className="inline-flex items-center gap-1.5 rounded-lg px-1.5 py-1 text-xs font-medium text-content-secondary transition-colors hover:text-content-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
      >
        <ArrowLeft size={14} />
        {t("cases.back_to_list", { defaultValue: "All cases" })}
      </button>

      {/* ── Header: title + meta left, a small framed case image right ────── */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span
              className={clsx(
                "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-2xs font-medium",
                tint.chip,
              )}
            >
              <PlaybookIcon size={11} strokeWidth={2} aria-hidden="true" />
              {t(cat.labelKey, { defaultValue: cat.labelDefault })}
            </span>
            <span className="text-2xs font-medium text-content-tertiary">
              {t("cases.card.minutes", {
                defaultValue: "about {{count}} min",
                count: playbook.estMinutes,
              })}
            </span>
            <span className="text-2xs font-medium text-content-tertiary">
              {t("cases.card.steps", {
                defaultValue: "{{count}} steps",
                count: total,
              })}
            </span>
          </div>
          <h1 className="text-xl font-semibold tracking-tight text-content-primary sm:text-2xl">
            {title}
          </h1>
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-content-secondary">
            {desc}
          </p>
        </div>

        {/* Decorative case image (alt=""): the H1 already names the case. Kept
            compact so the hero stays tight; the always-light tile chrome is the
            established illustration surface. */}
        <div className="w-32 shrink-0 sm:w-40 lg:w-44">
          <div className="aspect-[4/3] w-full overflow-hidden rounded-xl border border-border-light bg-gradient-to-b from-white to-slate-50 ring-1 ring-inset ring-slate-900/[0.04]">
            <CaseArt
              id={playbook.id}
              fallbackIcon={PlaybookIcon}
              fallbackClass={tint.text}
              alt=""
            />
          </div>
        </div>
      </div>

      {/* ── Control bar: progress + sample project + reset, all one line ─── */}
      <div className="flex flex-col gap-3 rounded-xl border border-border-light bg-surface-primary px-4 py-3 shadow-xs sm:flex-row sm:items-center sm:gap-5">
        <div
          className="flex flex-1 items-center gap-3"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={doneCount}
          aria-valuetext={progressLabel}
          aria-label={t("cases.progress_label", {
            defaultValue: "Case progress",
          })}
          aria-live="polite"
        >
          <span className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
            {t("cases.progress_label", { defaultValue: "Case progress" })}
          </span>
          <div className="h-2 min-w-[5rem] flex-1 overflow-hidden rounded-full bg-surface-secondary">
            <div
              className="h-full rounded-full bg-oe-blue transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="shrink-0 text-2xs font-medium tabular-nums text-content-secondary">
            {progressLabel}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <label
            htmlFor={selectId}
            className="shrink-0 text-2xs font-semibold uppercase tracking-wide text-content-tertiary"
          >
            {t("cases.run_on", { defaultValue: "Run on" })}
          </label>
          <select
            id={selectId}
            value={selectedRaw}
            onChange={(e) => setSelectedProject(playbook.id, e.target.value)}
            className="h-8 max-w-[16rem] rounded-lg border border-border bg-surface-primary px-2.5 text-xs text-content-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
          >
            <option value="">
              {t("cases.run_on_none", {
                defaultValue: "No sample project (just open the module)",
              })}
            </option>
            {sortedProjects.map((p) => {
              const label = isDemoProject(p)
                ? t("cases.run_on_sample_option", {
                    defaultValue: "{{name}} (sample)",
                    name: p.name,
                  })
                : p.name;
              return (
                <option key={p.id} value={p.id}>
                  {label}
                </option>
              );
            })}
          </select>
          {resetButton}
        </div>
      </div>

      {/* ── The process: a compact clickable strip of the ordered steps ──── */}
      <section
        aria-label={t("cases.the_process", { defaultValue: "The process" })}
      >
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
          <p className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
            {t("cases.the_process", { defaultValue: "The process" })}
          </p>
          <p className="text-xs text-content-tertiary">
            {t("cases.process_help", {
              defaultValue: "Choose a step to see what happens and why",
            })}
          </p>
        </div>
        <ol className="flex flex-wrap gap-2" aria-label={title}>
          {playbook.steps.map((step, i) => {
            const done = isStepDone(progress, step.id);
            const isCurrent = i === currentIndex;
            const stepTitle = t(step.titleKey, {
              defaultValue: step.titleDefault,
            });
            return (
              <li key={step.id} className="min-w-[8rem] max-w-[12rem] flex-1">
                <button
                  type="button"
                  ref={(el) => {
                    stepRefs.current[i] = el;
                  }}
                  onClick={(e) => {
                    selectStep(i);
                    if (e.detail !== 0) revealStage();
                  }}
                  onKeyDown={(e) => onStepKeyDown(e, i)}
                  aria-current={isCurrent ? "step" : undefined}
                  className={clsx(
                    "group flex h-full w-full flex-col gap-1.5 rounded-xl border p-2 text-left transition-all",
                    "focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40",
                    isCurrent
                      ? "border-oe-blue bg-oe-blue-subtle shadow-sm ring-1 ring-inset ring-oe-blue/30"
                      : "border-border-light bg-surface-primary hover:border-oe-blue/40 hover:bg-surface-secondary/40",
                  )}
                >
                  {/* A small 16:9 picture keeps the strip visual but compact; the
                      numbered title below is the prominent element, so the strip
                      reads as an ordered process, not a wall of pictures. */}
                  <StepThumb step={step} />
                  <div className="flex items-start gap-1.5">
                    <span
                      className={clsx(
                        "mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-2xs font-bold",
                        done || isCurrent
                          ? "bg-oe-blue text-white"
                          : "bg-surface-secondary text-content-secondary ring-1 ring-inset ring-border-light",
                      )}
                      aria-hidden="true"
                    >
                      {done ? <Check size={11} strokeWidth={2.5} /> : i + 1}
                    </span>
                    <span
                      className={clsx(
                        "min-w-0 text-sm font-semibold leading-snug line-clamp-2",
                        isCurrent ? "text-oe-blue-text" : "text-content-primary",
                      )}
                    >
                      {stepTitle}
                    </span>
                  </div>
                </button>
              </li>
            );
          })}
        </ol>
      </section>

      {/* ── Stage: the selected step in full, as IN -> ACTION -> OUT ─────── */}
      <section ref={stageRef} className="min-w-0 scroll-mt-4">
        {currentStep && (
          <div
            key={currentStep.id}
            className="animate-card-in rounded-2xl border border-border-light bg-surface-primary p-4 shadow-xs sm:p-6"
          >
            {/* Eyebrow: step counter + module chip */}
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <span className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
                {t("cases.step_counter", {
                  defaultValue: "Step {{n}} of {{total}}",
                  n: currentIndex + 1,
                  total,
                })}
              </span>
              <span className="inline-flex shrink-0 items-center gap-1 rounded-md border border-border-light bg-surface-secondary px-2 py-0.5 text-2xs font-medium text-content-secondary">
                <CurIcon size={12} strokeWidth={2} aria-hidden="true" />
                {curModule}
              </span>
            </div>

            {/* Title with status */}
            <div className="mb-4 flex items-start gap-2.5">
              <span
                className={clsx(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold",
                  curDone
                    ? "bg-oe-blue text-white"
                    : "bg-oe-blue/15 text-oe-blue-text ring-1 ring-inset ring-oe-blue/30",
                )}
                aria-hidden="true"
              >
                {curDone ? (
                  <Check size={16} strokeWidth={2.5} />
                ) : (
                  currentIndex + 1
                )}
              </span>
              <h2 className="mt-0.5 text-lg font-semibold leading-snug text-content-primary sm:text-xl">
                {curTitle}
              </h2>
            </div>

            {/* IN -> ACTION -> OUT. When a step has no flow data yet, the scene
                shows on its own so the stage still reads. */}
            {hasFlow ? (
              <div className="mx-auto flex w-full max-w-3xl flex-col items-stretch gap-3 lg:flex-row lg:gap-4">
                <FlowSide
                  label={t("cases.flow.in", { defaultValue: "Goes in" })}
                  items={curInputs}
                  tone="in"
                />
                <FlowConnector />
                <div className="mx-auto flex w-full max-w-[220px] shrink-0 flex-col items-center justify-center">
                  {StageScene}
                  <p className="mt-2 flex items-center justify-center gap-1 text-xs font-medium text-content-tertiary">
                    <CurIcon size={11} strokeWidth={2} aria-hidden="true" />
                    {curModule}
                  </p>
                </div>
                <FlowConnector />
                <FlowSide
                  label={t("cases.flow.out", { defaultValue: "Comes out" })}
                  items={curOutputs}
                  tone="out"
                />
              </div>
            ) : (
              <div className="mx-auto w-full max-w-md">{StageScene}</div>
            )}

            {/* What + Why */}
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <div>
                <p className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
                  {t("cases.step.what", { defaultValue: "What you do" })}
                </p>
                <p className="mt-1 text-sm leading-relaxed text-content-secondary">
                  {t(currentStep.whatKey, {
                    defaultValue: currentStep.whatDefault,
                  })}
                </p>
              </div>
              <div>
                <p className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
                  {t("cases.step.why", { defaultValue: "Why" })}
                </p>
                <p className="mt-1 text-sm leading-relaxed text-content-secondary">
                  {t(currentStep.whyKey, {
                    defaultValue: currentStep.whyDefault,
                  })}
                </p>
              </div>
            </div>

            {/* Actions + step-to-step navigation */}
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border-light pt-5">
              <div className="flex flex-wrap items-center gap-2.5">
                <Button
                  variant="primary"
                  size="md"
                  icon={<ArrowRight size={16} />}
                  iconPosition="right"
                  onClick={() => handleGo(currentStep)}
                  aria-label={t("cases.step.go_to", {
                    defaultValue: "Go to {{module}}",
                    module: curModule,
                  })}
                >
                  {t("cases.step.go_to_module", {
                    defaultValue: "Open {{module}}",
                    module: curModule,
                  })}
                </Button>
                <Button
                  variant={curDone ? "ghost" : "secondary"}
                  size="md"
                  icon={curDone ? <RotateCcw size={16} /> : <Check size={16} />}
                  onClick={() => handleToggle(currentStep)}
                >
                  {curDone
                    ? t("cases.step.mark_undone", {
                        defaultValue: "Mark not done",
                      })
                    : t("cases.step.mark_done", { defaultValue: "Mark done" })}
                </Button>
              </div>
              <div className="flex items-center gap-1.5">
                <Button
                  variant="ghost"
                  size="md"
                  icon={<ArrowLeft size={16} />}
                  onClick={() =>
                    selectStep(clampStepIndex(currentIndex - 1, total))
                  }
                  disabled={currentIndex === 0}
                >
                  {t("cases.prev_step", { defaultValue: "Previous" })}
                </Button>
                <Button
                  variant="ghost"
                  size="md"
                  icon={<ArrowRight size={16} />}
                  iconPosition="right"
                  onClick={() =>
                    selectStep(clampStepIndex(currentIndex + 1, total))
                  }
                  disabled={currentIndex === total - 1}
                >
                  {t("cases.next_step", { defaultValue: "Next" })}
                </Button>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ── Completion note ─────────────────────────────────────────────── */}
      {allDone && (
        <div
          role="status"
          className="flex items-start gap-3 rounded-xl border border-semantic-success/40 bg-semantic-success-bg px-4 py-3 animate-card-in"
        >
          <CheckCircle2
            size={18}
            className="mt-0.5 shrink-0 text-semantic-success"
          />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-content-primary">
              {t("cases.all_done_title", { defaultValue: "Case complete" })}
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-content-secondary">
              {t("cases.all_done_body", {
                defaultValue:
                  "You have stepped through every part of this case. Reset it to run again, or pick another case.",
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
