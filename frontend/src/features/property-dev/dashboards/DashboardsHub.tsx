/**
 * Property Development — Dashboards Hub (task #140).
 *
 * Grid of 5 dashboard cards (the 6th — buyer-journey — opens per-buyer
 * via the Buyers tab). A single Development selector at the top scopes
 * every card.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  Grid3X3,
  LineChart as LineChartIcon,
  Coins,
  Clock,
  Filter,
  Compass,
  Sparkles,
} from 'lucide-react';
import { Breadcrumb, Card } from '@/shared/ui';
import { listDevelopments, type Development } from '../api';
import { InventoryHeatmap } from './InventoryHeatmap';
import { SalesVelocity } from './SalesVelocity';
import { CashFlowWaterfall } from './CashFlowWaterfall';
import { InventoryAgeing } from './InventoryAgeing';
import { FunnelConversion } from './FunnelConversion';
import { DashboardLoading, DashboardEmpty } from './_shared';

interface DashboardTileProps {
  title: string;
  icon: React.ReactNode;
  to: string;
  children: React.ReactNode;
}

function DashboardTile({ title, icon, to, children }: DashboardTileProps) {
  const { t } = useTranslation();
  return (
    <Card className="flex flex-col p-3 min-h-[260px]">
      <header className="mb-2 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-content-primary">
          <span className="text-content-tertiary">{icon}</span>
          {title}
        </h3>
        <Link to={to} className="text-2xs text-oe-blue hover:underline">
          {t('propdev.dashboards.hub.open_full_view', {
            defaultValue: 'Open full view →',
          })}
        </Link>
      </header>
      <div className="flex-1 overflow-hidden">{children}</div>
    </Card>
  );
}

export function DashboardsHub() {
  const { t } = useTranslation();
  const [developmentId, setDevelopmentId] = useState<string>('');

  const { data: developments, isLoading } = useQuery({
    queryKey: ['propdev-developments'],
    queryFn: () => listDevelopments({ limit: 100 }),
  });

  // Earlier this set state during render which trips React's
  // ``setState in render`` warning under StrictMode. ``useEffect`` is
  // the supported way to seed local state from async query data.
  useEffect(() => {
    if (!developmentId && developments && developments.length > 0) {
      const first = developments[0];
      if (first) setDevelopmentId(first.id);
    }
  }, [developments, developmentId]);

  if (isLoading) return <DashboardLoading />;
  if (!developments || developments.length === 0) {
    return (
      <DashboardEmpty
        title={t('propdev.dashboards.hub.no_developments_title', {
          defaultValue: 'No developments yet',
        })}
        description={t('propdev.dashboards.hub.no_developments_desc', {
          defaultValue:
            'Create your first development on the main Property Development page.',
        })}
      />
    );
  }

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
          },
        ]}
      />
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-content-primary">
            {t('propdev.dashboards.hub.title', {
              defaultValue: 'Property Development Dashboards',
            })}
          </h1>
          <p className="mt-0.5 text-xs text-content-tertiary">
            {t('propdev.dashboards.hub.subtitle', {
              defaultValue:
                'Sales velocity, inventory ageing, cash flow and conversion — scoped to one development.',
            })}
          </p>
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

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <DashboardTile
          title={t('propdev.dashboards.heatmap.card_title', {
            defaultValue: 'Inventory heatmap',
          })}
          icon={<Grid3X3 size={14} />}
          to="/property-dev/dashboards/inventory-heatmap"
        >
          <InventoryHeatmap developmentId={developmentId} />
        </DashboardTile>
        <DashboardTile
          title={t('propdev.dashboards.velocity.card_title', {
            defaultValue: 'Sales velocity',
          })}
          icon={<LineChartIcon size={14} />}
          to="/property-dev/dashboards/sales-velocity"
        >
          <SalesVelocity developmentId={developmentId} />
        </DashboardTile>
        <DashboardTile
          title={t('propdev.dashboards.cashflow.card_title', {
            defaultValue: 'Cash-flow waterfall',
          })}
          icon={<Coins size={14} />}
          to="/property-dev/dashboards/cashflow-waterfall"
        >
          <CashFlowWaterfall developmentId={developmentId} />
        </DashboardTile>
        <DashboardTile
          title={t('propdev.dashboards.ageing.card_title', {
            defaultValue: 'Inventory ageing',
          })}
          icon={<Clock size={14} />}
          to="/property-dev/dashboards/inventory-ageing"
        >
          <InventoryAgeing developmentId={developmentId} />
        </DashboardTile>
        <DashboardTile
          title={t('propdev.dashboards.funnel.card_title', {
            defaultValue: 'Funnel conversion',
          })}
          icon={<Filter size={14} />}
          to="/property-dev/dashboards/funnel-conversion"
        >
          <FunnelConversion developmentId={developmentId} />
        </DashboardTile>
        <Card className="flex min-h-[260px] flex-col p-3">
          <header className="mb-2 flex items-center gap-2">
            <Compass size={14} className="text-content-tertiary" />
            <h3 className="text-sm font-semibold">
              {t('propdev.dashboards.journey.card_title', {
                defaultValue: 'Buyer journey',
              })}
            </h3>
          </header>
          <p className="text-xs text-content-tertiary">
            {t('propdev.dashboards.journey.card_desc', {
              defaultValue:
                'Open any buyer from the Buyers tab to view their journey timeline.',
            })}
          </p>
        </Card>
        <Card className="flex min-h-[260px] flex-col p-3 md:col-span-2">
          <header className="mb-2 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-content-primary">
              <Sparkles size={14} className="text-content-tertiary" />
              {t('propdev.dashboards.insights.card_title', {
                defaultValue: 'Sales insights (v3124)',
              })}
            </h3>
            <Link
              to="/property-dev/dashboards/insights"
              className="text-2xs text-oe-blue hover:underline"
            >
              {t('propdev.dashboards.hub.open_full_view', {
                defaultValue: 'Open full view →',
              })}
            </Link>
          </header>
          <p className="text-xs text-content-tertiary">
            {t('propdev.dashboards.insights.card_desc', {
              defaultValue:
                'Cohort retention, time-to-close, lead-source CPA, conversion funnel and broker leaderboard — director-grade rollups across the full portfolio.',
            })}
          </p>
        </Card>
      </div>
    </div>
  );
}
