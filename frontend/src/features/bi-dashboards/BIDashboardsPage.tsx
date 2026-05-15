import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  LayoutDashboard,
  Activity,
  FileText,
  CalendarClock,
  Bell,
  Plus,
  X,
  Play,
  TrendingUp,
  TrendingDown,
  Minus,
  Loader2,
  AlertOctagon,
} from 'lucide-react';
import {
  Button,
  Card,
  Badge,
  EmptyState,
  Breadcrumb,
  SkeletonTable,
  WideModal,
  WideModalSection,
  WideModalField,
} from '@/shared/ui';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';
import {
  listKpis,
  getKpiHistory,
  listDashboards,
  renderDashboard,
  createDashboard,
  listReports,
  runReport,
  createReport,
  listAlerts,
  toggleAlert,
  createAlert,
  type AlertCondition,
  type AlertRule,
  type AlertSeverity,
  type Dashboard,
  type DashboardScope,
  type KpiDefinition,
  type ReportDefinition,
  type WidgetRenderResult,
} from './api';

type Tab = 'dashboards' | 'kpis' | 'reports' | 'schedules' | 'alerts';

const inputCls =
  'h-9 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';
// Legacy `labelCls` removed when CreateModal moved to <WideModalField>.

const SEVERITY_VARIANT: Record<AlertSeverity, 'neutral' | 'blue' | 'success' | 'warning' | 'error'> = {
  info: 'blue',
  warning: 'warning',
  critical: 'error',
};

const SCOPE_VARIANT: Record<DashboardScope, 'neutral' | 'blue' | 'success' | 'warning' | 'error'> = {
  personal: 'neutral',
  role: 'blue',
  global: 'success',
  project: 'warning',
};

/* ─── helpers ─── */

