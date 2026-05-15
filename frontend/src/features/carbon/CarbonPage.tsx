import { useState, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  Leaf,
  Target,
  FileText,
  Database,
  X,
  Plus,
  Loader2,
  TrendingDown,
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
} from 'lucide-react';
import {
  Button,
  Card,
  Badge,
  EmptyState,
  Breadcrumb,
  SkeletonTable,
} from '@/shared/ui';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { useToastStore } from '@/stores/useToastStore';
import { apiGet, getErrorMessage } from '@/shared/lib/api';
import {
  listInventories,
  getInventoryTotals,
  listEmbodiedEntries,
  listScope1,
  listScope2,
  listScope3,
  listEPDs,
  listTargets,
  listReports,
  createInventory,
  createTarget,
  generateReport,
  getTargetProgress,
  type CarbonInventory,
  type EPDRecord,
  type CarbonTarget,
  type SustainabilityReport,
} from './api';

type Tab = 'inventory' | 'epds' | 'targets' | 'reports';

interface Project {
  id: string;
  name: string;
  description?: string;
  currency?: string;
}

const inputCls =
  'h-9 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

const labelCls = 'block text-xs font-medium text-content-secondary mb-1';

function toNum(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return 0;
  if (typeof v === 'number') return v;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

function formatKg(kg: number): string {
  if (Math.abs(kg) >= 1_000_000) return `${(kg / 1_000_000).toFixed(2)} kt`;
  if (Math.abs(kg) >= 1_000) return `${(kg / 1_000).toFixed(2)} t`;
  return `${kg.toFixed(0)} kg`;
}

function todayIso(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

/** Close a drawer/modal when the user presses Escape (matches WideModal UX). */
function useEscapeToClose(onClose: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
}

/* ─── Page ─── */

export function CarbonPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('inventory');
  const [projectId, setProjectId] = useState<string>('');
  const [inventoryDrawerId, setInventoryDrawerId] = useState<string | null>(null);
  const [createInvOpen, setCreateInvOpen] = useState(false);
  const [createTargetOpen, setCreateTargetOpen] = useState(false);
  const [generateReportOpen, setGenerateReportOpen] = useState(false);

  const projectsQ = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<Project[]>('/v1/projects/').catch(() => []),
    staleTime: 5 * 60_000,
  });
  const projects = projectsQ.data ?? [];
  const effectiveProjectId = projectId || projects[0]?.id || '';

  return (
    <div className="space-y-5">
      <Breadcrumb
        items={[{ label: t('carbon.title', { defaultValue: 'Carbon & Sustainability' }) }]}
      />

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">
            {t('carbon.title', { defaultValue: 'Carbon & Sustainability' })}
          </h1>
          <p className="mt-1 text-sm text-content-secondary">
            {t('carbon.subtitle', {
              defaultValue:
                'Embodied + scope 1/2/3 emissions, EPDs, reduction targets and GHG reports.',
            })}
          </p>
        </div>
        <div className="flex gap-2">
          {tab === 'inventory' && (
            <Button
              variant="primary"
              icon={<Plus size={14} />}
              onClick={() => setCreateInvOpen(true)}
              disabled={!effectiveProjectId}
            >
              {t('carbon.new_inventory', { defaultValue: 'New Inventory' })}
            </Button>
          )}
          {tab === 'targets' && (
            <Button
              variant="primary"
              icon={<Plus size={14} />}
              onClick={() => setCreateTargetOpen(true)}
              disabled={!effectiveProjectId}
            >
              {t('carbon.new_target', { defaultValue: 'New Target' })}
            </Button>
          )}
          {tab === 'reports' && (
            <Button
              variant="primary"
              icon={<FileText size={14} />}
              onClick={() => setGenerateReportOpen(true)}
              disabled={!effectiveProjectId}
            >
              {t('carbon.generate_report', { defaultValue: 'Generate Report' })}
            </Button>
          )}
        </div>
      </div>

      {/* Project picker */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[260px] max-w-md flex-1">
          <label className={labelCls}>
            {t('carbon.project', { defaultValue: 'Project' })}
          </label>
          <select
            value={effectiveProjectId}
            onChange={(e) => setProjectId(e.target.value)}
            className={inputCls}
            disabled={projectsQ.isLoading}
          >
            <option value="">
              {projectsQ.isLoading
                ? t('common.loading', { defaultValue: 'Loading…' })
                : t('carbon.select_project', { defaultValue: '— Select project —' })}
            </option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-border-light">
        <nav className="flex gap-1 -mb-px">
          {(
            [
              {
                id: 'inventory',
                label: t('carbon.tab_inventory', { defaultValue: 'Inventory' }),
                icon: Leaf,
              },
              { id: 'epds', label: t('carbon.tab_epds', { defaultValue: 'EPDs' }), icon: Database },
              {
                id: 'targets',
                label: t('carbon.tab_targets', { defaultValue: 'Targets' }),
                icon: Target,
              },
              {
                id: 'reports',
                label: t('carbon.tab_reports', { defaultValue: 'Reports' }),
                icon: FileText,
              },
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

      {!effectiveProjectId && tab !== 'epds' && (
        <EmptyState
          icon={<Leaf size={22} />}
          title={t('carbon.pick_project', { defaultValue: 'Pick a project' })}
          description={t('carbon.pick_project_desc', {
            defaultValue:
              'Carbon inventories, targets and reports are scoped to a single project.',
          })}
        />
      )}

      {tab === 'inventory' && effectiveProjectId && (
        <InventoryTab
          projectId={effectiveProjectId}
          onOpenDrawer={(id) => setInventoryDrawerId(id)}
        />
      )}
      {tab === 'epds' && <EPDsTab />}
      {tab === 'targets' && effectiveProjectId && (
        <TargetsTab projectId={effectiveProjectId} />
      )}
      {tab === 'reports' && effectiveProjectId && (
        <ReportsTab projectId={effectiveProjectId} />
      )}

      {inventoryDrawerId && (
        <InventoryDrawer
          inventoryId={inventoryDrawerId}
          onClose={() => setInventoryDrawerId(null)}
        />
      )}

      {createInvOpen && effectiveProjectId && (
        <CreateInventoryModal
          projectId={effectiveProjectId}
          onClose={() => setCreateInvOpen(false)}
        />
      )}
      {createTargetOpen && effectiveProjectId && (
        <CreateTargetModal
          projectId={effectiveProjectId}
          onClose={() => setCreateTargetOpen(false)}
        />
      )}
      {generateReportOpen && effectiveProjectId && (
        <GenerateReportModal
          projectId={effectiveProjectId}
          onClose={() => setGenerateReportOpen(false)}
        />
      )}
    </div>
  );
}

/* ─── Inventory tab ─── */

function InventoryTab({
  projectId,
  onOpenDrawer,
}: {
  projectId: string;
  onOpenDrawer: (id: string) => void;
}) {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ['carbon', 'inventories', projectId],
    queryFn: () => listInventories(projectId),
  });
  const list = q.data ?? [];

  return (
    <div className="space-y-4">
      <Card padding="none">
        {q.isLoading ? (
          <div className="p-4">
            <SkeletonTable rows={5} columns={5} />
          </div>
        ) : q.isError ? (
          <EmptyState
            icon={<AlertOctagon size={22} />}
            title={t('carbon.load_error', { defaultValue: 'Could not load carbon data' })}
            description={getErrorMessage(q.error)}
            action={{
              label: t('common.retry', { defaultValue: 'Retry' }),
              onClick: () => void q.refetch(),
            }}
          />
        ) : list.length === 0 ? (
          <EmptyState
            icon={<Leaf size={22} />}
            title={t('carbon.empty_inventories', {
              defaultValue: 'No carbon inventories yet',
            })}
            description={t('carbon.empty_inventories_desc', {
              defaultValue:
                'Create an inventory to track embodied + scope 1/2/3 emissions for this project.',
            })}
          />
        ) : (
          <InventoryTable rows={list} onSelect={onOpenDrawer} />
        )}
      </Card>
    </div>
  );
}

function InventoryTable({
  rows,
  onSelect,
}: {
  rows: CarbonInventory[];
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_name', { defaultValue: 'Inventory' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_scope', { defaultValue: 'Scope' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_status', { defaultValue: 'Status' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_as_of', { defaultValue: 'As of' })}
            </th>
            <th className="px-4 py-2.5 text-right">
              {t('carbon.col_total', { defaultValue: 'Total' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const total = toNum(
              (r.totals as Record<string, unknown>)['total'] as
                | number
                | string
                | null
                | undefined,
            );
            return (
              <tr
                key={r.id}
                onClick={() => onSelect(r.id)}
                className="border-t border-border-light hover:bg-surface-secondary cursor-pointer"
              >
                <td className="px-4 py-2 font-medium text-content-primary">{r.name}</td>
                <td className="px-4 py-2 text-xs text-content-secondary">{r.scope}</td>
                <td className="px-4 py-2">
                  <Badge
                    variant={
                      r.status === 'baseline'
                        ? 'blue'
                        : r.status === 'current'
                          ? 'success'
                          : r.status === 'archived'
                            ? 'neutral'
                            : 'warning'
                    }
                    dot
                    size="sm"
                  >
                    {r.status}
                  </Badge>
                </td>
                <td className="px-4 py-2 text-xs text-content-secondary">
                  {r.as_of_date ? <DateDisplay value={r.as_of_date} /> : '—'}
                </td>
                <td className="px-4 py-2 text-right tabular-nums font-medium">
                  {total > 0 ? formatKg(total) : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ─── EPDs tab ─── */

function EPDsTab() {
  const { t } = useTranslation();
  const [materialClass, setMaterialClass] = useState('');
  const [region, setRegion] = useState('');
  const q = useQuery({
    queryKey: ['carbon', 'epds', materialClass, region],
    queryFn: () =>
      listEPDs({
        material_class: materialClass || undefined,
        region: region || undefined,
        limit: 200,
      }),
  });
  const list: EPDRecord[] = q.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <div className="max-w-[220px]">
          <label className={labelCls}>
            {t('carbon.material_class', { defaultValue: 'Material class' })}
          </label>
          <input
            value={materialClass}
            onChange={(e) => setMaterialClass(e.target.value)}
            placeholder="concrete, steel…"
            className={inputCls}
          />
        </div>
        <div className="max-w-[140px]">
          <label className={labelCls}>
            {t('carbon.region', { defaultValue: 'Region' })}
          </label>
          <input
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="DE, EU…"
            maxLength={8}
            className={inputCls}
          />
        </div>
      </div>
      <Card padding="none">
        {q.isLoading ? (
          <div className="p-4">
            <SkeletonTable rows={8} columns={5} />
          </div>
        ) : q.isError ? (
          <EmptyState
            icon={<AlertOctagon size={22} />}
            title={t('carbon.load_error', { defaultValue: 'Could not load carbon data' })}
            description={getErrorMessage(q.error)}
            action={{
              label: t('common.retry', { defaultValue: 'Retry' }),
              onClick: () => void q.refetch(),
            }}
          />
        ) : list.length === 0 ? (
          <EmptyState
            icon={<Database size={22} />}
            title={t('carbon.empty_epds', { defaultValue: 'No EPDs match these filters' })}
            description={t('carbon.empty_epds_desc', {
              defaultValue:
                'Try broadening the material class or region. EPDs are sourced from Ökobaudat, ICE, EC3 and custom uploads.',
            })}
          />
        ) : (
          <EPDTable rows={list} />
        )}
      </Card>
    </div>
  );
}

function EPDTable({ rows }: { rows: EPDRecord[] }) {
  const { t } = useTranslation();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_product', { defaultValue: 'Product' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_class', { defaultValue: 'Class' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_region', { defaultValue: 'Region' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_source', { defaultValue: 'Source' })}
            </th>
            <th className="px-4 py-2.5 text-right">
              {t('carbon.col_gwp', { defaultValue: 'GWP A1–A3' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_unit', { defaultValue: 'Unit' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-border-light hover:bg-surface-secondary">
              <td className="px-4 py-2 font-medium text-content-primary truncate max-w-[260px]">
                {r.product_name}
              </td>
              <td className="px-4 py-2 text-xs text-content-secondary">{r.material_class}</td>
              <td className="px-4 py-2 text-xs text-content-secondary">{r.region || '—'}</td>
              <td className="px-4 py-2 text-xs">
                <Badge variant="neutral" size="sm">
                  {r.source}
                </Badge>
              </td>
              <td className="px-4 py-2 text-right tabular-nums font-medium">
                {toNum(r.gwp_a1a3).toFixed(3)}
              </td>
              <td className="px-4 py-2 text-xs text-content-tertiary">kg/{r.declared_unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ─── Targets tab ─── */

function TargetsTab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ['carbon', 'targets', projectId],
    queryFn: () => listTargets(projectId),
  });
  const list = q.data ?? [];

  return (
    <Card padding="none">
      {q.isLoading ? (
        <div className="p-4">
          <SkeletonTable rows={4} columns={4} />
        </div>
      ) : q.isError ? (
        <EmptyState
          icon={<AlertOctagon size={22} />}
          title={t('carbon.load_error', { defaultValue: 'Could not load carbon data' })}
          description={getErrorMessage(q.error)}
          action={{
            label: t('common.retry', { defaultValue: 'Retry' }),
            onClick: () => void q.refetch(),
          }}
        />
      ) : list.length === 0 ? (
        <EmptyState
          icon={<Target size={22} />}
          title={t('carbon.empty_targets', { defaultValue: 'No targets set' })}
          description={t('carbon.empty_targets_desc', {
            defaultValue:
              'Define a reduction target (absolute or per m²) to track progress against a baseline year.',
          })}
        />
      ) : (
        <ul className="divide-y divide-border-light">
          {list.map((target) => (
            <TargetRow key={target.id} target={target} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function TargetRow({ target }: { target: CarbonTarget }) {
  const { t } = useTranslation();
  const progressQ = useQuery({
    queryKey: ['carbon', 'target-progress', target.id],
    queryFn: () => getTargetProgress(target.id),
    staleTime: 30_000,
  });
  const p = progressQ.data;
  const pct = p ? Math.max(0, Math.min(100, p.progress_pct)) : 0;
  const met = p?.met ?? target.status === 'met';

  return (
    <li className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-content-primary">
            {target.name || `${target.target_type} ${target.target_year}`}
          </p>
          <p className="mt-0.5 text-xs text-content-secondary">
            {target.baseline_year} → {target.target_year} ·{' '}
            {target.target_type.replace('_', ' ')}
          </p>
        </div>
        <Badge
          variant={
            met
              ? 'success'
              : target.status === 'missed'
                ? 'error'
                : target.status === 'abandoned'
                  ? 'neutral'
                  : 'blue'
          }
          dot
          size="sm"
        >
          {target.status}
        </Badge>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3 text-xs">
        <div>
          <p className="text-content-tertiary uppercase tracking-wide">
            {t('carbon.baseline', { defaultValue: 'Baseline' })}
          </p>
          <p className="font-medium tabular-nums">
            {toNum(target.baseline_value).toFixed(0)}
          </p>
        </div>
        <div>
          <p className="text-content-tertiary uppercase tracking-wide">
            {t('carbon.current', { defaultValue: 'Current' })}
          </p>
          <p className="font-medium tabular-nums">
            {p ? toNum(p.current_value).toFixed(0) : '—'}
          </p>
        </div>
        <div>
          <p className="text-content-tertiary uppercase tracking-wide">
            {t('carbon.target_label', { defaultValue: 'Target' })}
          </p>
          <p className="font-medium tabular-nums">
            {toNum(target.target_value).toFixed(0)}
          </p>
        </div>
      </div>
      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-surface-secondary">
        <div
          className={clsx(
            'h-full rounded-full transition-all',
            met ? 'bg-semantic-success' : 'bg-oe-blue',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1 text-xs text-content-tertiary tabular-nums">
        {pct.toFixed(0)}%
        {met && (
          <span className="ms-1 inline-flex items-center gap-0.5 text-semantic-success">
            <CheckCircle2 size={11} />
            {t('carbon.met', { defaultValue: 'Met' })}
          </span>
        )}
      </p>
    </li>
  );
}

/* ─── Reports tab ─── */

function ReportsTab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ['carbon', 'reports', projectId],
    queryFn: () => listReports(projectId),
  });
  const list = q.data ?? [];

  return (
    <Card padding="none">
      {q.isLoading ? (
        <div className="p-4">
          <SkeletonTable rows={5} columns={4} />
        </div>
      ) : q.isError ? (
        <EmptyState
          icon={<AlertOctagon size={22} />}
          title={t('carbon.load_error', { defaultValue: 'Could not load carbon data' })}
          description={getErrorMessage(q.error)}
          action={{
            label: t('common.retry', { defaultValue: 'Retry' }),
            onClick: () => void q.refetch(),
          }}
        />
      ) : list.length === 0 ? (
        <EmptyState
          icon={<FileText size={22} />}
          title={t('carbon.empty_reports', { defaultValue: 'No sustainability reports yet' })}
          description={t('carbon.empty_reports_desc', {
            defaultValue:
              'Generate a GHG Protocol, GRI or ISSB report from the project’s current inventory.',
          })}
        />
      ) : (
        <ReportTable rows={list} />
      )}
    </Card>
  );
}

function ReportTable({ rows }: { rows: SustainabilityReport[] }) {
  const { t } = useTranslation();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_period', { defaultValue: 'Period' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_framework', { defaultValue: 'Framework' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('carbon.col_generated', { defaultValue: 'Generated' })}
            </th>
            <th className="px-4 py-2.5 text-right">
              {t('carbon.col_total', { defaultValue: 'Total kg CO2e' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const total = toNum(
              (r.totals as Record<string, unknown>)['total'] as
                | number
                | string
                | null
                | undefined,
            );
            return (
              <tr key={r.id} className="border-t border-border-light hover:bg-surface-secondary">
                <td className="px-4 py-2 text-xs text-content-secondary">
                  {r.period_start} → {r.period_end}
                </td>
                <td className="px-4 py-2">
                  <Badge variant="blue" size="sm">
                    {r.framework}
                  </Badge>
                </td>
                <td className="px-4 py-2 text-xs text-content-secondary">
                  {r.generated_at ? <DateDisplay value={r.generated_at} /> : '—'}
                </td>
                <td className="px-4 py-2 text-right tabular-nums font-medium">
                  {total > 0 ? formatKg(total) : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ─── Inventory drawer ─── */

function InventoryDrawer({
  inventoryId,
  onClose,
}: {
  inventoryId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  useEscapeToClose(onClose);

  const totalsQ = useQuery({
    queryKey: ['carbon', 'totals', inventoryId],
    queryFn: () => getInventoryTotals(inventoryId),
  });
  const embodiedQ = useQuery({
    queryKey: ['carbon', 'embodied', inventoryId],
    queryFn: () => listEmbodiedEntries(inventoryId, { limit: 200 }),
  });
  const s1Q = useQuery({
    queryKey: ['carbon', 's1', inventoryId],
    queryFn: () => listScope1(inventoryId).catch(() => []),
  });
  const s2Q = useQuery({
    queryKey: ['carbon', 's2', inventoryId],
    queryFn: () => listScope2(inventoryId).catch(() => []),
  });
  const s3Q = useQuery({
    queryKey: ['carbon', 's3', inventoryId],
    queryFn: () => listScope3(inventoryId).catch(() => []),
  });

  const totals = totalsQ.data;
  const scope1Kg = totals ? toNum(totals.scope1) : 0;
  const scope2Kg = totals ? toNum(totals.scope2) : 0;
  const scope3Kg = totals ? toNum(totals.scope3) : 0;
  const scopeTotal = scope1Kg + scope2Kg + scope3Kg;

  // Top emitters from embodied entries
  const topEmitters = useMemo(() => {
    const items = embodiedQ.data ?? [];
    return [...items]
      .sort((a, b) => toNum(b.carbon_kg) - toNum(a.carbon_kg))
      .slice(0, 8);
  }, [embodiedQ.data]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="carbon-inv-drawer-title"
        className="relative h-full w-full max-w-2xl overflow-y-auto bg-surface-elevated shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-light bg-surface-elevated px-5 py-3">
          <h2 id="carbon-inv-drawer-title" className="text-base font-semibold">
            {t('carbon.inventory_detail', { defaultValue: 'Inventory detail' })}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 hover:bg-surface-secondary"
            aria-label={t('common.close', { defaultValue: 'Close' })}
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-5 p-5">
          {totalsQ.isLoading ? (
            <SkeletonTable rows={3} columns={2} />
          ) : totalsQ.isError ? (
            <EmptyState
              icon={<AlertOctagon size={22} />}
              title={t('carbon.load_error', {
                defaultValue: 'Could not load carbon data',
              })}
              description={getErrorMessage(totalsQ.error)}
              action={{
                label: t('common.retry', { defaultValue: 'Retry' }),
                onClick: () => void totalsQ.refetch(),
              }}
            />
          ) : (
            totals && (
              <>
                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-content-tertiary">
                    {t('carbon.scope_breakdown', { defaultValue: 'Scope 1 / 2 / 3 breakdown' })}
                  </h3>
                  <ScopeBar
                    scope1={scope1Kg}
                    scope2={scope2Kg}
                    scope3={scope3Kg}
                  />
                  <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                    <ScopeKpi
                      label="Scope 1"
                      kg={scope1Kg}
                      pct={scopeTotal > 0 ? (scope1Kg / scopeTotal) * 100 : 0}
                      color="bg-oe-blue"
                    />
                    <ScopeKpi
                      label="Scope 2"
                      kg={scope2Kg}
                      pct={scopeTotal > 0 ? (scope2Kg / scopeTotal) * 100 : 0}
                      color="bg-emerald-500"
                    />
                    <ScopeKpi
                      label="Scope 3"
                      kg={scope3Kg}
                      pct={scopeTotal > 0 ? (scope3Kg / scopeTotal) * 100 : 0}
                      color="bg-amber-500"
                    />
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-content-secondary">
                    <span>
                      {s1Q.data?.length ?? 0}{' '}
                      {t('carbon.entries', { defaultValue: 'entries' })}
                    </span>
                    <span>
                      {s2Q.data?.length ?? 0}{' '}
                      {t('carbon.entries', { defaultValue: 'entries' })}
                    </span>
                    <span>
                      {s3Q.data?.length ?? 0}{' '}
                      {t('carbon.entries', { defaultValue: 'entries' })}
                    </span>
                  </div>
                </div>

                <div>
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-content-tertiary">
                    <TrendingDown size={12} />
                    {t('carbon.embodied_lifecycle', { defaultValue: 'Embodied (A1–D)' })}
                  </h3>
                  <div className="grid grid-cols-4 gap-2 text-xs">
                    <StageTile label="A1–A3" kg={toNum(totals.embodied_a1a3)} />
                    <StageTile label="A4" kg={toNum(totals.embodied_a4)} />
                    <StageTile label="A5" kg={toNum(totals.embodied_a5)} />
                    <StageTile label="B" kg={toNum(totals.embodied_b)} />
                    <StageTile label="C" kg={toNum(totals.embodied_c)} />
                    <StageTile label="D" kg={toNum(totals.embodied_d)} />
                  </div>
                </div>

                <div>
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-content-tertiary">
                    <AlertTriangle size={12} />
                    {t('carbon.top_emitters', { defaultValue: 'Top emitters' })}
                  </h3>
                  {topEmitters.length === 0 ? (
                    <p className="rounded-md bg-surface-secondary/60 p-3 text-xs text-content-tertiary">
                      {t('carbon.no_entries', {
                        defaultValue: 'No embodied entries yet.',
                      })}
                    </p>
                  ) : (
                    <ul className="divide-y divide-border-light rounded border border-border-light text-sm">
                      {topEmitters.map((e) => (
                        <li
                          key={e.id}
                          className="flex items-center justify-between px-3 py-2"
                        >
                          <span className="truncate max-w-[60%] text-content-primary">
                            {e.description || e.element_ref || '—'}
                          </span>
                          <span className="font-medium tabular-nums">
                            {formatKg(toNum(e.carbon_kg))}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-content-tertiary">
                    {t('carbon.alternative_materials', {
                      defaultValue: 'Alternative materials',
                    })}
                  </h3>
                  <div className="rounded-md border border-dashed border-border-light bg-surface-secondary/40 p-3 text-xs text-content-tertiary">
                    {t('carbon.alternatives_placeholder', {
                      defaultValue:
                        'Click an embodied entry to compare lower-carbon alternatives. Side-by-side comparison coming soon.',
                    })}
                  </div>
                </div>
              </>
            )
          )}
        </div>
      </div>
    </div>
  );
}

function ScopeBar({
  scope1,
  scope2,
  scope3,
}: {
  scope1: number;
  scope2: number;
  scope3: number;
}) {
  const total = scope1 + scope2 + scope3;
  if (total <= 0) {
    return (
      <div className="h-4 w-full rounded-full bg-surface-secondary" aria-label="empty" />
    );
  }
  const p1 = (scope1 / total) * 100;
  const p2 = (scope2 / total) * 100;
  const p3 = (scope3 / total) * 100;
  return (
    <div className="flex h-4 w-full overflow-hidden rounded-full bg-surface-secondary">
      <div className="bg-oe-blue" style={{ width: `${p1}%` }} title={`Scope 1: ${formatKg(scope1)}`} />
      <div
        className="bg-emerald-500"
        style={{ width: `${p2}%` }}
        title={`Scope 2: ${formatKg(scope2)}`}
      />
      <div
        className="bg-amber-500"
        style={{ width: `${p3}%` }}
        title={`Scope 3: ${formatKg(scope3)}`}
      />
    </div>
  );
}

function ScopeKpi({
  label,
  kg,
  pct,
  color,
}: {
  label: string;
  kg: number;
  pct: number;
  color: string;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5">
        <span className={clsx('inline-block h-2 w-2 rounded-full', color)} />
        <span className="text-xs uppercase tracking-wide text-content-tertiary">
          {label}
        </span>
      </div>
      <p className="mt-0.5 text-sm font-medium tabular-nums">{formatKg(kg)}</p>
      <p className="text-xs text-content-tertiary tabular-nums">{pct.toFixed(0)}%</p>
    </div>
  );
}

function StageTile({ label, kg }: { label: string; kg: number }) {
  return (
    <div className="rounded-md border border-border-light p-2">
      <p className="text-xs uppercase tracking-wide text-content-tertiary">{label}</p>
      <p className="mt-0.5 font-medium tabular-nums">{formatKg(kg)}</p>
    </div>
  );
}

/* ─── Modals ─── */

function CreateInventoryModal({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    name: 'Baseline inventory',
    scope: 'cradle_to_gate' as 'cradle_to_gate' | 'cradle_to_grave' | 'operational',
    as_of_date: todayIso(),
  });

  async function submit() {
    setBusy(true);
    try {
      await createInventory({
        project_id: projectId,
        name: form.name,
        scope: form.scope,
        as_of_date: form.as_of_date,
      });
      addToast({
        type: 'success',
        title: t('carbon.inv_created', { defaultValue: 'Inventory created' }),
      });
      qc.invalidateQueries({ queryKey: ['carbon', 'inventories', projectId] });
      onClose();
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <ModalShell
      title={t('carbon.new_inventory', { defaultValue: 'New Inventory' })}
      onClose={onClose}
    >
      <div className="space-y-3">
        <div>
          <label className={labelCls}>
            {t('carbon.name', { defaultValue: 'Name' })}
          </label>
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className={inputCls}
          />
        </div>
        <div>
          <label className={labelCls}>
            {t('carbon.col_scope', { defaultValue: 'Scope' })}
          </label>
          <select
            value={form.scope}
            onChange={(e) =>
              setForm({
                ...form,
                scope: e.target.value as
                  | 'cradle_to_gate'
                  | 'cradle_to_grave'
                  | 'operational',
              })
            }
            className={inputCls}
          >
            <option value="cradle_to_gate">cradle_to_gate</option>
            <option value="cradle_to_grave">cradle_to_grave</option>
            <option value="operational">operational</option>
          </select>
        </div>
        <div>
          <label className={labelCls}>
            {t('carbon.col_as_of', { defaultValue: 'As of' })}
          </label>
          <input
            type="date"
            value={form.as_of_date}
            onChange={(e) => setForm({ ...form, as_of_date: e.target.value })}
            className={inputCls}
          />
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-5">
        <Button variant="ghost" onClick={onClose}>
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
      </div>
    </ModalShell>
  );
}

function CreateTargetModal({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    name: '',
    target_type: 'absolute' as 'absolute' | 'intensity_per_m2' | 'intensity_per_unit',
    baseline_value: '0',
    target_value: '0',
    baseline_year: 2020,
    target_year: 2030,
  });

  async function submit() {
    setBusy(true);
    try {
      await createTarget({
        project_id: projectId,
        name: form.name,
        target_type: form.target_type,
        baseline_value: Number(form.baseline_value) || 0,
        target_value: Number(form.target_value) || 0,
        baseline_year: form.baseline_year,
        target_year: form.target_year,
      });
      addToast({
        type: 'success',
        title: t('carbon.target_created', { defaultValue: 'Target created' }),
      });
      qc.invalidateQueries({ queryKey: ['carbon', 'targets', projectId] });
      onClose();
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <ModalShell
      title={t('carbon.new_target', { defaultValue: 'New Target' })}
      onClose={onClose}
    >
      <div className="space-y-3">
        <div>
          <label className={labelCls}>
            {t('carbon.name', { defaultValue: 'Name' })}
          </label>
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className={inputCls}
            placeholder="e.g. Net-zero by 2030"
          />
        </div>
        <div>
          <label className={labelCls}>
            {t('carbon.target_type', { defaultValue: 'Type' })}
          </label>
          <select
            value={form.target_type}
            onChange={(e) =>
              setForm({
                ...form,
                target_type: e.target.value as
                  | 'absolute'
                  | 'intensity_per_m2'
                  | 'intensity_per_unit',
              })
            }
            className={inputCls}
          >
            <option value="absolute">absolute (kg CO2e)</option>
            <option value="intensity_per_m2">intensity per m²</option>
            <option value="intensity_per_unit">intensity per unit</option>
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>
              {t('carbon.baseline', { defaultValue: 'Baseline' })}
            </label>
            <input
              type="number"
              value={form.baseline_value}
              onChange={(e) => setForm({ ...form, baseline_value: e.target.value })}
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>
              {t('carbon.target_label', { defaultValue: 'Target' })}
            </label>
            <input
              type="number"
              value={form.target_value}
              onChange={(e) => setForm({ ...form, target_value: e.target.value })}
              className={inputCls}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>
              {t('carbon.baseline_year', { defaultValue: 'Baseline year' })}
            </label>
            <input
              type="number"
              value={form.baseline_year}
              onChange={(e) =>
                setForm({ ...form, baseline_year: Number(e.target.value) || 2020 })
              }
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>
              {t('carbon.target_year', { defaultValue: 'Target year' })}
            </label>
            <input
              type="number"
              value={form.target_year}
              onChange={(e) =>
                setForm({ ...form, target_year: Number(e.target.value) || 2030 })
              }
              className={inputCls}
            />
          </div>
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-5">
        <Button variant="ghost" onClick={onClose}>
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
      </div>
    </ModalShell>
  );
}

function GenerateReportModal({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [busy, setBusy] = useState(false);

  const inventoriesQ = useQuery({
    queryKey: ['carbon', 'inventories', projectId],
    queryFn: () => listInventories(projectId).catch(() => []),
  });
  const inventories: CarbonInventory[] = inventoriesQ.data ?? [];

  const [form, setForm] = useState({
    inventory_id: '',
    period_start: todayIso(-365),
    period_end: todayIso(),
    framework: 'ghg_protocol' as 'ghg_protocol' | 'gri' | 'issb' | 'custom',
    project_area_m2: '',
  });

  const generateMut = useMutation({
    mutationFn: () =>
      generateReport({
        project_id: projectId,
        inventory_id: form.inventory_id || null,
        period_start: form.period_start,
        period_end: form.period_end,
        framework: form.framework,
        project_area_m2: form.project_area_m2 ? Number(form.project_area_m2) : undefined,
      }),
    onSuccess: () => {
      addToast({
        type: 'success',
        title: t('carbon.report_generated', { defaultValue: 'Report generated' }),
      });
      qc.invalidateQueries({ queryKey: ['carbon', 'reports', projectId] });
      onClose();
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
    onSettled: () => setBusy(false),
  });

  return (
    <ModalShell
      title={t('carbon.generate_report', { defaultValue: 'Generate Report' })}
      onClose={onClose}
    >
      <div className="space-y-3">
        <div>
          <label className={labelCls}>
            {t('carbon.inventory', { defaultValue: 'Inventory' })}
          </label>
          <select
            value={form.inventory_id}
            onChange={(e) => setForm({ ...form, inventory_id: e.target.value })}
            className={inputCls}
          >
            <option value="">
              — {t('carbon.optional', { defaultValue: 'optional' })} —
            </option>
            {inventories.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelCls}>
            {t('carbon.col_framework', { defaultValue: 'Framework' })}
          </label>
          <select
            value={form.framework}
            onChange={(e) =>
              setForm({
                ...form,
                framework: e.target.value as 'ghg_protocol' | 'gri' | 'issb' | 'custom',
              })
            }
            className={inputCls}
          >
            <option value="ghg_protocol">GHG Protocol</option>
            <option value="gri">GRI</option>
            <option value="issb">ISSB</option>
            <option value="custom">custom</option>
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>
              {t('carbon.period_start', { defaultValue: 'Period start' })}
            </label>
            <input
              type="date"
              value={form.period_start}
              onChange={(e) => setForm({ ...form, period_start: e.target.value })}
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>
              {t('carbon.period_end', { defaultValue: 'Period end' })}
            </label>
            <input
              type="date"
              value={form.period_end}
              onChange={(e) => setForm({ ...form, period_end: e.target.value })}
              className={inputCls}
            />
          </div>
        </div>
        <div>
          <label className={labelCls}>
            {t('carbon.area_m2', { defaultValue: 'Project area (m²) — optional' })}
          </label>
          <input
            type="number"
            value={form.project_area_m2}
            onChange={(e) => setForm({ ...form, project_area_m2: e.target.value })}
            className={inputCls}
          />
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-5">
        <Button variant="ghost" onClick={onClose}>
          {t('common.cancel', { defaultValue: 'Cancel' })}
        </Button>
        <Button
          variant="primary"
          onClick={() => {
            setBusy(true);
            generateMut.mutate();
          }}
          loading={busy}
          icon={busy ? <Loader2 size={14} /> : <FileText size={14} />}
        >
          {t('carbon.generate', { defaultValue: 'Generate' })}
        </Button>
      </div>
    </ModalShell>
  );
}

function ModalShell({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  useEscapeToClose(onClose);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="carbon-modal-title"
        className="relative w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-xl bg-surface-elevated p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 id="carbon-modal-title" className="text-lg font-semibold">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 hover:bg-surface-secondary"
            aria-label={t('common.close', { defaultValue: 'Close' })}
          >
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
