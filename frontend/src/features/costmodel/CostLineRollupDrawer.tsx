// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// CostLineRollupDrawer - right-side detail panel for a single cost line.
//
// Shows the line's estimate vs budget / committed / contracted / actual
// figures and, below, the downstream records it links to (BOQ positions,
// budget lines, PO items, contract lines, RFQs). Money is the project-wide
// Decimal-as-string contract; format at the edge, never coerce to a number
// for storage.

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import {
  Layers,
  Wallet,
  ShoppingCart,
  FileSignature,
  Send,
  ListTree,
} from 'lucide-react';

import { SideDrawer, Skeleton } from '@/shared/ui';
import { fmtCurrency } from '@/shared/lib/formatters';
import { getErrorMessage } from '@/shared/lib/api';
import { costModelApi, type CostLineRollup } from './api';

export interface CostLineRollupDrawerProps {
  open: boolean;
  onClose: () => void;
  /** The cost line to inspect; when null the drawer renders nothing. */
  lineId: string | null;
  /**
   * Optional rollup already in hand (e.g. from the spine grid) used as the
   * initial render while the fresh per-line rollup loads. Keeps the drawer
   * instant on open.
   */
  initial?: CostLineRollup | null;
}

/** A single money row in the figures block. */
function MoneyRow({
  label,
  value,
  currency,
  emphasize = false,
}: {
  label: string;
  value: string;
  currency: string;
  emphasize?: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-sm text-content-secondary">{label}</span>
      <span
        className={`tabular-nums text-sm ${emphasize ? 'font-semibold text-content-primary' : 'text-content-primary'}`}
      >
        {fmtCurrency(value, currency)}
      </span>
    </div>
  );
}

/** A group of linked record ids under a labelled icon header. */
function LinkGroup({
  icon,
  label,
  ids,
}: {
  icon: React.ReactNode;
  label: string;
  ids: string[];
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-content-tertiary">{icon}</span>
        <span className="text-xs font-semibold text-content-primary">{label}</span>
        <span className="rounded-full bg-surface-secondary px-1.5 text-2xs font-medium text-content-secondary">
          {ids.length}
        </span>
      </div>
      {ids.length > 0 ? (
        <ul className="space-y-1 pl-6">
          {ids.map((id) => (
            <li
              key={id}
              className="truncate font-mono text-2xs text-content-secondary"
              title={id}
            >
              {id}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * Drawer showing a cost line's roll-up figures and its downstream links.
 */
export function CostLineRollupDrawer({
  open,
  onClose,
  lineId,
  initial,
}: CostLineRollupDrawerProps) {
  const { t } = useTranslation();

  const { data, isLoading, error } = useQuery({
    queryKey: ['spine', 'line-rollup', lineId],
    queryFn: () => costModelApi.getLineRollup(lineId as string),
    enabled: open && !!lineId,
    retry: false,
    initialData: initial ?? undefined,
  });

  const rollup = data ?? initial ?? null;
  const currency = rollup?.currency || 'EUR';

  const linkGroups = useMemo(() => {
    const links = rollup?.links;
    return [
      {
        key: 'boq',
        icon: <ListTree size={14} />,
        label: t('costmodel.spine.links_boq', { defaultValue: 'BOQ positions' }),
        ids: links?.boq_position_ids ?? [],
      },
      {
        key: 'budget',
        icon: <Wallet size={14} />,
        label: t('costmodel.spine.links_budget', { defaultValue: 'Budget lines' }),
        ids: links?.budget_line_ids ?? [],
      },
      {
        key: 'po',
        icon: <ShoppingCart size={14} />,
        label: t('costmodel.spine.links_po', { defaultValue: 'Purchase order items' }),
        ids: links?.po_item_ids ?? [],
      },
      {
        key: 'contract',
        icon: <FileSignature size={14} />,
        label: t('costmodel.spine.links_contract', { defaultValue: 'Contract lines' }),
        ids: links?.contract_line_ids ?? [],
      },
      {
        key: 'rfq',
        icon: <Send size={14} />,
        label: t('costmodel.spine.links_rfq', { defaultValue: 'Requests for quotation' }),
        ids: links?.rfq_ids ?? [],
      },
    ];
  }, [rollup, t]);

  const totalLinks = linkGroups.reduce((sum, g) => sum + g.ids.length, 0);

  return (
    <SideDrawer
      open={open}
      onClose={onClose}
      title={
        rollup
          ? `${rollup.code} ${rollup.description}`.trim()
          : t('costmodel.spine.line_detail', { defaultValue: 'Cost line' })
      }
      subtitle={
        <span className="inline-flex items-center gap-1">
          <Layers size={11} />
          {t('costmodel.spine.line_detail', { defaultValue: 'Cost line' })}
        </span>
      }
    >
      <div className="space-y-6 p-5">
        {isLoading && !rollup ? (
          <div className="space-y-3">
            <Skeleton height={28} className="w-full" rounded="md" />
            <Skeleton height={140} className="w-full" rounded="lg" />
            <Skeleton height={120} className="w-full" rounded="lg" />
          </div>
        ) : error && !rollup ? (
          <div className="rounded-lg border border-semantic-error/30 bg-semantic-error-bg/30 p-3 text-sm text-semantic-error">
            {getErrorMessage(error)}
          </div>
        ) : rollup ? (
          <>
            {/* Figures */}
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-content-tertiary">
                {t('costmodel.spine.figures', { defaultValue: 'Figures' })}
              </h3>
              <div className="divide-y divide-border-light rounded-lg border border-border-light px-3">
                <MoneyRow
                  label={t('costmodel.spine.col_estimate', { defaultValue: 'Estimate' })}
                  value={rollup.estimate_amount}
                  currency={currency}
                  emphasize
                />
                <MoneyRow
                  label={t('costmodel.spine.col_budget', { defaultValue: 'Budget' })}
                  value={rollup.budget_planned}
                  currency={currency}
                />
                <MoneyRow
                  label={t('costmodel.spine.col_committed', { defaultValue: 'Committed (PO)' })}
                  value={rollup.po_committed}
                  currency={currency}
                />
                <MoneyRow
                  label={t('costmodel.spine.col_contracted', { defaultValue: 'Contracted' })}
                  value={rollup.contracted_value}
                  currency={currency}
                />
                <MoneyRow
                  label={t('costmodel.spine.col_actual', { defaultValue: 'Actual (claimed)' })}
                  value={rollup.claimed_to_date}
                  currency={currency}
                />
                <MoneyRow
                  label={t('costmodel.spine.col_variance', { defaultValue: 'Variance' })}
                  value={rollup.variance_estimate_vs_budget}
                  currency={currency}
                  emphasize
                />
              </div>
            </section>

            {/* Links */}
            <section>
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-content-tertiary">
                {t('costmodel.spine.linked_records', { defaultValue: 'Linked records' })}
              </h3>
              {totalLinks === 0 ? (
                <p className="text-sm text-content-tertiary">
                  {t('costmodel.spine.no_links', {
                    defaultValue:
                      'This cost line is not linked to any downstream records yet.',
                  })}
                </p>
              ) : (
                <div className="space-y-4">
                  {linkGroups.map((g) => (
                    <LinkGroup key={g.key} icon={g.icon} label={g.label} ids={g.ids} />
                  ))}
                </div>
              )}
            </section>
          </>
        ) : null}
      </div>
    </SideDrawer>
  );
}
