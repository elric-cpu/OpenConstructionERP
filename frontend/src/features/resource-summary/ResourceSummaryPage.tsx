// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Resource Summary - one procurement-ready statement for the whole estimate.
// Rolls up the resource split stored on every priced position into total
// labour-hours and cost, and the total quantity and cost of each material,
// machine and subcontract line, so a buyer sees a single schedule of what the
// estimate implies they must procure. Reads existing per-position splits; it
// never edits the estimate.

import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { LucideIcon } from 'lucide-react';
import { Boxes, Download, HardHat, Layers, Package, Truck, Users, Wrench } from 'lucide-react';
import { Button, Card, EmptyState, ErrorState, PageHeader, SkeletonTable, StatCard } from '@/shared/ui';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { QuantityDisplay } from '@/shared/ui/QuantityDisplay';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { getErrorMessage } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import {
  downloadResourceStatementCsv,
  getResourceStatement,
  isEmptyStatement,
  kindAccentClass,
  statementCurrency,
  type ResourceStatementGroup,
} from './api';

const KIND_ICON: Record<string, LucideIcon> = {
  labor: HardHat,
  material: Package,
  machinery: Wrench,
  equipment: Boxes,
  subcontractor: Users,
  other: Layers,
};

export function ResourceSummaryPage() {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);

  const query = useQuery({
    queryKey: ['resource-summary', activeProjectId],
    queryFn: () => getResourceStatement(activeProjectId as string),
    enabled: !!activeProjectId,
    staleTime: 30_000,
  });

  const download = useMutation({
    mutationFn: () => downloadResourceStatementCsv(activeProjectId as string),
    onError: (e) => {
      addToast({
        type: 'error',
        title: t('resourceSummary.exportFailed', { defaultValue: 'Could not export the statement' }),
        message: getErrorMessage(e),
      });
    },
  });

  const data = query.data;
  const currency = statementCurrency(data);

  const header = (
    <PageHeader
      srTitle={t('resourceSummary.title', { defaultValue: 'Resource summary' })}
      subtitle={t('resourceSummary.subtitle', {
        defaultValue:
          'Resource splits from every position rolled up into one procurement statement: labour-hours and the quantity and cost of each material, machine and subcontract line.',
      })}
      actions={
        data && !isEmptyStatement(data) ? (
          <Button
            variant="secondary"
            size="sm"
            icon={<Download size={14} />}
            onClick={() => download.mutate()}
            disabled={download.isPending}
          >
            {download.isPending
              ? t('resourceSummary.exporting', { defaultValue: 'Exporting...' })
              : t('resourceSummary.exportCsv', { defaultValue: 'Export CSV' })}
          </Button>
        ) : null
      }
    />
  );

  if (!activeProjectId) {
    return (
      <div className="space-y-5">
        {header}
        <EmptyState
          icon={<Boxes className="h-6 w-6" />}
          title={t('resourceSummary.noProject.title', { defaultValue: 'No project selected' })}
          description={t('resourceSummary.noProject.description', {
            defaultValue: 'Open a project to see the resources and quantities its estimate implies you must procure.',
          })}
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {header}

      {query.isLoading ? (
        <Card padding="sm">
          <SkeletonTable rows={8} columns={5} />
        </Card>
      ) : query.isError ? (
        <ErrorState
          title={t('resourceSummary.loadError', { defaultValue: 'Could not load the resource summary' })}
          hint={t('resourceSummary.loadErrorHint', {
            defaultValue: 'Refresh to try again. If it keeps failing, the estimate may still be loading.',
          })}
          onRetry={() => query.refetch()}
        />
      ) : !data || isEmptyStatement(data) ? (
        <EmptyState
          icon={<Package className="h-6 w-6" />}
          title={t('resourceSummary.empty.title', { defaultValue: 'No resources to summarise yet' })}
          description={t('resourceSummary.empty.description', {
            defaultValue:
              'Add a resource split to positions (or apply assemblies) and this statement will roll them up across the whole estimate.',
          })}
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard
              label={t('resourceSummary.kpi.laborHours', { defaultValue: 'Labour hours' })}
              value={<QuantityDisplay value={data.labor_hours} unit="h" precision={1} />}
              icon={HardHat}
              tone="blue"
              tintValue
            />
            <StatCard
              label={t('resourceSummary.kpi.totalCost', { defaultValue: 'Total resource cost' })}
              value={<MoneyDisplay amount={data.total_cost} currency={currency} compact />}
              icon={Truck}
              tone="success"
              tintValue
            />
            <StatCard
              label={t('resourceSummary.kpi.distinctResources', { defaultValue: 'Distinct resources' })}
              value={data.line_count}
              icon={Boxes}
            />
            <StatCard
              label={t('resourceSummary.kpi.positionsCovered', { defaultValue: 'Positions covered' })}
              value={data.position_count}
              icon={Layers}
            />
          </div>

          {data.groups.map((group) => (
            <ResourceGroupCard key={group.kind} group={group} currency={currency} />
          ))}

          <p className="text-xs text-content-tertiary">
            {t('resourceSummary.generatedAt', { defaultValue: 'Generated' })}{' '}
            <DateDisplay value={data.generated_at} format="datetime" />
          </p>
        </>
      )}
    </div>
  );
}

