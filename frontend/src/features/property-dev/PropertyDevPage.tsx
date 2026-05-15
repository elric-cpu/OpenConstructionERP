import { useState, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  Building2,
  Grid3X3,
  Home,
  Users,
  Key,
  ShieldAlert,
  Plus,
  X,
  Search,
  Loader2,
  Check,
  Clock,
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
import {
  WideModal,
  WideModalSection,
  WideModalField,
} from '@/shared/ui/WideModal';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { useToastStore } from '@/stores/useToastStore';
import { usePreferencesStore } from '@/stores/usePreferencesStore';
import { getErrorMessage } from '@/shared/lib/api';
import {
  listDevelopments,
  createDevelopment,
  getDevelopmentDashboard,
  listPlots,
  createPlot,
  reservePlot,
  listHouseTypes,
  createHouseType,
  listVariants,
  listBuyers,
  createBuyer,
  contractBuyer,
  listSelections,
  listHandovers,
  listWarrantyClaims,
  acceptWarrantyClaim,
  rejectWarrantyClaim,
  closeWarrantyClaim,
  type Buyer,
  type BuyerStatus,
  type Development,
  type Handover,
  type HouseType,
  type Plot,
  type PlotStatus,
  type WarrantyClaim,
  type WarrantyStatus,
} from './api';

type Tab = 'developments' | 'plots' | 'house_types' | 'buyers' | 'handovers' | 'warranty';

const PLOT_STATUS_VARIANT: Record<PlotStatus, 'neutral' | 'blue' | 'success' | 'warning' | 'error'> = {
  planned: 'neutral',
  reserved: 'warning',
  under_construction: 'blue',
  ready: 'blue',
  sold: 'success',
  handed_over: 'success',
};

const PLOT_STATUS_COLOR: Record<PlotStatus, string> = {
  planned: 'bg-slate-200 text-slate-700 border-slate-300',
  reserved: 'bg-amber-100 text-amber-800 border-amber-300',
  under_construction: 'bg-sky-100 text-sky-800 border-sky-300',
  ready: 'bg-indigo-100 text-indigo-800 border-indigo-300',
  sold: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  handed_over: 'bg-emerald-200 text-emerald-900 border-emerald-400',
};

const BUYER_STAGE_ORDER: BuyerStatus[] = ['lead', 'reserved', 'contracted', 'completed'];
const BUYER_VARIANT: Record<BuyerStatus, 'neutral' | 'blue' | 'success' | 'warning' | 'error'> = {
  lead: 'neutral',
  reserved: 'warning',
  contracted: 'blue',
  completed: 'success',
  cancelled: 'error',
};

const WARRANTY_VARIANT: Record<WarrantyStatus, 'neutral' | 'blue' | 'success' | 'warning' | 'error'> = {
  raised: 'warning',
  under_review: 'blue',
  accepted: 'success',
  rejected: 'error',
  closed: 'neutral',
};

const inputCls =
  'h-9 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';
// labelCls is still used by a couple of small inline modals (e.g.
// BuyerContract date-pair) that were not migrated to WideModal because
// they're tiny confirmation panels rather than full forms.
const labelCls = 'block text-xs font-medium text-content-secondary mb-1';

/* ─── helpers ─── */

function toNumber(v: number | string | null | undefined): number {
  if (v == null) return 0;
  if (typeof v === 'number') return v;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function todayIso(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const target = new Date(iso);
  if (Number.isNaN(target.getTime())) return null;
  const now = new Date();
  const diff = (target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  return Math.ceil(diff);
}

/* ─── Page ─── */

export function PropertyDevPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('developments');
  const [selectedDevId, setSelectedDevId] = useState<string>('');
  const [search, setSearch] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [activePlotId, setActivePlotId] = useState<string | null>(null);
  const [activeBuyerId, setActiveBuyerId] = useState<string | null>(null);

  const developmentsQ = useQuery({
    queryKey: ['propdev', 'developments'],
    queryFn: () => listDevelopments({ limit: 100 }),
  });
  const developments = developmentsQ.data ?? [];

  useEffect(() => {
    if (!selectedDevId && developments.length > 0) {
      const first = developments[0];
      if (first) setSelectedDevId(first.id);
    }
  }, [developments, selectedDevId]);

  const plotsQ = useQuery({
    queryKey: ['propdev', 'plots', selectedDevId],
    queryFn: () => listPlots({ development_id: selectedDevId, limit: 500 }),
    enabled: !!selectedDevId && (tab === 'plots' || tab === 'developments'),
  });
  const houseTypesQ = useQuery({
    queryKey: ['propdev', 'house-types', selectedDevId],
    queryFn: () => listHouseTypes(selectedDevId),
    enabled: !!selectedDevId && (tab === 'house_types' || tab === 'plots'),
  });
  const buyersQ = useQuery({
    queryKey: ['propdev', 'buyers', selectedDevId],
    queryFn: () => listBuyers({ development_id: selectedDevId, limit: 500 }),
    enabled: !!selectedDevId && (tab === 'buyers' || tab === 'handovers' || tab === 'warranty'),
  });

  const allPlots = plotsQ.data ?? [];
  const allBuyers = buyersQ.data ?? [];

  const filteredBuyers = useMemo(() => {
    const s = search.toLowerCase();
    if (!s) return allBuyers;
    return allBuyers.filter(
      (b) =>
        (b.full_name || '').toLowerCase().includes(s) ||
        (b.email || '').toLowerCase().includes(s),
    );
  }, [allBuyers, search]);

  const isLoading =
    developmentsQ.isLoading ||
    (tab === 'plots' && plotsQ.isLoading) ||
    (tab === 'house_types' && houseTypesQ.isLoading) ||
    (tab === 'buyers' && buyersQ.isLoading);

  // A failed list query must NOT fall through to the "nothing here yet"
  // empty state — that hides real backend/permission failures behind a
  // success-looking screen. Surface it with a retry instead.
  const activeQuery =
    tab === 'plots'
      ? plotsQ
      : tab === 'house_types'
        ? houseTypesQ
        : tab === 'buyers' || tab === 'handovers' || tab === 'warranty'
          ? buyersQ
          : developmentsQ;
  const loadError =
    developmentsQ.isError
      ? developmentsQ.error
      : activeQuery.isError
        ? activeQuery.error
        : null;

  return (
    <div className="space-y-5">
      <Breadcrumb
        items={[
          { label: t('propdev.title', { defaultValue: 'Property Development' }) },
        ]}
      />

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">
            {t('propdev.title', { defaultValue: 'Property Development' })}
          </h1>
          <p className="mt-1 text-sm text-content-secondary">
            {t('propdev.subtitle', {
              defaultValue:
                'Developments, plots, buyer journeys, handovers and warranty claims.',
            })}
          </p>
        </div>
        <Button
          variant="primary"
          icon={<Plus size={14} />}
          onClick={() => setCreateOpen(true)}
        >
          {tab === 'developments'
            ? t('propdev.new_development', { defaultValue: 'New Development' })
            : tab === 'plots'
              ? t('propdev.new_plot', { defaultValue: 'New Plot' })
              : tab === 'house_types'
                ? t('propdev.new_house_type', { defaultValue: 'New House Type' })
                : tab === 'buyers'
                  ? t('propdev.new_buyer', { defaultValue: 'New Buyer' })
                  : t('common.create', { defaultValue: 'Create' })}
        </Button>
      </div>

      {/* Tabs */}
      <div className="border-b border-border-light">
        <nav className="flex gap-1 -mb-px overflow-x-auto">
          {(
            [
              { id: 'developments', label: t('propdev.developments', { defaultValue: 'Developments' }), icon: Building2 },
              { id: 'plots', label: t('propdev.plots', { defaultValue: 'Plots' }), icon: Grid3X3 },
              { id: 'house_types', label: t('propdev.house_types', { defaultValue: 'House Types' }), icon: Home },
              { id: 'buyers', label: t('propdev.buyers', { defaultValue: 'Buyers' }), icon: Users },
              { id: 'handovers', label: t('propdev.handovers', { defaultValue: 'Handovers' }), icon: Key },
              { id: 'warranty', label: t('propdev.warranty', { defaultValue: 'Warranty Claims' }), icon: ShieldAlert },
            ] as { id: Tab; label: string; icon: React.ElementType }[]
          ).map((tabItem) => {
            const Icon = tabItem.icon;
            return (
              <button
                key={tabItem.id}
                type="button"
                onClick={() => {
                  setTab(tabItem.id);
                  setSearch('');
                }}
                className={clsx(
                  'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
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

      {/* Filters */}
      {tab !== 'developments' && developments.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={selectedDevId}
            onChange={(e) => setSelectedDevId(e.target.value)}
            className={clsx(inputCls, 'max-w-[320px]')}
          >
            {developments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.code} — {d.name || t('propdev.untitled', { defaultValue: 'Untitled' })}
              </option>
            ))}
          </select>
          {tab === 'buyers' && (
            <div className="relative flex-1 min-w-[200px] max-w-md">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-content-tertiary"
              />
              <input
                type="text"
                placeholder={t('common.search', { defaultValue: 'Search…' })}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className={clsx(inputCls, 'pl-8')}
              />
            </div>
          )}
        </div>
      )}

      {/* Body */}
      {isLoading ? (
        <Card padding="md"><SkeletonTable rows={6} columns={4} /></Card>
      ) : loadError ? (
        <Card padding="md">
          <EmptyState
            icon={<AlertOctagon size={22} />}
            title={t('propdev.load_error', {
              defaultValue: 'Could not load property data',
            })}
            description={getErrorMessage(loadError)}
            action={{
              label: t('common.retry', { defaultValue: 'Retry' }),
              onClick: () => {
                developmentsQ.refetch();
                activeQuery.refetch();
              },
            }}
          />
        </Card>
      ) : tab === 'developments' ? (
        <DevelopmentsGrid
          rows={developments}
          onSelect={(id) => {
            setSelectedDevId(id);
            setTab('plots');
          }}
          onCreate={() => setCreateOpen(true)}
        />
      ) : tab === 'plots' ? (
        <PlotsTab
          plots={allPlots}
          houseTypes={houseTypesQ.data ?? []}
          onSelect={(id) => setActivePlotId(id)}
          onCreate={() => setCreateOpen(true)}
        />
      ) : tab === 'house_types' ? (
        <HouseTypesTab
          rows={houseTypesQ.data ?? []}
          onCreate={() => setCreateOpen(true)}
        />
      ) : tab === 'buyers' ? (
        <BuyersTab
          rows={filteredBuyers}
          onSelect={(id) => setActiveBuyerId(id)}
          onCreate={() => setCreateOpen(true)}
        />
      ) : tab === 'handovers' ? (
        <HandoversTab plots={allPlots} buyers={allBuyers} />
      ) : (
        <WarrantyTab buyers={allBuyers} plots={allPlots} />
      )}

      {/* Plot detail */}
      {activePlotId && (
        <PlotDetailDrawer
          plotId={activePlotId}
          plots={allPlots}
          houseTypes={houseTypesQ.data ?? []}
          onClose={() => setActivePlotId(null)}
        />
      )}

      {/* Buyer detail */}
      {activeBuyerId && (
        <BuyerDetailDrawer
          buyerId={activeBuyerId}
          buyers={allBuyers}
          plots={allPlots}
          onClose={() => setActiveBuyerId(null)}
        />
      )}

      {/* Create modal */}
      {createOpen && (
        <CreateModal
          kind={tab}
          developmentId={selectedDevId}
          developments={developments}
          houseTypes={houseTypesQ.data ?? []}
          onClose={() => setCreateOpen(false)}
        />
      )}
    </div>
  );
}

/* ─── Developments grid ─── */

function DevelopmentsGrid({
  rows,
  onSelect,
  onCreate,
}: {
  rows: Development[];
  onSelect: (id: string) => void;
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          icon={<Building2 size={22} />}
          title={t('propdev.empty_developments', { defaultValue: 'No developments yet' })}
          description={t('propdev.empty_developments_desc', {
            defaultValue: 'Create your first development to start tracking plots, buyers and handovers.',
          })}
          action={{
            label: t('propdev.new_development', { defaultValue: 'New Development' }),
            onClick: onCreate,
          }}
        />
      </Card>
    );
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {rows.map((d) => (
        <DevelopmentCard key={d.id} dev={d} onSelect={onSelect} />
      ))}
    </div>
  );
}

function DevelopmentCard({
  dev,
  onSelect,
}: {
  dev: Development;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const dashQ = useQuery({
    queryKey: ['propdev', 'dashboard', dev.id],
    queryFn: () => getDevelopmentDashboard(dev.id),
    staleTime: 60_000,
  });
  const dash = dashQ.data;
  const sold = dash ? (dash.plots_by_status['sold'] ?? 0) + (dash.plots_by_status['handed_over'] ?? 0) : 0;
  const total = dash?.total_plots ?? dev.total_plots ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((sold / total) * 100)) : 0;
  return (
    <Card padding="md" hoverable>
      <button type="button" onClick={() => onSelect(dev.id)} className="text-left w-full focus:outline-none">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="font-semibold text-content-primary truncate" title={dev.name || dev.code}>
              {dev.name || dev.code}
            </h3>
            <p className="mt-0.5 text-xs font-mono text-content-tertiary">{dev.code}</p>
          </div>
          <Badge variant={dev.status === 'active' ? 'success' : dev.status === 'paused' ? 'warning' : 'neutral'} dot>
            {dev.sales_phase}
          </Badge>
        </div>
        {dev.location_address && (
          <p className="mt-1 text-xs text-content-secondary line-clamp-1">{dev.location_address}</p>
        )}
        <div className="mt-3">
          <div className="flex items-center justify-between text-xs text-content-secondary mb-1">
            <span>
              {t('propdev.plots_sold', {
                defaultValue: '{{sold}}/{{total}} plots sold',
                sold,
                total,
              })}
            </span>
            <span className="font-medium">{pct}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-surface-secondary">
            <div
              className="h-full bg-oe-blue transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
        {dash && (
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div>
              <p className="text-content-tertiary">{t('propdev.contracted', { defaultValue: 'Contracted' })}</p>
              <p className="font-medium">
                <MoneyDisplay amount={toNumber(dash.contracted_value)} currency={undefined} />
              </p>
            </div>
            <div>
              <p className="text-content-tertiary">{t('propdev.open_snags', { defaultValue: 'Open snags' })}</p>
              <p className="font-medium">{dash.open_snags}</p>
            </div>
          </div>
        )}
      </button>
    </Card>
  );
}

/* ─── Plots tab — grid view ─── */

function PlotsTab({
  plots,
  houseTypes,
  onSelect,
  onCreate,
}: {
  plots: Plot[];
  houseTypes: HouseType[];
  onSelect: (id: string) => void;
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  if (plots.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          icon={<Grid3X3 size={22} />}
          title={t('propdev.empty_plots', { defaultValue: 'No plots' })}
          description={t('propdev.empty_plots_desc', {
            defaultValue: 'Add plots to the selected development to start the sales pipeline.',
          })}
          action={{
            label: t('propdev.new_plot', { defaultValue: 'New Plot' }),
            onClick: onCreate,
          }}
        />
      </Card>
    );
  }
  const htMap = new Map(houseTypes.map((h) => [h.id, h]));
  return (
    <Card padding="md">
      <div className="flex flex-wrap items-center gap-3 text-xs text-content-secondary mb-3">
        {(Object.keys(PLOT_STATUS_COLOR) as PlotStatus[]).map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <span className={clsx('h-3 w-3 rounded-sm border', PLOT_STATUS_COLOR[s])} />
            {s}
          </span>
        ))}
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(72px,1fr))] gap-1.5">
        {plots.map((p) => {
          const ht = p.house_type_id ? htMap.get(p.house_type_id) : null;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => onSelect(p.id)}
              className={clsx(
                'flex flex-col items-center justify-center rounded-md border-2 px-1 py-2 text-center transition-all hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-oe-blue',
                PLOT_STATUS_COLOR[p.status],
              )}
              title={`${p.plot_number} — ${p.status}`}
            >
              <span className="text-xs font-semibold leading-none">{p.plot_number}</span>
              {ht && <span className="mt-0.5 text-[10px] opacity-80">{ht.code}</span>}
            </button>
          );
        })}
      </div>
    </Card>
  );
}

