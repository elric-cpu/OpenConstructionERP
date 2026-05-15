import { useState, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  Truck,
  Plus,
  Search,
  X,
  Loader2,
  Activity,
  Wrench,
  ShieldCheck,
  AlertTriangle,
  MapPin,
  Pencil,
  Trash2,
  Save,
} from 'lucide-react';
import {
  Button,
  Card,
  Badge,
  EmptyState,
  Breadcrumb,
  SkeletonTable,
  ConfirmDialog,
} from '@/shared/ui';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';
import {
  listEquipment,
  createEquipment,
  updateEquipment,
  deleteEquipment,
  listTelemetry,
  listMaintenanceWorkOrders,
  listInspections,
  listDamageReports,
  type Equipment,
  type EquipmentStatus,
  type WorkOrderStatus,
  type InspectionResult,
  type DamageSeverity,
  type Ownership,
  type CreateEquipmentPayload,
} from './api';

type DrawerTab = 'utilization' | 'maintenance' | 'certifications' | 'damage';

const STATUS_VARIANT: Record<
  EquipmentStatus,
  'neutral' | 'blue' | 'success' | 'warning' | 'error'
> = {
  active: 'success',
  under_maintenance: 'warning',
  decommissioned: 'neutral',
  reserved: 'blue',
};

const WO_STATUS_VARIANT: Record<
  WorkOrderStatus,
  'neutral' | 'blue' | 'success' | 'warning' | 'error'
> = {
  scheduled: 'blue',
  in_progress: 'warning',
  completed: 'success',
  cancelled: 'neutral',
};

const INSPECTION_VARIANT: Record<
  InspectionResult,
  'neutral' | 'blue' | 'success' | 'warning' | 'error'
> = {
  pass: 'success',
  fail: 'error',
  conditional: 'warning',
};

const DAMAGE_VARIANT: Record<
  DamageSeverity,
  'neutral' | 'blue' | 'success' | 'warning' | 'error'
> = {
  minor: 'neutral',
  major: 'warning',
  critical: 'error',
};

const inputCls =
  'h-9 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

const labelCls = 'block text-xs font-medium text-content-secondary mb-1';

function toNum(n: number | string | null | undefined): number {
  if (n === null || n === undefined) return 0;
  return typeof n === 'number' ? n : Number(n) || 0;
}

export function EquipmentPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [ownershipFilter, setOwnershipFilter] = useState<string>('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const eqQ = useQuery({
    queryKey: ['equipment', 'list', statusFilter, ownershipFilter],
    queryFn: () =>
      listEquipment({
        limit: 200,
        status: statusFilter || undefined,
        ownership: ownershipFilter || undefined,
      }),
  });

  const filtered = useMemo(() => {
    const items = eqQ.data ?? [];
    const s = search.toLowerCase();
    if (!s) return items;
    return items.filter(
      (it) =>
        it.code.toLowerCase().includes(s) ||
        it.name.toLowerCase().includes(s) ||
        (it.manufacturer || '').toLowerCase().includes(s) ||
        (it.model || '').toLowerCase().includes(s) ||
        (it.serial || '').toLowerCase().includes(s),
    );
  }, [eqQ.data, search]);

  return (
    <div className="space-y-5">
      <Breadcrumb
        items={[
          {
            label: t('equipment.title', { defaultValue: 'Equipment & Fleet' }),
          },
        ]}
      />

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">
            {t('equipment.title', { defaultValue: 'Equipment & Fleet' })}
          </h1>
          <p className="mt-1 text-sm text-content-secondary">
            {t('equipment.subtitle', {
              defaultValue:
                'Track equipment assets, utilization, maintenance and certifications.',
            })}
          </p>
        </div>
        <Button
          variant="primary"
          icon={<Plus size={14} />}
          onClick={() => setCreateOpen(true)}
        >
          {t('equipment.new', { defaultValue: 'New Asset' })}
        </Button>
      </div>

      <div className="border-b border-border-light">
        <nav className="flex gap-1 -mb-px">
          <button
            type="button"
            className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 border-oe-blue text-oe-blue"
          >
            <Truck size={14} />
            {t('equipment.tab_assets', { defaultValue: 'Assets' })}
          </button>
        </nav>
      </div>

      <div className="flex flex-wrap items-center gap-2">
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
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className={clsx(inputCls, 'max-w-[180px]')}
        >
          <option value="">
            {t('common.all_statuses', { defaultValue: 'All statuses' })}
          </option>
          {(
            ['active', 'under_maintenance', 'decommissioned', 'reserved'] as EquipmentStatus[]
          ).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={ownershipFilter}
          onChange={(e) => setOwnershipFilter(e.target.value)}
          className={clsx(inputCls, 'max-w-[160px]')}
        >
          <option value="">
            {t('equipment.all_ownership', { defaultValue: 'All ownership' })}
          </option>
          {(['owned', 'rented', 'leased'] as Ownership[]).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </div>

      <Card padding="none">
        {eqQ.isLoading ? (
          <div className="p-4">
            <SkeletonTable rows={8} columns={5} />
          </div>
        ) : eqQ.isError ? (
          <EmptyState
            icon={<AlertTriangle size={22} />}
            title={t('equipment.load_error', {
              defaultValue: 'Could not load equipment',
            })}
            description={getErrorMessage(eqQ.error)}
            action={{
              label: t('common.retry', { defaultValue: 'Retry' }),
              onClick: () => {
                void eqQ.refetch();
              },
            }}
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<Truck size={22} />}
            title={t('equipment.empty', { defaultValue: 'No equipment yet' })}
            description={t('equipment.empty_desc', {
              defaultValue:
                'Register equipment to track utilization, maintenance schedules and certifications.',
            })}
            action={{
              label: t('equipment.new', { defaultValue: 'New Asset' }),
              onClick: () => setCreateOpen(true),
            }}
          />
        ) : (
          <AssetTable rows={filtered} onSelect={setSelectedId} />
        )}
      </Card>

      {selectedId && (
        <DetailDrawer id={selectedId} onClose={() => setSelectedId(null)} />
      )}

      {createOpen && (
        <EquipmentFormModal
          mode="create"
          onClose={() => setCreateOpen(false)}
        />
      )}
    </div>
  );
}

