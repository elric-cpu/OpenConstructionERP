/**
 * Clash Detection — geometric AABB interference / clearance coordination
 * over canonical BIM elements, with a discipline×discipline clash matrix,
 * a Navisworks/Solibri-grade clash-review workspace and one-click BCF export.
 *
 * Route: /clash  (project chosen via ?project= query param)
 *
 * Results area is a full client-side review tool: KPI tiles, a filter bar
 * (matrix click-through, status, type, min-penetration, free-text search),
 * a sticky-header sortable paginated table, optimistic status workflow,
 * per-row + bulk BCF export and a "Isolate in 3D" deep-link into the BIM
 * viewer.
 *
 * BIM deep-link contract (verified in features/bim/BIMPage.tsx):
 *   /projects/{projectId}/bim/{modelId}?isolate=id1,id2
 *   — the viewer reads `?isolate=` (BIMPage L1795-1813), isolates the listed
 *     element ids in the 3D scene and selects them when there is one. There
 *     is no camera/point param, so we isolate both clash elements by id.
 */

import { useMemo, useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  Radar,
  AlertTriangle,
  Ruler,
  CheckCircle2,
  Layers,
  Trash2,
  FileDown,
  Play,
  Search,
  X,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Box,
  Grid3x3,
  ChevronLeft,
  ChevronRight,
  SlidersHorizontal,
  Upload,
  Loader2,
  Boxes,
  ArrowUpRight,
  FolderOpen,
} from 'lucide-react';
import { Card } from '@/shared/ui/Card';
import { Button } from '@/shared/ui/Button';
import { Badge } from '@/shared/ui/Badge';
import { EmptyState } from '@/shared/ui/EmptyState';
import { useToastStore } from '@/stores/useToastStore';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import {
  clashApi,
  type ClashResult,
  type ClashRunSummary,
  type ClashSelectionSet,
  type ClashCategories,
} from './api';
import { buildClashBimLink } from './clashBimLink';

const EMPTY_SET: ClashSelectionSet = { disciplines: [], element_types: [] };

const OPEN_STATUSES = ['new', 'active'];
const STATUS_OPTIONS = [
  'new',
  'active',
  'reviewed',
  'approved',
  'resolved',
  'ignored',
] as const;
type StatusOpt = (typeof STATUS_OPTIONS)[number];

/** How many result rows we page into the browser for client-side
 *  filter/sort. Multiple of the backend's 500-row max. KPI tiles come from
 *  the authoritative run `summary`, NOT this capped set, so the tiles stay
 *  correct even when the row set is capped. */
const CLIENT_CAP = 2000;
const PAGE_SIZE = 100;

type SortKey =
  | 'idx'
  | 'a_name'
  | 'b_name'
  | 'clash_type'
  | 'penetration_m'
  | 'distance_m'
  | 'status';
type SortDir = 'asc' | 'desc';

/** Heat colour for a matrix cell, scaled against the busiest cell. */
function heat(count: number, max: number): string {
  if (count === 0) return 'bg-surface-secondary text-content-tertiary';
  const r = max > 0 ? count / max : 0;
  if (r > 0.66) return 'bg-semantic-error text-content-inverse';
  if (r > 0.33) return 'bg-amber-500 text-content-inverse';
  return 'bg-amber-200 text-amber-900';
}

/** Stable per-discipline chip palette (deterministic — same discipline →
 *  same colour for the whole session). */
const DISCIPLINE_PALETTE = [
  'bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300',
  'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300',
  'bg-purple-100 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300',
  'bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300',
  'bg-cyan-100 text-cyan-700 dark:bg-cyan-950/40 dark:text-cyan-300',
  'bg-pink-100 text-pink-700 dark:bg-pink-950/40 dark:text-pink-300',
  'bg-lime-100 text-lime-700 dark:bg-lime-950/40 dark:text-lime-300',
  'bg-indigo-100 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300',
];
function disciplineHash(d: string): number {
  let h = 0;
  for (let i = 0; i < d.length; i++) h = (h * 31 + d.charCodeAt(i)) >>> 0;
  return h % DISCIPLINE_PALETTE.length;
}
/** The seeded BIM models carry the project name baked into their label
 *  (e.g. "Edifício Comercial Faria Lima — São Paulo — Modelo Estrutural
 *  Revit"). Clash is intra-project and the project is already chosen
 *  globally, so the prefix is pure noise here — strip it down to the
 *  discipline/type part. Falls back to the full name if stripping empties
 *  it. */
function shortModelName(full: string, projectName?: string | null): string {
  let s = (full ?? '').trim();
  const pn = (projectName ?? '').trim();
  if (pn && s.toLowerCase().startsWith(pn.toLowerCase())) {
    s = s
      .slice(pn.length)
      .replace(/^[\s—–\-:/·|]+/, '')
      .trim();
  }
  return s || (full ?? '').trim();
}

function DisciplineChip({ name }: { name: string }) {
  const label = name || '—';
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-1.5 py-0.5 text-2xs font-medium',
        name
          ? DISCIPLINE_PALETTE[disciplineHash(name)]
          : 'bg-surface-secondary text-content-tertiary',
      )}
    >
      {label}
    </span>
  );
}

