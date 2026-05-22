// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// SupplierScorecardModal — trailing-window supplier KPI dialog (Wave 2 / T4).
//
// Opens from the supplier name in any PO row and surfaces three KPI tiles
// (on-time delivery %, qty variance %, GR rejection rate) plus the
// trailing-12-month PO summary. The data comes from
// GET /v1/procurement/suppliers/{contact_id}/scorecard.

import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { Loader2, TrendingUp, AlertTriangle, Truck } from 'lucide-react';
import { WideModal, Badge, EmptyState } from '@/shared/ui';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { getSupplierScorecard } from './api';

interface SupplierScorecardModalProps {
  open: boolean;
  onClose: () => void;
  contactId: string;
  contactName?: string | null;
  projectId?: string;
}

type TileTone = 'success' | 'warning' | 'error' | 'neutral';

function pctTone(
  value: number,
  thresholds: { good: number; warn: number },
  invert = false,
): TileTone {
  // Default: higher = better. `invert` flips so higher = worse
  // (rejection / variance).
  const v = value;
  if (invert) {
    if (v <= thresholds.good) return 'success';
    if (v <= thresholds.warn) return 'warning';
    return 'error';
  }
  if (v >= thresholds.good) return 'success';
  if (v >= thresholds.warn) return 'warning';
  return 'error';
}

const TONE_BG: Record<TileTone, string> = {
  success: 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-900',
  warning: 'bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900',
  error: 'bg-rose-50 dark:bg-rose-950/20 border-rose-200 dark:border-rose-900',
  neutral: 'bg-surface-secondary border-border',
};

const TONE_TEXT: Record<TileTone, string> = {
  success: 'text-emerald-700 dark:text-emerald-400',
  warning: 'text-amber-700 dark:text-amber-400',
  error: 'text-rose-700 dark:text-rose-400',
  neutral: 'text-content-primary',
};

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function SupplierScorecardModal({
  open,
  onClose,
  contactId,
  contactName,
  projectId,
}: SupplierScorecardModalProps) {
  const { t } = useTranslation();

  const {
    data: scorecard,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['procurement-scorecard', contactId, projectId ?? null],
    queryFn: () => getSupplierScorecard(contactId, { projectId }),
    enabled: open && Boolean(contactId),
  });

  const title =
    contactName ||
    scorecard?.supplier_name ||
    t('procurement.scorecard_title', { defaultValue: 'Supplier scorecard' });

  return (
    <WideModal
      open={open}
      onClose={onClose}
      title={title}
      subtitle={t('procurement.scorecard_subtitle', {
        defaultValue: 'Trailing {{days}}-day performance',
        days: scorecard?.period_days ?? 365,
      })}
      size="lg"
    >
      {isLoading && (
        <div className="flex items-center justify-center py-12 text-content-tertiary">
          <Loader2 size={20} className="animate-spin mr-2" />
          {t('common.loading', { defaultValue: 'Loading...' })}
        </div>
      )}

      {isError && !isLoading && (
        <EmptyState
          icon={<AlertTriangle size={24} strokeWidth={1.5} />}
          title={t('common.error', { defaultValue: 'Error' })}
          description={t('procurement.scorecard_load_error', {
            defaultValue: 'Failed to load supplier scorecard.',
          })}
        />
      )}

      {scorecard && !isLoading && (
        <div className="space-y-6">
          {/* ── Summary row ────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <SummaryStat
              label={t('procurement.scorecard_total_pos', {
                defaultValue: 'Purchase orders',
              })}
              value={scorecard.total_po_count.toLocaleString()}
            />
            <SummaryStat
              label={t('procurement.scorecard_total_grs', {
                defaultValue: 'Goods receipts',
              })}
              value={scorecard.total_gr_count.toLocaleString()}
            />
            <SummaryStat
              label={t('procurement.scorecard_total_value', {
                defaultValue: 'Total PO value',
              })}
              value={
                scorecard.currency ? (
                  <MoneyDisplay
                    amount={scorecard.total_po_value}
                    currency={scorecard.currency}
                  />
                ) : (
                  scorecard.total_po_value
                )
              }
            />
          </div>

          {/* ── KPI tiles ──────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <KpiTile
              icon={<Truck size={18} />}
              label={t('procurement.scorecard_on_time', {
                defaultValue: 'On-time delivery',
              })}
              value={formatPct(scorecard.on_time_delivery_pct)}
              tone={pctTone(scorecard.on_time_delivery_pct, {
                good: 0.9,
                warn: 0.75,
              })}
            />
            <KpiTile
              icon={<TrendingUp size={18} />}
              label={t('procurement.scorecard_qty_variance', {
                defaultValue: 'Qty variance',
              })}
              value={formatPct(scorecard.qty_variance_pct)}
              tone={pctTone(
                scorecard.qty_variance_pct,
                { good: 0.05, warn: 0.15 },
                true,
              )}
            />
            <KpiTile
              icon={<AlertTriangle size={18} />}
              label={t('procurement.scorecard_rejection', {
                defaultValue: 'GR rejection',
              })}
              value={formatPct(scorecard.gr_rejection_rate)}
              tone={pctTone(
                scorecard.gr_rejection_rate,
                { good: 0.02, warn: 0.1 },
                true,
              )}
            />
          </div>

          {/* ── Empty-state hint when there is no data ─────────────────── */}
          {scorecard.total_po_count === 0 && (
            <div className="rounded-lg border border-border-light bg-surface-secondary/40 px-4 py-6 text-center text-sm text-content-tertiary">
              {t('procurement.scorecard_empty', {
                defaultValue:
                  'No purchase orders for this supplier in the trailing window yet.',
              })}
            </div>
          )}
        </div>
      )}
    </WideModal>
  );
}

/* ── Small subcomponents ───────────────────────────────────────────────── */

function SummaryStat({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface-primary px-4 py-3">
      <div className="text-2xs uppercase tracking-wider font-medium text-content-tertiary">
        {label}
      </div>
      <div className="mt-1 text-base font-semibold tabular-nums text-content-primary">
        {value}
      </div>
    </div>
  );
}

function KpiTile({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: TileTone;
}) {
  return (
    <div className={`rounded-lg border px-4 py-4 ${TONE_BG[tone]}`}>
      <div className="flex items-center justify-between">
        <div className={`flex items-center gap-2 text-xs font-medium ${TONE_TEXT[tone]}`}>
          {icon}
          <span>{label}</span>
        </div>
        <Badge
          variant={
            tone === 'success'
              ? 'success'
              : tone === 'warning'
                ? 'warning'
                : tone === 'error'
                  ? 'error'
                  : 'neutral'
          }
          size="sm"
        >
          {tone === 'success'
            ? 'good'
            : tone === 'warning'
              ? 'warn'
              : tone === 'error'
                ? 'risk'
                : '-'}
        </Badge>
      </div>
      <div className={`mt-2 text-2xl font-bold tabular-nums ${TONE_TEXT[tone]}`}>
        {value}
      </div>
    </div>
  );
}
