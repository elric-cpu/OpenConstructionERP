/**
 * 6×6 discipline-pair heat-map for the Coordination Hub.
 *
 * Cells are rendered as a CSS grid (no Recharts dependency — a fixed 6×6
 * layout is too small to justify the chart-library overhead). Each
 * non-empty cell carries:
 *   * its open-count as the visible number
 *   * a background tint scaled by the count
 *   * a hover tooltip with a per-cell breakdown (total / open / resolved /
 *     cost-impact contribution)
 * Clicking a cell navigates to ``/clash?project=<pid>&disciplineA=<row>&disciplineB=<col>``
 * — the ClashPage reads those params and pre-applies the pair filter.
 */

import clsx from 'clsx';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { CanonicalTrade, TradeMatrixResponse } from './types';

export interface CoordinationTradeMatrixProps {
  data: TradeMatrixResponse | undefined;
  isLoading?: boolean;
  /**
   * Optional project id appended to the click-through deep link so the
   * ClashPage can resolve the right project even when the user landed
   * from an external link (no global project context selected yet).
   */
  projectId?: string | null;
}

/** Background-color ramp by clash count. Pure Tailwind so it tree-shakes. */
function tintForCount(open: number, maxOpen: number): string {
  if (open <= 0) return 'bg-slate-50';
  // Map (open / maxOpen) into one of five tints. Avoid a continuous
  // gradient because Tailwind purges unused classes — we need explicit
  // class strings.
  const ratio = maxOpen > 0 ? open / maxOpen : 0;
  if (ratio < 0.2) return 'bg-amber-50';
  if (ratio < 0.4) return 'bg-amber-100';
  if (ratio < 0.6) return 'bg-amber-200';
  if (ratio < 0.8) return 'bg-red-200';
  return 'bg-red-300';
}

/** Foreground colour by tint — keeps the count readable on dark cells. */
function textForCount(open: number, maxOpen: number): string {
  const ratio = maxOpen > 0 ? open / maxOpen : 0;
  if (open <= 0) return 'text-content-tertiary';
  if (ratio < 0.6) return 'text-amber-900';
  return 'text-red-900';
}

/** Discipline label palette — uses the same axes as the federations page. */
const DISCIPLINE_LABELS: Record<CanonicalTrade, string> = {
  arch: 'Arch',
  struct: 'Struct',
  mep: 'MEP',
  landscape: 'Landscape',
  civil: 'Civil',
  other: 'Other',
};