/* ─── House Types tab ─── */

function HouseTypesTab({
  rows,
  onCreate,
}: {
  rows: HouseType[];
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          icon={<Home size={22} />}
          title={t('propdev.empty_house_types', { defaultValue: 'No house types' })}
          description={t('propdev.empty_house_types_desc', {
            defaultValue: 'Define reusable house types (semi, detached, terrace) with base prices.',
          })}
          action={{
            label: t('propdev.new_house_type', { defaultValue: 'New House Type' }),
            onClick: onCreate,
          }}
        />
      </Card>
    );
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {rows.map((h) => (
        <HouseTypeCard key={h.id} ht={h} />
      ))}
    </div>
  );
}

function HouseTypeCard({ ht }: { ht: HouseType }) {
  const { t } = useTranslation();
  const variantsQ = useQuery({
    queryKey: ['propdev', 'variants', ht.id],
    queryFn: () => listVariants(ht.id),
    staleTime: 60_000,
  });
  return (
    <Card padding="md">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold text-content-primary truncate" title={ht.name || ht.code}>
            {ht.name || ht.code}
          </h3>
          <p className="mt-0.5 text-xs font-mono text-content-tertiary">{ht.code}</p>
        </div>
        <Badge variant="blue">{ht.bedrooms} BR</Badge>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-content-tertiary">{t('propdev.area', { defaultValue: 'Area' })}</p>
          <p className="font-medium">{toNumber(ht.total_area_m2).toFixed(1)} m²</p>
        </div>
        <div>
          <p className="text-content-tertiary">{t('propdev.levels', { defaultValue: 'Levels' })}</p>
          <p className="font-medium">{ht.levels}</p>
        </div>
        <div>
          <p className="text-content-tertiary">{t('propdev.base_price', { defaultValue: 'Base price' })}</p>
          <p className="font-medium">
            <MoneyDisplay amount={toNumber(ht.base_price)} currency={ht.currency || undefined} />
          </p>
        </div>
      </div>
      {variantsQ.data && variantsQ.data.length > 0 && (
        <div className="mt-3">
          <p className="text-xs uppercase tracking-wide text-content-tertiary mb-1">
            {t('propdev.variants', { defaultValue: 'Variants' })}
          </p>
          <div className="flex flex-wrap gap-1">
            {variantsQ.data.map((v) => (
              <Badge key={v.id} variant="neutral">
                {v.code} ({toNumber(v.modifier_pct) > 0 ? '+' : ''}
                {toNumber(v.modifier_pct).toFixed(1)}%)
              </Badge>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

/* ─── Buyers tab ─── */

function BuyersTab({
  rows,
  onSelect,
  onCreate,
}: {
  rows: Buyer[];
  onSelect: (id: string) => void;
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          icon={<Users size={22} />}
          title={t('propdev.empty_buyers', { defaultValue: 'No buyers yet' })}
          description={t('propdev.empty_buyers_desc', {
            defaultValue: 'Register leads, track contracts and configure buyer selections.',
          })}
          action={{
            label: t('propdev.new_buyer', { defaultValue: 'New Buyer' }),
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
              <th className="px-4 py-2.5 text-left">{t('propdev.buyer', { defaultValue: 'Buyer' })}</th>
              <th className="px-4 py-2.5 text-left">{t('propdev.email', { defaultValue: 'Email' })}</th>
              <th className="px-4 py-2.5 text-left">{t('propdev.stage', { defaultValue: 'Stage' })}</th>
              <th className="px-4 py-2.5 text-right">{t('propdev.contract_value', { defaultValue: 'Contract' })}</th>
              <th className="px-4 py-2.5 text-left">{t('propdev.freeze_deadline', { defaultValue: 'Freeze' })}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => {
              const days = daysUntil(b.freeze_deadline);
              return (
                <tr
                  key={b.id}
                  onClick={() => onSelect(b.id)}
                  className="border-t border-border-light hover:bg-surface-secondary cursor-pointer"
                >
                  <td className="px-4 py-2 font-medium">{b.full_name || '—'}</td>
                  <td className="px-4 py-2 text-xs text-content-secondary">{b.email}</td>
                  <td className="px-4 py-2">
                    <Badge variant={BUYER_VARIANT[b.status]} dot>{b.status}</Badge>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <MoneyDisplay amount={toNumber(b.contract_value)} currency={b.currency || undefined} />
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {b.freeze_deadline ? (
                      <span className={clsx(
                        'inline-flex items-center gap-1',
                        days != null && days < 7 ? 'text-rose-600 font-medium' : 'text-content-secondary',
                      )}>
                        <Clock size={11} />
                        {days != null ? (
                          days > 0
                            ? t('propdev.in_days', { defaultValue: 'in {{n}}d', n: days })
                            : t('propdev.overdue_days', { defaultValue: '{{n}}d overdue', n: Math.abs(days) })
                        ) : (
                          <DateDisplay value={b.freeze_deadline} />
                        )}
                      </span>
                    ) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ─── Handovers tab ─── */

function HandoversTab({ plots, buyers }: { plots: Plot[]; buyers: Buyer[] }) {
  const { t } = useTranslation();
  // Limit fetching to plots that have status ready/sold/handed_over
  const candidatePlots = plots.filter((p) =>
    ['ready', 'sold', 'handed_over'].includes(p.status),
  );
  if (candidatePlots.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          icon={<Key size={22} />}
          title={t('propdev.empty_handovers', { defaultValue: 'No handovers scheduled' })}
          description={t('propdev.empty_handovers_desc', {
            defaultValue: 'Handovers appear here once plots reach "ready" status and have buyers assigned.',
          })}
        />
      </Card>
    );
  }
  return (
    <div className="space-y-3">
      {candidatePlots.map((p) => {
        const buyer = buyers.find((b) => b.plot_id === p.id);
        return <HandoverPlotRow key={p.id} plot={p} buyer={buyer} />;
      })}
    </div>
  );
}

function HandoverPlotRow({ plot, buyer }: { plot: Plot; buyer: Buyer | undefined }) {
  const { t } = useTranslation();
  const handoversQ = useQuery({
    queryKey: ['propdev', 'handovers', plot.id],
    queryFn: () => listHandovers(plot.id),
    staleTime: 60_000,
  });
  const handovers = handoversQ.data ?? [];
  return (
    <Card padding="md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold">
            {t('propdev.plot_n', { defaultValue: 'Plot {{n}}', n: plot.plot_number })}
          </p>
          <p className="text-xs text-content-tertiary">
            {buyer ? buyer.full_name : t('propdev.no_buyer', { defaultValue: 'No buyer assigned' })}
          </p>
        </div>
        <Badge variant={PLOT_STATUS_VARIANT[plot.status]} dot>{plot.status}</Badge>
      </div>
      {handovers.length === 0 ? (
        <p className="mt-2 text-xs text-content-tertiary">
          {t('propdev.no_handovers', { defaultValue: 'No handover scheduled yet.' })}
        </p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {handovers.map((h: Handover) => (
            <li key={h.id} className="flex items-center gap-2 text-xs">
              {h.completed_at ? (
                <Badge variant="success" dot>
                  {t('propdev.completed', { defaultValue: 'Completed' })}
                </Badge>
              ) : (
                <Badge variant="warning" dot>
                  {t('propdev.scheduled', { defaultValue: 'Scheduled' })}
                </Badge>
              )}
              <span className="text-content-secondary">
                {h.scheduled_at ? <DateDisplay value={h.scheduled_at} /> : '—'}
              </span>
              {h.snag_count_at_handover > 0 && (
                <span className="text-amber-600">
                  · {h.snag_count_at_handover} {t('propdev.snags', { defaultValue: 'snags' })}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/* ─── Warranty tab ─── */

function WarrantyTab({ buyers, plots }: { buyers: Buyer[]; plots: Plot[] }) {
  const { t } = useTranslation();
  const [selectedBuyerId, setSelectedBuyerId] = useState<string>('');
  const effective = selectedBuyerId || buyers[0]?.id || '';
  const claimsQ = useQuery({
    queryKey: ['propdev', 'warranty', effective],
    queryFn: () => listWarrantyClaims({ buyer_id: effective }),
    enabled: !!effective,
  });
  const claims = claimsQ.data ?? [];
  const plotMap = new Map(plots.map((p) => [p.id, p]));
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const action = useMutation({
    mutationFn: async ({ id, kind }: { id: string; kind: 'accept' | 'reject' | 'close' }) => {
      if (kind === 'accept') return acceptWarrantyClaim(id);
      if (kind === 'reject') return rejectWarrantyClaim(id);
      return closeWarrantyClaim(id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['propdev', 'warranty'] });
      addToast({ type: 'success', title: t('propdev.warranty_updated', { defaultValue: 'Claim updated' }) });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  return (
    <div className="space-y-3">
      {buyers.length === 0 ? (
        <Card padding="md">
          <EmptyState
            icon={<ShieldAlert size={22} />}
            title={t('propdev.empty_buyers', { defaultValue: 'No buyers yet' })}
            description={t('propdev.warranty_needs_buyer', {
              defaultValue: 'Warranty claims are filed against a buyer — add a buyer first.',
            })}
          />
        </Card>
      ) : (
        <>
          <select
            value={effective}
            onChange={(e) => setSelectedBuyerId(e.target.value)}
            className={clsx(inputCls, 'max-w-[320px]')}
          >
            {buyers.map((b) => (
              <option key={b.id} value={b.id}>
                {b.full_name} — {b.email}
              </option>
            ))}
          </select>
          {claimsQ.isLoading ? (
            <Card padding="md"><SkeletonTable rows={3} columns={4} /></Card>
          ) : claims.length === 0 ? (
            <Card padding="md">
              <EmptyState
                icon={<ShieldAlert size={22} />}
                title={t('propdev.no_claims', { defaultValue: 'No warranty claims' })}
                description={t('propdev.no_claims_desc', {
                  defaultValue: 'This buyer has not raised any warranty claims yet.',
                })}
              />
            </Card>
          ) : (
            <Card padding="none">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
                    <tr>
                      <th className="px-4 py-2.5 text-left">{t('propdev.plot', { defaultValue: 'Plot' })}</th>
                      <th className="px-4 py-2.5 text-left">{t('propdev.category', { defaultValue: 'Category' })}</th>
                      <th className="px-4 py-2.5 text-left">{t('propdev.description', { defaultValue: 'Description' })}</th>
                      <th className="px-4 py-2.5 text-left">{t('propdev.status', { defaultValue: 'Status' })}</th>
                      <th className="px-4 py-2.5 text-right">{t('common.actions', { defaultValue: 'Actions' })}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {claims.map((c: WarrantyClaim) => {
                      const plot = plotMap.get(c.plot_id);
                      return (
                        <tr key={c.id} className="border-t border-border-light">
                          <td className="px-4 py-2 text-xs">{plot?.plot_number ?? '—'}</td>
                          <td className="px-4 py-2 text-xs uppercase">{c.category}</td>
                          <td className="px-4 py-2 max-w-[320px] truncate">{c.description}</td>
                          <td className="px-4 py-2"><Badge variant={WARRANTY_VARIANT[c.status]} dot>{c.status}</Badge></td>
                          <td className="px-4 py-2 text-right">
                            <div className="inline-flex gap-1">
                              {c.status === 'raised' && (
                                <>
                                  <Button variant="secondary" onClick={() => action.mutate({ id: c.id, kind: 'accept' })}>
                                    {t('propdev.accept', { defaultValue: 'Accept' })}
                                  </Button>
                                  <Button variant="ghost" onClick={() => action.mutate({ id: c.id, kind: 'reject' })}>
                                    {t('propdev.reject', { defaultValue: 'Reject' })}
                                  </Button>
                                </>
                              )}
                              {(c.status === 'accepted' || c.status === 'under_review') && (
                                <Button variant="secondary" onClick={() => action.mutate({ id: c.id, kind: 'close' })}>
                                  {t('propdev.close', { defaultValue: 'Close' })}
                                </Button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

/* ─── Plot detail drawer ─── */

function PlotDetailDrawer({
  plotId,
  plots,
  houseTypes,
  onClose,
}: {
  plotId: string;
  plots: Plot[];
  houseTypes: HouseType[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  // Esc-to-close — registered before the early return so the hook order
  // is stable regardless of whether the plot is resolved yet.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const plot = plots.find((p) => p.id === plotId);
  const ht = plot?.house_type_id ? houseTypes.find((h) => h.id === plot.house_type_id) : null;
  if (!plot) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="propdev-plot-drawer-title"
        className="relative h-full w-full max-w-lg overflow-y-auto bg-surface-elevated shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-light bg-surface-elevated px-5 py-3">
          <h2 id="propdev-plot-drawer-title" className="text-base font-semibold">
            {t('propdev.plot_n', { defaultValue: 'Plot {{n}}', n: plot.plot_number })}
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
        <div className="space-y-3 p-5">
          <div className="flex items-center justify-between">
            <Badge variant={PLOT_STATUS_VARIANT[plot.status]} dot>{plot.status}</Badge>
            <span className="text-xs text-content-tertiary">
              {Math.round(toNumber(plot.construction_status_percent))}% {t('propdev.built', { defaultValue: 'built' })}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field label={t('propdev.house_type', { defaultValue: 'House Type' })} value={ht?.name || ht?.code || '—'} />
            <Field label={t('propdev.area', { defaultValue: 'Area' })} value={`${toNumber(plot.area_m2).toFixed(1)} m²`} />
            <Field label={t('propdev.orientation', { defaultValue: 'Orientation' })} value={plot.orientation || '—'} />
            <Field
              label={t('propdev.garden', { defaultValue: 'Garden' })}
              value={plot.garden_area_m2 != null ? `${toNumber(plot.garden_area_m2).toFixed(1)} m²` : '—'}
            />
            <Field
              label={t('propdev.base_price', { defaultValue: 'Base price' })}
              value={<MoneyDisplay amount={toNumber(plot.price_base)} currency={plot.currency || undefined} />}
            />
            <Field
              label={t('propdev.reserved_until', { defaultValue: 'Reserved until' })}
              value={plot.reservation_deadline ? <DateDisplay value={plot.reservation_deadline} /> : '—'}
            />
          </div>
          {plot.status === 'planned' && (
            <ReserveBlock plotId={plot.id} onSuccess={onClose} />
          )}
        </div>
      </div>
    </div>
  );
}

function ReserveBlock({ plotId, onSuccess }: { plotId: string; onSuccess: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    reservation_deadline: todayIso(30),
  });
  const mut = useMutation({
    mutationFn: () => reservePlot(plotId, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['propdev', 'plots'] });
      qc.invalidateQueries({ queryKey: ['propdev', 'buyers'] });
      addToast({ type: 'success', title: t('propdev.plot_reserved', { defaultValue: 'Plot reserved' }) });
      onSuccess();
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });
  return (
    <Card padding="sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-2">
        {t('propdev.reserve_plot', { defaultValue: 'Reserve plot' })}
      </p>
      <div className="space-y-2">
        <input
          value={form.full_name}
          onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          placeholder={t('propdev.full_name', { defaultValue: 'Full name' })}
          className={inputCls}
        />
        <input
          type="email"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          placeholder={t('propdev.email', { defaultValue: 'Email' })}
          className={inputCls}
        />
        <input
          type="date"
          value={form.reservation_deadline}
          onChange={(e) => setForm({ ...form, reservation_deadline: e.target.value })}
          className={inputCls}
        />
        <Button
          variant="primary"
          icon={mut.isPending ? <Loader2 size={14} /> : <Check size={14} />}
          loading={mut.isPending}
          onClick={() => mut.mutate()}
          disabled={!form.full_name || !form.email}
        >
          {t('propdev.reserve', { defaultValue: 'Reserve' })}
        </Button>
      </div>
    </Card>
  );
}

/* ─── Buyer detail drawer with stage progression ─── */

function BuyerDetailDrawer({
  buyerId,
  buyers,
  plots,
  onClose,
}: {
  buyerId: string;
  buyers: Buyer[];
  plots: Plot[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const buyer = buyers.find((b) => b.id === buyerId);
  const plot = buyer?.plot_id ? plots.find((p) => p.id === buyer.plot_id) : null;
  const selectionsQ = useQuery({
    queryKey: ['propdev', 'selections', buyerId],
    queryFn: () => listSelections(buyerId),
    enabled: !!buyer,
  });
  const items = selectionsQ.data ?? [];
  const freezeDays = daysUntil(buyer?.freeze_deadline);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  if (!buyer) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="propdev-buyer-drawer-title"
        className="relative h-full w-full max-w-xl overflow-y-auto bg-surface-elevated shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-light bg-surface-elevated px-5 py-3">
          <div>
            <h2 id="propdev-buyer-drawer-title" className="text-base font-semibold">{buyer.full_name || buyer.email}</h2>
            <p className="text-xs text-content-tertiary">{buyer.email}</p>
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
        <div className="space-y-4 p-5">
          <StageProgress current={buyer.status} />

          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field
              label={t('propdev.plot', { defaultValue: 'Plot' })}
              value={plot ? plot.plot_number : '—'}
            />
            <Field
              label={t('propdev.contract_value', { defaultValue: 'Contract' })}
              value={
                <MoneyDisplay
                  amount={toNumber(buyer.contract_value)}
                  currency={buyer.currency || undefined}
                />
              }
            />
            <Field
              label={t('propdev.signed', { defaultValue: 'Signed' })}
              value={buyer.contract_signed_at ? <DateDisplay value={buyer.contract_signed_at} /> : '—'}
            />
            <Field
              label={t('propdev.deposit', { defaultValue: 'Deposit' })}
              value={buyer.deposit_paid_at ? <DateDisplay value={buyer.deposit_paid_at} /> : '—'}
            />
          </div>

          {buyer.freeze_deadline && freezeDays != null && (
            <Card padding="sm">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary">
                    {t('propdev.freeze_deadline', { defaultValue: 'Freeze deadline' })}
                  </p>
                  <p className="mt-0.5 text-sm">
                    <DateDisplay value={buyer.freeze_deadline} />
                  </p>
                </div>
                <div className={clsx(
                  'rounded-lg px-3 py-2 text-center',
                  freezeDays < 0
                    ? 'bg-rose-100 text-rose-800'
                    : freezeDays < 7
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-sky-100 text-sky-800',
                )}>
                  <p className="text-2xl font-semibold leading-none">
                    {Math.abs(freezeDays)}
                  </p>
                  <p className="mt-0.5 text-[10px] uppercase tracking-wide">
                    {freezeDays < 0
                      ? t('propdev.days_overdue', { defaultValue: 'days overdue' })
                      : t('propdev.days_left', { defaultValue: 'days left' })}
                  </p>
                </div>
              </div>
            </Card>
          )}

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-2">
              {t('propdev.selections', { defaultValue: 'Buyer selections' })}
            </p>
            {selectionsQ.isLoading ? (
              <SkeletonTable rows={2} columns={3} />
            ) : items.length === 0 ? (
              <p className="text-sm text-content-tertiary">
                {t('propdev.no_selections', { defaultValue: 'No selections recorded yet.' })}
              </p>
            ) : (
              <ul className="space-y-1.5">
                {items.map((s) => (
                  <li key={s.id} className="flex items-center justify-between rounded border border-border-light px-3 py-2 text-sm">
                    <span>
                      <Badge variant={s.status === 'locked' ? 'success' : 'neutral'}>{s.status}</Badge>
                      <span className="ml-2 text-content-secondary text-xs">
                        <DateDisplay value={s.created_at} />
                      </span>
                    </span>
                    <span className="font-medium">
                      <MoneyDisplay amount={toNumber(s.total_options_value)} currency={buyer.currency || undefined} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {buyer.status === 'reserved' && (
            <ContractBuyerBlock buyer={buyer} />
          )}
        </div>
      </div>
    </div>
  );
}

function StageProgress({ current }: { current: BuyerStatus }) {
  const { t } = useTranslation();
  const labels: Record<BuyerStatus, string> = {
    lead: t('propdev.stage_lead', { defaultValue: 'Lead' }),
    reserved: t('propdev.stage_reserved', { defaultValue: 'Reserved' }),
    contracted: t('propdev.stage_contracted', { defaultValue: 'Contracted' }),
    completed: t('propdev.stage_handover', { defaultValue: 'Handover' }),
    cancelled: t('propdev.stage_cancelled', { defaultValue: 'Cancelled' }),
  };
  if (current === 'cancelled') {
    return (
      <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-center text-sm text-rose-800">
        {labels.cancelled}
      </div>
    );
  }
  const idx = BUYER_STAGE_ORDER.indexOf(current);
  return (
    <div className="flex items-center justify-between gap-1">
      {BUYER_STAGE_ORDER.map((s, i) => {
        const active = i <= idx;
        const reached = i < idx;
        return (
          <div key={s} className="flex items-center flex-1 min-w-0">
            <div className="flex flex-col items-center flex-1 min-w-0">
              <div className={clsx(
                'flex h-7 w-7 items-center justify-center rounded-full border-2 text-xs font-semibold',
                active
                  ? 'border-oe-blue bg-oe-blue text-white'
                  : 'border-border bg-surface-primary text-content-tertiary',
              )}>
                {reached ? <Check size={12} /> : i + 1}
              </div>
              <span className={clsx(
                'mt-1 text-[10px] uppercase tracking-wide truncate max-w-full',
                active ? 'text-content-primary font-medium' : 'text-content-tertiary',
              )}>
                {labels[s]}
              </span>
            </div>
            {i < BUYER_STAGE_ORDER.length - 1 && (
              <div className={clsx(
                'h-0.5 flex-1 -mt-4',
                i < idx ? 'bg-oe-blue' : 'bg-border',
              )} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function ContractBuyerBlock({ buyer }: { buyer: Buyer }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const prefCurrency = usePreferencesStore((s) => s.currency);
  const [form, setForm] = useState({
    contract_value: String(toNumber(buyer.contract_value)),
    currency: buyer.currency || prefCurrency,
    contract_signed_at: todayIso(),
    freeze_deadline: todayIso(60),
  });
  const mut = useMutation({
    mutationFn: () =>
      contractBuyer(buyer.id, {
        contract_value: Number(form.contract_value) || 0,
        currency: form.currency,
        contract_signed_at: form.contract_signed_at,
        freeze_deadline: form.freeze_deadline,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['propdev', 'buyers'] });
      addToast({ type: 'success', title: t('propdev.contract_signed', { defaultValue: 'Contract signed' }) });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });
  return (
    <Card padding="sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-2">
        {t('propdev.sign_contract', { defaultValue: 'Sign contract' })}
      </p>
      <div className="space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <input
            type="number"
            value={form.contract_value}
            onChange={(e) => setForm({ ...form, contract_value: e.target.value })}
            placeholder={t('propdev.contract_value', { defaultValue: 'Contract value' })}
            className={inputCls}
          />
          <input
            value={form.currency}
            onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
            placeholder={prefCurrency}
            className={inputCls}
            maxLength={3}
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className={labelCls}>{t('propdev.signed', { defaultValue: 'Signed' })}</label>
            <input
              type="date"
              value={form.contract_signed_at}
              onChange={(e) => setForm({ ...form, contract_signed_at: e.target.value })}
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>{t('propdev.freeze_deadline', { defaultValue: 'Freeze deadline' })}</label>
            <input
              type="date"
              value={form.freeze_deadline}
              onChange={(e) => setForm({ ...form, freeze_deadline: e.target.value })}
              className={inputCls}
            />
          </div>
        </div>
        <Button
          variant="primary"
          icon={mut.isPending ? <Loader2 size={14} /> : <Check size={14} />}
          loading={mut.isPending}
          onClick={() => mut.mutate()}
        >
          {t('propdev.contract', { defaultValue: 'Contract' })}
        </Button>
      </div>
    </Card>
  );
}

function Field({ label, value }: { label: React.ReactNode; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-content-tertiary">{label}</p>
      <p className="mt-0.5 text-sm text-content-primary">{value}</p>
    </div>
  );
}

/* ─── Create modal ─── */

function CreateModal({
  kind,
  developmentId,
  developments,
  houseTypes,
  onClose,
}: {
  kind: Tab;
  developmentId: string;
  developments: Development[];
  houseTypes: HouseType[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const prefCurrency = usePreferencesStore((s) => s.currency);
  const [busy, setBusy] = useState(false);

  const [devForm, setDevForm] = useState({
    project_id: '',
    code: '',
    name: '',
    total_plots: 0,
  });
  const [plotForm, setPlotForm] = useState({
    development_id: developmentId,
    plot_number: '',
    house_type_id: '',
    area_m2: '0',
    price_base: '0',
    currency: prefCurrency,
  });
  const [htForm, setHtForm] = useState({
    development_id: developmentId,
    code: '',
    name: '',
    bedrooms: 3,
    total_area_m2: '120',
    base_price: '0',
    currency: prefCurrency,
  });
  const [buyerForm, setBuyerForm] = useState({
    development_id: developmentId,
    full_name: '',
    email: '',
    phone: '',
  });

  const submit = async () => {
    setBusy(true);
    try {
      if (kind === 'developments') {
        if (!devForm.project_id) throw new Error('Project ID required');
        if (!devForm.code) throw new Error('Code required');
        await createDevelopment({
          project_id: devForm.project_id,
          code: devForm.code,
          name: devForm.name,
          total_plots: devForm.total_plots,
        });
        addToast({ type: 'success', title: t('propdev.development_created', { defaultValue: 'Development created' }) });
        qc.invalidateQueries({ queryKey: ['propdev', 'developments'] });
      } else if (kind === 'plots') {
        if (!plotForm.development_id) throw new Error('Development required');
        if (!plotForm.plot_number) throw new Error('Plot number required');
        await createPlot({
          development_id: plotForm.development_id,
          plot_number: plotForm.plot_number,
          house_type_id: plotForm.house_type_id || undefined,
          area_m2: Number(plotForm.area_m2) || 0,
          price_base: Number(plotForm.price_base) || 0,
          currency: plotForm.currency,
        });
        addToast({ type: 'success', title: t('propdev.plot_created', { defaultValue: 'Plot created' }) });
        qc.invalidateQueries({ queryKey: ['propdev', 'plots'] });
      } else if (kind === 'house_types') {
        if (!htForm.development_id) throw new Error('Development required');
        if (!htForm.code) throw new Error('Code required');
        await createHouseType({
          development_id: htForm.development_id,
          code: htForm.code,
          name: htForm.name,
          bedrooms: htForm.bedrooms,
          total_area_m2: Number(htForm.total_area_m2) || 0,
          base_price: Number(htForm.base_price) || 0,
          currency: htForm.currency,
        });
        addToast({ type: 'success', title: t('propdev.house_type_created', { defaultValue: 'House type created' }) });
        qc.invalidateQueries({ queryKey: ['propdev', 'house-types'] });
      } else if (kind === 'buyers') {
        if (!buyerForm.development_id) throw new Error('Development required');
        if (!buyerForm.email) throw new Error('Email required');
        await createBuyer({
          development_id: buyerForm.development_id,
          full_name: buyerForm.full_name,
          email: buyerForm.email,
          phone: buyerForm.phone || undefined,
        });
        addToast({ type: 'success', title: t('propdev.buyer_created', { defaultValue: 'Buyer created' }) });
        qc.invalidateQueries({ queryKey: ['propdev', 'buyers'] });
      } else {
        throw new Error('Not supported');
      }
      onClose();
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  const title =
    kind === 'developments'
      ? t('propdev.new_development', { defaultValue: 'New Development' })
      : kind === 'plots'
        ? t('propdev.new_plot', { defaultValue: 'New Plot' })
        : kind === 'house_types'
          ? t('propdev.new_house_type', { defaultValue: 'New House Type' })
          : kind === 'buyers'
            ? t('propdev.new_buyer', { defaultValue: 'New Buyer' })
            : t('common.create', { defaultValue: 'Create' });

  // house_types uses a triplet (bedrooms/area/base_price); xl gives it
  // room. The other variants have ≤ 4 short fields, lg is enough.
  const size = kind === 'house_types' ? 'xl' : 'lg';

  return (
    <WideModal
      open
      onClose={onClose}
      title={title}
      size={size}
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
      {kind === 'developments' && (
        <WideModalSection columns={2}>
          <WideModalField
            label={t('propdev.project_id', { defaultValue: 'Project ID (UUID)' })}
            required
            span={2}
          >
            <input
              value={devForm.project_id}
              onChange={(e) => setDevForm({ ...devForm, project_id: e.target.value })}
              className={inputCls}
              placeholder="00000000-0000-0000-0000-000000000000"
            />
          </WideModalField>
          <WideModalField
            label={t('propdev.code', { defaultValue: 'Code' })}
            required
          >
            <input
              value={devForm.code}
              onChange={(e) => setDevForm({ ...devForm, code: e.target.value })}
              className={inputCls}
              placeholder="DEV-001"
            />
          </WideModalField>
          <WideModalField label={t('propdev.name', { defaultValue: 'Name' })}>
            <input
              value={devForm.name}
              onChange={(e) => setDevForm({ ...devForm, name: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('propdev.total_plots', { defaultValue: 'Total plots' })}
            span={2}
          >
            <input
              type="number"
              value={devForm.total_plots}
              onChange={(e) =>
                setDevForm({ ...devForm, total_plots: Number(e.target.value) || 0 })
              }
              className={inputCls}
              min={0}
            />
          </WideModalField>
        </WideModalSection>
      )}
      {kind === 'plots' && (
        <WideModalSection columns={2}>
          <WideModalField
            label={t('propdev.development', { defaultValue: 'Development' })}
            required
            span={2}
          >
            <select
              value={plotForm.development_id}
              onChange={(e) => setPlotForm({ ...plotForm, development_id: e.target.value })}
              className={inputCls}
            >
              <option value="">— {t('common.select', { defaultValue: 'Select' })} —</option>
              {developments.map((d) => (
                <option key={d.id} value={d.id}>{d.code} — {d.name}</option>
              ))}
            </select>
          </WideModalField>
          <WideModalField
            label={t('propdev.plot_number', { defaultValue: 'Plot number' })}
            required
          >
            <input
              value={plotForm.plot_number}
              onChange={(e) => setPlotForm({ ...plotForm, plot_number: e.target.value })}
              className={inputCls}
              placeholder="P-001"
            />
          </WideModalField>
          <WideModalField
            label={t('propdev.house_type', { defaultValue: 'House Type' })}
          >
            <select
              value={plotForm.house_type_id}
              onChange={(e) => setPlotForm({ ...plotForm, house_type_id: e.target.value })}
              className={inputCls}
            >
              <option value="">— {t('common.none', { defaultValue: 'None' })} —</option>
              {houseTypes.map((h) => (
                <option key={h.id} value={h.id}>{h.code} — {h.name}</option>
              ))}
            </select>
          </WideModalField>
          <WideModalField label={t('propdev.area', { defaultValue: 'Area (m²)' })}>
            <input
              type="number"
              value={plotForm.area_m2}
              onChange={(e) => setPlotForm({ ...plotForm, area_m2: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('propdev.base_price', { defaultValue: 'Base price' })}
          >
            <input
              type="number"
              value={plotForm.price_base}
              onChange={(e) => setPlotForm({ ...plotForm, price_base: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
        </WideModalSection>
      )}
      {kind === 'house_types' && (
        <WideModalSection columns={3}>
          <WideModalField
            label={t('propdev.code', { defaultValue: 'Code' })}
            required
          >
            <input
              value={htForm.code}
              onChange={(e) => setHtForm({ ...htForm, code: e.target.value })}
              className={inputCls}
              placeholder="TYPE-A"
            />
          </WideModalField>
          <WideModalField
            label={t('propdev.name', { defaultValue: 'Name' })}
            span={2}
          >
            <input
              value={htForm.name}
              onChange={(e) => setHtForm({ ...htForm, name: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('propdev.bedrooms', { defaultValue: 'Bedrooms' })}
          >
            <input
              type="number"
              value={htForm.bedrooms}
              onChange={(e) => setHtForm({ ...htForm, bedrooms: Number(e.target.value) || 0 })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField label={t('propdev.area', { defaultValue: 'Area' })}>
            <input
              type="number"
              value={htForm.total_area_m2}
              onChange={(e) => setHtForm({ ...htForm, total_area_m2: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('propdev.base_price', { defaultValue: 'Base price' })}
          >
            <input
              type="number"
              value={htForm.base_price}
              onChange={(e) => setHtForm({ ...htForm, base_price: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
        </WideModalSection>
      )}
      {kind === 'buyers' && (
        <WideModalSection columns={2}>
          <WideModalField
            label={t('propdev.full_name', { defaultValue: 'Full name' })}
            span={2}
          >
            <input
              value={buyerForm.full_name}
              onChange={(e) => setBuyerForm({ ...buyerForm, full_name: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('propdev.email', { defaultValue: 'Email' })}
            required
          >
            <input
              type="email"
              value={buyerForm.email}
              onChange={(e) => setBuyerForm({ ...buyerForm, email: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
          <WideModalField label={t('propdev.phone', { defaultValue: 'Phone' })}>
            <input
              value={buyerForm.phone}
              onChange={(e) => setBuyerForm({ ...buyerForm, phone: e.target.value })}
              className={inputCls}
            />
          </WideModalField>
        </WideModalSection>
      )}
    </WideModal>
  );
}
