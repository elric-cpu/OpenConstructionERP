/**
 * Property Development — Dashboard full-view route (task #140).
 *
 * Renders one dashboard at a time based on the URL slug (e.g.
 * /property-dev/dashboards/inventory-heatmap) and a development selector.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Breadcrumb } from '@/shared/ui';
import { listDevelopments, type Development } from '../api';
import { InventoryHeatmap } from './InventoryHeatmap';
import { SalesVelocity } from './SalesVelocity';
import { CashFlowWaterfall } from './CashFlowWaterfall';
import { InventoryAgeing } from './InventoryAgeing';
import { FunnelConversion } from './FunnelConversion';
import { CohortRetentionWidget } from './CohortRetentionWidget';
import { TimeToCloseWidget } from './TimeToCloseWidget';
import { LeadSourceAttributionWidget } from './LeadSourceAttributionWidget';
import { ConversionFunnelWidget } from './ConversionFunnelWidget';
import { BrokerPerformanceWidget } from './BrokerPerformanceWidget';
import { DashboardEmpty, DashboardLoading } from './_shared';

const VALID_KEYS = new Set([
  'inventory-heatmap',
  'sales-velocity',
  'cashflow-waterfall',
  'inventory-ageing',
  'funnel-conversion',
  'insights',
]);


export function FullViewPage() {
  const { t } = useTranslation();
  const params = useParams<{ key?: string }>();
  const key = params.key ?? '';
  const [developmentId, setDevelopmentId] = useState<string>('');

  const { data: developments, isLoading } = useQuery({
    queryKey: ['propdev-developments'],
    queryFn: () => listDevelopments({ limit: 100 }),
  });

  // Seed local state from async query data via useEffect — assigning
  // during render trips StrictMode's "setState during render" warning.
  useEffect(() => {
    if (!developmentId && developments && developments.length > 0) {
      const first = developments[0];
      if (first) setDevelopmentId(first.id);
    }
  }, [developments, developmentId]);

  if (!VALID_KEYS.has(key)) {
    return (
      <DashboardEmpty
        title={t('propdev.dashboards.full.unknown_title', {
          defaultValue: 'Unknown dashboard',
        })}
        description={t('propdev.dashboards.full.unknown_desc', {
          defaultValue:
            'The dashboard you tried to open doesn\'t exist.',
        })}
      />
    );
  }
  if (isLoading) return <DashboardLoading />;
  if (!developments || developments.length === 0) {
    return (
      <DashboardEmpty
        title={t('propdev.dashboards.hub.no_developments_title', {
          defaultValue: 'No developments yet',
        })}
      />
    );
  }

  const renderActive = () => {
    if (!developmentId) return null;
    switch (key) {
      case 'inventory-heatmap':
        return <InventoryHeatmap developmentId={developmentId} />;
      case 'sales-velocity':
        return <SalesVelocity developmentId={developmentId} />;
      case 'cashflow-waterfall':
        return <CashFlowWaterfall developmentId={developmentId} />;
      case 'inventory-ageing':
        return <InventoryAgeing developmentId={developmentId} />;
      case 'funnel-conversion':
        return <FunnelConversion developmentId={developmentId} />;
      case 'insights':
        return <InsightsGrid developmentId={developmentId} />;
      default:
        return null;
    }
  };

  const dashboardTitle = t(
    `propdev.dashboards.full.${key.replace(/-/g, '_')}`,
    { defaultValue: key.replace(/-/g, ' ') },
  );

  return (
    <div className="space-y-4 p-4">
      <Breadcrumb
        items={[
          {
            label: t('propdev.title', { defaultValue: 'Property Development' }),
            to: '/property-dev',
          },
          {
            label: t('propdev.dashboards.hub.title', {
              defaultValue: 'Property Development Dashboards',
            }),
            to: '/property-dev/dashboards',
          },
          { label: dashboardTitle },
        ]}
      />
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <Link
            to="/property-dev/dashboards"
            className="flex items-center gap-1 text-2xs text-content-tertiary hover:text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue/40 rounded"
          >
            <ArrowLeft size={12} />
            {t('propdev.dashboards.full.back_to_hub', {
              defaultValue: 'Back to hub',
            })}
          </Link>
          <h1 className="text-lg font-semibold text-content-primary capitalize">
            {dashboardTitle}
          </h1>
        </div>
        <label className="flex items-center gap-2 text-xs">
          <span className="text-content-secondary">
            {t('propdev.dashboards.hub.development', {
              defaultValue: 'Development',
            })}
          </span>
          <select
            value={developmentId}
            onChange={(e) => setDevelopmentId(e.target.value)}
            className="rounded border border-border-light bg-surface-elevated px-2 py-1"
          >
            {developments.map((d: Development) => (
              <option key={d.id} value={d.id}>
                {d.code} — {d.name}
              </option>
            ))}
          </select>
        </label>
      </header>
      <div>{renderActive()}</div>
    </div>
  );
}

/**
 * Insights tab — the 5 v3124 sales-analytics widgets in a 2-col grid
 * (1-col on mobile). Each widget is independently cached (React Query
 * staleTime 60s) so swapping tabs or window-filter changes only
 * re-fetches the widgets the user actually scrolls to.
 *
 * The Insights grid intentionally drops the development_id scope —
 * these analytics are tenant-wide (cohort retention, lead-source CPA,
 * broker leaderboard all make more sense across the full portfolio).
 * The Conversion-funnel widget takes ``devId`` to keep the per-dev
 * drilldown available without adding a second selector.
 */
function InsightsGrid({ developmentId }: { developmentId: string }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <div className="rounded-lg border border-divider bg-surface-primary p-3">
        <CohortRetentionWidget />
      </div>
      <div className="rounded-lg border border-divider bg-surface-primary p-3">
        <TimeToCloseWidget />
      </div>
      <div className="rounded-lg border border-divider bg-surface-primary p-3 md:col-span-2">
        <LeadSourceAttributionWidget />
      </div>
      <div className="rounded-lg border border-divider bg-surface-primary p-3">
        <ConversionFunnelWidget devId={developmentId} />
      </div>
      <div className="rounded-lg border border-divider bg-surface-primary p-3">
        <BrokerPerformanceWidget />
      </div>
    </div>
  );
}