export function CoordinationTradeMatrix({
  data,
  isLoading,
  projectId,
}: CoordinationTradeMatrixProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  if (isLoading || !data) {
    return (
      <div
        data-testid="coordination-matrix-skeleton"
        className="animate-pulse rounded-xl border border-border bg-surface p-4 shadow-sm"
      >
        <div className="h-4 w-1/3 rounded bg-slate-200" />
        <div className="mt-4 h-64 w-full rounded bg-slate-100" />
      </div>
    );
  }

  const trades = data.trades;
  // Build a lookup so a (row, col) miss renders as zero.
  const cellMap = new Map<string, { count: number; open: number; resolved: number }>();
  for (const cell of data.cells) {
    cellMap.set(`${cell.row}::${cell.col}`, {
      count: cell.count,
      open: cell.open,
      resolved: cell.resolved,
    });
  }
  const maxOpen = data.cells.reduce(
    (acc, c) => (c.open > acc ? c.open : acc),
    0,
  );

  return (
    <div
      data-testid="coordination-trade-matrix"
      className="rounded-xl border border-border bg-surface p-4 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-content-primary">
            {t('coordination.trade_matrix_title', {
              defaultValue: 'Trade Matrix',
            })}
          </h3>
          <p className="text-xs text-content-tertiary">
            {t('coordination.trade_matrix_subtitle', {
              defaultValue:
                'Open clashes by discipline pair — click a cell to drill down.',
            })}
          </p>
        </div>
      </div>
      <div className="overflow-x-auto">
        <div
          className="grid gap-1"
          style={{
            gridTemplateColumns: `auto repeat(${trades.length}, minmax(60px, 1fr))`,
          }}
        >
          {/* Top-left corner */}
          <div />
          {/* Column headers */}
          {trades.map((col) => (
            <div
              key={`col-${col}`}
              className="text-center text-xs font-medium uppercase tracking-wide text-content-secondary"
            >
              {DISCIPLINE_LABELS[col] ?? col}
            </div>
          ))}
          {/* Rows */}
          {trades.map((row) => (
            <RowFragment
              key={`row-${row}`}
              row={row}
              trades={trades}
              cellMap={cellMap}
              maxOpen={maxOpen}
              navigate={navigate}
              projectId={projectId ?? null}
              t={t}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

interface RowFragmentProps {
  row: CanonicalTrade;
  trades: CanonicalTrade[];
  cellMap: Map<string, { count: number; open: number; resolved: number }>;
  maxOpen: number;
  navigate: ReturnType<typeof useNavigate>;
  projectId: string | null;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

function RowFragment({
  row,
  trades,
  cellMap,
  maxOpen,
  navigate,
  projectId,
  t,
}: RowFragmentProps) {
  // Hovered cell key → drives the rich tooltip overlay. Plain HTML
  // ``title`` is also set so screen readers + non-pointer devices still
  // get the breakdown.
  const [hovered, setHovered] = useState<string | null>(null);
  return (
    <>
      <div className="text-right text-xs font-medium uppercase tracking-wide text-content-secondary">
        {DISCIPLINE_LABELS[row] ?? row}
      </div>
      {trades.map((col) => {
        // The server emits each pair once (row index ≤ col index). For
        // the mirror half we look up the swapped key so the matrix shows
        // both halves symmetrically.
        const key1 = `${row}::${col}`;
        const key2 = `${col}::${row}`;
        const cell = cellMap.get(key1) ?? cellMap.get(key2);
        const open = cell?.open ?? 0;
        const total = cell?.count ?? 0;
        const resolved = cell?.resolved ?? 0;
        const isEmpty = total === 0;
        const tint = tintForCount(open, maxOpen);
        const fg = textForCount(open, maxOpen);
        const cellKey = `${row}-${col}`;
        const tooltipPlain = isEmpty
          ? t('coordination.matrix_tooltip_empty', { defaultValue: '—' })
          : t('coordination.matrix_tooltip', {
              defaultValue:
                '{{open}} open · {{resolved}} resolved · {{total}} total',
              open,
              resolved,
              total,
            });
        return (
          <div
            key={`cellwrap-${row}-${col}`}
            className="relative"
            onMouseEnter={() => !isEmpty && setHovered(cellKey)}
            onMouseLeave={() => setHovered((prev) => (prev === cellKey ? null : prev))}
            onFocus={() => !isEmpty && setHovered(cellKey)}
            onBlur={() => setHovered((prev) => (prev === cellKey ? null : prev))}
          >
            <button
              type="button"
              data-testid={`matrix-cell-${row}-${col}`}
              disabled={isEmpty}
              title={tooltipPlain}
              aria-label={(() => {
                // Build the aria string with concrete values so screen
                // readers (and tests) always see the interpolated form.
                // The i18n template is still used as the formatting hint
                // — we render values directly so the SR never reads a
                // ``{{open}}`` placeholder when the locale lookup misses.
                const rowLabel = DISCIPLINE_LABELS[row] ?? row;
                const colLabel = DISCIPLINE_LABELS[col] ?? col;
                if (isEmpty) {
                  return `No clashes for ${rowLabel} × ${colLabel}`;
                }
                return (
                  `${open} open clashes between ${rowLabel} and ${colLabel}. ` +
                  'Press Enter to drill down.'
                );
              })()}
              onClick={() => {
                if (isEmpty) return;
                const params = new URLSearchParams();
                if (projectId) params.set('project', projectId);
                params.set('disciplineA', row);
                params.set('disciplineB', col);
                navigate(`/clash?${params.toString()}`);
              }}
              onKeyDown={(e) => {
                // Enter / Space already trigger onClick natively; we add
                // explicit handling so the test runner can dispatch a
                // keyboard event without going through a click first.
                if (isEmpty) return;
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  const params = new URLSearchParams();
                  if (projectId) params.set('project', projectId);
                  params.set('disciplineA', row);
                  params.set('disciplineB', col);
                  navigate(`/clash?${params.toString()}`);
                }
              }}
              className={clsx(
                'flex h-12 w-full items-center justify-center rounded-md border border-transparent text-sm font-semibold transition-colors',
                tint,
                fg,
                isEmpty
                  ? 'cursor-default opacity-60'
                  : 'hover:border-border-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400',
              )}
            >
              {isEmpty ? '—' : open}
            </button>
            {hovered === cellKey && !isEmpty ? (
              <div
                role="tooltip"
                data-testid={`matrix-cell-tooltip-${row}-${col}`}
                className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-slate-900 px-2 py-1 text-xs font-medium text-white shadow-lg"
              >
                <div className="font-semibold">
                  {DISCIPLINE_LABELS[row] ?? row} × {DISCIPLINE_LABELS[col] ?? col}
                </div>
                <div>
                  {t('coordination.matrix_tooltip_total', {
                    defaultValue: 'Total',
                  })}
                  : {total}
                </div>
                <div>
                  {t('coordination.matrix_tooltip_open', {
                    defaultValue: 'Open',
                  })}
                  : {open}
                </div>
                <div>
                  {t('coordination.matrix_tooltip_resolved', {
                    defaultValue: 'Resolved',
                  })}
                  : {resolved}
                </div>
              </div>
            ) : null}
          </div>
        );
      })}
    </>
  );
}