/* ─── Table ─── */

function AssetTable({
  rows,
  onSelect,
}: {
  rows: Equipment[];
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-4 py-2.5 text-left">
              {t('equipment.col_code', { defaultValue: 'Code' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('equipment.col_name', { defaultValue: 'Name' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('equipment.col_type', { defaultValue: 'Type' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('equipment.col_status', { defaultValue: 'Status' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('equipment.col_location', { defaultValue: 'Location' })}
            </th>
            <th className="px-4 py-2.5 text-right">
              {t('equipment.col_hours', { defaultValue: 'Hours' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              onClick={() => onSelect(r.id)}
              className="border-t border-border-light hover:bg-surface-secondary cursor-pointer"
            >
              <td className="px-4 py-2 font-mono text-xs text-content-secondary">
                {r.code}
              </td>
              <td className="px-4 py-2">
                <div className="font-medium text-content-primary truncate max-w-[280px]">
                  {r.name}
                </div>
                {(r.manufacturer || r.model) && (
                  <div className="text-xs text-content-tertiary truncate max-w-[280px]">
                    {[r.manufacturer, r.model].filter(Boolean).join(' · ')}
                  </div>
                )}
              </td>
              <td className="px-4 py-2 text-content-secondary text-xs">
                {r.type_code}
              </td>
              <td className="px-4 py-2">
                <Badge variant={STATUS_VARIANT[r.status]} dot>
                  {r.status}
                </Badge>
              </td>
              <td className="px-4 py-2 text-xs text-content-secondary">
                {r.location_lat !== null &&
                r.location_lng !== null &&
                r.location_lat !== undefined &&
                r.location_lng !== undefined ? (
                  <span className="inline-flex items-center gap-1">
                    <MapPin size={11} className="text-content-tertiary" />
                    {r.location_lat.toFixed(2)}, {r.location_lng.toFixed(2)}
                  </span>
                ) : (
                  '—'
                )}
              </td>
              <td className="px-4 py-2 text-right text-xs tabular-nums">
                {toNum(r.hour_meter).toFixed(0)} h
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ─── Detail Drawer ─── */

function DetailDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [tab, setTab] = useState<DrawerTab>('utilization');
  // Edit + delete UI state — both gated to the loaded equipment so the
  // header buttons can't fire stale operations against a different id.
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const eqQ = useQuery({
    queryKey: ['equipment', 'detail', id],
    queryFn: () =>
      listEquipment({ limit: 500 }).then(
        (rows) => rows.find((r) => r.id === id) ?? null,
      ),
  });
  const eq = eqQ.data;

  // Close on Escape — symmetric with EquipmentFormModal so keyboard
  // users get a predictable dismissal. Skipped while a destructive
  // confirm/delete is in flight so we don't tear the drawer out from
  // under an in-progress request, and while a child modal is open
  // (that modal handles its own Escape).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        e.key === 'Escape' &&
        !deleting &&
        !editOpen &&
        !deleteOpen
      ) {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [deleting, editOpen, deleteOpen, onClose]);

  const handleDelete = async () => {
    if (!eq) return;
    setDeleting(true);
    try {
      await deleteEquipment(eq.id);
      addToast({
        type: 'success',
        title: t('equipment.deleted', {
          defaultValue: '{{name}} deleted',
          name: eq.name,
        }),
      });
      // Invalidate every cached query that referenced this asset so the
      // list page, the dashboard and any open child drawers (telemetry,
      // work orders, inspections, damage) drop their stale rows.
      qc.invalidateQueries({ queryKey: ['equipment'] });
      setDeleteOpen(false);
      onClose();
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    } finally {
      setDeleting(false);
    }
  };

  const telemetryQ = useQuery({
    queryKey: ['equipment', 'telemetry', id],
    queryFn: () => listTelemetry(id, { limit: 50 }),
    enabled: !!id && tab === 'utilization',
  });

  const wosQ = useQuery({
    queryKey: ['equipment', 'workOrders', id],
    queryFn: () => listMaintenanceWorkOrders({ equipment_id: id }),
    enabled: !!id && tab === 'maintenance',
  });

  const insQ = useQuery({
    queryKey: ['equipment', 'inspections', id],
    queryFn: () => listInspections(id),
    enabled: !!id && tab === 'certifications',
  });

  const damQ = useQuery({
    queryKey: ['equipment', 'damage', id],
    queryFn: () => listDamageReports({ equipment_id: id }),
    enabled: !!id && tab === 'damage',
  });

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="equipment-drawer-title"
    >
      <div className="absolute inset-0 bg-black/30" />
      <div
        className="relative h-full w-full max-w-2xl overflow-y-auto bg-surface-elevated shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-light bg-surface-elevated px-5 py-3 gap-3">
          <div className="min-w-0 flex-1">
            <h2
              id="equipment-drawer-title"
              className="text-base font-semibold truncate"
            >
              {eq ? `${eq.code} · ${eq.name}` : t('common.loading', { defaultValue: 'Loading…' })}
            </h2>
            {eq?.serial && (
              <p className="text-xs text-content-tertiary">SN: {eq.serial}</p>
            )}
          </div>
          {/* Action toolbar — Edit + Delete + Close. Disabled while the
              equipment is still loading so the buttons cannot fire
              against an undefined id. Each control is its own
              accessible button with aria-label rather than a tooltip-
              only icon, so screen-reader users get the same affordance. */}
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={() => setEditOpen(true)}
              disabled={!eq}
              className="inline-flex items-center gap-1.5 rounded-md border border-border-light bg-surface-primary px-2.5 py-1.5 text-xs font-medium text-content-secondary hover:text-oe-blue hover:border-oe-blue hover:bg-oe-blue-subtle transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label={t('common.edit', { defaultValue: 'Edit' })}
              title={t('equipment.edit_hint', {
                defaultValue: 'Edit equipment details',
              })}
            >
              <Pencil size={12} />
              {t('common.edit', { defaultValue: 'Edit' })}
            </button>
            <button
              type="button"
              onClick={() => setDeleteOpen(true)}
              disabled={!eq}
              className="inline-flex items-center gap-1.5 rounded-md border border-border-light bg-surface-primary px-2.5 py-1.5 text-xs font-medium text-content-secondary hover:text-rose-600 hover:border-rose-300 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label={t('common.delete', { defaultValue: 'Delete' })}
              title={t('equipment.delete_hint', {
                defaultValue: 'Permanently remove this asset',
              })}
            >
              <Trash2 size={12} />
              {t('common.delete', { defaultValue: 'Delete' })}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="ml-1 rounded p-1 hover:bg-surface-secondary"
              aria-label={t('common.close', { defaultValue: 'Close' })}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {!eq && eqQ.isLoading && (
          <div className="p-5">
            <SkeletonTable rows={6} columns={3} />
          </div>
        )}

        {!eq && !eqQ.isLoading && (
          <div className="p-5">
            <EmptyState
              icon={<AlertTriangle size={20} />}
              title={
                eqQ.isError
                  ? t('equipment.detail_error', {
                      defaultValue: 'Could not load this asset',
                    })
                  : t('equipment.detail_not_found', {
                      defaultValue: 'This asset no longer exists',
                    })
              }
              description={
                eqQ.isError ? getErrorMessage(eqQ.error) : undefined
              }
              action={
                eqQ.isError
                  ? {
                      label: t('common.retry', { defaultValue: 'Retry' }),
                      onClick: () => {
                        void eqQ.refetch();
                      },
                    }
                  : {
                      label: t('common.close', { defaultValue: 'Close' }),
                      onClick: onClose,
                    }
              }
            />
          </div>
        )}

        {eq && (
          <>
            <div className="grid grid-cols-2 gap-3 p-5 text-sm border-b border-border-light sm:grid-cols-4">
              <KV
                label={t('equipment.col_status', { defaultValue: 'Status' })}
                value={
                  <Badge variant={STATUS_VARIANT[eq.status]} dot>
                    {eq.status}
                  </Badge>
                }
              />
              <KV
                label={t('equipment.col_type', { defaultValue: 'Type' })}
                value={eq.type_code}
              />
              <KV
                label={t('equipment.ownership', { defaultValue: 'Ownership' })}
                value={eq.ownership}
              />
              <KV
                label={t('equipment.col_hours', { defaultValue: 'Hours' })}
                value={`${toNum(eq.hour_meter).toFixed(0)} h`}
              />
            </div>

            <div className="border-b border-border-light px-5">
              <nav className="flex gap-1 -mb-px">
                {(
                  [
                    {
                      id: 'utilization',
                      label: t('equipment.tab_utilization', {
                        defaultValue: 'Utilization',
                      }),
                      icon: Activity,
                    },
                    {
                      id: 'maintenance',
                      label: t('equipment.tab_maintenance', {
                        defaultValue: 'Maintenance',
                      }),
                      icon: Wrench,
                    },
                    {
                      id: 'certifications',
                      label: t('equipment.tab_certifications', {
                        defaultValue: 'Certifications',
                      }),
                      icon: ShieldCheck,
                    },
                    {
                      id: 'damage',
                      label: t('equipment.tab_damage', {
                        defaultValue: 'Damage',
                      }),
                      icon: AlertTriangle,
                    },
                  ] as { id: DrawerTab; label: string; icon: React.ElementType }[]
                ).map((ti) => {
                  const Icon = ti.icon;
                  return (
                    <button
                      key={ti.id}
                      type="button"
                      onClick={() => setTab(ti.id)}
                      className={clsx(
                        'flex items-center gap-2 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors',
                        tab === ti.id
                          ? 'border-oe-blue text-oe-blue'
                          : 'border-transparent text-content-secondary hover:text-content-primary',
                      )}
                    >
                      <Icon size={12} />
                      {ti.label}
                    </button>
                  );
                })}
              </nav>
            </div>

            <div className="p-5 space-y-3">
              {tab === 'utilization' && (
                <UtilizationTab
                  equipment={eq}
                  telemetry={telemetryQ.data ?? []}
                  loading={telemetryQ.isLoading}
                />
              )}
              {tab === 'maintenance' && (
                <MaintenanceTab
                  rows={wosQ.data ?? []}
                  loading={wosQ.isLoading}
                />
              )}
              {tab === 'certifications' && (
                <CertificationsTab
                  rows={insQ.data ?? []}
                  loading={insQ.isLoading}
                />
              )}
              {tab === 'damage' && (
                <DamageTab rows={damQ.data ?? []} loading={damQ.isLoading} />
              )}
            </div>
          </>
        )}
      </div>

      {/* Edit modal — only mounts when the user clicks "Edit" AND the
          equipment record has finished loading. The modal is portalled
          to fixed positioning so it escapes the drawer's overflow-y. */}
      {editOpen && eq && (
        <EquipmentFormModal
          mode="edit"
          existing={eq}
          onClose={() => setEditOpen(false)}
        />
      )}
      {/* Delete confirmation — destructive action, intentionally requires
          a second click. The danger-variant ConfirmDialog already
          handles focus trapping + Escape. */}
      <ConfirmDialog
        open={deleteOpen}
        title={t('equipment.delete_title', {
          defaultValue: 'Delete equipment?',
        })}
        message={
          eq
            ? t('equipment.delete_message', {
                defaultValue:
                  'Delete "{{name}}" ({{code}})? This removes all telemetry, work orders, inspections and damage reports linked to this asset. This action cannot be undone.',
                name: eq.name,
                code: eq.code,
              })
            : ''
        }
        confirmLabel={t('common.delete', { defaultValue: 'Delete' })}
        cancelLabel={t('common.cancel', { defaultValue: 'Cancel' })}
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteOpen(false)}
        loading={deleting}
      />
    </div>
  );
}

function UtilizationTab({
  equipment,
  telemetry,
  loading,
}: {
  equipment: Equipment;
  telemetry: { id: string; recorded_at: string; fuel_level?: number | string | null; hour_meter?: number | string | null; odometer_km?: number | string | null; engine_status?: string | null }[];
  loading: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <Card padding="sm">
          <p className="text-xs text-content-tertiary">
            {t('equipment.hour_meter', { defaultValue: 'Hour meter' })}
          </p>
          <p className="mt-1 text-lg font-semibold tabular-nums">
            {toNum(equipment.hour_meter).toFixed(0)} h
          </p>
        </Card>
        <Card padding="sm">
          <p className="text-xs text-content-tertiary">
            {t('equipment.odometer', { defaultValue: 'Odometer' })}
          </p>
          <p className="mt-1 text-lg font-semibold tabular-nums">
            {toNum(equipment.odometer_km).toFixed(0)} km
          </p>
        </Card>
        <Card padding="sm">
          <p className="text-xs text-content-tertiary">
            {t('equipment.last_telemetry', { defaultValue: 'Last reading' })}
          </p>
          <p className="mt-1 text-xs">
            {equipment.last_telemetry_at ? (
              <DateDisplay value={equipment.last_telemetry_at} />
            ) : (
              '—'
            )}
          </p>
        </Card>
      </div>

      {loading && <SkeletonTable rows={4} columns={4} />}
      {!loading && telemetry.length === 0 && (
        <EmptyState
          icon={<Activity size={20} />}
          title={t('equipment.no_telemetry', {
            defaultValue: 'No telemetry recorded',
          })}
        />
      )}
      {!loading && telemetry.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border-light">
          <table className="w-full text-xs">
            <thead className="bg-surface-secondary text-content-tertiary uppercase tracking-wide">
              <tr>
                <th className="px-3 py-2 text-left">
                  {t('equipment.recorded_at', { defaultValue: 'Recorded at' })}
                </th>
                <th className="px-3 py-2 text-right">
                  {t('equipment.col_hours', { defaultValue: 'Hours' })}
                </th>
                <th className="px-3 py-2 text-right">
                  {t('equipment.km', { defaultValue: 'km' })}
                </th>
                <th className="px-3 py-2 text-right">
                  {t('equipment.fuel_level', { defaultValue: 'Fuel %' })}
                </th>
                <th className="px-3 py-2 text-left">
                  {t('equipment.engine_status', {
                    defaultValue: 'Engine',
                  })}
                </th>
              </tr>
            </thead>
            <tbody>
              {telemetry.map((r) => (
                <tr key={r.id} className="border-t border-border-light">
                  <td className="px-3 py-2 text-content-secondary">
                    <DateDisplay value={r.recorded_at} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {r.hour_meter !== null && r.hour_meter !== undefined
                      ? toNum(r.hour_meter).toFixed(0)
                      : '—'}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {r.odometer_km !== null && r.odometer_km !== undefined
                      ? toNum(r.odometer_km).toFixed(0)
                      : '—'}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {r.fuel_level !== null && r.fuel_level !== undefined
                      ? `${toNum(r.fuel_level).toFixed(0)}%`
                      : '—'}
                  </td>
                  <td className="px-3 py-2 text-content-secondary">
                    {r.engine_status || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MaintenanceTab({
  rows,
  loading,
}: {
  rows: { id: string; status: WorkOrderStatus; scheduled_for?: string | null; completed_at?: string | null; technician_id?: string | null; work_summary?: string | null; cost: number | string; currency: string }[];
  loading: boolean;
}) {
  const { t } = useTranslation();
  if (loading) return <SkeletonTable rows={4} columns={4} />;
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<Wrench size={20} />}
        title={t('equipment.no_workorders', {
          defaultValue: 'No maintenance work orders',
        })}
      />
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-border-light">
      <table className="w-full text-xs">
        <thead className="bg-surface-secondary text-content-tertiary uppercase tracking-wide">
          <tr>
            <th className="px-3 py-2 text-left">
              {t('equipment.scheduled_for', { defaultValue: 'Scheduled' })}
            </th>
            <th className="px-3 py-2 text-left">
              {t('equipment.technician', { defaultValue: 'Technician' })}
            </th>
            <th className="px-3 py-2 text-left">
              {t('equipment.summary', { defaultValue: 'Summary' })}
            </th>
            <th className="px-3 py-2 text-right">
              {t('equipment.cost', { defaultValue: 'Cost' })}
            </th>
            <th className="px-3 py-2 text-left">
              {t('equipment.col_status', { defaultValue: 'Status' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-border-light">
              <td className="px-3 py-2 text-content-secondary">
                {r.scheduled_for || '—'}
              </td>
              <td className="px-3 py-2 text-content-secondary">
                {r.technician_id || '—'}
              </td>
              <td className="px-3 py-2 truncate max-w-[200px]">
                {r.work_summary || '—'}
              </td>
              <td className="px-3 py-2 text-right">
                <MoneyDisplay
                  amount={toNum(r.cost)}
                  currency={r.currency || undefined}
                />
              </td>
              <td className="px-3 py-2">
                <Badge variant={WO_STATUS_VARIANT[r.status]} dot>
                  {r.status}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CertificationsTab({
  rows,
  loading,
}: {
  rows: { id: string; inspection_type: string; inspected_at: string; valid_until: string; inspector_name?: string | null; result: InspectionResult }[];
  loading: boolean;
}) {
  const { t } = useTranslation();
  if (loading) return <SkeletonTable rows={3} columns={4} />;
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<ShieldCheck size={20} />}
        title={t('equipment.no_certifications', {
          defaultValue: 'No inspections recorded',
        })}
      />
    );
  }
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="overflow-x-auto rounded-lg border border-border-light">
      <table className="w-full text-xs">
        <thead className="bg-surface-secondary text-content-tertiary uppercase tracking-wide">
          <tr>
            <th className="px-3 py-2 text-left">
              {t('equipment.inspection_type', { defaultValue: 'Type' })}
            </th>
            <th className="px-3 py-2 text-left">
              {t('equipment.inspected_at', { defaultValue: 'Inspected' })}
            </th>
            <th className="px-3 py-2 text-left">
              {t('equipment.valid_until', { defaultValue: 'Valid until' })}
            </th>
            <th className="px-3 py-2 text-left">
              {t('equipment.inspector', { defaultValue: 'Inspector' })}
            </th>
            <th className="px-3 py-2 text-left">
              {t('equipment.result', { defaultValue: 'Result' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const expired = r.valid_until < today;
            return (
              <tr key={r.id} className="border-t border-border-light">
                <td className="px-3 py-2">{r.inspection_type}</td>
                <td className="px-3 py-2 text-content-secondary">
                  {r.inspected_at}
                </td>
                <td
                  className={clsx(
                    'px-3 py-2',
                    expired ? 'text-status-error font-medium' : 'text-content-secondary',
                  )}
                >
                  {r.valid_until}
                  {expired && (
                    <span className="ml-1 text-[10px] uppercase">
                      {t('equipment.expired', { defaultValue: 'expired' })}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-content-secondary">
                  {r.inspector_name || '—'}
                </td>
                <td className="px-3 py-2">
                  <Badge variant={INSPECTION_VARIANT[r.result]} dot>
                    {r.result}
                  </Badge>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DamageTab({
  rows,
  loading,
}: {
  rows: { id: string; reported_at: string; severity: DamageSeverity; description: string; repair_cost_estimate?: number | string | null; currency: string; status: string }[];
  loading: boolean;
}) {
  const { t } = useTranslation();
  if (loading) return <SkeletonTable rows={3} columns={4} />;
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<AlertTriangle size={20} />}
        title={t('equipment.no_damage', { defaultValue: 'No damage reports' })}
      />
    );
  }
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <Card key={r.id} padding="sm">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-xs text-content-tertiary">{r.reported_at}</p>
              <p className="mt-1 text-sm text-content-primary whitespace-pre-wrap">
                {r.description || '—'}
              </p>
            </div>
            <div className="flex flex-col items-end gap-1">
              <Badge variant={DAMAGE_VARIANT[r.severity]} dot>
                {r.severity}
              </Badge>
              <Badge variant="neutral">{r.status}</Badge>
            </div>
          </div>
          {r.repair_cost_estimate !== null &&
            r.repair_cost_estimate !== undefined && (
              <p className="mt-2 text-xs text-content-secondary">
                {t('equipment.repair_estimate', {
                  defaultValue: 'Repair estimate',
                })}
                :{' '}
                <MoneyDisplay
                  amount={toNum(r.repair_cost_estimate)}
                  currency={r.currency || undefined}
                />
              </p>
            )}
        </Card>
      ))}
    </div>
  );
}

function KV({ label, value }: { label: React.ReactNode; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-content-tertiary">
        {label}
      </p>
      <p className="mt-0.5 text-sm text-content-primary">{value}</p>
    </div>
  );
}

/* ─── Equipment form modal (create + edit) ────────────────────────────
 *
 * Single component used for both new-asset registration and editing an
 * existing record. Centralising create + edit in one form keeps the
 * field list, validation rules and UX in lock-step — when a senior
 * reviewer adds a new property (warranty_expiry, GPS provider, …)
 * they only touch one component.
 *
 * Mode semantics:
 *   • mode="create" — POST /api/v1/equipment/equipment/. ``existing`` MUST be omitted.
 *   • mode="edit"   — PATCH /api/v1/equipment/equipment/{id}. ``existing`` is required;
 *                     fields are pre-filled from it and only changed
 *                     fields end up in the PATCH body (avoids touching
 *                     server-managed columns like depreciation_method
 *                     when the user only edits the name).
 *
 * All numeric inputs accept blank strings to mean "no value"; converted
 * to ``number | undefined`` on submit so the backend's Decimal columns
 * receive nulls instead of zeros when the field is intentionally empty.
 */

interface EquipmentFormState {
  code: string;
  name: string;
  type_code: string;
  manufacturer: string;
  model: string;
  serial: string;
  ownership: Ownership;
  status: EquipmentStatus;
  year: string;                   // text input — empty = unset
  purchase_date: string;          // ISO yyyy-mm-dd, empty = unset
  purchase_value: string;
  currency: string;
  useful_life_years: string;
  residual_value: string;
  hour_meter: string;
  odometer_km: string;
  location_lat: string;
  location_lng: string;
  notes: string;
}

function _toFormState(eq: Equipment | undefined): EquipmentFormState {
  // Decimal/numeric columns come back as ``number | string`` from the
  // backend (depending on JSON serialiser). Normalise to string so the
  // <input> stays controlled and round-trips losslessly.
  const numStr = (v: number | string | null | undefined): string =>
    v === null || v === undefined || v === '' ? '' : String(v);
  return {
    code: eq?.code ?? '',
    name: eq?.name ?? '',
    type_code: eq?.type_code ?? 'other',
    manufacturer: eq?.manufacturer ?? '',
    model: eq?.model ?? '',
    serial: eq?.serial ?? '',
    ownership: (eq?.ownership ?? 'owned') as Ownership,
    status: (eq?.status ?? 'active') as EquipmentStatus,
    year: eq?.year ? String(eq.year) : '',
    purchase_date: eq?.purchase_date ?? '',
    purchase_value: numStr(eq?.purchase_value),
    currency: eq?.currency ?? '',
    useful_life_years: eq?.useful_life_years
      ? String(eq.useful_life_years)
      : '',
    residual_value: numStr(eq?.residual_value),
    hour_meter: numStr(eq?.hour_meter),
    odometer_km: numStr(eq?.odometer_km),
    location_lat: numStr(eq?.location_lat),
    location_lng: numStr(eq?.location_lng),
    notes: eq?.notes ?? '',
  };
}

function _toPayload(
  form: EquipmentFormState,
): CreateEquipmentPayload {
  // Empty-string → undefined so backend models leave server-managed
  // defaults (e.g. depreciation_method, decimal columns) alone.
  const toOptStr = (v: string): string | undefined =>
    v.trim() === '' ? undefined : v.trim();
  const toOptNum = (v: string): number | undefined => {
    if (v.trim() === '') return undefined;
    const n = Number(v.replace(',', '.'));
    return Number.isFinite(n) ? n : undefined;
  };
  return {
    code: form.code.trim(),
    name: form.name.trim(),
    type_code: form.type_code.trim() || 'other',
    manufacturer: toOptStr(form.manufacturer),
    model: toOptStr(form.model),
    serial: toOptStr(form.serial),
    year: toOptNum(form.year),
    ownership: form.ownership,
    status: form.status,
    hour_meter: toOptNum(form.hour_meter),
    odometer_km: toOptNum(form.odometer_km),
    purchase_date: toOptStr(form.purchase_date),
    purchase_value: toOptNum(form.purchase_value),
    currency: toOptStr(form.currency),
    notes: toOptStr(form.notes),
  };
}

interface EquipmentFormModalProps {
  mode: 'create' | 'edit';
  existing?: Equipment;
  onClose: () => void;
}

function EquipmentFormModal({
  mode,
  existing,
  onClose,
}: EquipmentFormModalProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<EquipmentFormState>(() =>
    _toFormState(existing),
  );

  // Close on Escape — symmetric with the rest of the modal stack so
  // keyboard users get a predictable dismissal.
  // No focus trap here (the existing CreateModal didn't have one
  // either) — handled separately when we add the design-system Modal.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', handler, { capture: true });
    return () =>
      document.removeEventListener('keydown', handler, { capture: true });
  }, [busy, onClose]);

  const submit = async () => {
    if (!form.code.trim() || !form.name.trim()) {
      addToast({
        type: 'error',
        title: t('equipment.code_name_required', {
          defaultValue: 'Code and name are required',
        }),
      });
      return;
    }
    setBusy(true);
    try {
      const payload = _toPayload(form);
      if (mode === 'edit' && existing) {
        // Diff against the original so server-managed columns aren't
        // touched when only the name was changed. This also keeps PATCH
        // requests small and audit logs readable.
        const originalPayload = _toPayload(_toFormState(existing));
        const diff: Partial<CreateEquipmentPayload> = {};
        // Index through ``unknown`` first to satisfy strict-mode TS —
        // CreateEquipmentPayload doesn't carry an index signature, so
        // we explicitly opt into property-bag semantics for the diff.
        const originalRecord = originalPayload as unknown as Record<
          string,
          unknown
        >;
        const newRecord = payload as unknown as Record<string, unknown>;
        const diffRecord = diff as unknown as Record<string, unknown>;
        (Object.keys(payload) as (keyof CreateEquipmentPayload)[]).forEach(
          (k) => {
            if (originalRecord[k] !== newRecord[k]) {
              diffRecord[k] = newRecord[k];
            }
          },
        );
        if (Object.keys(diff).length === 0) {
          // Nothing changed — close without surprising the user with a
          // toast that says "updated" when nothing actually changed.
          onClose();
          return;
        }
        await updateEquipment(existing.id, diff);
        addToast({
          type: 'success',
          title: t('equipment.updated', {
            defaultValue: '{{name}} updated',
            name: form.name.trim(),
          }),
        });
      } else {
        await createEquipment(payload);
        addToast({
          type: 'success',
          title: t('equipment.created', { defaultValue: 'Equipment created' }),
        });
      }
      // Invalidate the whole equipment query family so every dashboard
      // (list view + detail drawer + fleet kpis) re-fetches.
      qc.invalidateQueries({ queryKey: ['equipment'] });
      onClose();
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  const set = <K extends keyof EquipmentFormState>(
    key: K,
    value: EquipmentFormState[K],
  ): void => setForm((prev) => ({ ...prev, [key]: value }));

  const isEdit = mode === 'edit';

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-3"
      onClick={() => !busy && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="equipment-form-title"
    >
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div
        className="relative w-full max-w-2xl max-h-[92vh] overflow-y-auto rounded-xl bg-surface-elevated p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2
            id="equipment-form-title"
            className="text-lg font-semibold text-content-primary"
          >
            {isEdit
              ? t('equipment.edit_title', {
                  defaultValue: 'Edit equipment',
                })
              : t('equipment.new', { defaultValue: 'New Asset' })}
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded p-1 hover:bg-surface-secondary disabled:opacity-50"
            aria-label={t('common.close', { defaultValue: 'Close' })}
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4">
          {/* ── Section: Identity ─────────────────────────────────── */}
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-2">
              {t('equipment.section_identity', {
                defaultValue: 'Identity',
              })}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>
                  {t('equipment.col_code', { defaultValue: 'Code' })}{' '}
                  <span className="text-rose-500">*</span>
                </label>
                <input
                  value={form.code}
                  onChange={(e) => set('code', e.target.value)}
                  className={inputCls}
                  placeholder="EXC-001"
                  // Code is the human-readable handle for the asset and
                  // is also used in URLs / barcodes — disallow editing
                  // on existing records to keep cross-references stable.
                  disabled={isEdit}
                  title={
                    isEdit
                      ? t('equipment.code_immutable_hint', {
                          defaultValue:
                            'Asset code is immutable after creation to keep barcodes / external references stable.',
                        })
                      : undefined
                  }
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.col_type', { defaultValue: 'Type code' })}
                </label>
                <input
                  value={form.type_code}
                  onChange={(e) => set('type_code', e.target.value)}
                  className={inputCls}
                  placeholder="excavator, crane, generator…"
                />
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>
                  {t('equipment.col_name', { defaultValue: 'Name' })}{' '}
                  <span className="text-rose-500">*</span>
                </label>
                <input
                  value={form.name}
                  onChange={(e) => set('name', e.target.value)}
                  className={inputCls}
                  placeholder={t('equipment.name_placeholder', {
                    defaultValue: 'CAT 320 Excavator – Site A',
                  })}
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.manufacturer', { defaultValue: 'Manufacturer' })}
                </label>
                <input
                  value={form.manufacturer}
                  onChange={(e) => set('manufacturer', e.target.value)}
                  className={inputCls}
                  placeholder="Caterpillar"
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.model', { defaultValue: 'Model' })}
                </label>
                <input
                  value={form.model}
                  onChange={(e) => set('model', e.target.value)}
                  className={inputCls}
                  placeholder="320 GC"
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.serial', { defaultValue: 'Serial number' })}
                </label>
                <input
                  value={form.serial}
                  onChange={(e) => set('serial', e.target.value)}
                  className={inputCls}
                  placeholder="VIN / serial / asset number"
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.year', { defaultValue: 'Year of manufacture' })}
                </label>
                <input
                  type="number"
                  inputMode="numeric"
                  min={1900}
                  max={new Date().getFullYear() + 1}
                  value={form.year}
                  onChange={(e) => set('year', e.target.value)}
                  className={inputCls}
                  placeholder="2022"
                />
              </div>
            </div>
          </section>

          {/* ── Section: Lifecycle ──────────────────────────────── */}
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-2">
              {t('equipment.section_lifecycle', {
                defaultValue: 'Lifecycle & status',
              })}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>
                  {t('equipment.ownership', { defaultValue: 'Ownership' })}
                </label>
                <select
                  value={form.ownership}
                  onChange={(e) =>
                    set('ownership', e.target.value as Ownership)
                  }
                  className={inputCls}
                >
                  {(['owned', 'rented', 'leased'] as Ownership[]).map((o) => (
                    <option key={o} value={o}>
                      {t(`equipment.ownership_${o}`, {
                        defaultValue: o,
                      })}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.col_status', { defaultValue: 'Status' })}
                </label>
                <select
                  value={form.status}
                  onChange={(e) =>
                    set('status', e.target.value as EquipmentStatus)
                  }
                  className={inputCls}
                >
                  {(
                    [
                      'active',
                      'under_maintenance',
                      'decommissioned',
                      'reserved',
                    ] as EquipmentStatus[]
                  ).map((s) => (
                    <option key={s} value={s}>
                      {t(`equipment.status_${s}`, {
                        defaultValue: s,
                      })}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.purchase_date', {
                    defaultValue: 'Purchase / start date',
                  })}
                </label>
                <input
                  type="date"
                  value={form.purchase_date}
                  onChange={(e) => set('purchase_date', e.target.value)}
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.useful_life_years', {
                    defaultValue: 'Useful life (years)',
                  })}
                </label>
                <input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={100}
                  value={form.useful_life_years}
                  onChange={(e) => set('useful_life_years', e.target.value)}
                  className={inputCls}
                  placeholder="10"
                />
              </div>
            </div>
          </section>

          {/* ── Section: Financial ─────────────────────────────── */}
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-2">
              {t('equipment.section_financial', {
                defaultValue: 'Financial',
              })}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className={labelCls}>
                  {t('equipment.purchase_value', {
                    defaultValue: 'Purchase value',
                  })}
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={form.purchase_value}
                  onChange={(e) => set('purchase_value', e.target.value)}
                  className={inputCls}
                  placeholder="125000"
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.residual_value', {
                    defaultValue: 'Residual value',
                  })}
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={form.residual_value}
                  onChange={(e) => set('residual_value', e.target.value)}
                  className={inputCls}
                  placeholder="15000"
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.currency', { defaultValue: 'Currency' })}
                </label>
                <input
                  value={form.currency}
                  onChange={(e) => set('currency', e.target.value.toUpperCase().slice(0, 3))}
                  className={inputCls}
                  placeholder="EUR"
                  maxLength={3}
                />
              </div>
            </div>
          </section>

          {/* ── Section: Telemetry & location ───────────────── */}
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-2">
              {t('equipment.section_telemetry', {
                defaultValue: 'Telemetry & location',
              })}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>
                  {t('equipment.hour_meter', { defaultValue: 'Hour meter' })}
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={form.hour_meter}
                  onChange={(e) => set('hour_meter', e.target.value)}
                  className={inputCls}
                  placeholder="1234"
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.odometer_km', { defaultValue: 'Odometer (km)' })}
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={form.odometer_km}
                  onChange={(e) => set('odometer_km', e.target.value)}
                  className={inputCls}
                  placeholder="42000"
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.location_lat', {
                    defaultValue: 'Location latitude',
                  })}
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={form.location_lat}
                  onChange={(e) => set('location_lat', e.target.value)}
                  className={inputCls}
                  placeholder="52.5200"
                />
              </div>
              <div>
                <label className={labelCls}>
                  {t('equipment.location_lng', {
                    defaultValue: 'Location longitude',
                  })}
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={form.location_lng}
                  onChange={(e) => set('location_lng', e.target.value)}
                  className={inputCls}
                  placeholder="13.4050"
                />
              </div>
            </div>
          </section>

          {/* ── Section: Notes ───────────────────────────────── */}
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-2">
              {t('equipment.section_notes', { defaultValue: 'Notes' })}
            </h3>
            <textarea
              value={form.notes}
              onChange={(e) => set('notes', e.target.value)}
              className={clsx(inputCls, 'min-h-[80px] py-2 leading-snug')}
              placeholder={t('equipment.notes_placeholder', {
                defaultValue:
                  'Operator notes, warranty contact, attachments, certificate IDs…',
              })}
              maxLength={2000}
              rows={3}
            />
          </section>
        </div>

        <div className="flex justify-end gap-2 mt-5 sticky bottom-0 pt-3 -mx-5 -mb-5 px-5 pb-3 bg-surface-elevated border-t border-border-light">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            loading={busy}
            icon={
              busy ? (
                <Loader2 size={14} />
              ) : isEdit ? (
                <Save size={14} />
              ) : (
                <Plus size={14} />
              )
            }
          >
            {isEdit
              ? t('common.save', { defaultValue: 'Save changes' })
              : t('common.create', { defaultValue: 'Create' })}
          </Button>
        </div>
      </div>
    </div>
  );
}