interface ResourceGroupCardProps {
  group: ResourceStatementGroup;
  currency: string | undefined;
}

function ResourceGroupCard({ group, currency }: ResourceGroupCardProps) {
  const { t } = useTranslation();
  const Icon = KIND_ICON[group.kind] ?? Layers;

  return (
    <Card padding="sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon size={16} className={kindAccentClass(group.kind)} aria-hidden />
          <h3 className="text-sm font-semibold text-content-primary">
            {t(`resourceSummary.kind.${group.kind}`, { defaultValue: group.label })}
          </h3>
          <span className="text-xs text-content-tertiary">
            {t('resourceSummary.lineCount', { defaultValue: '{{count}} lines', count: group.line_count })}
          </span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          {group.total_hours != null && (
            <span className="text-content-secondary">
              <QuantityDisplay value={group.total_hours} unit="h" precision={1} />
            </span>
          )}
          <span className="font-semibold tabular-nums text-content-primary">
            <MoneyDisplay amount={group.total_cost} currency={currency} />
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] text-sm">
          <thead>
            <tr className="border-b border-border-light text-left text-2xs uppercase tracking-wide text-content-tertiary">
              <th className="py-1.5 pr-3 font-medium">{t('resourceSummary.col.resource', { defaultValue: 'Resource' })}</th>
              <th className="py-1.5 pr-3 font-medium">{t('resourceSummary.col.unit', { defaultValue: 'Unit' })}</th>
              <th className="py-1.5 pr-3 text-right font-medium">
                {t('resourceSummary.col.quantity', { defaultValue: 'Quantity' })}
              </th>
              <th className="py-1.5 pr-3 text-right font-medium">
                {t('resourceSummary.col.cost', { defaultValue: 'Cost' })}
              </th>
              <th className="py-1.5 text-right font-medium">
                {t('resourceSummary.col.positions', { defaultValue: 'Positions' })}
              </th>
            </tr>
          </thead>
          <tbody>
            {group.lines.map((line, idx) => (
              <tr key={`${line.name}-${line.unit}-${idx}`} className="border-b border-border-light/60 last:border-0">
                <td className="py-1.5 pr-3 text-content-primary">{line.name}</td>
                <td className="py-1.5 pr-3 text-content-tertiary">{line.unit || '-'}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums text-content-secondary">
                  <QuantityDisplay value={line.quantity} unit={line.unit} precision={2} />
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums text-content-primary">
                  <MoneyDisplay amount={line.cost} currency={currency} />
                </td>
                <td className="py-1.5 text-right tabular-nums text-content-tertiary">{line.position_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
