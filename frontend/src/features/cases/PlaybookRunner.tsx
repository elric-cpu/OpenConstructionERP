// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// PlaybookRunner - the case detail page that drives one case.
//
// Layout, top to bottom: a title block (the hero) that answers "what is this,
// why, how far am I and how do I start" in one place - the category, time and
// step count, the case title and purpose, one obvious primary action (Start /
// Continue / Review), the sample-project picker and reset, and the progress
// track. Below the hero the page splits into two columns on wide screens: a
// sticky "The process" step rail on the left (the ordered steps as compact,
// clickable rows, each showing its module, so the whole journey stays in view
// while you read), and the stage on the right - the selected step in full. The
// stage reads top to bottom: What you do / Why, then the step's IN -> ACTION ->
// OUT data flow across the full column width (what data goes in, the action
// scene you click to open the module, what comes out), then the actions. On
// narrow screens the columns stack (rail above the stage).
//
// The selected step is a single source of truth: `useCasesStore`'s per-run
// current step index. Clicking a process row, using Prev/Next, or marking a
// step done all write that one index, and the rail, the highlight and the stage
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
  Clock,
  ListChecks,
  Play,
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
  hint,
}: {
  label: string;
  items: string[];
  tone: "in" | "out";
  hint?: string;
}): ReactElement {
  const Icon = tone === "in" ? LogIn : LogOut;
  return (
    <div className="flex flex-1 flex-col rounded-xl border border-border-light bg-surface-secondary/40 p-4">
      <p
        className={clsx(
          "flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-content-secondary",
          hint ? "mb-1" : "mb-3",
        )}
      >
        <Icon size={16} strokeWidth={2.2} aria-hidden="true" />
        {label}
      </p>
      {hint ? (
        <p className="mb-3 text-2xs leading-relaxed text-content-tertiary">{hint}</p>
      ) : null}
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
 *  left to right) and down when the columns stack on narrow screens. Pass
 *  `vertical` to force the down arrow, e.g. when the flow runs as a vertical
 *  In -> Action -> Out pipeline inside the step's right-hand visualisation
 *  column. */
function FlowConnector({ vertical = false }: { vertical?: boolean }): ReactElement {
  if (vertical) {
    return (
      <div
        className="flex shrink-0 flex-col items-center justify-center"
        aria-hidden="true"
      >
        <span className="h-3 w-px bg-oe-blue/30" />
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-oe-blue/10 text-oe-blue-text ring-1 ring-inset ring-oe-blue/25">
          <ArrowDown size={13} strokeWidth={2.4} />
        </span>
        <span className="h-3 w-px bg-oe-blue/30" />
      </div>
    );
  }
  return (
    <div className="flex shrink-0 items-center justify-center" aria-hidden="true">
      {/* Desktop: a short gradient rail into a soft circular arrow node, so the
          hand-off between blocks reads as a deliberate step, not a bare arrow. */}
      <div className="hidden items-center lg:flex">
        <span className="h-px w-2.5 bg-gradient-to-r from-transparent to-oe-blue/40" />
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-oe-blue/10 text-oe-blue-text shadow-sm ring-1 ring-inset ring-oe-blue/25">
          <ArrowRight size={14} strokeWidth={2.4} />
        </span>
        <span className="h-px w-2.5 bg-gradient-to-r from-oe-blue/40 to-transparent" />
      </div>
      {/* Mobile: the same node, stacked between rows. */}
      <div className="flex flex-col items-center lg:hidden">
        <span className="h-3 w-px bg-oe-blue/30" />
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-oe-blue/10 text-oe-blue-text ring-1 ring-inset ring-oe-blue/25">
          <ArrowDown size={13} strokeWidth={2.4} />
        </span>
        <span className="h-3 w-px bg-oe-blue/30" />
      </div>
    </div>
  );
}

/** The thumbnail for one step in the process rail: the step's bespoke process
 *  scene when it has one, otherwise its icon scene, framed to match the stage so
 *  the rail reads as a row of pictures of the actual work. `className` sizes the
 *  tile (the rail passes a small fixed width; the default fills its box). */
function StepThumb({
  step,
  className = "aspect-[16/9] w-full",
}: {
  step: PlaybookStep;
  className?: string;
}): ReactElement {
  return step.scene && hasProcessScene(step.scene) ? (
    <StepProcessScene sceneId={step.scene} rounded="rounded-lg" className={className} />
  ) : (
    <StepScene icon={step.icon} rounded="rounded-lg" className={className} />
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
      // The rail is a single sequence, so both axes walk it.
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

  // Pointer taps on a process row should reveal the stage below, so the switch
  // is visible even when the stage sits under the fold (mobile / short
  // viewports). Only scroll when little to none of the stage is on screen; when
  // it is already visible (wide screens, side by side) the viewport stays put.
  // Keyboard activation reports `detail === 0` and is skipped, so arrowing
  // through the rows never yanks focus out of view.
  const revealStage = useCallback(() => {
    const el = stageRef.current;
    if (!el) return;
    if (el.getBoundingClientRect().top > window.innerHeight - 120) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  // The hero's primary action always brings the working stage into view (and on
  // narrow screens that is a real scroll down to it), then leaves the user on
  // their current step ready to read and act.
  const scrollToStage = useCallback(() => {
    stageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
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

  // The hero primary reads as Start / Continue / Review depending on where the
  // run stands, so returning to a half-finished case is obvious.
  const hasStarted = doneCount > 0 || currentIndex > 0;
  const primaryLabel = allDone
    ? t("cases.hero.review", { defaultValue: "Review case" })
    : hasStarted
      ? t("cases.hero.continue", { defaultValue: "Continue" })
      : t("cases.hero.start", { defaultValue: "Start case" });

  // The clickable action scene that opens the step's module, reused by the flow
  // and the no-flow layouts so the module link is always the same affordance.
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
  const openModuleLabel = t("cases.step.go_to_module", {
    defaultValue: "Open {{module}}",
    module: curModule,
  });
  const openModuleButton = currentStep ? (
    <button
      type="button"
      onClick={() => handleGo(currentStep)}
      title={t("cases.step.go_to", {
        defaultValue: "Go to {{module}}",
        module: curModule,
      })}
      className="group w-full max-w-[260px] rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
    >
      {StageScene}
      <span className="mt-2 inline-flex w-full items-center justify-center gap-1 text-xs font-semibold text-oe-blue-text transition-colors group-hover:text-oe-blue">
        <CurIcon size={12} strokeWidth={2} aria-hidden="true" />
        {openModuleLabel}
        <ArrowRight
          size={12}
          strokeWidth={2.2}
          className="transition-transform group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </span>
    </button>
  ) : null;

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

      {/* ── Hero: purpose + primary action + run context + progress ──────── */}
      <section className="relative overflow-hidden rounded-2xl border border-border-light bg-gradient-to-br from-oe-blue/[0.08] via-oe-blue/[0.03] to-transparent p-5 sm:p-6">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-10 -top-12 h-44 w-44 rounded-full bg-oe-blue/10 blur-3xl"
        />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-stretch lg:justify-between">
          <div className="min-w-0 flex-1">
            {/* Meta: discipline, time and step count */}
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
              <span className="inline-flex items-center gap-1 text-2xs font-medium text-content-tertiary">
                <Clock size={11} aria-hidden="true" />
                {t("cases.card.minutes", {
                  defaultValue: "about {{count}} min",
                  count: playbook.estMinutes,
                })}
              </span>
              <span className="inline-flex items-center gap-1 text-2xs font-medium text-content-tertiary">
                <ListChecks size={11} aria-hidden="true" />
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

            {/* Primary action + sample-project context + reset, one command row */}
            <div className="mt-4 flex flex-wrap items-center gap-2.5">
              <Button
                variant="primary"
                size="lg"
                icon={<Play size={16} />}
                onClick={() => {
                  selectStep(currentIndex);
                  scrollToStage();
                }}
              >
                {primaryLabel}
              </Button>
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
                  onChange={(e) =>
                    setSelectedProject(playbook.id, e.target.value)
                  }
                  className="h-8 max-w-[15rem] rounded-lg border border-border bg-surface-primary px-2.5 text-xs text-content-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
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
              </div>
              {resetButton}
            </div>

            {/* Progress track */}
            <div
              className="mt-4 flex items-center gap-3"
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
              <div className="h-2 min-w-[5rem] max-w-xs flex-1 overflow-hidden rounded-full bg-surface-secondary">
                <div
                  className="h-full rounded-full bg-oe-blue transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="shrink-0 text-2xs font-medium tabular-nums text-content-secondary">
                {progressLabel}
              </span>
            </div>
          </div>

          {/* Decorative case image (alt=""): the H1 already names the case. A
              plain white surface so the illustration reads as content rather
              than a boxed-out card. On wide screens the tile is absolutely
              positioned to fill the column, so its height tracks the text
              column (the image bottom lines up with the progress row) instead
              of the art forcing the hero taller than the copy. */}
          <div className="w-40 shrink-0 sm:w-52 lg:relative lg:w-72">
            <div className="aspect-[4/3] w-full overflow-hidden rounded-xl border border-border-light bg-white lg:absolute lg:inset-0 lg:aspect-auto">
              <CaseArt
                id={playbook.id}
                fallbackIcon={PlaybookIcon}
                fallbackClass={tint.text}
                alt=""
              />
            </div>
          </div>
        </div>
      </section>

      {/* ── Two columns on wide screens: the step rail + the stage ───────── */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[19rem_minmax(0,1fr)] xl:items-start">
        {/* The process: a sticky, scannable rail of the ordered steps. Each row
            shows its number/status, a small picture of the work and the module
            it uses, so the whole journey stays readable while the stage scrolls. */}
        <section
          aria-label={t("cases.the_process", { defaultValue: "The process" })}
          className="xl:sticky xl:top-4 xl:self-start"
        >
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
            <p className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
              {t("cases.the_process", { defaultValue: "The process" })}
            </p>
            <p className="text-xs text-content-tertiary xl:hidden">
              {t("cases.process_help", {
                defaultValue: "Choose a step to see what happens and why",
              })}
            </p>
          </div>
          <ol
            className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:flex xl:max-h-[calc(100vh-3rem)] xl:flex-col xl:overflow-y-auto xl:pr-1"
            aria-label={title}
          >
            {playbook.steps.map((step, i) => {
              const done = isStepDone(progress, step.id);
              const isCurrent = i === currentIndex;
              const stepTitle = t(step.titleKey, {
                defaultValue: step.titleDefault,
              });
              const stepModule = step.moduleLabelKey
                ? t(step.moduleLabelKey, { defaultValue: step.moduleLabel })
                : step.moduleLabel;
              return (
                <li key={step.id} className="min-w-0">
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
                      "group flex h-full w-full items-center gap-2.5 rounded-xl border p-2 text-left transition-all",
                      "focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40",
                      isCurrent
                        ? "border-oe-blue bg-oe-blue-subtle shadow-sm ring-1 ring-inset ring-oe-blue/30"
                        : "border-border-light bg-surface-primary hover:border-oe-blue/40 hover:bg-surface-secondary/40",
                    )}
                  >
                    <span
                      className={clsx(
                        "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-2xs font-bold",
                        done || isCurrent
                          ? "bg-oe-blue text-white"
                          : "bg-surface-secondary text-content-secondary ring-1 ring-inset ring-border-light",
                      )}
                      aria-hidden="true"
                    >
                      {done ? <Check size={12} strokeWidth={2.5} /> : i + 1}
                    </span>
                    <StepThumb
                      step={step}
                      className="aspect-[16/9] w-16 shrink-0 sm:w-20"
                    />
                    <span className="min-w-0 flex-1">
                      <span
                        className={clsx(
                          "block text-sm font-semibold leading-snug line-clamp-2",
                          isCurrent
                            ? "text-oe-blue-text"
                            : "text-content-primary",
                        )}
                      >
                        {stepTitle}
                      </span>
                      <span className="mt-1 flex">
                        <span className="inline-block max-w-full truncate rounded border border-border-light bg-surface-secondary px-1.5 py-px text-2xs font-medium text-content-tertiary">
                          {stepModule}
                        </span>
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </section>

        {/* ── Stage: the selected step in full, IN -> ACTION -> OUT ───────── */}
        <section ref={stageRef} className="min-w-0 scroll-mt-4">
          {currentStep && (
            <div
              key={currentStep.id}
              className="animate-card-in rounded-2xl border border-border-light bg-surface-primary p-4 shadow-xs sm:p-6"
            >
              {/* Eyebrow: step counter + module chip, and quick prev/next */}
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
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
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() =>
                      selectStep(clampStepIndex(currentIndex - 1, total))
                    }
                    disabled={currentIndex === 0}
                    aria-label={t("cases.prev_step", { defaultValue: "Previous" })}
                    className="flex h-7 w-7 items-center justify-center rounded-lg border border-border-light bg-surface-primary text-content-secondary transition-colors hover:border-oe-blue/40 hover:text-content-primary disabled:cursor-not-allowed disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
                  >
                    <ArrowLeft size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      selectStep(clampStepIndex(currentIndex + 1, total))
                    }
                    disabled={currentIndex === total - 1}
                    aria-label={t("cases.next_step", { defaultValue: "Next" })}
                    className="flex h-7 w-7 items-center justify-center rounded-lg border border-border-light bg-surface-primary text-content-secondary transition-colors hover:border-oe-blue/40 hover:text-content-primary disabled:cursor-not-allowed disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
                  >
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>

              {/* Title with status */}
              <div className="mb-5 flex items-start gap-2.5">
                <span
                  className={clsx(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold",
                    curDone
                      ? "bg-oe-blue text-white"
                      : "bg-oe-blue/15 text-oe-blue-text ring-1 ring-inset ring-oe-blue/30",
                  )}
                  aria-hidden="true"
                >
                  {curDone ? <Check size={16} strokeWidth={2.5} /> : currentIndex + 1}
                </span>
                <h2 className="mt-0.5 text-lg font-semibold leading-snug text-content-primary sm:text-xl">
                  {curTitle}
                </h2>
              </div>

              {/* What you do + Why: two readable columns on wider screens. */}
              <div className="grid gap-5 sm:grid-cols-2 sm:gap-7">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-oe-blue-text">
                    {t("cases.step.what", { defaultValue: "What you do" })}
                  </p>
                  <p className="mt-1.5 text-base leading-relaxed text-content-primary sm:text-lg">
                    {t(currentStep.whatKey, {
                      defaultValue: currentStep.whatDefault,
                    })}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-content-tertiary">
                    {t("cases.step.why", { defaultValue: "Why" })}
                  </p>
                  <p className="mt-1.5 text-base leading-relaxed text-content-secondary sm:text-lg">
                    {t(currentStep.whyKey, {
                      defaultValue: currentStep.whyDefault,
                    })}
                  </p>
                </div>
              </div>

              {/* The data flow, across the full width: In -> Action -> Out. The
                  Goes-in and Comes-out blocks sit either side of the action
                  scene, and the scene is a button into the module, so it is
                  obvious where the work happens. Stacks on narrow screens. */}
              <div className="mt-6 border-t border-border-light pt-5">
                {hasFlow ? (
                  <div className="flex flex-col items-stretch gap-2.5 lg:flex-row lg:items-stretch lg:gap-1">
                    <FlowSide
                      label={t("cases.flow.in", { defaultValue: "Goes in" })}
                      hint={t("cases.flow.in_hint", {
                        defaultValue: "What this step needs to start",
                      })}
                      items={curInputs}
                      tone="in"
                    />
                    <FlowConnector />
                    <div className="flex shrink-0 flex-col items-center justify-center lg:w-[32%]">
                      {openModuleButton}
                    </div>
                    <FlowConnector />
                    <FlowSide
                      label={t("cases.flow.out", { defaultValue: "Comes out" })}
                      hint={t("cases.flow.out_hint", {
                        defaultValue: "What you have when it is done",
                      })}
                      items={curOutputs}
                      tone="out"
                    />
                  </div>
                ) : (
                  <div className="mx-auto flex w-full max-w-md flex-col items-center">
                    {openModuleButton}
                  </div>
                )}
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
                    {openModuleLabel}
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
      </div>

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
