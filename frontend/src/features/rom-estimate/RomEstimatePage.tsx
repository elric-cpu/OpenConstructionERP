import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  Calculator,
  AlertTriangle,
  Scale,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  type LucideIcon,
} from 'lucide-react';
import { Card, CardHeader, CardContent } from '@/shared/ui';
import { formatCurrency, toNum } from '@/shared/lib/money';
import { useActiveProjectId } from '@/shared/hooks/useActiveProjectId';
import { romEstimateApi, type RomEstimateResult, type RomReconciliation } from './api';

/**
 * Conceptual (ROM) estimate page.
 *
 * From four inputs (building type, gross floor area, quality, region) it asks
 * the backend for an instant order-of-magnitude estimate and renders the
 * headline total, an honest accuracy band and the six-element cost breakdown.
 * It is the day-one starting point a detailed take-off later refines.
 *
 * Money and ratios arrive as Decimal strings; they are only ever coerced for
 * display through the shared money helpers, never float-mathed here.
 */

const INPUT_CLASS =
  'w-full rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary ' +
  'placeholder:text-content-tertiary focus:border-oe-blue focus:outline-none focus:ring-1 focus:ring-oe-blue';

/** Format a percentage Decimal string as a signed whole-number percent. */
function formatPct(value: string): string {
  const n = toNum(value);
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(0)}%`;
}

export function RomEstimatePage() {
  const { t } = useTranslation();

  const referenceQuery = useQuery({
    queryKey: ['rom-estimate', 'reference'],
    queryFn: romEstimateApi.reference,
    staleTime: 60 * 60 * 1000,
  });

  const [buildingType, setBuildingType] = useState('');
  const [quality, setQuality] = useState('standard');
  const [region, setRegion] = useState('global');
  const [area, setArea] = useState('');
  const [currency, setCurrency] = useState('');

  // Seed the selectors from the reference table once it loads.
  const reference = referenceQuery.data;
  useEffect(() => {
    if (!reference) return;
    setBuildingType((prev) => prev || reference.building_types[0]?.key || '');
    setQuality((prev) => prev || reference.default_quality || 'standard');
    setRegion((prev) => prev || reference.default_region || 'global');
  }, [reference]);

  const generate = useMutation({
    mutationFn: () =>
      romEstimateApi.generate({
        building_type: buildingType,
        gross_floor_area: area,
        quality,
        region,
        gfa_unit: 'm2',
        currency: currency.trim().toUpperCase(),
      }),
  });

  const areaNum = parseFloat(area);
  const canGenerate = Boolean(buildingType) && !Number.isNaN(areaNum) && areaNum > 0;
  const result = generate.data;

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (canGenerate) generate.mutate();
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-content-primary">
          <Calculator size={22} />
          {t('romEstimate.title', { defaultValue: 'Conceptual Estimate' })}
        </h1>
        <p className="mt-1 text-sm text-content-secondary">
          {t('romEstimate.subtitle', {
            defaultValue:
              'A rapid order-of-magnitude cost from just building type, area, quality and region. Refine it later with a detailed take-off.',
          })}
        </p>
      </div>

      <RomReconciliationPanel />

      <Card>
        <CardHeader title={t('romEstimate.inputs_title', { defaultValue: 'Project basics' })} />
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {/* Building type */}
              <div>
                <label htmlFor="rom-type" className="mb-1.5 block text-xs font-medium text-content-secondary">
                  {t('romEstimate.building_type', { defaultValue: 'Building type' })}
                </label>
                <select
                  id="rom-type"
                  value={buildingType}
                  onChange={(e) => setBuildingType(e.target.value)}
                  className={INPUT_CLASS}
                >
                  {(reference?.building_types ?? []).map((opt) => (
                    <option key={opt.key} value={opt.key}>
                      {t(`romEstimate.type_${opt.key}`, { defaultValue: opt.label })}
                    </option>
                  ))}
                </select>
              </div>

              {/* Gross floor area */}
              <div>
                <label htmlFor="rom-area" className="mb-1.5 block text-xs font-medium text-content-secondary">
                  {t('romEstimate.gross_floor_area', { defaultValue: 'Gross floor area (m²)' })}
                </label>
                <input
                  id="rom-area"
                  type="number"
                  min={1}
                  step="any"
                  value={area}
                  onChange={(e) => setArea(e.target.value)}
                  placeholder={t('romEstimate.area_placeholder', { defaultValue: 'e.g. 1200' })}
                  className={`${INPUT_CLASS} tabular-nums`}
                />
              </div>

              {/* Quality */}
              <div>
                <label htmlFor="rom-quality" className="mb-1.5 block text-xs font-medium text-content-secondary">
                  {t('romEstimate.quality', { defaultValue: 'Quality level' })}
                </label>
                <select
                  id="rom-quality"
                  value={quality}
                  onChange={(e) => setQuality(e.target.value)}
                  className={INPUT_CLASS}
                >
                  {(reference?.quality_levels ?? []).map((opt) => (
                    <option key={opt.key} value={opt.key}>
                      {t(`romEstimate.quality_${opt.key}`, { defaultValue: opt.label })}
                    </option>
                  ))}
                </select>
              </div>

              {/* Region */}
              <div>
                <label htmlFor="rom-region" className="mb-1.5 block text-xs font-medium text-content-secondary">
                  {t('romEstimate.region', { defaultValue: 'Region' })}
                </label>
                <select
                  id="rom-region"
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  className={INPUT_CLASS}
                >
                  {(reference?.regions ?? []).map((opt) => (
                    <option key={opt.key} value={opt.key}>
                      {t(`romEstimate.region_${opt.key}`, { defaultValue: opt.label })}
                    </option>
                  ))}
                </select>
              </div>

              {/* Currency (optional display label) */}
              <div>
                <label htmlFor="rom-currency" className="mb-1.5 block text-xs font-medium text-content-secondary">
                  {t('romEstimate.currency', { defaultValue: 'Currency (optional)' })}
                </label>
                <input
                  id="rom-currency"
                  type="text"
                  maxLength={3}
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  placeholder={t('romEstimate.currency_placeholder', { defaultValue: 'e.g. EUR' })}
                  className={`${INPUT_CLASS} uppercase`}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={!canGenerate || generate.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-oe-blue px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-oe-blue/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Calculator size={16} />
              {generate.isPending
                ? t('romEstimate.generating', { defaultValue: 'Estimating…' })
                : t('romEstimate.generate', { defaultValue: 'Generate estimate' })}
            </button>

            {generate.isError && (
              <p className="text-sm text-semantic-error">
                {t('romEstimate.error', {
                  defaultValue: 'Could not build the estimate. Check the inputs and try again.',
                })}
              </p>
            )}
          </form>
        </CardContent>
      </Card>

      {result && <RomResultView result={result} />}
    </div>
  );
}

/** Read-only rendering of a computed estimate: total, band and breakdown. */
function RomResultView({ result }: { result: RomEstimateResult }) {
  const { t } = useTranslation();
  const currency = result.currency || '';

  const gfaLabel = useMemo(() => {
    const n = toNum(result.gfa_canonical_m2);
    return n.toLocaleString();
  }, [result.gfa_canonical_m2]);

  return (
    <div className="space-y-6">
      {/* Headline figures */}
      <Card>
        <CardHeader
          title={t('romEstimate.result_title', {
            defaultValue: '{{type}} - order-of-magnitude estimate',
            type: t(`romEstimate.type_${result.building_type}`, { defaultValue: result.building_type_label }),
          })}
        />
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-xl bg-surface-secondary p-4">
              <div className="mb-1 text-2xs font-medium uppercase tracking-wider text-content-tertiary">
                {t('romEstimate.total', { defaultValue: 'Estimated total' })}
              </div>
              <div className="text-2xl font-bold tabular-nums text-content-primary">
                {formatCurrency(result.total, currency, undefined, { maximumFractionDigits: 0 })}
              </div>
              <div className="mt-1 text-2xs text-content-tertiary">
                {t('romEstimate.for_area', { defaultValue: 'for {{area}} m² GFA', area: gfaLabel })}
              </div>
            </div>

            <div className="rounded-xl border border-border-light bg-surface-elevated/90 p-4">
              <div className="mb-1 text-2xs font-medium uppercase tracking-wider text-content-tertiary">
                {t('romEstimate.cost_per_m2', { defaultValue: 'Cost / m²' })}
              </div>
              <div className="text-lg font-semibold tabular-nums text-content-primary">
                {formatCurrency(result.cost_per_m2, currency)}
              </div>
              <div className="mt-1 text-2xs text-content-tertiary">
                {t('romEstimate.quality_region', {
                  defaultValue: '{{quality}}, {{region}}',
                  quality: t(`romEstimate.quality_${result.quality}`, { defaultValue: result.quality_label }),
                  region: t(`romEstimate.region_${result.region}`, { defaultValue: result.region_label }),
                })}
              </div>
            </div>

            {/* Accuracy band */}
            <div className="rounded-xl border border-border-light bg-surface-elevated/90 p-4">
              <div className="mb-1 text-2xs font-medium uppercase tracking-wider text-content-tertiary">
                {t('romEstimate.accuracy_band', { defaultValue: 'Likely range' })}
              </div>
              <div className="text-sm font-semibold tabular-nums text-content-primary">
                {formatCurrency(result.accuracy.low_amount, currency, undefined, { maximumFractionDigits: 0 })}
                {' – '}
                {formatCurrency(result.accuracy.high_amount, currency, undefined, { maximumFractionDigits: 0 })}
              </div>
              <div className="mt-1 text-2xs text-content-tertiary tabular-nums">
                {formatPct(result.accuracy.low_pct)} / {formatPct(result.accuracy.high_pct)}
              </div>
            </div>
          </div>

          {!result.accuracy.localized && (
            <div className="mt-4 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-2xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>
                {t('romEstimate.no_region_note', {
                  defaultValue:
                    'No regional cost factor applied, so the range is wider. Select a region to narrow it.',
                })}
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Elemental breakdown */}
      <Card>
        <CardHeader title={t('romEstimate.breakdown_title', { defaultValue: 'Elemental breakdown' })} />
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-2xs uppercase tracking-wider text-content-tertiary">
                  <th className="py-2 pr-4 font-medium">
                    {t('romEstimate.col_element', { defaultValue: 'Element' })}
                  </th>
                  <th className="py-2 pr-4 text-right font-medium">
                    {t('romEstimate.col_share', { defaultValue: 'Share' })}
                  </th>
                  <th className="py-2 pr-4 text-right font-medium">
                    {t('romEstimate.col_rate', { defaultValue: 'Cost / m²' })}
                  </th>
                  <th className="py-2 text-right font-medium">
                    {t('romEstimate.col_amount', { defaultValue: 'Amount' })}
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.elements.map((line) => (
                  <tr key={line.key} className="border-b border-border-light last:border-0">
                    <td className="py-2 pr-4 text-content-primary">
                      {t(`romEstimate.element_${line.key}`, { defaultValue: line.label })}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums text-content-secondary">
                      {toNum(line.cost_share_pct).toFixed(0)}%
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums text-content-secondary">
                      {formatCurrency(line.rate_per_m2, currency)}
                    </td>
                    <td className="py-2 text-right font-medium tabular-nums text-content-primary">
                      {formatCurrency(line.amount, currency, undefined, { maximumFractionDigits: 0 })}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-border font-semibold">
                  <td className="py-2 pr-4 text-content-primary" colSpan={3}>
                    {t('romEstimate.total', { defaultValue: 'Estimated total' })}
                  </td>
                  <td className="py-2 text-right tabular-nums text-content-primary">
                    {formatCurrency(result.total, currency, undefined, { maximumFractionDigits: 0 })}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="mt-3 text-2xs text-content-tertiary">
            {t('romEstimate.class_note', {
              defaultValue:
                'Order-of-magnitude estimate. Use it to sanity-check scope and budget, then refine with a detailed take-off.',
            })}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

/** Traffic-light treatment per reconciliation status. */
const RECONCILE_STATUS_STYLE: Record<
  RomReconciliation['status'],
  { pill: string; accent: string; Icon: LucideIcon }
> = {
  on_track: {
    pill: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    accent: 'text-emerald-600 dark:text-emerald-400',
    Icon: CheckCircle2,
  },
  over: {
    pill: 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300',
    accent: 'text-red-600 dark:text-red-400',
    Icon: TrendingUp,
  },
  under: {
    pill: 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    accent: 'text-amber-600 dark:text-amber-400',
    Icon: TrendingDown,
  },
  no_baseline: {
    pill: 'bg-surface-secondary text-content-tertiary',
    accent: 'text-content-tertiary',
    Icon: Scale,
  },
};

/** Prefix a positive money string with '+'; negatives already carry a minus. */
function signedMoney(value: string | null, currency: string): string {
  if (value === null) return '';
  const formatted = formatCurrency(value, currency, undefined, { maximumFractionDigits: 0 });
  return toNum(value) > 0 ? `+${formatted}` : formatted;
}

/**
 * Project-scoped reconciliation of the conceptual baseline against the live BOQ.
 *
 * Answers the design-development question the concept number was losing: is the
 * detailed estimate still tracking the number the project was approved on? It
 * reads the backend reconciliation for the active project and shows conceptual
 * vs detailed, the variance amount and percent, and a traffic-light band. It
 * renders nothing when no project is active (the calculator is usable stand-alone).
 *
 * All money and percentages come straight from the API as Decimal strings and
 * are only ever formatted, never float-mathed, here.
 */
export function RomReconciliationPanel() {
  const { t } = useTranslation();
  const projectId = useActiveProjectId();

  const query = useQuery({
    queryKey: ['rom-estimate', 'reconciliation', projectId],
    queryFn: () => romEstimateApi.reconciliation(projectId),
    enabled: Boolean(projectId),
    staleTime: 30 * 1000,
  });

  if (!projectId) return null;

  const rec = query.data;

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <Scale size={18} />
            {t('romEstimate.reconcile.title', { defaultValue: 'Concept vs detailed estimate' })}
          </span>
        }
      />
      <CardContent>
        {query.isLoading && (
          <p className="text-sm text-content-tertiary">
            {t('romEstimate.reconcile.loading', { defaultValue: 'Loading reconciliation…' })}
          </p>
        )}
        {query.isError && (
          <p className="text-sm text-semantic-error">
            {t('romEstimate.reconcile.error', {
              defaultValue: 'Could not load the reconciliation for this project.',
            })}
          </p>
        )}
        {rec && <RomReconciliationView rec={rec} />}
      </CardContent>
    </Card>
  );
}

/** Read-only rendering of a reconciliation payload. */
function RomReconciliationView({ rec }: { rec: RomReconciliation }) {
  const { t } = useTranslation();
  const style = RECONCILE_STATUS_STYLE[rec.status] ?? RECONCILE_STATUS_STYLE.no_baseline;
  const { Icon } = style;
  const currency = rec.currency || '';
  const hasBaseline = rec.status !== 'no_baseline' && rec.conceptual_total !== null;

  const statusLabel = t(`romEstimate.reconcile.status_${rec.status}`, {
    defaultValue: {
      on_track: 'On track',
      over: 'Over concept',
      under: 'Under concept',
      no_baseline: 'No baseline',
    }[rec.status],
  });
  const statusDesc = t(`romEstimate.reconcile.desc_${rec.status}`, {
    defaultValue: {
      on_track: 'The detailed estimate is tracking the conceptual budget.',
      over: 'The detailed estimate is running above the conceptual budget.',
      under: 'The detailed estimate is below the conceptual budget.',
      no_baseline:
        'No conceptual baseline is saved for this project yet. Save a conceptual estimate to track the detailed design against it.',
    }[rec.status],
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${style.pill}`}
        >
          <Icon size={14} />
          {statusLabel}
        </span>
        <span className="text-sm text-content-secondary">{statusDesc}</span>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {/* Conceptual baseline */}
        <div className="rounded-xl bg-surface-secondary p-4">
          <div className="mb-1 text-2xs font-medium uppercase tracking-wider text-content-tertiary">
            {t('romEstimate.reconcile.conceptual', { defaultValue: 'Conceptual baseline' })}
          </div>
          <div className="text-xl font-bold tabular-nums text-content-primary">
            {hasBaseline
              ? formatCurrency(rec.conceptual_total, currency, undefined, { maximumFractionDigits: 0 })
              : t('romEstimate.reconcile.not_set', { defaultValue: 'Not set' })}
          </div>
          {rec.conceptual_name && (
            <div className="mt-1 truncate text-2xs text-content-tertiary" title={rec.conceptual_name}>
              {rec.conceptual_name}
            </div>
          )}
        </div>

        {/* Live detailed total */}
        <div className="rounded-xl border border-border-light bg-surface-elevated/90 p-4">
          <div className="mb-1 text-2xs font-medium uppercase tracking-wider text-content-tertiary">
            {t('romEstimate.reconcile.detailed', { defaultValue: 'Detailed BOQ total' })}
          </div>
          <div className="text-xl font-bold tabular-nums text-content-primary">
            {formatCurrency(rec.detailed_total, currency, undefined, { maximumFractionDigits: 0 })}
          </div>
          <div className="mt-1 text-2xs text-content-tertiary">
            {t('romEstimate.reconcile.boq_count', {
              defaultValue: '{{n}} bill(s) of quantities',
              n: rec.boq_count,
            })}
          </div>
        </div>

        {/* Variance */}
        <div className="rounded-xl border border-border-light bg-surface-elevated/90 p-4">
          <div className="mb-1 text-2xs font-medium uppercase tracking-wider text-content-tertiary">
            {t('romEstimate.reconcile.variance', { defaultValue: 'Variance' })}
          </div>
          <div className={`text-xl font-bold tabular-nums ${hasBaseline ? style.accent : 'text-content-tertiary'}`}>
            {hasBaseline
              ? signedMoney(rec.variance_amount, currency)
              : t('romEstimate.reconcile.not_set', { defaultValue: 'Not set' })}
          </div>
          {hasBaseline && rec.variance_pct !== null && (
            <div className={`mt-1 text-2xs font-medium tabular-nums ${style.accent}`}>
              {formatPct(rec.variance_pct)}{' '}
              <span className="text-content-tertiary">
                {t('romEstimate.reconcile.tolerance', {
                  defaultValue: 'vs concept (band ±{{pct}}%)',
                  pct: toNum(rec.tolerance_pct).toFixed(0),
                })}
              </span>
            </div>
          )}
        </div>
      </div>

      {rec.currency_mismatch && (
        <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-2xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>
            {t('romEstimate.reconcile.currency_mismatch', {
              defaultValue:
                'The concept ({{concept}}) and detailed estimate ({{detailed}}) use different currencies, so the comparison mixes currencies. Align them for an exact variance.',
              concept: rec.conceptual_currency || '?',
              detailed: rec.currency || '?',
            })}
          </span>
        </div>
      )}
    </div>
  );
}
