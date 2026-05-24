/**
 * NewWidgets — wave-2 dashboard widgets shipped 2026-05-23.
 *
 * Each widget is a self-contained presentational component:
 *   - takes a small typed prop set (e.g. `projects`),
 *   - issues its own React Query (shared keys with the rest of the
 *     dashboard so concurrent widgets dedupe their fetches),
 *   - renders a Skeleton while loading,
 *   - renders an EmptyState with a CTA when the endpoint 404s or returns
 *     no rows (graceful degradation — modules absent from this install
 *     must not crash the dashboard).
 *
 * All endpoints are wrapped in `.catch(() => null)` so a missing module
 * cannot break the dashboard. Money values are formatted from string or
 * number — never coerced to Float on read.
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  FileSpreadsheet,
  GitBranch,
  ShieldAlert,
  HardHat,
  ShoppingCart,
  Wallet,
  ClipboardList,
  Cog,
  CheckSquare,
  CloudSun,
  ArrowRight,
  TrendingUp,
} from 'lucide-react';
import { apiGet } from '@/shared/lib/api';
import { Card, CardContent, Button, Skeleton, Badge } from '@/shared/ui';

/* ── Types ────────────────────────────────────────────────────────────── */

interface ProjectRef {
  id: string;
  name: string;
  currency: string;
  address?: {
    lat?: number | null;
    lng?: number | null;
    city?: string | null;
    country?: string | null;
  } | null;
}

/** Generic shape for safe-fetch — endpoints that may not exist 404 silently. */
async function safeGet<T>(path: string): Promise<T | null> {
  try {
    return await apiGet<T>(path);
  } catch {
    return null;
  }
}

/** Some list endpoints return a paginated envelope; coerce to a plain array. */
function asArray<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if (Array.isArray(obj.items)) return obj.items as T[];
    if (Array.isArray(obj.results)) return obj.results as T[];
    if (Array.isArray(obj.data)) return obj.data as T[];
  }
  return [];
}