export function ClashDetectionPage() {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  // The active project is chosen once, globally, from the selector at the
  // top of the app — clash does NOT show its own project picker. We fall
  // back to a legacy ``?project=`` deep-link only when no global context
  // is set yet (external links into a specific project's clashes).
  const ctxProjectId = useProjectContextStore((s) => s.activeProjectId);
  const ctxProjectName = useProjectContextStore((s) => s.activeProjectName);
  const projectId = ctxProjectId ?? params.get('project') ?? '';
  const runId = params.get('run') ?? '';
  const navigate = useNavigate();

  // Run-config form state.
  const [selModels, setSelModels] = useState<string[]>([]);
  const [toleranceMm, setToleranceMm] = useState(10);
  const [clearanceMm, setClearanceMm] = useState(0);
  // Category/type-based search (Set A × Set B) is the primary mode — it is
  // what users reach for first when coordinating a model.
  const [mode, setMode] = useState('selection_sets');
  const [setA, setSetA] = useState<ClashSelectionSet>(EMPTY_SET);
  const [setB, setSetB] = useState<ClashSelectionSet>(EMPTY_SET);

  // Result filters (all client-side).
  const [fStatus, setFStatus] = useState<Set<string>>(new Set());
  const [fType, setFType] = useState<'all' | 'hard' | 'clearance'>('all');
  const [fPair, setFPair] = useState<string>(''); // "A|B" ordered pair
  const [fMinPen, setFMinPen] = useState(0); // mm
  const [fSearch, setFSearch] = useState('');
  const [kpiFilter, setKpiFilter] = useState<
    'all' | 'hard' | 'clearance' | 'open' | 'resolved'
  >('all');

  // Table state.
  const [sortKey, setSortKey] = useState<SortKey>('idx');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [page, setPage] = useState(0);
  const [selResults, setSelResults] = useState<Set<string>>(new Set());

  const modelsQ = useQuery({
    queryKey: ['clash-models', projectId],
    queryFn: () => clashApi.models(projectId),
    enabled: !!projectId,
  });
  const runsQ = useQuery({
    queryKey: ['clash-runs', projectId],
    queryFn: () => clashApi.listRuns(projectId),
    enabled: !!projectId,
  });
  const runQ = useQuery({
    queryKey: ['clash-run', projectId, runId],
    queryFn: () => clashApi.getRun(projectId, runId),
    enabled: !!projectId && !!runId,
  });
  // Element-type / discipline facets for the Set A vs Set B pickers.
  // Keyed by the selected models so switching models refreshes counts.
  const categoriesQ = useQuery({
    queryKey: ['clash-categories', projectId, [...selModels].sort()],
    queryFn: () => clashApi.categories(projectId, selModels),
    enabled:
      !!projectId && mode === 'selection_sets' && selModels.length > 0,
  });
  // Page the result rows into the browser at the backend's 500-row max
  // (single limit=2000 used to 422 → empty UI). KPI tiles do NOT depend on
  // this set — they read the authoritative run `summary`. This set only
  // backs the client-side table filter/sort, and may be capped.
  const resultsQ = useQuery({
    queryKey: ['clash-results', projectId, runId],
    queryFn: ({ signal }) =>
      clashApi.loadAllResults(projectId, runId, {
        cap: CLIENT_CAP,
        signal,
      }),
    enabled: !!projectId && !!runId,
    retry: 1,
  });
  const allResults: ClashResult[] = useMemo(
    () => resultsQ.data?.items ?? [],
    [resultsQ.data],
  );
  /** Server-reported full filtered row count (authoritative for paging). */
  const loadedTotal = resultsQ.data?.total ?? 0;
  /** True when the run has more result rows than we paged into the browser. */
  const rowsCapped = resultsQ.data?.capped ?? false;

  // Surface a fetch failure as a toast (don't swallow it — a non-2xx must
  // never look like "models are clean").
  useEffect(() => {
    if (resultsQ.isError) {
      addToast({
        type: 'error',
        title: t('clash.results_error', {
          defaultValue: 'Failed to load clash results‌⁠‍',
        }),
        message:
          resultsQ.error instanceof Error
            ? resultsQ.error.message
            : undefined,
      });
    }
  }, [resultsQ.isError]); // eslint-disable-line react-hooks/exhaustive-deps

  // Default the model selection to every parsed model once they load.
  useEffect(() => {
    if (modelsQ.data && selModels.length === 0) {
      setSelModels(
        modelsQ.data.filter((m) => m.element_count > 0).map((m) => m.id),
      );
    }
  }, [modelsQ.data]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reset filters/paging/selection whenever the active run changes.
  useEffect(() => {
    setFStatus(new Set());
    setFType('all');
    setFPair('');
    setFMinPen(0);
    setFSearch('');
    setKpiFilter('all');
    setSortKey('idx');
    setSortDir('asc');
    setPage(0);
    setSelResults(new Set());
  }, [runId]);

  const setNonEmpty = (s: ClashSelectionSet) =>
    s.disciplines.length > 0 || s.element_types.length > 0;
  const selectionSetsValid =
    mode !== 'selection_sets' ||
    (setNonEmpty(setA) && setNonEmpty(setB));

  const runMut = useMutation({
    mutationFn: () =>
      clashApi.createRun(projectId, {
        model_ids: selModels,
        tolerance_m: toleranceMm / 1000,
        clearance_m: clearanceMm / 1000,
        mode,
        ...(mode === 'selection_sets'
          ? { set_a: setA, set_b: setB }
          : {}),
      }),
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ['clash-runs', projectId] });
      setParams((p) => {
        p.set('run', run.id);
        return p;
      });
      if (run.status === 'failed') {
        addToast({
          type: 'error',
          title: t('clash.run_failed', { defaultValue: 'Clash run failed‌⁠‍' }),
          message: run.error ?? undefined,
        });
      } else {
        addToast({
          type: 'success',
          title: t('clash.run_done', {
            defaultValue: '{{n}} clashes found across {{e}} elements‌⁠‍',
            n: run.total_clashes,
            e: run.element_count,
          }),
        });
      }
    },
    onError: (e: Error) => addToast({ type: 'error', title: e.message }),
  });

  const statusMut = useMutation({
    mutationFn: (v: { id: string; status: string }) =>
      clashApi.updateResult(projectId, runId, v.id, { status: v.status }),
    // Optimistic: flip the cached row immediately, roll back on error.
    onMutate: async (v) => {
      await qc.cancelQueries({
        queryKey: ['clash-results', projectId, runId],
      });
      const prev = qc.getQueryData<{ items: ClashResult[] }>([
        'clash-results',
        projectId,
        runId,
      ]);
      qc.setQueryData<{ items: ClashResult[] }>(
        ['clash-results', projectId, runId],
        (old) =>
          old
            ? {
                ...old,
                items: old.items.map((r) =>
                  r.id === v.id ? { ...r, status: v.status } : r,
                ),
              }
            : old,
      );
      return { prev };
    },
    onError: (e: Error, _v, ctx) => {
      if (ctx?.prev)
        qc.setQueryData(['clash-results', projectId, runId], ctx.prev);
      addToast({
        type: 'error',
        title: t('clash.status_failed', {
          defaultValue: 'Could not update status‌⁠‍',
        }),
        message: e.message,
      });
    },
    onSuccess: () => {
      addToast({
        type: 'success',
        title: t('clash.status_saved', { defaultValue: 'Status updated‌⁠‍' }),
      });
    },
    onSettled: () => {
      qc.invalidateQueries({
        queryKey: ['clash-results', projectId, runId],
      });
      qc.invalidateQueries({ queryKey: ['clash-run', projectId, runId] });
    },
  });

  const exportMut = useMutation({
    mutationFn: (ids: string[] | null) =>
      clashApi.exportBcf(projectId, runId, { result_ids: ids }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['clash-results', projectId, runId] });
      setSelResults(new Set());
      addToast({
        type: 'success',
        title: t('clash.bcf_done', {
          defaultValue: 'Exported {{n}} clash(es) to BCF ({{s}} skipped)‌⁠‍',
          n: r.exported,
          s: r.skipped,
        }),
      });
    },
    onError: (e: Error) => addToast({ type: 'error', title: e.message }),
  });

  const delMut = useMutation({
    mutationFn: (id: string) => clashApi.deleteRun(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clash-runs', projectId] });
      setParams((p) => {
        p.delete('run');
        return p;
      });
    },
  });

  const summary: ClashRunSummary | undefined = runQ.data?.summary;
  const disciplines = summary?.disciplines ?? [];
  const cellMap = useMemo(() => {
    const m = new Map<string, { count: number; open: number }>();
    for (const c of summary?.matrix ?? []) {
      m.set(`${c.a}|${c.b}`, { count: c.count, open: c.open_count });
    }
    return m;
  }, [summary]);
  const maxCell = useMemo(
    () => Math.max(1, ...(summary?.matrix ?? []).map((c) => c.count)),
    [summary],
  );

  // ── KPI counts — AUTHORITATIVE, from the run + its cached summary ──────
  // These reflect the FULL run (which may be 25k+ clashes), never the
  // capped rows loaded into the table. `run.total_clashes` and
  // `summary.by_type` / `summary.by_status` are computed server-side over
  // every clash. The capped row set only feeds the table below.
  const kpis = useMemo(() => {
    const byType = summary?.by_type ?? {};
    const byStatus = summary?.by_status ?? {};
    // Authoritative full-run total: ClashRunResponse.total_clashes.
    const total = runQ.data?.total_clashes ?? 0;
    const hard = byType['hard'] ?? 0;
    const clearance = byType['clearance'] ?? 0;
    const open = OPEN_STATUSES.reduce(
      (acc, s) => acc + (byStatus[s] ?? 0),
      0,
    );
    const resolved =
      (byStatus['resolved'] ?? 0) + (byStatus['approved'] ?? 0);
    const matrixCells = (summary?.matrix ?? []).filter(
      (c) => c.count > 0,
    ).length;
    return {
      total,
      hard,
      clearance,
      open,
      resolved,
      resolvedPct: total ? Math.round((resolved / total) * 100) : 0,
      disciplines: (summary?.disciplines ?? []).length,
      matrixCells,
    };
  }, [runQ.data, summary]);

  // ── Client-side filter pipeline ───────────────────────────────────────
  const filtered = useMemo(() => {
    const q = fSearch.trim().toLowerCase();
    const minPenM = fMinPen / 1000;
    return allResults.filter((r, i) => {
      r.__idx = i; // stable original ordinal for the # column / idx sort
      if (kpiFilter === 'hard' && r.clash_type !== 'hard') return false;
      if (kpiFilter === 'clearance' && r.clash_type !== 'clearance')
        return false;
      if (kpiFilter === 'open' && !OPEN_STATUSES.includes(r.status))
        return false;
      if (
        kpiFilter === 'resolved' &&
        r.status !== 'resolved' &&
        r.status !== 'approved'
      )
        return false;
      if (fType !== 'all' && r.clash_type !== fType) return false;
      if (fStatus.size > 0 && !fStatus.has(r.status)) return false;
      if (fPair) {
        const [pa, pb] =
          (r.a_discipline || '') < (r.b_discipline || '')
            ? [r.a_discipline, r.b_discipline]
            : [r.b_discipline, r.a_discipline];
        if (`${pa}|${pb}` !== fPair) return false;
      }
      if (r.clash_type === 'hard' && r.penetration_m < minPenM) return false;
      if (q) {
        const hay = `${r.a_name} ${r.b_name} ${r.a_stable_id} ${r.b_stable_id} ${r.a_discipline} ${r.b_discipline}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [allResults, fSearch, fMinPen, fType, fStatus, fPair, kpiFilter]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    const dir = sortDir === 'asc' ? 1 : -1;
    arr.sort((a, b) => {
      let av: number | string;
      let bv: number | string;
      switch (sortKey) {
        case 'a_name':
          av = (a.a_name || a.a_stable_id || '').toLowerCase();
          bv = (b.a_name || b.a_stable_id || '').toLowerCase();
          break;
        case 'b_name':
          av = (a.b_name || a.b_stable_id || '').toLowerCase();
          bv = (b.b_name || b.b_stable_id || '').toLowerCase();
          break;
        case 'clash_type':
          av = a.clash_type;
          bv = b.clash_type;
          break;
        case 'penetration_m':
          av = a.penetration_m ?? 0;
          bv = b.penetration_m ?? 0;
          break;
        case 'distance_m':
          av = a.distance_m ?? 0;
          bv = b.distance_m ?? 0;
          break;
        case 'status':
          av = STATUS_OPTIONS.indexOf(a.status as StatusOpt);
          bv = STATUS_OPTIONS.indexOf(b.status as StatusOpt);
          break;
        default:
          av = a.__idx ?? 0;
          bv = b.__idx ?? 0;
      }
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = useMemo(
    () => sorted.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE),
    [sorted, safePage],
  );

  // Reset to first page whenever the filtered set shrinks/changes.
  useEffect(() => {
    setPage(0);
  }, [fSearch, fMinPen, fType, fStatus, fPair, kpiFilter, sortKey, sortDir]);

  const toggleSort = useCallback(
    (k: SortKey) => {
      if (sortKey === k) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortKey(k);
        setSortDir(k === 'idx' || k === 'a_name' || k === 'b_name' ? 'asc' : 'desc');
      }
    },
    [sortKey],
  );

  const pageIds = useMemo(() => pageRows.map((r) => r.id), [pageRows]);
  const allPageSelected =
    pageIds.length > 0 && pageIds.every((id) => selResults.has(id));
  const somePageSelected = pageIds.some((id) => selResults.has(id));

  function togglePageSelectAll() {
    setSelResults((s) => {
      const n = new Set(s);
      if (allPageSelected) pageIds.forEach((id) => n.delete(id));
      else pageIds.forEach((id) => n.add(id));
      return n;
    });
  }

  function toggleStatusFilter(s: string) {
    setFStatus((cur) => {
      const n = new Set(cur);
      if (n.has(s)) n.delete(s);
      else n.add(s);
      return n;
    });
  }

  function clearAllFilters() {
    setFStatus(new Set());
    setFType('all');
    setFPair('');
    setFMinPen(0);
    setFSearch('');
    setKpiFilter('all');
  }

  const hasActiveFilters =
    fStatus.size > 0 ||
    fType !== 'all' ||
    !!fPair ||
    fMinPen > 0 ||
    !!fSearch.trim() ||
    kpiFilter !== 'all';

  /** Build the verified BIM-viewer deep-link for a clash result.
   *
   *  We isolate BOTH interfering elements, flag them clash-red (`clash=1`),
   *  and pass the clash world centroid (`focus=cx,cy,cz`, raw canonical
   *  Z-up — the viewer applies its own Z-up→Y-up rotation) so the camera
   *  reliably frames the interference even on showcase IFC/RVT models whose
   *  GLB nodes are numeric Revit ids that never match the DB element UUIDs
   *  (the per-element mesh resolution is only an approximate positional
   *  fallback there; the centroid is exact). */
  function bimLink(r: ClashResult): string {
    return buildClashBimLink({
      projectId,
      modelId: r.a_model_id,
      aElementId: r.a_element_id,
      bElementId: r.b_element_id,
      cx: r.cx,
      cy: r.cy,
      cz: r.cz,
    });
  }

  // Layout mode. Before any run is triggered/selected we show a spacious
  // full-width horizontal setup. Once a run is in flight or a run is
  // selected, the config collapses into a left-rail "menu" and the results
  // take over the main area.
  const compactLayout =
    !!runId || runMut.isPending || runQ.data?.status === 'running';

  // ── No active project ────────────────────────────────────────────────
  // The project is selected globally at the top of the app. If none is set
  // we don't show a picker here — we invite the user to upload a BIM model
  // (a new project) to run coordination on.
  if (!projectId) {
    return (
      <div className="w-full animate-fade-in">
        <Header />
        <Card className="mt-6">
          <EmptyState
            icon={<Upload className="h-10 w-10" />}
            title={t('clash.no_project_title', {
              defaultValue: 'No active project‌⁠‍',
            })}
            description={t('clash.no_project_desc', {
              defaultValue:
                'Pick a project from the selector at the top of the page, or upload a BIM model to start coordinating clashes.‌⁠‍',
            })}
            action={
              <Link to="/bim">
                <Button
                  variant="primary"
                  size="sm"
                  icon={<Upload className="h-4 w-4" />}
                >
                  {t('clash.upload_model', {
                    defaultValue: 'Upload a BIM model‌⁠‍',
                  })}
                </Button>
              </Link>
            }
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="w-full animate-fade-in">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <Header />
        {/* ── Active-project context panel ────────────────────────────────
              Project name + a live data summary (BIM models, total
              elements, clash runs) + working deep-links into the 3D
              viewer / element matcher / project overview. Compact enough
              to sit in the header row above the grid in both layouts. */}
        <div className="flex flex-col gap-2.5 rounded-xl border border-border-light bg-surface-secondary/60 px-3.5 py-2.5">
          <div className="flex items-center gap-2 text-sm font-medium text-content-primary">
            <Box className="h-4 w-4 shrink-0 text-oe-blue" />
            <span className="max-w-[280px] truncate" title={ctxProjectName ?? ''}>
              {ctxProjectName ||
                t('clash.active_project', {
                  defaultValue: 'Active project‌⁠‍',
                })}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-content-secondary">
            <span className="inline-flex items-center gap-1.5">
              <Boxes className="h-3.5 w-3.5 text-content-tertiary" />
              {modelsQ.isLoading ? (
                <span className="text-content-tertiary">…</span>
              ) : (
                <>
                  <span className="font-semibold text-content-primary">
                    {modelsQ.data?.length ?? 0}
                  </span>{' '}
                  {t('clash.ctx_models', { defaultValue: 'BIM models‌⁠‍' })}
                </>
              )}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 text-content-tertiary" />
              {modelsQ.isLoading ? (
                <span className="text-content-tertiary">…</span>
              ) : (
                <>
                  <span className="font-semibold text-content-primary">
                    {(
                      modelsQ.data?.reduce(
                        (s, m) => s + (m.element_count ?? 0),
                        0,
                      ) ?? 0
                    ).toLocaleString()}
                  </span>{' '}
                  {t('clash.ctx_elements', { defaultValue: 'elements‌⁠‍' })}
                </>
              )}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Radar className="h-3.5 w-3.5 text-content-tertiary" />
              {runsQ.isLoading ? (
                <span className="text-content-tertiary">…</span>
              ) : (
                <>
                  <span className="font-semibold text-content-primary">
                    {runsQ.data?.length ?? 0}
                  </span>{' '}
                  {t('clash.ctx_runs', { defaultValue: 'clash runs‌⁠‍' })}
                </>
              )}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={<Box className="h-3.5 w-3.5" />}
              disabled={!projectId}
              onClick={() => {
                // Target the first model that actually has parsed
                // geometry so the viewer opens on valid data, not an
                // empty/unparsed model. Falls back to the global viewer.
                const m =
                  modelsQ.data?.find((x) => (x.element_count ?? 0) > 0) ??
                  modelsQ.data?.[0];
                navigate(
                  m
                    ? `/projects/${projectId}/bim/${m.id}`
                    : projectId
                      ? `/projects/${projectId}/bim`
                      : '/bim',
                );
              }}
            >
              {t('clash.open_bim_viewer', {
                defaultValue: 'Open BIM 3D Viewer‌⁠‍',
              })}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={<ArrowUpRight className="h-3.5 w-3.5" />}
              disabled={!projectId}
              onClick={() =>
                navigate(`/match-elements?project=${projectId}`)
              }
            >
              {t('clash.match_elements', {
                defaultValue: 'Match / Analyze elements‌⁠‍',
              })}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              icon={<FolderOpen className="h-3.5 w-3.5" />}
              disabled={!projectId}
              onClick={() => navigate(`/projects/${projectId}`)}
            >
              {t('clash.project_overview', {
                defaultValue: 'Project overview‌⁠‍',
              })}
            </Button>
          </div>
        </div>
      </div>

      <div
        className={clsx(
          'mt-6 grid gap-6',
          compactLayout ? 'lg:grid-cols-[300px_1fr]' : 'grid-cols-1',
        )}
      >
        {/* ── Config rail. Compact → narrow left menu; initial → a wide,
              horizontal full-page setup. ─────────────────────────────── */}
        <div
          className={clsx(
            compactLayout
              ? 'space-y-4'
              : 'grid gap-6 lg:grid-cols-[1fr_320px] lg:items-start',
          )}
        >
          <Card padding="md">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-content-primary">
              <Radar className="h-4 w-4 text-oe-blue" />
              {t('clash.new_run', { defaultValue: 'New clash run‌⁠‍' })}
            </h2>
            <div
              className={clsx(
                'mt-3',
                compactLayout
                  ? 'space-y-3'
                  : 'grid gap-x-6 gap-y-4 md:grid-cols-2 xl:grid-cols-4 items-start',
              )}
            >
              {/* PRIMARY control — what to coordinate. Clash is always
                  intra-project (every selected model's elements tested
                  against each other); the project itself is chosen once,
                  globally, at the top of the app. */}
              <label
                className={clsx(
                  'block text-xs font-medium text-content-secondary',
                  !compactLayout && 'md:col-span-2 xl:col-span-4',
                )}
              >
                {t('clash.mode', {
                  defaultValue: 'What to check for clashes‌⁠‍',
                })}
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border bg-surface-primary px-2 py-1.5 text-sm"
                >
                  <option value="selection_sets">
                    {t('clash.mode_sets', {
                      defaultValue: 'By category / type (Set A vs Set B)‌⁠‍',
                    })}
                  </option>
                  <option value="cross_discipline">
                    {t('clash.mode_cross', {
                      defaultValue: 'Cross-discipline only‌⁠‍',
                    })}
                  </option>
                  <option value="all">
                    {t('clash.mode_all', { defaultValue: 'Every pair‌⁠‍' })}
                  </option>
                </select>
              </label>

              {mode === 'selection_sets' && (
                <div
                  className={clsx(
                    'space-y-2 rounded-lg border border-border bg-surface-secondary/30 p-2',
                    !compactLayout && 'md:col-span-2 xl:col-span-4',
                  )}
                >
                  <p className="text-2xs leading-snug text-content-tertiary">
                    {t('clash.sets_hint', {
                      defaultValue:
                        'Only pairs where one element is in Set A and the other in Set B are tested — e.g. all Walls (A) against all Pipes (B).‌⁠‍',
                    })}
                  </p>
                  <div
                    className={clsx(
                      compactLayout
                        ? 'space-y-2'
                        : 'grid gap-3 lg:grid-cols-2',
                    )}
                  >
                    <SelectionSetPicker
                      label={t('clash.set_a', { defaultValue: 'Set A‌⁠‍' })}
                      accent="oe-blue"
                      value={setA}
                      onChange={setSetA}
                      categories={categoriesQ.data}
                      loading={categoriesQ.isLoading}
                    />
                    <SelectionSetPicker
                      label={t('clash.set_b', { defaultValue: 'Set B‌⁠‍' })}
                      accent="amber"
                      value={setB}
                      onChange={setSetB}
                      categories={categoriesQ.data}
                      loading={categoriesQ.isLoading}
                    />
                  </div>
                  {!selectionSetsValid && (
                    <p className="text-2xs text-semantic-error">
                      {t('clash.sets_required', {
                        defaultValue:
                          'Pick at least one type or discipline for both Set A and Set B.‌⁠‍',
                      })}
                    </p>
                  )}
                </div>
              )}

              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs text-content-secondary">
                  {t('clash.tolerance', {
                    defaultValue: 'Tolerance (mm)‌⁠‍',
                  })}
                  <input
                    type="number"
                    min={0}
                    value={toleranceMm}
                    onChange={(e) => setToleranceMm(Number(e.target.value))}
                    className="mt-1 w-full rounded-md border border-border bg-surface-primary px-2 py-1 text-sm"
                  />
                </label>
                <label className="text-xs text-content-secondary">
                  {t('clash.clearance', {
                    defaultValue: 'Clearance (mm)‌⁠‍',
                  })}
                  <input
                    type="number"
                    min={0}
                    value={clearanceMm}
                    onChange={(e) => setClearanceMm(Number(e.target.value))}
                    className="mt-1 w-full rounded-md border border-border bg-surface-primary px-2 py-1 text-sm"
                  />
                </label>
              </div>

              {/* SECONDARY — every parsed model in this project is included
                  by default (intra-project coordination). Collapsed; only
                  open it to narrow the scope to specific models. */}
              <details
                className={clsx(
                  'rounded-lg border border-border-light',
                  !compactLayout && 'md:col-span-2 xl:col-span-4',
                )}
              >
                <summary className="cursor-pointer select-none px-2.5 py-1.5 text-xs text-content-secondary">
                  {t('clash.models_scope', {
                    defaultValue:
                      'Models in scope — {{n}} of {{total}} included‌⁠‍',
                    n: selModels.length,
                    total: (modelsQ.data ?? []).length,
                  })}
                </summary>
                <div className="max-h-40 space-y-1 overflow-auto border-t border-border-light p-2">
                  {(modelsQ.data ?? []).length === 0 && (
                    <p className="text-xs text-content-tertiary">
                      {t('clash.no_models', {
                        defaultValue:
                          'No parsed BIM models in this project.‌⁠‍',
                      })}
                    </p>
                  )}
                  {(modelsQ.data ?? []).map((m) => (
                    <label
                      key={m.id}
                      className="flex items-center gap-2 text-xs text-content-primary"
                    >
                      <input
                        type="checkbox"
                        checked={selModels.includes(m.id)}
                        onChange={(e) =>
                          setSelModels((s) =>
                            e.target.checked
                              ? [...s, m.id]
                              : s.filter((x) => x !== m.id),
                          )
                        }
                      />
                      <span className="truncate">
                        {shortModelName(m.name, ctxProjectName)}
                      </span>
                      <span className="ml-auto text-content-tertiary">
                        {m.element_count}
                      </span>
                    </label>
                  ))}
                </div>
              </details>

              <div
                className={clsx(
                  !compactLayout &&
                    'flex items-end md:col-span-2 xl:col-span-4',
                )}
              >
                <Button
                  variant="primary"
                  size="sm"
                  className="w-full"
                  loading={runMut.isPending}
                  disabled={selModels.length === 0 || !selectionSetsValid}
                  icon={<Play className="h-4 w-4" />}
                  onClick={() => runMut.mutate()}
                >
                  {t('clash.run', { defaultValue: 'Run clash detection‌⁠‍' })}
                </Button>
              </div>
            </div>
          </Card>

          <Card padding="md">
            <h2 className="text-sm font-semibold text-content-primary">
              {t('clash.history', { defaultValue: 'Run history‌⁠‍' })}
            </h2>
            <div className="mt-2 space-y-1">
              {(runsQ.data ?? []).length === 0 && (
                <p className="text-xs text-content-tertiary">
                  {t('clash.no_runs', { defaultValue: 'No runs yet.‌⁠‍' })}
                </p>
              )}
              {(runsQ.data ?? []).map((r) => (
                <div
                  key={r.id}
                  className={clsx(
                    'flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs',
                    r.id === runId
                      ? 'bg-oe-blue/10 text-oe-blue'
                      : 'hover:bg-surface-secondary text-content-primary',
                  )}
                >
                  <button
                    className="flex-1 truncate text-left"
                    onClick={() =>
                      setParams((p) => {
                        p.set('run', r.id);
                        return p;
                      })
                    }
                  >
                    {r.name}
                    <span className="ml-1 text-content-tertiary">
                      · {r.total_clashes}
                    </span>
                  </button>
                  <button
                    aria-label={t('common.delete', {
                      defaultValue: 'Delete‌⁠‍',
                    })}
                    onClick={() => delMut.mutate(r.id)}
                    className="text-content-tertiary hover:text-semantic-error"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* ── Main: KPIs + matrix + review workspace ────────────────── */}
        <div className="min-w-0 space-y-6">
          {(runMut.isPending || runQ.data?.status === 'running') && (
            <Card padding="md" className="border-oe-blue/30">
              <div className="flex items-center gap-3">
                <Loader2 className="h-5 w-5 shrink-0 animate-spin text-oe-blue" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-content-primary">
                    {t('clash.running_title', {
                      defaultValue: 'Running clash detection…‌⁠‍',
                    })}
                  </p>
                  <p className="text-xs text-content-tertiary">
                    {t('clash.running_desc', {
                      defaultValue:
                        'Testing element geometry for interferences. This can take up to ~30s on large models — please keep this tab open.‌⁠‍',
                    })}
                  </p>
                </div>
              </div>
              <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface-secondary">
                <div
                  className="h-full w-1/3 rounded-full bg-gradient-to-r from-oe-blue/40 via-oe-blue to-oe-blue/40"
                  style={{
                    animation: 'indeterminate 1.15s ease-in-out infinite',
                  }}
                />
              </div>
            </Card>
          )}

          {runId && runQ.data && (
            <>
              {/* ── KPI tiles ──────────────────────────────────────── */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
                <Kpi
                  icon={<Layers className="h-4 w-4" />}
                  label={t('clash.kpi_total', {
                    defaultValue: 'Total clashes‌⁠‍',
                  })}
                  value={kpis.total}
                  active={kpiFilter === 'all'}
                  onClick={() => setKpiFilter('all')}
                />
                <Kpi
                  icon={
                    <AlertTriangle className="h-4 w-4 text-semantic-error" />
                  }
                  label={t('clash.kpi_hard', { defaultValue: 'Hard‌⁠‍' })}
                  value={kpis.hard}
                  active={kpiFilter === 'hard'}
                  onClick={() =>
                    setKpiFilter((v) => (v === 'hard' ? 'all' : 'hard'))
                  }
                />
                <Kpi
                  icon={<Ruler className="h-4 w-4 text-amber-500" />}
                  label={t('clash.kpi_clearance', {
                    defaultValue: 'Clearance‌⁠‍',
                  })}
                  value={kpis.clearance}
                  active={kpiFilter === 'clearance'}
                  onClick={() =>
                    setKpiFilter((v) =>
                      v === 'clearance' ? 'all' : 'clearance',
                    )
                  }
                />
                <Kpi
                  icon={<CheckCircle2 className="h-4 w-4 text-oe-blue" />}
                  label={t('clash.kpi_open', { defaultValue: 'Open‌⁠‍' })}
                  value={kpis.open}
                  active={kpiFilter === 'open'}
                  onClick={() =>
                    setKpiFilter((v) => (v === 'open' ? 'all' : 'open'))
                  }
                />
                <Kpi
                  icon={
                    <CheckCircle2 className="h-4 w-4 text-semantic-success" />
                  }
                  label={t('clash.kpi_resolved', {
                    defaultValue: 'Resolved‌⁠‍',
                  })}
                  value={`${kpis.resolvedPct}%`}
                  active={kpiFilter === 'resolved'}
                  onClick={() =>
                    setKpiFilter((v) =>
                      v === 'resolved' ? 'all' : 'resolved',
                    )
                  }
                />
                <Kpi
                  icon={<Box className="h-4 w-4 text-content-tertiary" />}
                  label={t('clash.kpi_disciplines', {
                    defaultValue: 'Disciplines‌⁠‍',
                  })}
                  value={kpis.disciplines}
                />
                <Kpi
                  icon={<Grid3x3 className="h-4 w-4 text-content-tertiary" />}
                  label={t('clash.kpi_matrix_cells', {
                    defaultValue: 'Matrix cells‌⁠‍',
                  })}
                  value={kpis.matrixCells}
                />
              </div>

              {/* ── Clash matrix ───────────────────────────────────── */}
              <Card padding="md">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-content-primary">
                    {t('clash.matrix_title', {
                      defaultValue:
                        'Clash matrix — discipline × discipline‌⁠‍',
                    })}
                  </h2>
                  {fPair && (
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<X className="h-3.5 w-3.5" />}
                      onClick={() => setFPair('')}
                    >
                      {t('clash.clear_filter', {
                        defaultValue: 'Clear filter‌⁠‍',
                      })}
                    </Button>
                  )}
                </div>
                {disciplines.length === 0 ? (
                  <p className="mt-3 text-sm text-content-tertiary">
                    {t('clash.no_clashes', {
                      defaultValue:
                        'No clashes — the models are clean.‌⁠‍',
                    })}
                  </p>
                ) : (
                  <div className="mt-3 overflow-auto">
                    <table className="border-collapse text-xs">
                      <thead>
                        <tr>
                          <th className="p-2" />
                          {disciplines.map((d) => (
                            <th
                              key={d}
                              className="p-2 font-medium text-content-secondary"
                            >
                              {d}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {disciplines.map((row) => (
                          <tr key={row}>
                            <th className="p-2 text-right font-medium text-content-secondary">
                              {row}
                            </th>
                            {disciplines.map((col) => {
                              const [a, b] =
                                row < col ? [row, col] : [col, row];
                              const cell = cellMap.get(`${a}|${b}`);
                              const c = cell?.count ?? 0;
                              const pairKey = `${a}|${b}`;
                              const isActive = fPair === pairKey;
                              return (
                                <td key={col} className="p-1">
                                  <button
                                    disabled={c === 0}
                                    onClick={() =>
                                      setFPair((cur) =>
                                        cur === pairKey ? '' : pairKey,
                                      )
                                    }
                                    className={clsx(
                                      'flex h-12 w-16 flex-col items-center justify-center rounded-md font-semibold transition-transform',
                                      heat(c, maxCell),
                                      c > 0 && 'hover:scale-105',
                                      isActive &&
                                        'ring-2 ring-oe-blue ring-offset-1',
                                    )}
                                    title={`${a} ↔ ${b}: ${c}`}
                                  >
                                    <span>{c || '·'}</span>
                                    {cell && cell.open > 0 && (
                                      <span className="text-[10px] font-normal opacity-80">
                                        {t('clash.matrix_open', {
                                          defaultValue: '{{n}} open‌⁠‍',
                                          n: cell.open,
                                        })}
                                      </span>
                                    )}
                                  </button>
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              {/* ── Review workspace ──────────────────────────────── */}
              <Card padding="none">
                {/* Toolbar */}
                <div className="border-b border-border-light p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="flex items-center gap-2 text-sm font-semibold text-content-primary">
                      {t('clash.results', {
                        defaultValue: 'Clash results‌⁠‍',
                      })}
                      <Badge variant="neutral" size="sm">
                        {t('clash.count_of', {
                          defaultValue: '{{shown}} of {{total}}‌⁠‍',
                          shown: sorted.length,
                          total: kpis.total,
                        })}
                      </Badge>
                    </h2>

                    <div className="relative ml-auto">
                      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-tertiary" />
                      <input
                        value={fSearch}
                        onChange={(e) => setFSearch(e.target.value)}
                        placeholder={t('clash.search_ph', {
                          defaultValue: 'Search element name…‌⁠‍',
                        })}
                        className="h-8 w-56 rounded-md border border-border bg-surface-primary pl-8 pr-2 text-xs"
                      />
                    </div>

                    <select
                      value={fType}
                      onChange={(e) =>
                        setFType(
                          e.target.value as 'all' | 'hard' | 'clearance',
                        )
                      }
                      className="h-8 rounded-md border border-border bg-surface-primary px-2 text-xs"
                    >
                      <option value="all">
                        {t('clash.all_types', {
                          defaultValue: 'All types‌⁠‍',
                        })}
                      </option>
                      <option value="hard">
                        {t('clash.type_hard', { defaultValue: 'Hard‌⁠‍' })}
                      </option>
                      <option value="clearance">
                        {t('clash.type_clearance', {
                          defaultValue: 'Clearance‌⁠‍',
                        })}
                      </option>
                    </select>

                    <Button
                      variant={
                        selResults.size ? 'primary' : 'secondary'
                      }
                      size="sm"
                      loading={exportMut.isPending}
                      icon={<FileDown className="h-4 w-4" />}
                      onClick={() =>
                        exportMut.mutate(
                          selResults.size ? [...selResults] : null,
                        )
                      }
                    >
                      {selResults.size
                        ? t('clash.export_sel', {
                            defaultValue: 'Export {{n}} to BCF‌⁠‍',
                            n: selResults.size,
                          })
                        : t('clash.export_open', {
                            defaultValue: 'Export open → BCF‌⁠‍',
                          })}
                    </Button>
                  </div>

                  {/* Status filter pills + min-penetration slider */}
                  <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="flex items-center gap-1 text-2xs font-medium uppercase tracking-wide text-content-tertiary">
                        <SlidersHorizontal className="h-3 w-3" />
                        {t('clash.filter_status', {
                          defaultValue: 'Status‌⁠‍',
                        })}
                      </span>
                      {STATUS_OPTIONS.map((s) => (
                        <button
                          key={s}
                          onClick={() => toggleStatusFilter(s)}
                          className={clsx(
                            'rounded-full px-2 py-0.5 text-2xs font-medium transition-colors',
                            fStatus.has(s)
                              ? 'bg-oe-blue text-content-inverse'
                              : 'bg-surface-secondary text-content-secondary hover:bg-surface-tertiary',
                          )}
                        >
                          {t(`clash.status.${s}`, { defaultValue: s })}
                        </button>
                      ))}
                    </div>

                    <label className="flex items-center gap-2 text-2xs text-content-secondary">
                      <span className="font-medium uppercase tracking-wide text-content-tertiary">
                        {t('clash.filter_min_pen', {
                          defaultValue: 'Min penetration‌⁠‍',
                        })}
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={500}
                        step={5}
                        value={fMinPen}
                        onChange={(e) =>
                          setFMinPen(Number(e.target.value))
                        }
                        className="h-1 w-32 accent-oe-blue"
                      />
                      <span className="w-14 tabular-nums text-content-primary">
                        {fMinPen} mm
                      </span>
                    </label>
                  </div>

                  {/* Active-filter chips */}
                  {hasActiveFilters && (
                    <div className="mt-3 flex flex-wrap items-center gap-1.5">
                      {kpiFilter !== 'all' && (
                        <FilterChip
                          label={t(`clash.kpi_${kpiFilter}`, {
                            defaultValue: kpiFilter,
                          })}
                          onClear={() => setKpiFilter('all')}
                        />
                      )}
                      {fType !== 'all' && (
                        <FilterChip
                          label={t(`clash.type_${fType}`, {
                            defaultValue: fType,
                          })}
                          onClear={() => setFType('all')}
                        />
                      )}
                      {fPair && (
                        <FilterChip
                          label={fPair.replace('|', ' ↔ ')}
                          onClear={() => setFPair('')}
                        />
                      )}
                      {[...fStatus].map((s) => (
                        <FilterChip
                          key={s}
                          label={t(`clash.status.${s}`, {
                            defaultValue: s,
                          })}
                          onClear={() => toggleStatusFilter(s)}
                        />
                      ))}
                      {fMinPen > 0 && (
                        <FilterChip
                          label={`≥ ${fMinPen} mm`}
                          onClear={() => setFMinPen(0)}
                        />
                      )}
                      {fSearch.trim() && (
                        <FilterChip
                          label={`"${fSearch.trim()}"`}
                          onClear={() => setFSearch('')}
                        />
                      )}
                      <button
                        onClick={clearAllFilters}
                        className="ml-1 text-2xs font-medium text-oe-blue hover:underline"
                      >
                        {t('clash.clear_all', {
                          defaultValue: 'Clear all‌⁠‍',
                        })}
                      </button>
                    </div>
                  )}
                </div>

                {/* Table — honest three-state handling so a failed fetch
                    can NEVER read as "models are clean". Order matters:
                    error → loading/rows-arriving → genuinely-zero →
                    filtered-to-zero → table. */}
                {resultsQ.isError ? (
                  <EmptyState
                    icon={
                      <AlertTriangle className="h-10 w-10 text-semantic-error" />
                    }
                    title={t('clash.results_error', {
                      defaultValue: 'Failed to load clash results‌⁠‍',
                    })}
                    description={
                      (resultsQ.error instanceof Error
                        ? resultsQ.error.message
                        : '') ||
                      t('clash.results_error_desc', {
                        defaultValue:
                          'The clash results could not be loaded. This does not mean the models are clean — please retry.‌⁠‍',
                      })
                    }
                    action={
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={resultsQ.isFetching}
                        onClick={() => resultsQ.refetch()}
                      >
                        {t('clash.retry', { defaultValue: 'Retry‌⁠‍' })}
                      </Button>
                    }
                  />
                ) : resultsQ.isLoading ||
                  (kpis.total > 0 && allResults.length === 0) ? (
                  <TableSkeleton />
                ) : kpis.total === 0 ? (
                  <EmptyState
                    icon={<Radar className="h-10 w-10" />}
                    title={t('clash.no_clashes_title', {
                      defaultValue: 'No clashes detected‌⁠‍',
                    })}
                    description={t('clash.no_clashes', {
                      defaultValue:
                        'No clashes — the models are clean.‌⁠‍',
                    })}
                  />
                ) : sorted.length === 0 ? (
                  <EmptyState
                    icon={<Radar className="h-10 w-10" />}
                    title={t('clash.no_match_title', {
                      defaultValue: 'No clashes match the filters‌⁠‍',
                    })}
                    description={t('clash.no_match_desc', {
                      defaultValue:
                        'Try widening or clearing the active filters.‌⁠‍',
                    })}
                    action={
                      hasActiveFilters ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={clearAllFilters}
                        >
                          {t('clash.clear_all', {
                            defaultValue: 'Clear all‌⁠‍',
                          })}
                        </Button>
                      ) : undefined
                    }
                  />
                ) : (
                  <div>
                    {/* Capped-rows notice: the run has more clashes than we
                        paged into the browser. KPIs above are still the
                        full authoritative totals. Lives ABOVE the scroll
                        container so it doesn't fight the sticky header. */}
                    {rowsCapped && (
                      <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-2xs text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-300">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                        <span>
                          {t('clash.capped_notice', {
                            defaultValue:
                              'Showing the first {{loaded}} of {{total}} clashes — refine the filters to narrow the review set.‌⁠‍',
                            loaded: allResults.length,
                            total: loadedTotal,
                          })}
                        </span>
                      </div>
                    )}
                    <div className="max-h-[640px] overflow-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="sticky top-0 z-10 bg-surface-elevated">
                        <tr className="border-b border-border-light text-content-tertiary">
                          <th className="w-9 px-3 py-2.5">
                            <input
                              type="checkbox"
                              aria-label={t('clash.select_all', {
                                defaultValue: 'Select all on page‌⁠‍',
                              })}
                              checked={allPageSelected}
                              ref={(el) => {
                                if (el)
                                  el.indeterminate =
                                    !allPageSelected && somePageSelected;
                              }}
                              onChange={togglePageSelectAll}
                            />
                          </th>
                          <SortableTh
                            label="#"
                            k="idx"
                            sortKey={sortKey}
                            sortDir={sortDir}
                            onSort={toggleSort}
                            className="w-12"
                          />
                          <SortableTh
                            label={t('clash.col_a', {
                              defaultValue: 'Element A‌⁠‍',
                            })}
                            k="a_name"
                            sortKey={sortKey}
                            sortDir={sortDir}
                            onSort={toggleSort}
                          />
                          <SortableTh
                            label={t('clash.col_b', {
                              defaultValue: 'Element B‌⁠‍',
                            })}
                            k="b_name"
                            sortKey={sortKey}
                            sortDir={sortDir}
                            onSort={toggleSort}
                          />
                          <SortableTh
                            label={t('clash.col_type', {
                              defaultValue: 'Type‌⁠‍',
                            })}
                            k="clash_type"
                            sortKey={sortKey}
                            sortDir={sortDir}
                            onSort={toggleSort}
                          />
                          <SortableTh
                            label={t('clash.col_penetration', {
                              defaultValue: 'Penetration‌⁠‍',
                            })}
                            k="penetration_m"
                            sortKey={sortKey}
                            sortDir={sortDir}
                            onSort={toggleSort}
                            align="right"
                          />
                          <SortableTh
                            label={t('clash.col_distance', {
                              defaultValue: 'Distance‌⁠‍',
                            })}
                            k="distance_m"
                            sortKey={sortKey}
                            sortDir={sortDir}
                            onSort={toggleSort}
                            align="right"
                          />
                          <SortableTh
                            label={t('clash.col_status', {
                              defaultValue: 'Status‌⁠‍',
                            })}
                            k="status"
                            sortKey={sortKey}
                            sortDir={sortDir}
                            onSort={toggleSort}
                          />
                          <th className="px-3 py-2.5 text-right">
                            {t('clash.col_actions', {
                              defaultValue: 'Actions‌⁠‍',
                            })}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {pageRows.map((r) => {
                          const selected = selResults.has(r.id);
                          return (
                            <tr
                              key={r.id}
                              className={clsx(
                                'border-b border-border-light/60 transition-colors',
                                selected
                                  ? 'bg-oe-blue/5'
                                  : 'hover:bg-surface-secondary',
                              )}
                            >
                              <td className="px-3 py-2">
                                <input
                                  type="checkbox"
                                  aria-label={t('clash.select_row', {
                                    defaultValue: 'Select clash‌⁠‍',
                                  })}
                                  checked={selected}
                                  onChange={(e) =>
                                    setSelResults((s) => {
                                      const n = new Set(s);
                                      if (e.target.checked) n.add(r.id);
                                      else n.delete(r.id);
                                      return n;
                                    })
                                  }
                                />
                              </td>
                              <td className="px-3 py-2 tabular-nums text-content-tertiary">
                                {(r.__idx ?? 0) + 1}
                              </td>
                              <td className="max-w-[220px] px-3 py-2">
                                <div className="truncate font-medium text-content-primary">
                                  {r.a_name || r.a_stable_id}
                                </div>
                                <div className="mt-0.5 flex items-center gap-1">
                                  <DisciplineChip
                                    name={r.a_discipline}
                                  />
                                  {r.a_element_type && (
                                    <span
                                      className="max-w-[130px] truncate text-2xs text-content-tertiary"
                                      title={r.a_element_type}
                                    >
                                      {r.a_element_type}
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="max-w-[220px] px-3 py-2">
                                <div className="truncate font-medium text-content-primary">
                                  {r.b_name || r.b_stable_id}
                                </div>
                                <div className="mt-0.5 flex items-center gap-1">
                                  <DisciplineChip
                                    name={r.b_discipline}
                                  />
                                  {r.b_element_type && (
                                    <span
                                      className="max-w-[130px] truncate text-2xs text-content-tertiary"
                                      title={r.b_element_type}
                                    >
                                      {r.b_element_type}
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="px-3 py-2">
                                <Badge
                                  size="sm"
                                  variant={
                                    r.clash_type === 'hard'
                                      ? 'error'
                                      : 'warning'
                                  }
                                >
                                  {r.clash_type === 'hard'
                                    ? t('clash.type_hard', {
                                        defaultValue: 'Hard‌⁠‍',
                                      })
                                    : t('clash.type_clearance', {
                                        defaultValue: 'Clearance‌⁠‍',
                                      })}
                                </Badge>
                              </td>
                              <td className="px-3 py-2 text-right tabular-nums text-content-secondary">
                                {r.clash_type === 'hard'
                                  ? `${r.penetration_m.toFixed(3)} m`
                                  : '—'}
                              </td>
                              <td className="px-3 py-2 text-right tabular-nums text-content-secondary">
                                {r.clash_type === 'clearance'
                                  ? `${r.distance_m.toFixed(3)} m`
                                  : '—'}
                              </td>
                              <td className="px-3 py-2">
                                <select
                                  value={r.status}
                                  onChange={(e) =>
                                    statusMut.mutate({
                                      id: r.id,
                                      status: e.target.value,
                                    })
                                  }
                                  className={clsx(
                                    'rounded-md border px-1.5 py-1 text-2xs font-medium',
                                    'border-border bg-surface-primary',
                                  )}
                                >
                                  {STATUS_OPTIONS.map((s) => (
                                    <option key={s} value={s}>
                                      {t(`clash.status.${s}`, {
                                        defaultValue: s,
                                      })}
                                    </option>
                                  ))}
                                </select>
                              </td>
                              <td className="px-3 py-2">
                                <div className="flex items-center justify-end gap-1.5">
                                  {r.bcf_topic_guid && (
                                    <Badge variant="blue" size="sm">
                                      {t('clash.bcf', {
                                        defaultValue: 'BCF‌⁠‍',
                                      })}
                                    </Badge>
                                  )}
                                  <button
                                    aria-label={t('clash.export_row', {
                                      defaultValue:
                                        'Export this clash to BCF‌⁠‍',
                                    })}
                                    title={t('clash.export_row', {
                                      defaultValue:
                                        'Export this clash to BCF‌⁠‍',
                                    })}
                                    onClick={() =>
                                      exportMut.mutate([r.id])
                                    }
                                    className="rounded-md p-1 text-content-tertiary hover:bg-surface-tertiary hover:text-content-primary"
                                  >
                                    <FileDown className="h-3.5 w-3.5" />
                                  </button>
                                  <Link
                                    to={bimLink(r)}
                                    title={t('clash.isolate_3d', {
                                      defaultValue: 'Isolate in 3D‌⁠‍',
                                    })}
                                    className="inline-flex items-center gap-1 rounded-md bg-oe-blue/10 px-2 py-1 text-2xs font-medium text-oe-blue hover:bg-oe-blue/20"
                                  >
                                    <Box className="h-3.5 w-3.5" />
                                    {t('clash.isolate_3d_short', {
                                      defaultValue: '3D‌⁠‍',
                                    })}
                                  </Link>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    </div>
                  </div>
                )}

                {/* Footer: selection summary + pagination */}
                {sorted.length > 0 && (
                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-light p-3 text-xs">
                    <div className="text-content-tertiary">
                      {selResults.size > 0 ? (
                        <span className="flex items-center gap-2">
                          {t('clash.n_selected', {
                            defaultValue: '{{n}} selected‌⁠‍',
                            n: selResults.size,
                          })}
                          <button
                            onClick={() => setSelResults(new Set())}
                            className="text-oe-blue hover:underline"
                          >
                            {t('clash.clear_selection', {
                              defaultValue: 'Clear‌⁠‍',
                            })}
                          </button>
                        </span>
                      ) : (
                        t('clash.page_range', {
                          defaultValue:
                            '{{from}}–{{to}} of {{total}}‌⁠‍',
                          from: safePage * PAGE_SIZE + 1,
                          to: Math.min(
                            (safePage + 1) * PAGE_SIZE,
                            sorted.length,
                          ),
                          total: sorted.length,
                        })
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={safePage === 0}
                        icon={<ChevronLeft className="h-4 w-4" />}
                        onClick={() => setPage((p) => Math.max(0, p - 1))}
                      >
                        {t('clash.prev', { defaultValue: 'Prev‌⁠‍' })}
                      </Button>
                      <span className="tabular-nums text-content-secondary">
                        {t('clash.page_of', {
                          defaultValue: 'Page {{p}} / {{n}}‌⁠‍',
                          p: safePage + 1,
                          n: pageCount,
                        })}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={safePage >= pageCount - 1}
                        icon={<ChevronRight className="h-4 w-4" />}
                        iconPosition="right"
                        onClick={() =>
                          setPage((p) =>
                            Math.min(pageCount - 1, p + 1),
                          )
                        }
                      >
                        {t('clash.next', { defaultValue: 'Next‌⁠‍' })}
                      </Button>
                    </div>
                  </div>
                )}
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ───────────────────────────────────────────────────── */

function Header() {
  const { t } = useTranslation();
  return (
    <div>
      <h1 className="flex items-center gap-2 text-2xl font-bold text-content-primary">
        <Radar className="h-6 w-6 text-oe-blue" />
        {t('clash.title', { defaultValue: 'Clash Detection‌⁠‍' })}
      </h1>
      <p className="mt-1 text-sm text-content-secondary">
        {t('clash.subtitle', {
          defaultValue:
            'Geometric interference & clearance coordination across federated BIM models — with a clash matrix and BCF export.‌⁠‍',
        })}
      </p>
    </div>
  );
}

function Kpi({
  icon,
  label,
  value,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  active?: boolean;
  onClick?: () => void;
}) {
  const interactive = !!onClick;
  return (
    <button
      type="button"
      disabled={!interactive}
      onClick={onClick}
      className={clsx(
        'rounded-xl border bg-surface-elevated p-3 text-left shadow-xs transition-all',
        interactive && 'hover:-translate-y-0.5 hover:shadow-md',
        active
          ? 'border-oe-blue ring-2 ring-oe-blue/20'
          : 'border-border-light',
        !interactive && 'cursor-default',
      )}
    >
      <div className="flex items-center gap-1.5 text-content-tertiary">
        {icon}
        <span className="truncate text-2xs">{label}</span>
      </div>
      <div className="mt-1 text-2xl font-bold tabular-nums text-content-primary">
        {value}
      </div>
    </button>
  );
}

function SortableTh({
  label,
  k,
  sortKey,
  sortDir,
  onSort,
  align = 'left',
  className,
}: {
  label: string;
  k: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (k: SortKey) => void;
  align?: 'left' | 'right';
  className?: string;
}) {
  const isActive = sortKey === k;
  return (
    <th
      className={clsx(
        'select-none px-3 py-2.5 font-medium',
        align === 'right' ? 'text-right' : 'text-left',
        className,
      )}
    >
      <button
        onClick={() => onSort(k)}
        className={clsx(
          'inline-flex items-center gap-1 hover:text-content-primary',
          align === 'right' && 'flex-row-reverse',
          isActive ? 'text-content-primary' : 'text-content-tertiary',
        )}
      >
        {label}
        {isActive ? (
          sortDir === 'asc' ? (
            <ArrowUp className="h-3 w-3" />
          ) : (
            <ArrowDown className="h-3 w-3" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-40" />
        )}
      </button>
    </th>
  );
}

function FilterChip({
  label,
  onClear,
}: {
  label: string;
  onClear: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-oe-blue/10 py-0.5 pl-2 pr-1 text-2xs font-medium text-oe-blue">
      <span className="max-w-[160px] truncate">{label}</span>
      <button
        onClick={onClear}
        className="rounded-full p-0.5 hover:bg-oe-blue/20"
        aria-label="clear"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

function TableSkeleton() {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: 10 }).map((_, i) => (
        <div
          key={i}
          className="h-9 animate-pulse rounded-md bg-surface-secondary"
        />
      ))}
    </div>
  );
}

/**
 * One side (A or B) of a Navisworks-style selection-set clash.
 *
 * A "set" is the union of the ticked disciplines + element types — every
 * chip widens it. Searchable, count-annotated, scroll-bounded so a model
 * with hundreds of distinct Revit types stays usable. Pure controlled
 * component: it owns no state beyond the local search box.
 */
function SelectionSetPicker({
  label,
  accent,
  value,
  onChange,
  categories,
  loading,
}: {
  label: string;
  accent: 'oe-blue' | 'amber';
  value: ClashSelectionSet;
  onChange: (next: ClashSelectionSet) => void;
  categories: ClashCategories | undefined;
  loading: boolean;
}) {
  const { t } = useTranslation();
  const [q, setQ] = useState('');
  const selectedCount =
    value.disciplines.length + value.element_types.length;
  const dot =
    accent === 'oe-blue' ? 'bg-oe-blue' : 'bg-amber-500';
  const ql = q.trim().toLowerCase();

  const discs = (categories?.disciplines ?? []).filter(
    (d) => !ql || d.value.toLowerCase().includes(ql),
  );
  const types = (categories?.element_types ?? []).filter(
    (e) => !ql || e.value.toLowerCase().includes(ql),
  );

  function toggle(kind: 'disciplines' | 'element_types', v: string) {
    const cur = value[kind];
    const next = cur.includes(v)
      ? cur.filter((x) => x !== v)
      : [...cur, v];
    onChange({ ...value, [kind]: next });
  }

  return (
    <div className="rounded-lg border border-border bg-surface-primary p-2">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-semibold text-content-primary">
          <span className={clsx('h-2 w-2 rounded-full', dot)} />
          {label}
          {selectedCount > 0 && (
            <span className="rounded-full bg-surface-secondary px-1.5 text-2xs text-content-secondary">
              {selectedCount}
            </span>
          )}
        </span>
        {selectedCount > 0 && (
          <button
            type="button"
            onClick={() =>
              onChange({ disciplines: [], element_types: [] })
            }
            className="text-2xs text-content-tertiary hover:text-semantic-error"
          >
            {t('common.clear', { defaultValue: 'Clear‌⁠‍' })}
          </button>
        )}
      </div>

      <div className="relative mt-1.5">
        <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-content-tertiary" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t('clash.set_search', {
            defaultValue: 'Search types / disciplines…‌⁠‍',
          })}
          className="w-full rounded-md border border-border bg-surface-primary py-1 pl-7 pr-2 text-2xs"
        />
      </div>

      <div className="mt-1.5 max-h-44 space-y-2 overflow-y-auto pr-0.5">
        {loading && (
          <p className="px-1 py-2 text-2xs text-content-tertiary">
            {t('common.loading', { defaultValue: 'Loading…‌⁠‍' })}
          </p>
        )}
        {!loading && discs.length === 0 && types.length === 0 && (
          <p className="px-1 py-2 text-2xs text-content-tertiary">
            {t('clash.set_empty', {
              defaultValue: 'No elements — select a parsed model first.‌⁠‍',
            })}
          </p>
        )}
        {discs.length > 0 && (
          <div>
            <p className="px-1 pb-0.5 text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
              {t('clash.disciplines', { defaultValue: 'Disciplines‌⁠‍' })}
            </p>
            {discs.map((d) => (
              <SetRow
                key={`d-${d.value}`}
                checked={value.disciplines.includes(d.value)}
                label={d.value}
                count={d.count}
                onToggle={() => toggle('disciplines', d.value)}
              />
            ))}
          </div>
        )}
        {types.length > 0 && (
          <div>
            <p className="px-1 pb-0.5 text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
              {t('clash.element_types', { defaultValue: 'Element types‌⁠‍' })}
            </p>
            {types.map((e) => (
              <SetRow
                key={`t-${e.value}`}
                checked={value.element_types.includes(e.value)}
                label={e.value}
                count={e.count}
                onToggle={() => toggle('element_types', e.value)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SetRow({
  checked,
  label,
  count,
  onToggle,
}: {
  checked: boolean;
  label: string;
  count: number;
  onToggle: () => void;
}) {
  return (
    <label
      className={clsx(
        'flex cursor-pointer items-center gap-1.5 rounded px-1 py-0.5 text-2xs',
        checked
          ? 'bg-oe-blue/10 text-content-primary'
          : 'hover:bg-surface-secondary text-content-secondary',
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="h-3 w-3 shrink-0 accent-oe-blue"
      />
      <span className="flex-1 truncate" title={label}>
        {label}
      </span>
      <span className="shrink-0 text-content-tertiary">{count}</span>
    </label>
  );
}

export default ClashDetectionPage;
