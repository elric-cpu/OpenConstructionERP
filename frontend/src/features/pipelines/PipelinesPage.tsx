/**
 * `<PipelinesPage>` — full-bleed 3-zone shell for the Pipeline Builder.
 *
 * Layout (03_ux_visual §1), mirroring `EACBlockEditorPage`'s
 * `h-[calc(100vh-var(--oe-header-height,56px))]`:
 *
 *   ┌──────────┬──────────────────────────────────┬───────────┐
 *   │ Palette  │  Toolbar                          │ Inspector │
 *   │ 260px    ├──────────────────────────────────┤ 320px     │
 *   │ collap.  │  Canvas (xyflow)                  │ collap.   │
 *   │          ├──────────────────────────────────┴───────────┤
 *   │          │  Run dock (28px idle → 280px)                 │
 *   └──────────┴──────────────────────────────────────────────┘
 *
 * Server state via React Query (`api.ts`); local graph state via the Zustand
 * store. Live run = polling `GET /runs/{run_id}` (no websocket).
 * Empty canvas → `EmptyState`. Onboarding via the shared `OnboardingTour`.
 */
import { Workflow } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { EmptyState, OnboardingTour } from '@/shared/ui';
import type { TourStep } from '@/shared/ui';
import { getErrorMessage } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';

import { PipelineCanvas } from './canvas/PipelineCanvas';
import { PipelineToolbar } from './canvas/PipelineToolbar';
import { InspectorPanel } from './components/InspectorPanel';
import { NodePalette } from './components/NodePalette';
import { RunDock } from './components/RunDock';
import {
  isTerminalRunStatus,
  useCreatePipeline,
  useNodeTypes,
  usePipeline,
  usePipelineRun,
  usePipelineRuns,
  useRunPipeline,
  useUpdatePipeline,
} from './api';
import { usePipelineStore } from './usePipelineStore';

