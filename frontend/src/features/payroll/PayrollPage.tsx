import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { Wallet, Plus, Users, Coins, Loader2, ChevronRight, CheckCircle2 } from 'lucide-react';
import {
  Button,
  Card,
  Badge,
  EmptyState,
  Breadcrumb,
  ConfirmDialog,
  DateDisplay,
  Skeleton,
} from '@/shared/ui';
import { RequiresProject } from '@/shared/auth/RequiresProject';
import { useToastStore } from '@/stores/useToastStore';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { getErrorMessage } from '@/shared/lib/api';
import {
  fetchPayrollBatches,
  fetchPayrollBatch,
  generatePayrollBatch,
  finalizeBatch,
  fetchLabourCost,
} from './api';
import type { PayrollBatch } from './api';

/* ── Helpers ───────────────────────────────────────────────────────────── */

function money(value: string | number, currency?: string): string {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return String(value);
  try {
    return new Intl.NumberFormat(undefined, {
      style: currency ? 'currency' : 'decimal',
      currency: currency || undefined,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n);
  } catch {
    return n.toFixed(2);
  }
}

function hours(value: string): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : value;
}

/* ── Page ──────────────────────────────────────────────────────────────── */

export default function PayrollPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const activeProjectName = useProjectContextStore((s) => s.activeProjectName);
  const projectId = activeProjectId ?? '';

  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [confirmFinalizeOpen, setConfirmFinalizeOpen] = useState(false);

  const batchesQuery = useQuery({
    queryKey: ['payroll', 'batches', projectId],
    queryFn: () => fetchPayrollBatches(projectId),
    enabled: Boolean(projectId),
  });

  const labourCostQuery = useQuery({
    queryKey: ['payroll', 'labour-cost', projectId],
    queryFn: () => fetchLabourCost(projectId),
    enabled: Boolean(projectId),
  });

  const batchDetailQuery = useQuery({
    queryKey: ['payroll', 'batch', selectedBatchId],
    queryFn: () => fetchPayrollBatch(selectedBatchId as string),
    enabled: Boolean(selectedBatchId),
  });

  const generateMut = useMutation({
    mutationFn: () => generatePayrollBatch(projectId, {}),
    onSuccess: (batch) => {
      addToast({
        type: 'success',
        title: '',
        message: t('payroll.generated', {
          defaultValue: 'Draft payroll batch generated ({{count}} entries).',
          count: batch.entry_count,
        }),
      });
      void queryClient.invalidateQueries({ queryKey: ['payroll', 'batches', projectId] });
      setSelectedBatchId(batch.id);
    },
    onError: (err) => {
      addToast({
        type: 'error',
        title: t('common.error', { defaultValue: 'Error' }),
        message: getErrorMessage(err),
      });
    },
  });

  const finalizeMut = useMutation({
    mutationFn: (batchId: string) => finalizeBatch(batchId),
    onSuccess: (batch) => {
      addToast({
        type: 'success',
        title: '',
        message: t('payroll.finalized', {
          defaultValue: 'Batch approved. Labour cost posted to the budget.',
        }),
      });
      // Refresh the list (status badge) and the open detail (Finalize hidden).
      void queryClient.invalidateQueries({ queryKey: ['payroll', 'batches', projectId] });
      void queryClient.invalidateQueries({ queryKey: ['payroll', 'batch', batch.id] });
    },
    onError: (err) => {
      addToast({
        type: 'error',
        title: t('common.error', { defaultValue: 'Error' }),
        message: getErrorMessage(err),
      });
    },
  });

  const handleSelect = useCallback((id: string) => {
    setSelectedBatchId((prev) => (prev === id ? null : id));
  }, []);

  const selectedBatch = batchDetailQuery.data ?? null;
  const canFinalize = selectedBatch?.status === 'draft';

  const handleConfirmFinalize = useCallback(() => {
    if (!selectedBatchId) return;
    finalizeMut.mutate(selectedBatchId, {
      onSettled: () => setConfirmFinalizeOpen(false),
    });
  }, [finalizeMut, selectedBatchId]);

  /* Project gate */
  if (!projectId) {
    return (
      <div className="p-6">
        <RequiresProject
          emptyHint={t('payroll.no_project_desc', {
            defaultValue: 'Choose a project from the sidebar to view payroll.',
          })}
        >
          {null}
        </RequiresProject>
      </div>
    );
  }

  const batches = batchesQuery.data ?? [];
  const labourCost = labourCostQuery.data ?? null;

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <Breadcrumb
        items={[
          { label: t('nav.dashboard', { defaultValue: 'Dashboard' }), to: '/' },
          { label: t('payroll.title', { defaultValue: 'Payroll' }) },
        ]}
      />

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
            <Wallet size={22} />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-content-primary">
              {t('payroll.title', { defaultValue: 'Payroll' })}
            </h1>
            <p className="text-sm text-content-tertiary">{activeProjectName}</p>
          </div>
        </div>
        <Button
          variant="primary"
          onClick={() => generateMut.mutate()}
          disabled={generateMut.isPending}
          aria-label={t('payroll.generate', { defaultValue: 'Generate draft batch' })}
        >
          {generateMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus size={16} />}
          {t('payroll.generate', { defaultValue: 'Generate draft batch' })}
        </Button>
      </div>

      {/* Labour cost rollup (surfaced beside the cost model) */}
      <Card className="p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
            <Coins size={18} />
          </div>
          <div className="flex-1">
            <p className="text-xs uppercase tracking-wide text-content-tertiary">
              {t('payroll.labour_cost', { defaultValue: 'Labour cost' })}
            </p>
            {labourCostQuery.isLoading ? (
              <Skeleton className="mt-1 h-6 w-32" />
            ) : (
              <p className="text-lg font-semibold text-content-primary">
                {labourCost ? money(labourCost.labour_cost, labourCost.currency || undefined) : '-'}
                {labourCost && (
                  <span className="ml-2 text-sm font-normal text-content-tertiary">
                    {t('payroll.over_hours', {
                      defaultValue: 'over {{hours}} h',
                      hours: hours(labourCost.total_hours),
                    })}
                  </span>
                )}
              </p>
            )}
          </div>
        </div>
      </Card>

      {/* Batch list */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="p-0">
          <div className="border-b border-border-subtle px-4 py-3">
            <h2 className="text-sm font-semibold text-content-primary">
              {t('payroll.batches', { defaultValue: 'Pay batches' })}
            </h2>
          </div>
          {batchesQuery.isLoading ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : batches.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={<Wallet size={28} />}
                title={t('payroll.empty_title', { defaultValue: 'No payroll batches yet' })}
                description={t('payroll.empty_desc', {
                  defaultValue: 'Generate a draft batch to aggregate field labour into pay entries.',
                })}
              />
            </div>
          ) : (
            <ul className="divide-y divide-border-subtle">
              {batches.map((b: PayrollBatch) => (
                <li key={b.id}>
                  <button
                    type="button"
                    onClick={() => handleSelect(b.id)}
                    className={clsx(
                      'flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-surface-hover',
                      selectedBatchId === b.id && 'bg-surface-hover',
                    )}
                    aria-pressed={selectedBatchId === b.id}
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-content-primary">{b.period_label}</span>
                        <Badge variant={b.status === 'approved' ? 'success' : 'neutral'}>
                          {t(`payroll.status.${b.status}`, { defaultValue: b.status })}
                        </Badge>
                      </div>
                      <p className="text-xs text-content-tertiary">
                        <DateDisplay value={b.created_at} format="date" />
                        {' · '}
                        {t('payroll.entry_count', { defaultValue: '{{count}} entries', count: b.entry_count })}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold text-content-primary">
                        {money(b.total_amount, b.currency || undefined)}
                      </p>
                      <p className="text-xs text-content-tertiary">{hours(b.total_hours)} h</p>
                    </div>
                    <ChevronRight size={16} className="text-content-tertiary" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Entries for the selected batch */}
        <Card className="p-0">
          <div className="flex items-center justify-between gap-2 border-b border-border-subtle px-4 py-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-content-primary">
              <Users size={16} />
              {t('payroll.entries', { defaultValue: 'Entries' })}
            </h2>
            {canFinalize && (
              <Button
                variant="primary"
                size="sm"
                onClick={() => setConfirmFinalizeOpen(true)}
                disabled={finalizeMut.isPending}
                aria-label={t('payroll.finalize', { defaultValue: 'Finalize batch' })}
              >
                {finalizeMut.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 size={16} />
                )}
                {t('payroll.finalize', { defaultValue: 'Finalize batch' })}
              </Button>
            )}
          </div>
          {!selectedBatchId ? (
            <div className="p-6 text-sm text-content-tertiary">
              {t('payroll.select_batch', { defaultValue: 'Select a batch to view its entries.' })}
            </div>
          ) : batchDetailQuery.isLoading ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-subtle text-left text-xs uppercase tracking-wide text-content-tertiary">
                    <th className="px-4 py-2">{t('payroll.col.worker', { defaultValue: 'Worker' })}</th>
                    <th className="px-4 py-2">{t('payroll.col.date', { defaultValue: 'Date' })}</th>
                    <th className="px-4 py-2 text-right">{t('payroll.col.hours', { defaultValue: 'Hours' })}</th>
                    <th className="px-4 py-2 text-right">{t('payroll.col.rate', { defaultValue: 'Rate' })}</th>
                    <th className="px-4 py-2 text-right">{t('payroll.col.amount', { defaultValue: 'Amount' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {(batchDetailQuery.data?.entries ?? []).map((e) => (
                    <tr key={e.id} className="border-b border-border-subtle/60">
                      <td className="px-4 py-2 text-content-primary">{e.worker}</td>
                      <td className="px-4 py-2 text-content-secondary">
                        {e.work_date ? <DateDisplay value={e.work_date} format="date" /> : '-'}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">{hours(e.hours)}</td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {money(e.rate, e.currency || undefined)}
                      </td>
                      <td className="px-4 py-2 text-right font-medium tabular-nums">
                        {money(e.amount, e.currency || undefined)}
                      </td>
                    </tr>
                  ))}
                  {(batchDetailQuery.data?.entries ?? []).length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-6 text-center text-content-tertiary">
                        {t('payroll.no_entries', { defaultValue: 'This batch has no entries.' })}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <ConfirmDialog
        open={confirmFinalizeOpen}
        variant="warning"
        title={t('payroll.finalize_confirm_title', { defaultValue: 'Approve batch?' })}
        message={t('payroll.finalize_confirm_message', {
          defaultValue: 'Labour cost will post to the project budget. This cannot be undone.',
        })}
        confirmLabel={t('payroll.finalize', { defaultValue: 'Finalize batch' })}
        cancelLabel={t('confirm_dialog.cancel', { defaultValue: 'Cancel' })}
        loading={finalizeMut.isPending}
        onConfirm={handleConfirmFinalize}
        onCancel={() => setConfirmFinalizeOpen(false)}
      />
    </div>
  );
}