function toNumber(v: number | string | null | undefined): number {
  if (v == null) return 0;
  if (typeof v === 'number') return v;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function formatValue(value: number, unit: string | null | undefined): string {
  if (!Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  let formatted: string;
  if (abs >= 1_000_000) formatted = `${(value / 1_000_000).toFixed(2)}M`;
  else if (abs >= 1_000) formatted = `${(value / 1_000).toFixed(1)}k`;
  else if (Number.isInteger(value)) formatted = String(value);
  else formatted = value.toFixed(2);
  if (unit === 'percent') return `${formatted}%`;
  if (unit === 'currency') return formatted;
  return formatted;
}

/* ─── Page ─── */

export function BIDashboardsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('dashboards');
  const [createOpen, setCreateOpen] = useState(false);
  const [activeDashboardId, setActiveDashboardId] = useState<string | null>(null);

  const dashboardsQ = useQuery({
    queryKey: ['bi', 'dashboards'],
    queryFn: listDashboards,
    enabled: tab === 'dashboards',
  });
  const kpisQ = useQuery({
    queryKey: ['bi', 'kpis'],
    queryFn: () => listKpis(),
    enabled: tab === 'kpis',
  });
  const reportsQ = useQuery({
    queryKey: ['bi', 'reports'],
    queryFn: listReports,
    enabled: tab === 'reports' || tab === 'schedules',
  });
  const alertsQ = useQuery({
    queryKey: ['bi', 'alerts'],
    queryFn: listAlerts,
    enabled: tab === 'alerts',
  });

  const activeQuery =
    tab === 'dashboards'
      ? dashboardsQ
      : tab === 'kpis'
        ? kpisQ
        : tab === 'reports' || tab === 'schedules'
          ? reportsQ
          : alertsQ;
  const isLoading = activeQuery.isLoading;
  // A failed list query must NOT fall through to the "nothing here yet"
  // empty state — that hides real backend/permission failures behind a
  // success-looking screen. Surface it with a retry instead.
  const loadError = activeQuery.isError ? activeQuery.error : null;

  return (
    <div className="space-y-5">
      <Breadcrumb
        items={[
          { label: t('bi.title', { defaultValue: 'BI & Dashboards' }) },
        ]}
      />

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">
            {t('bi.title', { defaultValue: 'BI & Dashboards' })}
          </h1>
          <p className="mt-1 text-sm text-content-secondary">
            {t('bi.subtitle', {
              defaultValue:
                'KPIs, scheduled reports, executive dashboards and alert rules — all in one place.',
            })}
          </p>
        </div>
        {(tab === 'dashboards' || tab === 'reports' || tab === 'alerts') && (
          <Button
            variant="primary"
            icon={<Plus size={14} />}
            onClick={() => setCreateOpen(true)}
          >
            {tab === 'dashboards'
              ? t('bi.new_dashboard', { defaultValue: 'New Dashboard' })
              : tab === 'reports'
                ? t('bi.new_report', { defaultValue: 'New Report' })
                : t('bi.new_alert', { defaultValue: 'New Alert' })}
          </Button>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-border-light">
        <nav className="flex gap-1 -mb-px">
          {(
            [
              { id: 'dashboards', label: t('bi.dashboards', { defaultValue: 'My Dashboards' }), icon: LayoutDashboard },
              { id: 'kpis', label: t('bi.kpis', { defaultValue: 'KPIs' }), icon: Activity },
              { id: 'reports', label: t('bi.reports', { defaultValue: 'Reports' }), icon: FileText },
              { id: 'schedules', label: t('bi.schedules', { defaultValue: 'Schedules' }), icon: CalendarClock },
              { id: 'alerts', label: t('bi.alerts', { defaultValue: 'Alerts' }), icon: Bell },
            ] as { id: Tab; label: string; icon: React.ElementType }[]
          ).map((tabItem) => {
            const Icon = tabItem.icon;
            return (
              <button
                key={tabItem.id}
                type="button"
                onClick={() => setTab(tabItem.id)}
                className={clsx(
                  'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
                  tab === tabItem.id
                    ? 'border-oe-blue text-oe-blue'
                    : 'border-transparent text-content-secondary hover:text-content-primary',
                )}
              >
                <Icon size={14} />
                {tabItem.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Body */}
      {isLoading ? (
        <Card padding="md">
          <SkeletonTable rows={6} columns={4} />
        </Card>
      ) : loadError ? (
        <Card padding="md">
          <EmptyState
            icon={<AlertOctagon size={22} />}
            title={t('bi.load_error', { defaultValue: 'Could not load BI data' })}
            description={getErrorMessage(loadError)}
            action={{
              label: t('common.retry', { defaultValue: 'Retry' }),
              onClick: () => activeQuery.refetch(),
            }}
          />
        </Card>
      ) : tab === 'dashboards' ? (
        <DashboardsGrid
          rows={dashboardsQ.data ?? []}
          onOpen={(id) => setActiveDashboardId(id)}
          onCreate={() => setCreateOpen(true)}
        />
      ) : tab === 'kpis' ? (
        <KpiLibrary rows={kpisQ.data ?? []} />
      ) : tab === 'reports' ? (
        <ReportList rows={reportsQ.data ?? []} onCreate={() => setCreateOpen(true)} />
      ) : tab === 'schedules' ? (
        <SchedulesList reports={reportsQ.data ?? []} />
      ) : (
        <AlertsList rows={alertsQ.data ?? []} onCreate={() => setCreateOpen(true)} />
      )}

      {/* Dashboard render drawer */}
      {activeDashboardId && (
        <DashboardRenderPanel
          dashboardId={activeDashboardId}
          onClose={() => setActiveDashboardId(null)}
        />
      )}

      {/* Create modal */}
      {createOpen && (
        <CreateModal
          kind={tab as 'dashboards' | 'reports' | 'alerts'}
          kpis={kpisQ.data ?? []}
          onClose={() => setCreateOpen(false)}
        />
      )}
    </div>
  );
}

/* ─── Dashboards grid ─── */

function DashboardsGrid({
  rows,
  onOpen,
  onCreate,
}: {
  rows: Dashboard[];
  onOpen: (id: string) => void;
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          icon={<LayoutDashboard size={22} />}
          title={t('bi.empty_dashboards', { defaultValue: 'No dashboards yet' })}
          description={t('bi.empty_dashboards_desc', {
            defaultValue:
              'Create a dashboard for your role or project — pin KPI cards, charts and gauges.',
          })}
          action={{
            label: t('bi.new_dashboard', { defaultValue: 'New Dashboard' }),
            onClick: onCreate,
          }}
        />
      </Card>
    );
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {rows.map((d) => {
        const widgets = Array.isArray((d.layout_json as { widgets?: unknown[] } | null)?.widgets)
          ? ((d.layout_json as { widgets?: unknown[] }).widgets as unknown[]).length
          : 0;
        return (
          <Card key={d.id} padding="md" hoverable>
            <button
              type="button"
              onClick={() => onOpen(d.id)}
              className="text-left w-full focus:outline-none"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold text-content-primary truncate">{d.name}</h3>
                <Badge variant={SCOPE_VARIANT[d.scope]}>{d.scope}</Badge>
              </div>
              {d.description && (
                <p className="mt-1 text-xs text-content-secondary line-clamp-2">{d.description}</p>
              )}
              <div className="mt-3 flex items-center justify-between text-xs text-content-tertiary">
                <span>
                  {t('bi.widgets_count', {
                    defaultValue: '{{count}} widgets',
                    count: widgets,
                  })}
                </span>
                <span>
                  <DateDisplay value={d.updated_at} />
                </span>
              </div>
              {d.is_default && (
                <div className="mt-2">
                  <Badge variant="success">
                    {t('bi.default', { defaultValue: 'Default' })}
                  </Badge>
                </div>
              )}
            </button>
          </Card>
        );
      })}
    </div>
  );
}

/* ─── KPI library with sparklines ─── */

function KpiLibrary({ rows }: { rows: KpiDefinition[] }) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          icon={<Activity size={22} />}
          title={t('bi.empty_kpis', { defaultValue: 'No KPIs registered' })}
          description={t('bi.empty_kpis_desc', {
            defaultValue: 'KPI definitions are seeded per role; check the seed loader.',
          })}
        />
      </Card>
    );
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {rows.map((k) => (
        <KpiLibraryCard key={k.id} kpi={k} />
      ))}
    </div>
  );
}

function KpiLibraryCard({ kpi }: { kpi: KpiDefinition }) {
  const { t } = useTranslation();
  const historyQ = useQuery({
    queryKey: ['bi', 'kpi-history', kpi.code],
    queryFn: () => getKpiHistory(kpi.code, { limit: 12 }),
    staleTime: 60_000,
  });
  const history = historyQ.data?.history ?? [];
  const values = history.map((p) => toNumber(p.value));
  const latest = values.length > 0 ? values[values.length - 1] : null;
  const previous = values.length > 1 ? values[values.length - 2] : null;
  const delta =
    latest != null && previous != null && previous !== 0
      ? ((latest - previous) / Math.abs(previous)) * 100
      : null;

  return (
    <Card padding="md">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold text-content-primary truncate" title={kpi.name}>
            {kpi.name}
          </h3>
          <p className="mt-0.5 text-xs font-mono text-content-tertiary">{kpi.code}</p>
        </div>
        <Badge variant="neutral">{kpi.category}</Badge>
      </div>
      <div className="mt-3 flex items-end justify-between gap-2">
        <div>
          <p className="text-2xl font-semibold text-content-primary leading-none">
            {latest != null ? formatValue(latest, kpi.unit) : '—'}
          </p>
          <p className="mt-1 text-xs text-content-tertiary">{kpi.unit}</p>
        </div>
        {delta != null && (
          <DeltaChip delta={delta} />
        )}
      </div>
      <div className="mt-3">
        <Sparkline values={values} loading={historyQ.isLoading} />
      </div>
      {kpi.description && (
        <p className="mt-3 text-xs text-content-secondary line-clamp-2">{kpi.description}</p>
      )}
      <p className="mt-2 text-[10px] uppercase tracking-wide text-content-tertiary">
        {t('bi.last_n_periods', { defaultValue: 'Last {{n}} periods', n: values.length })}
      </p>
    </Card>
  );
}

function Sparkline({ values, loading }: { values: number[]; loading?: boolean }) {
  if (loading) {
    return <div className="h-10 w-full animate-pulse rounded bg-surface-secondary" />;
  }
  if (values.length === 0) {
    return <div className="h-10 w-full rounded bg-surface-secondary/40" />;
  }
  const W = 200;
  const H = 40;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = values.length > 1 ? W / (values.length - 1) : 0;
  const points = values
    .map((v, i) => {
      const x = i * step;
      const y = H - ((v - min) / range) * (H - 4) - 2;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
  const last = values[values.length - 1] ?? 0;
  const lastX = (values.length - 1) * step;
  const lastY = H - ((last - min) / range) * (H - 4) - 2;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-10 w-full">
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        points={points}
        className="text-oe-blue"
      />
      {values.map((v, i) => {
        const x = i * step;
        const y = H - ((v - min) / range) * (H - 4) - 2;
        return (
          <circle key={i} cx={x} cy={y} r={1.5} className="fill-oe-blue/60" />
        );
      })}
      <circle cx={lastX} cy={lastY} r={2.5} className="fill-oe-blue" />
    </svg>
  );
}

function DeltaChip({ delta }: { delta: number }) {
  const Icon = delta > 0.5 ? TrendingUp : delta < -0.5 ? TrendingDown : Minus;
  const variant: 'success' | 'error' | 'neutral' =
    delta > 0.5 ? 'success' : delta < -0.5 ? 'error' : 'neutral';
  const sign = delta > 0 ? '+' : '';
  return (
    <Badge variant={variant}>
      <span className="flex items-center gap-1">
        <Icon size={10} />
        {sign}
        {delta.toFixed(1)}%
      </span>
    </Badge>
  );
}

/* ─── Reports ─── */

function ReportList({
  rows,
  onCreate,
}: {
  rows: ReportDefinition[];
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const runMut = useMutation({
    mutationFn: (id: string) => runReport(id),
    onSuccess: (data) => {
      addToast({
        type: 'success',
        title: t('bi.report_run_ok', { defaultValue: 'Report generated' }),
        message: `${data.row_count} ${t('bi.rows', { defaultValue: 'rows' })}`,
      });
      qc.invalidateQueries({ queryKey: ['bi', 'reports'] });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  if (rows.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          icon={<FileText size={22} />}
          title={t('bi.empty_reports', { defaultValue: 'No reports yet' })}
          description={t('bi.empty_reports_desc', {
            defaultValue:
              'Define a report (PDF/Excel/CSV) and schedule it for stakeholders.',
          })}
          action={{
            label: t('bi.new_report', { defaultValue: 'New Report' }),
            onClick: onCreate,
          }}
        />
      </Card>
    );
  }
  return (
    <Card padding="none">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
            <tr>
              <th className="px-4 py-2.5 text-left">{t('bi.code', { defaultValue: 'Code' })}</th>
              <th className="px-4 py-2.5 text-left">{t('bi.name', { defaultValue: 'Name' })}</th>
              <th className="px-4 py-2.5 text-left">{t('bi.scope', { defaultValue: 'Scope' })}</th>
              <th className="px-4 py-2.5 text-left">{t('bi.format', { defaultValue: 'Format' })}</th>
              <th className="px-4 py-2.5 text-right">{t('common.actions', { defaultValue: 'Actions' })}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-border-light">
                <td className="px-4 py-2 font-mono text-xs text-content-secondary">{r.code}</td>
                <td className="px-4 py-2 font-medium">{r.name}</td>
                <td className="px-4 py-2"><Badge variant="neutral">{r.scope}</Badge></td>
                <td className="px-4 py-2 text-xs text-content-secondary uppercase">{r.output_format}</td>
                <td className="px-4 py-2 text-right">
                  <Button
                    variant="secondary"
                    icon={<Play size={12} />}
                    onClick={() => runMut.mutate(r.id)}
                    loading={runMut.isPending && runMut.variables === r.id}
                  >
                    {t('bi.run_now', { defaultValue: 'Run now' })}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ─── Schedules ─── */

function SchedulesList({ reports }: { reports: ReportDefinition[] }) {
  const { t } = useTranslation();

  // There is no list-schedules endpoint, so the client cannot resolve a
  // report → its schedule id. Previously the row actions passed the
  // *report* id straight into runScheduleNow()/updateSchedule(), which
  // require a *schedule* id — every click was a guaranteed wrong-object
  // call. Until a GET /report-schedules endpoint exists this panel is an
  // honest read-only summary; running is done from the Reports tab
  // (which correctly calls runReport with the report id).

  if (reports.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          icon={<CalendarClock size={22} />}
          title={t('bi.empty_schedules', { defaultValue: 'No scheduled reports' })}
          description={t('bi.empty_schedules_desc', {
            defaultValue:
              'Create a report first, then attach a recurring schedule with recipients.',
          })}
        />
      </Card>
    );
  }

  return (
    <Card padding="none">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
            <tr>
              <th className="px-4 py-2.5 text-left">{t('bi.report', { defaultValue: 'Report' })}</th>
              <th className="px-4 py-2.5 text-left">{t('bi.frequency', { defaultValue: 'Frequency' })}</th>
              <th className="px-4 py-2.5 text-left">{t('bi.next_run', { defaultValue: 'Next run' })}</th>
              <th className="px-4 py-2.5 text-left">{t('bi.recipients', { defaultValue: 'Recipients' })}</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((r) => (
              <tr key={r.id} className="border-t border-border-light">
                <td className="px-4 py-2 font-medium">{r.name}</td>
                <td className="px-4 py-2 text-xs text-content-secondary">
                  {t('bi.frequency_value', { defaultValue: 'On demand' })}
                </td>
                <td className="px-4 py-2 text-xs text-content-secondary">—</td>
                <td className="px-4 py-2 text-xs text-content-secondary">—</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="border-t border-border-light px-4 py-2.5 text-xs text-content-tertiary">
        {t('bi.schedules_run_hint', {
          defaultValue:
            'Run a report on demand from the Reports tab. Recurring delivery is configured server-side.',
        })}
      </div>
    </Card>
  );
}

/* ─── Alerts ─── */

function AlertsList({
  rows,
  onCreate,
}: {
  rows: AlertRule[];
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const toggleMut = useMutation({
    mutationFn: (args: { id: string; enabled: boolean }) => toggleAlert(args.id, args.enabled),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bi', 'alerts'] });
      addToast({ type: 'success', title: t('bi.alert_toggled', { defaultValue: 'Alert updated' }) });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  if (rows.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          icon={<Bell size={22} />}
          title={t('bi.empty_alerts', { defaultValue: 'No alert rules' })}
          description={t('bi.empty_alerts_desc', {
            defaultValue: 'Watch a KPI and notify your team when it crosses a threshold.',
          })}
          action={{
            label: t('bi.new_alert', { defaultValue: 'New Alert' }),
            onClick: onCreate,
          }}
        />
      </Card>
    );
  }
  return (
    <Card padding="none">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
            <tr>
              <th className="px-4 py-2.5 text-left">{t('bi.name', { defaultValue: 'Name' })}</th>
              <th className="px-4 py-2.5 text-left">{t('bi.kpi', { defaultValue: 'KPI' })}</th>
              <th className="px-4 py-2.5 text-left">{t('bi.condition', { defaultValue: 'Condition' })}</th>
              <th className="px-4 py-2.5 text-left">{t('bi.severity', { defaultValue: 'Severity' })}</th>
              <th className="px-4 py-2.5 text-left">{t('bi.last_triggered', { defaultValue: 'Last fired' })}</th>
              <th className="px-4 py-2.5 text-right">{t('bi.enabled', { defaultValue: 'Enabled' })}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.id} className="border-t border-border-light">
                <td className="px-4 py-2 font-medium">{a.name}</td>
                <td className="px-4 py-2 font-mono text-xs text-content-secondary">{a.kpi_code}</td>
                <td className="px-4 py-2 text-xs text-content-secondary">
                  {a.condition} {String(a.threshold_value)}
                </td>
                <td className="px-4 py-2">
                  <Badge variant={SEVERITY_VARIANT[a.severity]} dot>
                    {a.severity}
                  </Badge>
                </td>
                <td className="px-4 py-2 text-xs text-content-secondary">
                  {a.last_triggered_at ? <DateDisplay value={a.last_triggered_at} /> : '—'}
                </td>
                <td className="px-4 py-2 text-right">
                  <label className="inline-flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={a.enabled}
                      onChange={(e) =>
                        toggleMut.mutate({ id: a.id, enabled: e.target.checked })
                      }
                      className="h-4 w-4 rounded border-border accent-oe-blue"
                    />
                  </label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ─── Dashboard render panel ─── */

/** Close a drawer when the user presses Escape (matches WideModal UX). */
function useEscapeToClose(onClose: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
}

function DashboardRenderPanel({
  dashboardId,
  onClose,
}: {
  dashboardId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  useEscapeToClose(onClose);
  const renderQ = useQuery({
    queryKey: ['bi', 'dashboard-render', dashboardId],
    queryFn: () => renderDashboard(dashboardId),
  });
  const data = renderQ.data;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="bi-dashboard-drawer-title"
        className="relative h-full w-full max-w-3xl overflow-y-auto bg-surface-elevated shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-light bg-surface-elevated px-5 py-3">
          <div>
            <h2 id="bi-dashboard-drawer-title" className="text-base font-semibold">
              {data?.dashboard.name ?? t('bi.dashboard', { defaultValue: 'Dashboard' })}
            </h2>
            {data?.rendered_at && (
              <p className="text-xs text-content-tertiary">
                <DateDisplay value={data.rendered_at} format="datetime" />
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 hover:bg-surface-secondary"
            aria-label={t('common.close', { defaultValue: 'Close' })}
          >
            <X size={16} />
          </button>
        </div>
        <div className="space-y-3 p-5">
          {renderQ.isLoading && <SkeletonTable rows={4} columns={3} />}
          {renderQ.isError && (
            <p className="text-sm text-rose-600">{getErrorMessage(renderQ.error)}</p>
          )}
          {data && data.widgets.length === 0 && (
            <EmptyState
              icon={<LayoutDashboard size={22} />}
              title={t('bi.empty_widgets', { defaultValue: 'No widgets pinned' })}
              description={t('bi.empty_widgets_desc', {
                defaultValue: 'Edit the dashboard layout to pin KPI cards or charts.',
              })}
            />
          )}
          {data && data.widgets.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {data.widgets.map((w) => (
                <WidgetCard key={w.widget.id} widget={w} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function WidgetCard({ widget }: { widget: WidgetRenderResult }) {
  const { t } = useTranslation();
  const type = widget.widget.widget_type;
  const value = toNumber(widget.value);
  const trend = (widget.breakdown?.['trend'] as unknown[]) || [];
  const trendValues = Array.isArray(trend)
    ? trend.map((p) => toNumber((p as { value?: number | string }).value ?? 0))
    : [];
  const tableRows = (widget.breakdown?.['rows'] as unknown[]) || [];

  if (type === 'kpi_card') {
    const prev =
      trendValues.length > 1 ? trendValues[trendValues.length - 2] : null;
    const delta =
      prev != null && prev !== 0 ? ((value - prev) / Math.abs(prev)) * 100 : null;
    return (
      <Card padding="md">
        <p className="text-xs uppercase tracking-wide text-content-tertiary">
          {widget.widget.kpi_code || t('bi.kpi', { defaultValue: 'KPI' })}
        </p>
        <div className="mt-2 flex items-end justify-between">
          <p className="text-3xl font-semibold">
            {formatValue(value, widget.unit ?? null)}
          </p>
          {delta != null && <DeltaChip delta={delta} />}
        </div>
        <p className="mt-1 text-xs text-content-tertiary">{widget.unit ?? ''}</p>
      </Card>
    );
  }

  if (type === 'line_chart' || type === 'bar_chart') {
    return (
      <Card padding="md">
        <p className="text-xs uppercase tracking-wide text-content-tertiary">
          {widget.widget.kpi_code || t('bi.chart', { defaultValue: 'Chart' })}
        </p>
        <div className="mt-2">
          {type === 'line_chart' ? (
            <Sparkline values={trendValues.length ? trendValues : [value]} />
          ) : (
            <MiniBarChart values={trendValues.length ? trendValues : [value]} />
          )}
        </div>
      </Card>
    );
  }

  if (type === 'gauge') {
    const threshold = toNumber(widget.breakdown?.['threshold'] as number | string);
    return (
      <Card padding="md">
        <p className="text-xs uppercase tracking-wide text-content-tertiary">
          {widget.widget.kpi_code || t('bi.gauge', { defaultValue: 'Gauge' })}
        </p>
        <HalfGauge value={value} threshold={threshold || Math.max(1, value * 1.5)} />
        <p className="mt-1 text-center text-sm font-semibold">
          {formatValue(value, widget.unit ?? null)}
        </p>
      </Card>
    );
  }

  if (type === 'table') {
    const rows = Array.isArray(tableRows) ? (tableRows as Array<Record<string, unknown>>) : [];
    const cols = rows.length > 0 ? Object.keys(rows[0] ?? {}) : [];
    return (
      <Card padding="md" className="md:col-span-2">
        <p className="text-xs uppercase tracking-wide text-content-tertiary mb-2">
          {widget.widget.kpi_code || t('bi.table', { defaultValue: 'Table' })}
        </p>
        {rows.length === 0 ? (
          <p className="text-xs text-content-tertiary">
            {t('bi.no_rows', { defaultValue: 'No rows' })}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-content-tertiary">
                <tr>
                  {cols.map((c) => (
                    <th key={c} className="px-2 py-1 text-left font-medium">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 10).map((row, i) => (
                  <tr key={i} className="border-t border-border-light">
                    {cols.map((c) => (
                      <td key={c} className="px-2 py-1">{String(row[c] ?? '')}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    );
  }

  return (
    <Card padding="md">
      <p className="text-xs uppercase tracking-wide text-content-tertiary">{type}</p>
      <p className="mt-2 text-lg font-semibold">{formatValue(value, widget.unit ?? null)}</p>
    </Card>
  );
}

function MiniBarChart({ values }: { values: number[] }) {
  if (values.length === 0) return <div className="h-16 w-full bg-surface-secondary/40" />;
  const W = 200;
  const H = 60;
  const max = Math.max(...values, 1);
  const bw = W / values.length;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-16 w-full">
      {values.map((v, i) => {
        const h = (v / max) * (H - 4);
        return (
          <rect
            key={i}
            x={i * bw + 1}
            y={H - h - 2}
            width={Math.max(1, bw - 2)}
            height={Math.max(1, h)}
            className="fill-oe-blue/70"
          />
        );
      })}
    </svg>
  );
}

function HalfGauge({ value, threshold }: { value: number; threshold: number }) {
  const t = Math.max(0.001, threshold);
  const pct = Math.max(0, Math.min(1, value / t));
  // Half circle from -180° to 0°. Needle angle:
  const angle = -Math.PI + Math.PI * pct;
  const cx = 60;
  const cy = 50;
  const r = 40;
  const nx = cx + Math.cos(angle) * (r - 4);
  const ny = cy + Math.sin(angle) * (r - 4);
  const arc = (theta: number) => ({
    x: cx + Math.cos(theta) * r,
    y: cy + Math.sin(theta) * r,
  });
  const start = arc(Math.PI);
  const end = arc(0);
  return (
    <svg viewBox="0 0 120 60" className="mx-auto h-20 w-full">
      <path
        d={`M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${end.x} ${end.y}`}
        fill="none"
        stroke="currentColor"
        strokeWidth={6}
        className="text-surface-secondary"
      />
      <path
        d={`M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${arc(-Math.PI + Math.PI * pct).x} ${arc(-Math.PI + Math.PI * pct).y}`}
        fill="none"
        stroke="currentColor"
        strokeWidth={6}
        className={pct > 0.85 ? 'text-rose-500' : pct > 0.6 ? 'text-amber-500' : 'text-oe-blue'}
      />
      <line x1={cx} y1={cy} x2={nx} y2={ny} strokeWidth={2} className="stroke-content-primary" />
      <circle cx={cx} cy={cy} r={3} className="fill-content-primary" />
    </svg>
  );
}

/* ─── Create modal ─── */

function CreateModal({
  kind,
  kpis,
  onClose,
}: {
  kind: 'dashboards' | 'reports' | 'alerts';
  kpis: KpiDefinition[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [busy, setBusy] = useState(false);

  const [dashForm, setDashForm] = useState({
    name: '',
    description: '',
    scope: 'personal' as DashboardScope,
  });
  const [reportForm, setReportForm] = useState({
    code: '',
    name: '',
    description: '',
    output_format: 'pdf' as 'pdf' | 'xlsx' | 'csv' | 'json',
  });
  const [alertForm, setAlertForm] = useState({
    name: '',
    kpi_code: kpis[0]?.code ?? '',
    condition: 'below' as AlertCondition,
    threshold_value: '0',
    severity: 'warning' as AlertSeverity,
  });

  const submit = async () => {
    setBusy(true);
    try {
      if (kind === 'dashboards') {
        if (!dashForm.name.trim()) throw new Error('Name required');
        await createDashboard(dashForm);
        addToast({ type: 'success', title: t('bi.dashboard_created', { defaultValue: 'Dashboard created' }) });
        qc.invalidateQueries({ queryKey: ['bi', 'dashboards'] });
      } else if (kind === 'reports') {
        if (!reportForm.code.trim() || !reportForm.name.trim()) throw new Error('Code & name required');
        await createReport(reportForm);
        addToast({ type: 'success', title: t('bi.report_created', { defaultValue: 'Report created' }) });
        qc.invalidateQueries({ queryKey: ['bi', 'reports'] });
      } else {
        if (!alertForm.name.trim() || !alertForm.kpi_code.trim()) throw new Error('Name & KPI required');
        await createAlert({
          name: alertForm.name,
          kpi_code: alertForm.kpi_code,
          condition: alertForm.condition,
          threshold_value: Number(alertForm.threshold_value) || 0,
          severity: alertForm.severity,
        });
        addToast({ type: 'success', title: t('bi.alert_created', { defaultValue: 'Alert created' }) });
        qc.invalidateQueries({ queryKey: ['bi', 'alerts'] });
      }
      onClose();
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  const titleByKind: Record<typeof kind, string> = {
    dashboards: t('bi.new_dashboard', { defaultValue: 'New dashboard' }),
    reports: t('bi.new_report', { defaultValue: 'New scheduled report' }),
    alerts: t('bi.new_alert', { defaultValue: 'New KPI alert rule' }),
  };
  const subtitleByKind: Record<typeof kind, string> = {
    dashboards: t('bi.new_dashboard_subtitle', {
      defaultValue:
        'Start with the basics — you can add KPI cards, charts and gauges after the dashboard is created.',
    }),
    reports: t('bi.new_report_subtitle', {
      defaultValue:
        'Define a report once, then schedule it for recurring delivery or run it on demand.',
    }),
    alerts: t('bi.new_alert_subtitle', {
      defaultValue:
        'Trigger a notification whenever a KPI crosses a threshold. Throttling is on by default.',
    }),
  };

  return (
    <WideModal
      open
      onClose={onClose}
      title={titleByKind[kind]}
      subtitle={subtitleByKind[kind]}
      size={kind === 'alerts' ? 'lg' : 'md'}
      busy={busy}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            loading={busy}
            icon={busy ? <Loader2 size={14} /> : <Plus size={14} />}
          >
            {t('common.create', { defaultValue: 'Create' })}
          </Button>
        </>
      }
    >
      {kind === 'dashboards' && (
        <WideModalSection columns={2}>
          <WideModalField
            label={t('bi.name', { defaultValue: 'Name' })}
            required
            span={2}
          >
            <input
              value={dashForm.name}
              onChange={(e) => setDashForm({ ...dashForm, name: e.target.value })}
              className={inputCls}
              placeholder={t('bi.dashboard_name_placeholder', {
                defaultValue: 'PM weekly overview',
              })}
            />
          </WideModalField>
          <WideModalField
            label={t('bi.description', { defaultValue: 'Description' })}
            hint={t('bi.description_hint', {
              defaultValue: 'Shown in the dashboard tile and the share link.',
            })}
            span={2}
          >
            <textarea
              value={dashForm.description}
              onChange={(e) => setDashForm({ ...dashForm, description: e.target.value })}
              rows={3}
              className={clsx(inputCls, 'h-auto py-2 resize-y')}
            />
          </WideModalField>
          <WideModalField
            label={t('bi.scope', { defaultValue: 'Visibility scope' })}
            hint={t('bi.scope_hint', {
              defaultValue:
                'Personal = only you. Role = everyone in your role. Project = all members. Global = company-wide.',
            })}
            span={2}
          >
            <select
              value={dashForm.scope}
              onChange={(e) => setDashForm({ ...dashForm, scope: e.target.value as DashboardScope })}
              className={inputCls}
            >
              <option value="personal">{t('bi.scope_personal', { defaultValue: 'Personal — only me' })}</option>
              <option value="role">{t('bi.scope_role', { defaultValue: 'Role — my team' })}</option>
              <option value="project">{t('bi.scope_project', { defaultValue: 'Project — project members' })}</option>
              <option value="global">{t('bi.scope_global', { defaultValue: 'Global — entire company' })}</option>
            </select>
          </WideModalField>
        </WideModalSection>
      )}

      {kind === 'reports' && (
        <WideModalSection columns={2}>
          <WideModalField
            label={t('bi.code', { defaultValue: 'Report code' })}
            required
            hint={t('bi.code_hint', {
              defaultValue: 'Short identifier used in URLs and webhooks. Lowercase + underscores.',
            })}
          >
            <input
              value={reportForm.code}
              onChange={(e) => setReportForm({ ...reportForm, code: e.target.value })}
              className={inputCls}
              placeholder="weekly_cost_summary"
            />
          </WideModalField>
          <WideModalField
            label={t('bi.name', { defaultValue: 'Display name' })}
            required
          >
            <input
              value={reportForm.name}
              onChange={(e) => setReportForm({ ...reportForm, name: e.target.value })}
              className={inputCls}
              placeholder={t('bi.report_name_placeholder', {
                defaultValue: 'Weekly cost summary',
              })}
            />
          </WideModalField>
          <WideModalField
            label={t('bi.description', { defaultValue: 'Description' })}
            span={2}
          >
            <textarea
              value={reportForm.description}
              onChange={(e) => setReportForm({ ...reportForm, description: e.target.value })}
              rows={3}
              className={clsx(inputCls, 'h-auto py-2 resize-y')}
            />
          </WideModalField>
          <WideModalField
            label={t('bi.format', { defaultValue: 'Output format' })}
            hint={t('bi.format_hint', {
              defaultValue: 'PDF for executives, XLSX for analysts, CSV/JSON for integrations.',
            })}
            span={2}
          >
            <select
              value={reportForm.output_format}
              onChange={(e) =>
                setReportForm({
                  ...reportForm,
                  output_format: e.target.value as 'pdf' | 'xlsx' | 'csv' | 'json',
                })
              }
              className={inputCls}
            >
              <option value="pdf">PDF</option>
              <option value="xlsx">Excel (XLSX)</option>
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
            </select>
          </WideModalField>
        </WideModalSection>
      )}

      {kind === 'alerts' && (
        <WideModalSection columns={2}>
          <WideModalField
            label={t('bi.name', { defaultValue: 'Rule name' })}
            required
            span={2}
          >
            <input
              value={alertForm.name}
              onChange={(e) => setAlertForm({ ...alertForm, name: e.target.value })}
              className={inputCls}
              placeholder={t('bi.alert_name_placeholder', {
                defaultValue: 'CPI dropped below 0.9',
              })}
            />
          </WideModalField>
          <WideModalField
            label={t('bi.kpi', { defaultValue: 'KPI to monitor' })}
            required
            span={2}
          >
            {kpis.length > 0 ? (
              <select
                value={alertForm.kpi_code}
                onChange={(e) => setAlertForm({ ...alertForm, kpi_code: e.target.value })}
                className={inputCls}
              >
                {kpis.map((k) => (
                  <option key={k.id} value={k.code}>
                    {k.code} — {k.name}
                  </option>
                ))}
              </select>
            ) : (
              <input
                value={alertForm.kpi_code}
                onChange={(e) => setAlertForm({ ...alertForm, kpi_code: e.target.value })}
                className={inputCls}
                placeholder="cost_variance_pct"
              />
            )}
          </WideModalField>
          <WideModalField label={t('bi.condition', { defaultValue: 'Trigger when value is' })}>
            <select
              value={alertForm.condition}
              onChange={(e) =>
                setAlertForm({ ...alertForm, condition: e.target.value as AlertCondition })
              }
              className={inputCls}
            >
              <option value="above">{t('bi.cond_above', { defaultValue: 'Above threshold' })}</option>
              <option value="below">{t('bi.cond_below', { defaultValue: 'Below threshold' })}</option>
              <option value="equals">{t('bi.cond_equals', { defaultValue: 'Equal to threshold' })}</option>
              <option value="not_equals">{t('bi.cond_not_equals', { defaultValue: 'Not equal to threshold' })}</option>
              <option value="changed_by_more_than">{t('bi.cond_change', { defaultValue: 'Changed by more than' })}</option>
            </select>
          </WideModalField>
          <WideModalField label={t('bi.threshold', { defaultValue: 'Threshold value' })}>
            <input
              type="number"
              value={alertForm.threshold_value}
              onChange={(e) =>
                setAlertForm({ ...alertForm, threshold_value: e.target.value })
              }
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('bi.severity', { defaultValue: 'Severity' })}
            hint={t('bi.severity_hint', {
              defaultValue: 'Drives notification channel & escalation behaviour.',
            })}
            span={2}
          >
            <select
              value={alertForm.severity}
              onChange={(e) =>
                setAlertForm({ ...alertForm, severity: e.target.value as AlertSeverity })
              }
              className={inputCls}
            >
              <option value="info">{t('bi.sev_info', { defaultValue: 'Info — log only' })}</option>
              <option value="warning">{t('bi.sev_warning', { defaultValue: 'Warning — in-app banner' })}</option>
              <option value="critical">{t('bi.sev_critical', { defaultValue: 'Critical — email + Slack' })}</option>
            </select>
          </WideModalField>
        </WideModalSection>
      )}
    </WideModal>
  );
}