export function PipelinesPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get('project');
  const pipelineIdParam = searchParams.get('id') ?? undefined;
  const addToast = useToastStore((s) => s.addToast);

  const [paletteCollapsed, setPaletteCollapsed] = useState(false);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [dockExpanded, setDockExpanded] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | undefined>(undefined);
  const [loadToken, setLoadToken] = useState(0);
  const fitViewRef = useRef<(() => void) | null>(null);

  // ── Server state ────────────────────────────────────────────────────────
  const nodeTypesQuery = useNodeTypes();
  const pipelineQuery = usePipeline(pipelineIdParam);
  const runsQuery = usePipelineRuns(
    usePipelineStore((s) => s.meta.id) ?? pipelineIdParam,
  );
  const runDetailQuery = usePipelineRun(activeRunId);

  const createMut = useCreatePipeline();
  const savedId = usePipelineStore((s) => s.meta.id);
  const updateMut = useUpdatePipeline(savedId ?? pipelineIdParam ?? '');
  const runMut = useRunPipeline(savedId ?? pipelineIdParam ?? '');

  const nodeTypes = useMemo(
    () => nodeTypesQuery.data ?? [],
    [nodeTypesQuery.data],
  );

  // ── Store wiring ────────────────────────────────────────────────────────
  const nodeCount = usePipelineStore((s) => s.nodes.length);
  const edgeCount = usePipelineStore((s) => s.edges.length);
  const loadGraphMeta = usePipelineStore((s) => s.loadGraph);
  const markSaved = usePipelineStore((s) => s.markSaved);
  const patchMeta = usePipelineStore((s) => s.patchMeta);
  const startRun = usePipelineStore((s) => s.startRun);
  const applyRunDetail = usePipelineStore((s) => s.applyRunDetail);
  const clearRun = usePipelineStore((s) => s.clearRun);
  const toGraphJSON = usePipelineStore((s) => s.toGraphJSON);
  const reset = usePipelineStore((s) => s.reset);

  // Reset the store on unmount so a fresh visit starts clean.
  useEffect(() => () => reset(), [reset]);

  // Set the project binding once from the URL.
  useEffect(() => {
    if (projectId) patchMeta({ projectId });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // Hydrate a loaded pipeline (canvas does the actual graph rebuild).
  const loadedGraph = pipelineQuery.data?.graph ?? null;
  useEffect(() => {
    if (!pipelineQuery.data) return;
    const p = pipelineQuery.data;
    loadGraphMeta(p.graph, {
      id: p.id,
      name: p.name ?? '',
      description: p.description ?? '',
      projectId: p.project_id ?? projectId ?? null,
      isPublished: Boolean(p.is_published),
    });
    setLoadToken((n) => n + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineQuery.data]);

  // Project polled run detail onto the canvas/dock; stop when terminal.
  useEffect(() => {
    const d = runDetailQuery.data;
    if (!d) return;
    applyRunDetail({
      status: d.status,
      progress_percent: d.progress_percent,
      error: d.error,
      nodes: d.nodes,
    });
    if (isTerminalRunStatus(d.status)) {
      setActiveRunId(undefined);
      void runsQuery.refetch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runDetailQuery.data]);

  // ── Authoring-time issues (lightweight linter) ─────────────────────────
  const issueCount = useMemo(() => {
    // Phase-1 heuristic: a node with required inputs but no incoming edge.
    const edges = usePipelineStore.getState().edges;
    const nodes = usePipelineStore.getState().nodes;
    let count = 0;
    for (const n of nodes) {
      if (n.inputs.length > 0 && !edges.some((e) => e.target === n.id)) {
        count += 1;
      }
    }
    return count;
    // recompute when the node OR edge set changes (an unconnected
    // required input is an edge-level fact, so edgeCount must be a dep)
  }, [nodeCount, edgeCount, loadToken, runDetailQuery.dataUpdatedAt]);

  // ── Actions ─────────────────────────────────────────────────────────────
  const handleSave = useCallback(async () => {
    const meta = usePipelineStore.getState().meta;
    const graph = toGraphJSON();
    const name =
      meta.name.trim() ||
      t('pipeline.untitled', { defaultValue: 'Untitled pipeline' });
    try {
      if (meta.id) {
        await updateMut.mutateAsync({
          name,
          description: meta.description,
          graph,
          is_published: meta.isPublished,
        });
      } else {
        const created = await createMut.mutateAsync({
          name,
          description: meta.description || undefined,
          project_id: meta.projectId,
          graph,
        });
        if (created?.id) markSaved(created.id);
      }
      addToast({
        type: 'success',
        title: t('pipeline.toast.saved', { defaultValue: 'Pipeline saved' }),
      });
    } catch (err) {
      addToast({
        type: 'error',
        title: t('pipeline.toast.save_failed', {
          defaultValue: 'Could not save pipeline',
        }),
        message: getErrorMessage(err),
      });
    }
  }, [addToast, createMut, markSaved, t, toGraphJSON, updateMut]);

  const handleRun = useCallback(async () => {
    const meta = usePipelineStore.getState().meta;
    let id = meta.id;
    if (!id) {
      // Auto-save first so there's something to run.
      try {
        const created = await createMut.mutateAsync({
          name:
            meta.name.trim() ||
            t('pipeline.untitled', { defaultValue: 'Untitled pipeline' }),
          description: meta.description || undefined,
          project_id: meta.projectId,
          graph: toGraphJSON(),
        });
        id = created?.id ?? null;
        if (id) markSaved(id);
      } catch (err) {
        addToast({
          type: 'error',
          title: t('pipeline.toast.run_failed', {
            defaultValue: 'Could not start the run',
          }),
          message: getErrorMessage(err),
        });
        return;
      }
    }
    if (!id) return;
    try {
      const res = await runMut.mutateAsync();
      if (res?.run_id) {
        startRun(res.run_id);
        setActiveRunId(res.run_id);
        setDockExpanded(true);
      }
    } catch (err) {
      addToast({
        type: 'error',
        title: t('pipeline.toast.run_failed', {
          defaultValue: 'Could not start the run',
        }),
        message: getErrorMessage(err),
      });
    }
  }, [addToast, createMut, markSaved, runMut, startRun, t, toGraphJSON]);

  const handleStop = useCallback(() => {
    // Phase-1: no cancel endpoint in the pinned contract — just detach the
    // poller and clear the local overlay (run continues server-side).
    setActiveRunId(undefined);
    clearRun();
  }, [clearRun]);

  const handleExplain = useCallback(() => {
    addToast({
      type: 'info',
      title: t('pipeline.explain.coming_soon_title', {
        defaultValue: 'Explain this pipeline',
      }),
      message: t('pipeline.explain.coming_soon_body', {
        defaultValue:
          'The plain-language story view arrives in the next release.',
      }),
    });
  }, [addToast, t]);

  // The shared OnboardingTour resolves `title`/`description` via its internal
  // STEP_DEFAULTS map and falls back to the raw value when a key is unknown —
  // so we pass already-translated strings (we may not edit locale files).
  const tourSteps: TourStep[] = useMemo(
    () => [
      {
        target: '[data-tour="pipeline-palette"]',
        title: t('pipeline.tour.palette_title', {
          defaultValue: 'Pick your steps',
        }),
        description: t('pipeline.tour.palette_body', {
          defaultValue:
            'Drag a step from here onto the canvas, or just click it to drop it in the middle.',
        }),
        position: 'right',
      },
      {
        target: '[data-tour="pipeline-canvas"]',
        title: t('pipeline.tour.canvas_title', {
          defaultValue: 'Connect the steps',
        }),
        description: t('pipeline.tour.canvas_body', {
          defaultValue:
            'Drag from one step output dot to the next step input. Colours show the data type.',
        }),
        position: 'bottom',
      },
      {
        target: '[data-testid="pipeline-run"]',
        title: t('pipeline.tour.run_title', { defaultValue: 'Run it' }),
        description: t('pipeline.tour.run_body', {
          defaultValue:
            'Press Run to execute the pipeline and watch each step light up live.',
        }),
        position: 'bottom',
      },
    ],
    [t],
  );

  const isRunning =
    Boolean(activeRunId) &&
    !isTerminalRunStatus(runDetailQuery.data?.status);
  const busy =
    createMut.isPending || updateMut.isPending || runMut.isPending;

  return (
    <div
      data-testid="pipelines-page"
      data-tour="pipelines"
      className="flex h-[calc(100vh-var(--oe-header-height,56px))] w-full overflow-hidden bg-surface-primary"
    >
      <NodePalette
        nodeTypes={nodeTypes}
        loading={nodeTypesQuery.isLoading}
        collapsed={paletteCollapsed}
        onToggleCollapsed={() => setPaletteCollapsed((v) => !v)}
      />

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <PipelineToolbar
          onFitView={() => fitViewRef.current?.()}
          onSave={handleSave}
          onRun={handleRun}
          onStop={handleStop}
          onExplain={handleExplain}
          busy={busy}
          running={isRunning}
          issueCount={issueCount}
        />
        <div
          className="relative min-h-0 flex-1"
          data-tour="pipeline-canvas"
        >
          {nodeCount === 0 && !pipelineQuery.isLoading ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-surface-primary">
              <EmptyState
                icon={<Workflow size={24} aria-hidden="true" />}
                title={t('pipeline.empty.title', {
                  defaultValue: 'Build your first automation',
                })}
                description={t('pipeline.empty.description', {
                  defaultValue:
                    'Drag a trigger and a few steps from the palette on the left, connect them, then press Run.',
                })}
              />
            </div>
          ) : null}
          <PipelineCanvas
            nodeTypes={nodeTypes}
            loadGraph={loadedGraph}
            loadToken={loadToken}
            onFitViewReady={(fit) => {
              fitViewRef.current = fit;
            }}
            testId="pipeline-canvas"
          />
        </div>
        <RunDock
          runs={runsQuery.data ?? []}
          runsLoading={runsQuery.isLoading}
          expanded={dockExpanded}
          onToggleExpanded={() => setDockExpanded((v) => !v)}
        />
      </main>

      <InspectorPanel
        nodeTypes={nodeTypes}
        collapsed={inspectorCollapsed}
        onToggleCollapsed={() => setInspectorCollapsed((v) => !v)}
      />

      <OnboardingTour steps={tourSteps} />
    </div>
  );
}

export default PipelinesPage;