/** Format money — accepts string or number, never NaN. */
function fmtMoney(value: string | number | null | undefined, currency: string): string {
  if (value == null) return `${currency} 0`;
  const n = typeof value === 'string' ? Number(value) : value;
  if (!Number.isFinite(n)) return `${currency} 0`;
  return `${currency} ${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

/** Shared widget shell so empty / loading states stay consistent.
 *
 * ``CardHeader`` expects a plain string title (see ``shared/ui/Card.tsx``),
 * so we render the icon as a sibling above the header inside the same card
 * rather than inlining it into the title prop. */
function WidgetCard({
  icon,
  title,
  subtitle,
  delay = '160ms',
  children,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  delay?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="animate-card-in" style={{ animationDelay: delay }}>
      <Card>
        <div className="flex items-start gap-3 px-6 pt-5">
          <span className="mt-1 shrink-0">{icon}</span>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-content-primary">{title}</h3>
            {subtitle && (
              <p className="text-xs text-content-tertiary mt-0.5">{subtitle}</p>
            )}
          </div>
        </div>
        <CardContent>{children}</CardContent>
      </Card>
    </div>
  );
}

function EmptyCTA({
  message,
  ctaLabel,
  onClick,
}: {
  message: string;
  ctaLabel: string;
  onClick: () => void;
}) {
  return (
    <div className="flex flex-col items-start gap-3 py-2">
      <p className="text-sm text-content-tertiary">{message}</p>
      <Button variant="secondary" size="sm" icon={<ArrowRight size={14} />} iconPosition="right" onClick={onClick}>
        {ctaLabel}
      </Button>
    </div>
  );
}

function LoadingRows({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} height={32} className="w-full" rounded="md" />
      ))}
    </div>
  );
}

/* ── 1. BOQ Summary ───────────────────────────────────────────────────── */

interface BOQLite {
  id: string;
  project_id: string;
  grand_total?: number | string | null;
  position_count?: number | null;
  positions_missing_quantity?: number | null;
  positions_zero_price?: number | null;
}

export function BOQSummaryWidget({ projects }: { projects?: ProjectRef[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Share key with the dashboard's existing per-project BOQ fan-out so React
  // Query dedupes the request. The non-shared key (`?project_id=…`) still
  // fans out per project — same as KPI ribbon.
  const { data: boqs, isLoading } = useQuery({
    queryKey: ['dashboard-all-boqs', projects?.map((p) => p.id).join(',')],
    queryFn: async (): Promise<BOQLite[]> => {
      if (!projects || projects.length === 0) return [];
      const lists = await Promise.all(
        projects.map((p) => safeGet<BOQLite[]>(`/v1/boq/boqs/?project_id=${p.id}`)),
      );
      return lists.flatMap((l) => l ?? []);
    },
    enabled: Boolean(projects && projects.length > 0),
    retry: false,
    staleTime: 30_000,
  });

  const stats = useMemo(() => {
    const rows = asArray<BOQLite>(boqs);
    if (rows.length === 0) return null;
    const count = rows.length;
    let total = 0;
    let positions = 0;
    let missingQty = 0;
    let zeroPrice = 0;
    for (const b of rows) {
      const gt = typeof b.grand_total === 'string' ? Number(b.grand_total) : b.grand_total ?? 0;
      if (Number.isFinite(gt)) total += gt as number;
      positions += b.position_count ?? 0;
      missingQty += b.positions_missing_quantity ?? 0;
      zeroPrice += b.positions_zero_price ?? 0;
    }
    return {
      count,
      total,
      positions,
      pctMissingQty: positions > 0 ? Math.round((missingQty / positions) * 100) : 0,
      pctZeroPrice: positions > 0 ? Math.round((zeroPrice / positions) * 100) : 0,
    };
  }, [boqs]);

  const title = t('dashboard.layout.w_boq_summary', { defaultValue: 'BOQ Summary' });
  const subtitle = t('dashboard.boq_summary_subtitle', {
    defaultValue: 'Bill of Quantities health across your projects',
  });
  const icon = <FileSpreadsheet size={16} className="text-content-tertiary" />;

  if (isLoading) {
    return <WidgetCard icon={icon} title={title} subtitle={subtitle}><LoadingRows /></WidgetCard>;
  }
  if (!stats || stats.count === 0) {
    return (
      <WidgetCard icon={icon} title={title} subtitle={subtitle}>
        <EmptyCTA
          message={t('dashboard.boq_summary_empty', {
            defaultValue: 'No BOQs yet — create your first to track value and completeness.',
          })}
          ctaLabel={t('dashboard.boq_summary_cta', { defaultValue: 'Open BOQs' })}
          onClick={() => navigate('/boq')}
        />
      </WidgetCard>
    );
  }

  const currency = projects?.[0]?.currency ?? 'EUR';

  return (
    <WidgetCard icon={icon} title={title} subtitle={subtitle}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.total_boqs', { defaultValue: 'Total BOQs' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{stats.count}</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.boq_total_value', { defaultValue: 'Total value' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{fmtMoney(stats.total, currency)}</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.boq_missing_qty', { defaultValue: 'Missing qty' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">
            {stats.pctMissingQty}%
          </div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.boq_zero_price', { defaultValue: 'Zero priced' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{stats.pctZeroPrice}%</div>
        </div>
      </div>
    </WidgetCard>
  );
}

/* ── 2. Critical Path ─────────────────────────────────────────────────── */

interface CriticalTask {
  id: string;
  name: string;
  project_id?: string;
  end_date?: string | null;
  status?: string | null;
  slack_days?: number | null;
}

interface ScheduleLite {
  id: string;
  name?: string | null;
  project_id?: string;
  start_date?: string | null;
  end_date?: string | null;
  status?: string | null;
  is_critical?: boolean | null;
  slack_days?: number | null;
}

export function CriticalPathWidget({ projects }: { projects?: ProjectRef[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-critical-path', projects?.map((p) => p.id).join(',') ?? ''],
    enabled: !!projects && projects.length > 0,
    queryFn: async (): Promise<ScheduleLite[]> => {
      if (!projects || projects.length === 0) return [];
      const lists = await Promise.all(
        projects.map((p) =>
          safeGet<ScheduleLite[]>(`/v1/schedule/schedules/?project_id=${p.id}`),
        ),
      );
      return lists.flatMap((l) => asArray<ScheduleLite>(l));
    },
    retry: false,
    staleTime: 60_000,
  });

  const top5 = useMemo<CriticalTask[]>(() => {
    const rows = asArray<ScheduleLite>(data);
    if (rows.length === 0) return [];
    // Prefer items explicitly flagged ``is_critical`` (server-computed on
    // critical-path runs). When no row carries the flag, fall back to the
    // 5 earliest-starting open schedules so the widget still surfaces
    // something meaningful on installs that haven't computed a CPM yet.
    const flagged = rows.filter((r) => r.is_critical === true);
    const pool = flagged.length > 0 ? flagged : rows;
    return pool
      .slice()
      .sort((a, b) => {
        const ta = Date.parse(a.start_date ?? '') || Number.POSITIVE_INFINITY;
        const tb = Date.parse(b.start_date ?? '') || Number.POSITIVE_INFINITY;
        return ta - tb;
      })
      .slice(0, 5)
      .map((s) => ({
        id: s.id,
        name: s.name ?? '—',
        project_id: s.project_id,
        end_date: s.end_date ?? null,
        status: s.status ?? null,
        slack_days: s.slack_days ?? null,
      }));
  }, [data]);

  const title = t('dashboard.layout.w_schedule', { defaultValue: 'Critical Path' });
  const subtitle = t('dashboard.critical_path_subtitle', {
    defaultValue: 'Tasks at risk on your critical path',
  });
  const icon = <GitBranch size={16} className="text-content-tertiary" />;

  if (isLoading) return <WidgetCard icon={icon} title={title} subtitle={subtitle}><LoadingRows /></WidgetCard>;
  if (top5.length === 0) {
    return (
      <WidgetCard icon={icon} title={title} subtitle={subtitle}>
        <EmptyCTA
          message={t('dashboard.critical_path_empty', { defaultValue: 'No at-risk schedule items.' })}
          ctaLabel={t('dashboard.critical_path_cta', { defaultValue: 'Open Schedules' })}
          onClick={() => navigate('/schedule')}
        />
      </WidgetCard>
    );
  }

  return (
    <WidgetCard icon={icon} title={title} subtitle={subtitle}>
      <ul className="divide-y divide-border-light">
        {top5.map((task) => (
          <li key={task.id} className="flex items-center justify-between gap-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-content-primary">{task.name}</p>
              {task.end_date && (
                <p className="text-xs text-content-tertiary">{task.end_date}</p>
              )}
            </div>
            <Badge variant={task.slack_days != null && task.slack_days < 0 ? 'error' : 'warning'} size="sm">
              {task.slack_days != null
                ? t('dashboard.slack_days', { defaultValue: '{{n}}d slack', n: task.slack_days })
                : (task.status ?? '—')}
            </Badge>
          </li>
        ))}
      </ul>
    </WidgetCard>
  );
}

/* ── 3. Top Risks ─────────────────────────────────────────────────────── */

interface RiskRow {
  id: string;
  title: string;
  probability?: number | null;
  impact?: number | null;
  score?: number | null;
  status?: string | null;
}

export function TopRisksWidget({ projects: projectsProp }: { projects?: ProjectRef[] } = {}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Fall back to the dashboard-wide ``['projects']`` query when the caller
  // doesn't pass the list explicitly (React Query dedupes the request with
  // the parent fetch in DashboardPage.tsx).
  const { data: fetchedProjects } = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<ProjectRef[]>('/v1/projects/').catch(() => [] as ProjectRef[]),
    enabled: !projectsProp,
    retry: false,
    staleTime: 5 * 60_000,
  });
  const projects = projectsProp ?? fetchedProjects;

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-top-risks', projects?.map((p) => p.id).join(',') ?? ''],
    enabled: !!projects && projects.length > 0,
    queryFn: async (): Promise<RiskRow[]> => {
      if (!projects || projects.length === 0) return [];
      const lists = await Promise.all(
        projects.map((p) => safeGet<RiskRow[]>(`/v1/risk/?project_id=${p.id}`)),
      );
      return lists.flatMap((l) => asArray<RiskRow>(l));
    },
    retry: false,
    staleTime: 60_000,
  });

  const top5 = useMemo(() => {
    const rows = asArray<RiskRow>(data);
    if (rows.length === 0) return [];
    return rows
      .map((r) => ({
        ...r,
        _calcScore: r.score ?? (r.probability ?? 0) * (r.impact ?? 0),
      }))
      .sort((a, b) => b._calcScore - a._calcScore)
      .slice(0, 5);
  }, [data]);

  const title = t('dashboard.layout.w_risk', { defaultValue: 'Top Risks' });
  const subtitle = t('dashboard.risk_top_subtitle', {
    defaultValue: 'Highest probability × impact across your register',
  });
  const icon = <ShieldAlert size={16} className="text-content-tertiary" />;

  if (isLoading) return <WidgetCard icon={icon} title={title} subtitle={subtitle}><LoadingRows /></WidgetCard>;
  if (top5.length === 0) {
    return (
      <WidgetCard icon={icon} title={title} subtitle={subtitle}>
        <EmptyCTA
          message={t('dashboard.risk_top_empty', { defaultValue: 'No risks logged yet.' })}
          ctaLabel={t('dashboard.risk_top_cta', { defaultValue: 'Open Risk Register' })}
          onClick={() => navigate('/risk-register')}
        />
      </WidgetCard>
    );
  }

  return (
    <WidgetCard icon={icon} title={title} subtitle={subtitle}>
      <ul className="divide-y divide-border-light">
        {top5.map((r) => (
          <li key={r.id} className="flex items-center justify-between gap-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-content-primary">{r.title}</p>
              {r.status && <p className="text-xs text-content-tertiary">{r.status}</p>}
            </div>
            <Badge variant={r._calcScore > 12 ? 'error' : r._calcScore > 6 ? 'warning' : 'neutral'} size="sm">
              {t('dashboard.risk_score', { defaultValue: 'Score {{n}}', n: Math.round(r._calcScore) })}
            </Badge>
          </li>
        ))}
      </ul>
    </WidgetCard>
  );
}

/* ── 4. HSE Scorecard ─────────────────────────────────────────────────── */

interface HSEIncident {
  id: string;
  reported_at?: string | null;
  occurred_at?: string | null;
  incident_date?: string | null;
  incident_type?: string | null;
  near_miss?: boolean | null;
  osha_recordable?: boolean | null;
  severity?: string | null;
}

export function HSEScoreCardWidget({ projects: projectsProp }: { projects?: ProjectRef[] } = {}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data: fetchedProjects } = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<ProjectRef[]>('/v1/projects/').catch(() => [] as ProjectRef[]),
    enabled: !projectsProp,
    retry: false,
    staleTime: 5 * 60_000,
  });
  const projects = projectsProp ?? fetchedProjects;

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-hse-incidents', projects?.map((p) => p.id).join(',') ?? ''],
    enabled: !!projects && projects.length > 0,
    queryFn: async (): Promise<HSEIncident[]> => {
      if (!projects || projects.length === 0) return [];
      const lists = await Promise.all(
        projects.map((p) => safeGet<HSEIncident[]>(`/v1/safety/incidents/?project_id=${p.id}`)),
      );
      return lists.flatMap((l) => asArray<HSEIncident>(l));
    },
    retry: false,
    staleTime: 60_000,
  });

  const stats = useMemo(() => {
    const rows = asArray<HSEIncident>(data);
    if (rows.length === 0) return null;
    const now = Date.now();
    const day30 = 30 * 24 * 60 * 60 * 1000;
    let last = 0;
    let last30 = 0;
    let nearMiss = 0;
    let recordables = 0;
    for (const i of rows) {
      // Safety API uses ``incident_date`` (YYYY-MM-DD); accept the older
      // ``reported_at`` / ``occurred_at`` shapes too for forward compat.
      const ts = Date.parse(i.reported_at ?? i.occurred_at ?? i.incident_date ?? '');
      if (Number.isFinite(ts)) {
        if (ts > last) last = ts;
        if (now - ts <= day30) last30 += 1;
      }
      // ``incident_type === 'near_miss'`` is the safety-module convention.
      if (i.near_miss || i.incident_type === 'near_miss') nearMiss += 1;
      // OSHA recordable proxy: any non-near-miss with severity >= moderate.
      if (
        i.osha_recordable ||
        (i.severity && ['moderate', 'major', 'critical', 'fatal'].includes(i.severity))
      )
        recordables += 1;
    }
    return { count: rows.length, last30, nearMiss, recordables, lastTs: last };
  }, [data]);

  const title = t('dashboard.layout.w_hse', { defaultValue: 'HSE Scorecard' });
  const subtitle = t('dashboard.hse_subtitle', { defaultValue: 'Health, safety and environment summary' });
  const icon = <HardHat size={16} className="text-content-tertiary" />;

  if (isLoading) return <WidgetCard icon={icon} title={title} subtitle={subtitle}><LoadingRows /></WidgetCard>;
  if (!stats || stats.count === 0) {
    return (
      <WidgetCard icon={icon} title={title} subtitle={subtitle}>
        <EmptyCTA
          message={t('dashboard.hse_empty', { defaultValue: 'No incidents logged yet.' })}
          ctaLabel={t('dashboard.hse_cta', { defaultValue: 'Open HSE module' })}
          onClick={() => navigate('/hse')}
        />
      </WidgetCard>
    );
  }

  const lastIncident = stats.lastTs > 0 ? new Date(stats.lastTs).toLocaleDateString() : '—';
  return (
    <WidgetCard icon={icon} title={title} subtitle={subtitle}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.hse_last_30d', { defaultValue: 'Last 30 days' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{stats.last30}</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.hse_near_miss', { defaultValue: 'Near-misses' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{stats.nearMiss}</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.hse_recordable', { defaultValue: 'Recordables' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{stats.recordables}</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.hse_last_incident', { defaultValue: 'Last incident' })}
          </div>
          <div className="text-sm font-medium text-content-primary">{lastIncident}</div>
        </div>
      </div>
    </WidgetCard>
  );
}

/* ── 5. Procurement Pipeline ──────────────────────────────────────────── */

interface ProcurementRollup {
  rfqs_pending?: number | null;
  pos_issued?: number | null;
  pos_received?: number | null;
}

export function ProcurementPipelineWidget({
  projects: projectsProp,
}: { projects?: ProjectRef[] } = {}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data: fetchedProjects } = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<ProjectRef[]>('/v1/projects/').catch(() => [] as ProjectRef[]),
    enabled: !projectsProp,
    retry: false,
    staleTime: 5 * 60_000,
  });
  const projects = projectsProp ?? fetchedProjects;

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-procurement-rollup', projects?.map((p) => p.id).join(',') ?? ''],
    enabled: !!projects && projects.length > 0,
    queryFn: async (): Promise<ProcurementRollup | null> => {
      if (!projects || projects.length === 0) return null;
      // The procurement module returns POs only — list is at the module
      // root with ``project_id`` required. The legacy ``/rollup``,
      // ``/procurement/rfqs/`` and ``/procurement/pos/`` URLs returned
      // 404 — they never existed.
      //
      // The sibling ``rfq_bidding`` module is optional (disabled on
      // fresh installs), so we don't hit ``/v1/rfq-bidding/`` from this
      // widget — its 404 would noise up the dashboard. Surface PO
      // counts only; the dedicated Procurement page covers RFQs.
      const lists = await Promise.all(
        projects.map((p) => safeGet<unknown>(`/v1/procurement/?project_id=${p.id}`)),
      );
      const pos = lists.flatMap((l) => asArray<{ status?: string }>(l));
      if (pos.length === 0) return null;
      const pending = pos.filter(
        (p) => p.status === 'draft' || p.status === 'pending' || p.status === 'open',
      ).length;
      const issued = pos.filter(
        (p) => p.status === 'issued' || p.status === 'sent' || p.status === 'approved',
      ).length;
      const received = pos.filter(
        (p) => p.status === 'received' || p.status === 'closed' || p.status === 'completed',
      ).length;
      return { rfqs_pending: pending, pos_issued: issued, pos_received: received };
    },
    retry: false,
    staleTime: 60_000,
  });

  const title = t('dashboard.layout.w_procurement', { defaultValue: 'Procurement' });
  const subtitle = t('dashboard.procurement_subtitle', { defaultValue: 'RFQ and PO pipeline' });
  const icon = <ShoppingCart size={16} className="text-content-tertiary" />;

  if (isLoading) return <WidgetCard icon={icon} title={title} subtitle={subtitle}><LoadingRows /></WidgetCard>;
  if (!data) {
    return (
      <WidgetCard icon={icon} title={title} subtitle={subtitle}>
        <EmptyCTA
          message={t('dashboard.procurement_empty', { defaultValue: 'No RFQs or POs yet.' })}
          ctaLabel={t('dashboard.procurement_cta', { defaultValue: 'Open Procurement' })}
          onClick={() => navigate('/procurement')}
        />
      </WidgetCard>
    );
  }

  return (
    <WidgetCard icon={icon} title={title} subtitle={subtitle}>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.procurement_rfqs', { defaultValue: 'RFQs pending' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{data.rfqs_pending ?? 0}</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.procurement_pos_issued', { defaultValue: 'POs issued' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{data.pos_issued ?? 0}</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.procurement_pos_received', { defaultValue: 'POs received' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{data.pos_received ?? 0}</div>
        </div>
      </div>
    </WidgetCard>
  );
}

/* ── 6. Budget Variance ───────────────────────────────────────────────── */

interface BudgetRow {
  id: string;
  project_id: string;
  project_name?: string;
  /** Pre-v4.5 field — kept for forward compat. */
  planned_amount?: number | string | null;
  actual_amount?: number | string | null;
  /** Real backend shape — see ``finance/schemas.py::BudgetResponse``. */
  original_budget?: number | string | null;
  revised_budget?: number | string | null;
  actual?: number | string | null;
  variance?: number | string | null;
  currency?: string | null;
  currency_code?: string | null;
}

export function BudgetVarianceWidget({ projects }: { projects?: ProjectRef[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-budget-variance', projects?.map((p) => p.id).join(',') ?? ''],
    enabled: !!projects && projects.length > 0,
    queryFn: async (): Promise<BudgetRow[]> => {
      if (!projects || projects.length === 0) return [];
      // Finance ``/budgets/`` returns ``BudgetListResponse`` ({items, total});
      // ``asArray`` already coerces the envelope. Fan out per project so the
      // ``project_id`` filter is applied — the endpoint accepts an optional
      // ``project_id`` but ``_require_project_access`` 422s when it's missing
      // on tenants without admin rights.
      const lists = await Promise.all(
        projects.map((p) => safeGet<unknown>(`/v1/finance/budgets/?project_id=${p.id}`)),
      );
      return lists.flatMap((l) => asArray<BudgetRow>(l));
    },
    retry: false,
    staleTime: 60_000,
  });

  const overBudget = useMemo(() => {
    const rows = asArray<BudgetRow>(data);
    if (rows.length === 0) return [];
    return rows
      .map((b) => {
        // Backend ships ``revised_budget`` / ``actual`` as Decimal-safe
        // strings. Fall back to the older ``planned_amount`` /
        // ``actual_amount`` field names so any module that still emits
        // them keeps rendering.
        const planned = Number(b.revised_budget ?? b.original_budget ?? b.planned_amount ?? 0);
        const actual = Number(b.actual ?? b.actual_amount ?? 0);
        const variance = actual - planned;
        const pct = planned > 0 ? Math.round((variance / planned) * 100) : 0;
        const project = projects?.find((p) => p.id === b.project_id);
        return {
          ...b,
          planned,
          actual,
          variance,
          pct,
          projectName: project?.name ?? b.project_name ?? '—',
          currency: b.currency_code ?? b.currency ?? project?.currency ?? 'EUR',
        };
      })
      .filter((b) => b.variance > 0)
      .sort((a, b) => b.variance - a.variance)
      .slice(0, 3);
  }, [data, projects]);

  const title = t('dashboard.layout.w_budget', { defaultValue: 'Budget Variance' });
  const subtitle = t('dashboard.budget_subtitle', { defaultValue: 'Planned vs actual across budgets' });
  const icon = <Wallet size={16} className="text-content-tertiary" />;

  if (isLoading) return <WidgetCard icon={icon} title={title} subtitle={subtitle}><LoadingRows /></WidgetCard>;
  if (overBudget.length === 0) {
    return (
      <WidgetCard icon={icon} title={title} subtitle={subtitle}>
        <EmptyCTA
          message={t('dashboard.budget_empty', { defaultValue: 'No over-budget projects.' })}
          ctaLabel={t('dashboard.budget_cta', { defaultValue: 'Open Finance' })}
          onClick={() => navigate('/finance')}
        />
      </WidgetCard>
    );
  }

  return (
    <WidgetCard icon={icon} title={title} subtitle={subtitle}>
      <ul className="divide-y divide-border-light">
        {overBudget.map((b) => (
          <li key={b.id} className="flex items-center justify-between gap-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-content-primary">{b.projectName}</p>
              <p className="text-xs text-content-tertiary">
                {fmtMoney(b.actual, b.currency)} / {fmtMoney(b.planned, b.currency)}
              </p>
            </div>
            <Badge variant={b.pct > 20 ? 'error' : 'warning'} size="sm">
              <TrendingUp size={11} className="mr-1" />
              +{b.pct}%
            </Badge>
          </li>
        ))}
      </ul>
    </WidgetCard>
  );
}

/* ── 7. Change Orders ─────────────────────────────────────────────────── */

interface ChangeOrder {
  id: string;
  number?: string | null;
  title?: string | null;
  status?: string | null;
  cost_impact?: number | string | null;
  currency?: string | null;
  project_id?: string;
}

export function ChangeOrdersWidget({ projects }: { projects?: ProjectRef[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-change-orders', projects?.map((p) => p.id).join(',') ?? ''],
    enabled: !!projects && projects.length > 0,
    queryFn: async (): Promise<ChangeOrder[]> => {
      if (!projects || projects.length === 0) return [];
      // Module dir is ``changeorders`` (no hyphen, no underscore) — the
      // legacy ``/v1/change-orders/`` URL was a 404.
      const lists = await Promise.all(
        projects.map((p) => safeGet<unknown>(`/v1/changeorders/?project_id=${p.id}`)),
      );
      return lists.flatMap((l) => asArray<ChangeOrder>(l));
    },
    retry: false,
    staleTime: 60_000,
  });

  const summary = useMemo(() => {
    const rows = asArray<ChangeOrder>(data);
    if (rows.length === 0) return null;
    const open = rows.filter((c) => c.status && !['approved', 'rejected', 'closed'].includes(c.status));
    let totalImpact = 0;
    for (const c of open) {
      const v = Number(c.cost_impact ?? 0);
      if (Number.isFinite(v)) totalImpact += v;
    }
    const topPending = [...open].slice(0, 3);
    return { openCount: open.length, totalImpact, topPending };
  }, [data]);

  const title = t('dashboard.layout.w_changeorders', { defaultValue: 'Change Orders' });
  const subtitle = t('dashboard.change_orders_subtitle', { defaultValue: 'Open change orders and impact' });
  const icon = <ClipboardList size={16} className="text-content-tertiary" />;

  if (isLoading) return <WidgetCard icon={icon} title={title} subtitle={subtitle}><LoadingRows /></WidgetCard>;
  if (!summary || summary.openCount === 0) {
    return (
      <WidgetCard icon={icon} title={title} subtitle={subtitle}>
        <EmptyCTA
          message={t('dashboard.change_orders_empty', { defaultValue: 'No open change orders.' })}
          ctaLabel={t('dashboard.change_orders_cta', { defaultValue: 'Open Change Orders' })}
          onClick={() => navigate('/change-orders')}
        />
      </WidgetCard>
    );
  }

  const currency = projects?.[0]?.currency ?? 'EUR';

  return (
    <WidgetCard icon={icon} title={title} subtitle={subtitle}>
      <div className="grid grid-cols-2 gap-4 mb-3">
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.change_orders_open', { defaultValue: 'Open' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{summary.openCount}</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.change_orders_impact', { defaultValue: 'Total impact' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{fmtMoney(summary.totalImpact, currency)}</div>
        </div>
      </div>
      {summary.topPending.length > 0 && (
        <ul className="divide-y divide-border-light border-t border-border-light">
          {summary.topPending.map((co) => (
            <li key={co.id} className="flex items-center justify-between gap-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-content-primary">{co.title || co.number || co.id}</p>
                {co.status && <p className="text-xs text-content-tertiary">{co.status}</p>}
              </div>
              <span className="text-xs font-medium text-content-secondary tabular-nums">
                {fmtMoney(co.cost_impact, co.currency ?? currency)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  );
}

/* ── 8. Clash Health ──────────────────────────────────────────────────── */

interface ClashRow {
  id: string;
  /** Pre-v4.5 field — kept for forward compat. */
  severity?: string | null;
  /** Real backend shape — ``ClashIssueRead`` uses ``priority`` for severity. */
  priority?: string | null;
  status?: string | null;
  ai_triaged?: boolean | null;
  signature_quality?: string | null;
}

export function ClashHealthWidget({ projects: projectsProp }: { projects?: ProjectRef[] } = {}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data: fetchedProjects } = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<ProjectRef[]>('/v1/projects/').catch(() => [] as ProjectRef[]),
    enabled: !projectsProp,
    retry: false,
    staleTime: 5 * 60_000,
  });
  const projects = projectsProp ?? fetchedProjects;

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-clash-health', projects?.map((p) => p.id).join(',') ?? ''],
    enabled: !!projects && projects.length > 0,
    queryFn: async (): Promise<ClashRow[]> => {
      if (!projects || projects.length === 0) return [];
      // Clash has no flat ``/v1/clash/`` list — every list endpoint is
      // either run-scoped (``/projects/{id}/runs/{run_id}/results``) or
      // project-scoped via the v41 smart-issues endpoint
      // ``/v1/clash/issues?project_id=...`` (returns a ``ClashIssuePage``
      // envelope). The issues view is what the widget actually wants —
      // one persistent identity per signature across re-runs.
      const lists = await Promise.all(
        projects.map((p) => safeGet<unknown>(`/v1/clash/issues?project_id=${p.id}`)),
      );
      return lists.flatMap((l) => asArray<ClashRow>(l));
    },
    retry: false,
    staleTime: 60_000,
  });

  const stats = useMemo(() => {
    const rows = asArray<ClashRow>(data);
    if (rows.length === 0) return null;
    const open = rows.filter((c) => c.status && !['resolved', 'closed', 'ignored'].includes(c.status));
    // ``ClashIssueRead.priority`` is the canonical severity field; older
    // payloads carry ``severity`` directly.
    const sev = (c: ClashRow) => c.priority ?? c.severity ?? null;
    const high = open.filter((c) => sev(c) === 'high' || sev(c) === 'critical').length;
    const medium = open.filter((c) => sev(c) === 'medium').length;
    const low = open.filter((c) => sev(c) === 'low').length;
    const triaged = rows.filter((c) => c.ai_triaged).length;
    const resolved = rows.length - open.length;
    const pctResolved = rows.length > 0 ? Math.round((resolved / rows.length) * 100) : 0;
    return { total: rows.length, open: open.length, high, medium, low, triaged, pctResolved };
  }, [data]);

  const title = t('dashboard.layout.w_clash', { defaultValue: 'Clash Health' });
  const subtitle = t('dashboard.clash_subtitle', { defaultValue: 'Open clashes by severity and progress' });
  const icon = <Cog size={16} className="text-content-tertiary" />;

  if (isLoading) return <WidgetCard icon={icon} title={title} subtitle={subtitle}><LoadingRows /></WidgetCard>;
  if (!stats || stats.total === 0) {
    return (
      <WidgetCard icon={icon} title={title} subtitle={subtitle}>
        <EmptyCTA
          message={t('dashboard.clash_empty', { defaultValue: 'No clashes detected yet.' })}
          ctaLabel={t('dashboard.clash_cta', { defaultValue: 'Open Clash module' })}
          onClick={() => navigate('/clash')}
        />
      </WidgetCard>
    );
  }

  return (
    <WidgetCard icon={icon} title={title} subtitle={subtitle}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.clash_high', { defaultValue: 'High' })}
          </div>
          <div className="text-xl font-semibold text-red-600 tabular-nums">{stats.high}</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.clash_medium', { defaultValue: 'Medium' })}
          </div>
          <div className="text-xl font-semibold text-amber-600 tabular-nums">{stats.medium}</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.clash_low', { defaultValue: 'Low' })}
          </div>
          <div className="text-xl font-semibold text-content-secondary tabular-nums">{stats.low}</div>
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mb-1">
            {t('dashboard.clash_resolved', { defaultValue: '% resolved' })}
          </div>
          <div className="text-xl font-semibold tabular-nums">{stats.pctResolved}%</div>
        </div>
      </div>
      {stats.triaged > 0 && (
        <p className="text-xs text-content-tertiary border-t border-border-light pt-2">
          {t('dashboard.clash_triaged_note', {
            defaultValue: '{{n}} clash(es) AI-triaged',
            n: stats.triaged,
          })}
        </p>
      )}
    </WidgetCard>
  );
}

/* ── 9. Validation Health ─────────────────────────────────────────────── */

interface ValidationReport {
  id: string;
  status?: string | null;
  score?: number | null;
  created_at?: string | null;
  project_id?: string | null;
}

export function ValidationHealthWidget({
  projects: projectsProp,
}: { projects?: ProjectRef[] } = {}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data: fetchedProjects } = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<ProjectRef[]>('/v1/projects/').catch(() => [] as ProjectRef[]),
    enabled: !projectsProp,
    retry: false,
    staleTime: 5 * 60_000,
  });
  const projects = projectsProp ?? fetchedProjects;

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-validation-reports', projects?.map((p) => p.id).join(',') ?? ''],
    enabled: !!projects && projects.length > 0,
    queryFn: async (): Promise<ValidationReport[]> => {
      if (!projects || projects.length === 0) return [];
      // ``project_id`` is REQUIRED on ``/v1/validation/reports/`` (the
      // pre-merge call without it 422'd as missing-query-param).
      const lists = await Promise.all(
        projects.map((p) => safeGet<unknown>(`/v1/validation/reports/?project_id=${p.id}`)),
      );
      return lists.flatMap((l) => asArray<ValidationReport>(l));
    },
    retry: false,
    staleTime: 60_000,
  });

  const stats = useMemo(() => {
    const rows = asArray<ValidationReport>(data);
    if (rows.length === 0) return null;
    let passed = 0;
    let warnings = 0;
    let errors = 0;
    for (const r of rows) {
      if (r.status === 'passed') passed += 1;
      else if (r.status === 'warnings') warnings += 1;
      else if (r.status === 'errors' || r.status === 'failed') errors += 1;
    }
    const latest = [...rows]
      .filter((r) => r.created_at)
      .sort(
        (a, b) => Date.parse(b.created_at ?? '') - Date.parse(a.created_at ?? ''),
      )[0];
    return { total: rows.length, passed, warnings, errors, latest };
  }, [data]);

  const title = t('dashboard.layout.w_validation', { defaultValue: 'Validation Health' });
  const subtitle = t('dashboard.validation_subtitle', {
    defaultValue: 'Pass / warn / fail counts across reports',
  });
  const icon = <CheckSquare size={16} className="text-content-tertiary" />;

  if (isLoading) return <WidgetCard icon={icon} title={title} subtitle={subtitle}><LoadingRows /></WidgetCard>;
  if (!stats || stats.total === 0) {
    return (
      <WidgetCard icon={icon} title={title} subtitle={subtitle}>
        <EmptyCTA
          message={t('dashboard.validation_empty', { defaultValue: 'No validation reports yet.' })}
          ctaLabel={t('dashboard.validation_cta', { defaultValue: 'Open Validation' })}
          onClick={() => navigate('/validation')}
        />
      </WidgetCard>
    );
  }

  return (
    <WidgetCard icon={icon} title={title} subtitle={subtitle}>
      <div className="grid grid-cols-3 gap-4">
        <div className="text-center rounded-md bg-emerald-50 dark:bg-emerald-950/30 py-3">
          <div className="text-2xl font-semibold text-emerald-700 dark:text-emerald-300 tabular-nums">
            {stats.passed}
          </div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mt-1">
            {t('dashboard.validation_pass', { defaultValue: 'Passed' })}
          </div>
        </div>
        <div className="text-center rounded-md bg-amber-50 dark:bg-amber-950/30 py-3">
          <div className="text-2xl font-semibold text-amber-700 dark:text-amber-300 tabular-nums">
            {stats.warnings}
          </div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mt-1">
            {t('dashboard.validation_warn', { defaultValue: 'Warnings' })}
          </div>
        </div>
        <div className="text-center rounded-md bg-red-50 dark:bg-red-950/30 py-3">
          <div className="text-2xl font-semibold text-red-700 dark:text-red-300 tabular-nums">
            {stats.errors}
          </div>
          <div className="text-2xs uppercase tracking-wider text-content-tertiary mt-1">
            {t('dashboard.validation_err', { defaultValue: 'Errors' })}
          </div>
        </div>
      </div>
      {stats.latest && (
        <button
          type="button"
          onClick={() => navigate(`/validation/reports/${stats.latest!.id}`)}
          className="mt-3 flex w-full items-center justify-between text-xs text-content-tertiary hover:text-content-secondary"
        >
          <span>
            {t('dashboard.validation_latest', { defaultValue: 'Latest report' })}
            : {stats.latest.score != null ? `${Math.round(stats.latest.score * 100)}%` : '—'}
          </span>
          <ArrowRight size={12} />
        </button>
      )}
    </WidgetCard>
  );
}

/* ── 10. Weather & Site ───────────────────────────────────────────────── */

interface OpenMeteoResponse {
  current_weather?: {
    temperature?: number;
    windspeed?: number;
    weathercode?: number;
  };
  daily?: {
    temperature_2m_max?: number[];
    temperature_2m_min?: number[];
  };
}

const WEATHER_CODE_DESCRIPTIONS: Record<number, string> = {
  0: 'Clear sky',
  1: 'Mainly clear',
  2: 'Partly cloudy',
  3: 'Overcast',
  45: 'Fog',
  48: 'Rime fog',
  51: 'Light drizzle',
  61: 'Light rain',
  63: 'Moderate rain',
  65: 'Heavy rain',
  71: 'Light snow',
  80: 'Rain showers',
  95: 'Thunderstorm',
};

export function WeatherSiteWidget({ projects }: { projects?: ProjectRef[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const firstWithCoords = useMemo(
    () =>
      (projects ?? []).find(
        (p) => p.address?.lat != null && p.address?.lng != null,
      ),
    [projects],
  );

  const { data, isLoading } = useQuery({
    queryKey: [
      'dashboard-weather',
      firstWithCoords?.id ?? 'none',
      firstWithCoords?.address?.lat ?? null,
      firstWithCoords?.address?.lng ?? null,
    ],
    queryFn: async () => {
      // 1. Try the project diary endpoint first. The real backend path
      //    is ``/v1/daily_diary/weather/today`` (underscore — the legacy
      //    kebab alias ``/v1/daily-diary/weather/today`` also works).
      //    Endpoint requires ``project_id`` and returns
      //    ``list[WeatherRecordResponse]``.
      if (firstWithCoords?.id) {
        const diary = await safeGet<unknown>(
          `/v1/daily_diary/weather/today?project_id=${firstWithCoords.id}`,
        );
        const records = asArray<{
          temperature_c?: number | string | null;
          conditions_text?: string | null;
          conditions_code?: string | null;
          location_lat?: number | null;
          location_lng?: number | null;
        }>(diary);
        const latest = records[records.length - 1];
        if (latest && latest.temperature_c != null) {
          const tempNum = Number(latest.temperature_c);
          return {
            city: firstWithCoords.address?.city ?? firstWithCoords.name,
            temp: Number.isFinite(tempNum) ? tempNum : null,
            description:
              latest.conditions_text ??
              (latest.conditions_code
                ? WEATHER_CODE_DESCRIPTIONS[Number(latest.conditions_code)] ?? null
                : null),
            source: 'diary' as const,
          };
        }
      }
      // 2. Fall back to open-meteo using first project's geo (no API key needed).
      if (firstWithCoords?.address?.lat != null && firstWithCoords?.address?.lng != null) {
        try {
          const url = `https://api.open-meteo.com/v1/forecast?latitude=${firstWithCoords.address.lat}&longitude=${firstWithCoords.address.lng}&current_weather=true&daily=temperature_2m_max,temperature_2m_min&timezone=auto`;
          const resp = await fetch(url);
          if (!resp.ok) return null;
          const body = (await resp.json()) as OpenMeteoResponse;
          const code = body.current_weather?.weathercode;
          return {
            city: firstWithCoords.address.city ?? firstWithCoords.name,
            temp: body.current_weather?.temperature ?? null,
            description: code != null ? WEATHER_CODE_DESCRIPTIONS[code] ?? `Code ${code}` : null,
            high: body.daily?.temperature_2m_max?.[0],
            low: body.daily?.temperature_2m_min?.[0],
            source: 'open-meteo' as const,
          };
        } catch {
          return null;
        }
      }
      return null;
    },
    retry: false,
    staleTime: 10 * 60_000,
  });

  const title = t('dashboard.layout.w_weather', { defaultValue: 'Weather & Site' });
  const subtitle = t('dashboard.weather_subtitle', {
    defaultValue: "Today's conditions at your first project site",
  });
  const icon = <CloudSun size={16} className="text-content-tertiary" />;

  if (isLoading) return <WidgetCard icon={icon} title={title} subtitle={subtitle}><LoadingRows count={2} /></WidgetCard>;
  if (!data) {
    return (
      <WidgetCard icon={icon} title={title} subtitle={subtitle}>
        <EmptyCTA
          message={t('dashboard.weather_empty', {
            defaultValue: 'Add a project address to see local weather.',
          })}
          ctaLabel={t('dashboard.weather_cta', { defaultValue: 'Open Projects' })}
          onClick={() => navigate('/projects')}
        />
      </WidgetCard>
    );
  }

  return (
    <WidgetCard icon={icon} title={title} subtitle={subtitle}>
      <div className="flex items-center gap-4">
        <div className="text-4xl font-light tabular-nums">
          {data.temp != null ? `${Math.round(data.temp)}°` : '—'}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-content-primary truncate">{data.city ?? '—'}</p>
          <p className="text-xs text-content-tertiary truncate">{data.description ?? '—'}</p>
          {'high' in data && data.high != null && data.low != null && (
            <p className="text-2xs text-content-quaternary mt-1">
              {t('dashboard.weather_high_low', {
                defaultValue: 'H {{h}}° / L {{l}}°',
                h: Math.round(data.high),
                l: Math.round(data.low),
              })}
            </p>
          )}
        </div>
      </div>
    </WidgetCard>
  );
}

/* ── Compatibility re-export so the dashboard page doesn't need to know
 *    each individual import. */
export const NEW_WIDGET_IDS = [
  'boq_summary',
  'validation_score',
  'clash_health',
  'schedule_critical',
  'risk_top',
  'hse_scorecard',
  'procurement_pipeline',
  'budget_variance',
  'change_orders',
  'weather_site',
] as const;
