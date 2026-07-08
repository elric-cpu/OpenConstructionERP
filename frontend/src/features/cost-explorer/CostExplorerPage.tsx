// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Cost Explorer - one search-first workspace over the cost and resource
// databases. Five tabs, one backbone (the resource -> work reverse index):
//   By resources | Find work | Analog rates | Compare bases | Substitute
// Any result can hand its work or code to another tab, so an estimator moves
// from "which works use this material" to "which analog rate fits this need"
// to "how is it priced elsewhere" to "what if I swap it" without re-entering
// anything.

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Boxes, GitCompareArrows, RefreshCw, Repeat2, Scale, Search } from 'lucide-react';
import { Button, PageHeader, TabBar, tabIds } from '@/shared/ui';
import { getErrorMessage } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';
import { getIndexStatus, reindex } from './api';
import { ByResourcesPanel } from './ByResourcesPanel';
import { FindWorkPanel } from './FindWorkPanel';
import { AnalogRatesPanel } from './AnalogRatesPanel';
import { ComparePanel } from './ComparePanel';
import { SubstitutePanel } from './SubstitutePanel';
import type { CostExplorerTab, CrossNav, SubstituteSeed } from './types';

/** Local tab set: the shared four (see {@link CostExplorerTab}) plus the
 *  analog-rates compare wired in here. Kept local so the cross-tab nav contract
 *  in ``types.ts`` stays untouched. */
type ExplorerTab = CostExplorerTab | 'analogs';

export function CostExplorerPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<ExplorerTab>('by-resources');
  const [compareCode, setCompareCode] = useState('');
  const [subSeed, setSubSeed] = useState<SubstituteSeed | null>(null);

  const nav: CrossNav = {
    openCompare: (code) => {
      setCompareCode(code);
      setTab('compare');
    },
    openSubstitute: (seed) => {
      setSubSeed(seed);
      setTab('substitute');
    },
  };

  const ids = tabIds('cost-explorer');
  const tabs = [
    { id: 'by-resources' as const, label: t('costExplorer.tabs.byResources', { defaultValue: 'By resources' }), icon: <Boxes className="h-4 w-4" /> },
    { id: 'find-work' as const, label: t('costExplorer.tabs.findWork', { defaultValue: 'Find work' }), icon: <Search className="h-4 w-4" /> },
    { id: 'analogs' as const, label: t('costExplorer.tabs.analogs', { defaultValue: 'Analog rates' }), icon: <Scale className="h-4 w-4" /> },
    { id: 'compare' as const, label: t('costExplorer.tabs.compare', { defaultValue: 'Compare bases' }), icon: <GitCompareArrows className="h-4 w-4" /> },
    { id: 'substitute' as const, label: t('costExplorer.tabs.substitute', { defaultValue: 'Substitute' }), icon: <Repeat2 className="h-4 w-4" /> },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        srTitle={t('costExplorer.title', { defaultValue: 'Cost Explorer' })}
        subtitle={t('costExplorer.subtitle', {
          defaultValue: 'Find priced work by the resources it uses, search the catalogs, compare price bases and test substitutions.',
        })}
      />

      <IndexStatusNote />

      <div>
        <TabBar<ExplorerTab>
          tabs={tabs}
          activeId={tab}
          onChange={setTab}
          idPrefix="cost-explorer"
          ariaLabel={t('costExplorer.title', { defaultValue: 'Cost Explorer' })}
        />
        {/* All five panels stay mounted; only the active one is shown. Keeping
            them mounted preserves each panel's in-progress input (picked
            resources, a typed query, its results) when the user switches tabs
            and comes back, instead of resetting it on every switch. Every
            panel's data fetch is gated (mutation or an enabled query), so the
            hidden panels issue no requests until acted on. */}
        <div role="tabpanel" id={ids.panelId('by-resources')} aria-labelledby={ids.tabId('by-resources')} hidden={tab !== 'by-resources'} className="pt-4">
          <ByResourcesPanel nav={nav} />
        </div>
        <div role="tabpanel" id={ids.panelId('find-work')} aria-labelledby={ids.tabId('find-work')} hidden={tab !== 'find-work'} className="pt-4">
          <FindWorkPanel nav={nav} />
        </div>
        <div role="tabpanel" id={ids.panelId('analogs')} aria-labelledby={ids.tabId('analogs')} hidden={tab !== 'analogs'} className="pt-4">
          <AnalogRatesPanel nav={nav} />
        </div>
        <div role="tabpanel" id={ids.panelId('compare')} aria-labelledby={ids.tabId('compare')} hidden={tab !== 'compare'} className="pt-4">
          <ComparePanel code={compareCode} onCodeChange={setCompareCode} />
        </div>
        <div role="tabpanel" id={ids.panelId('substitute')} aria-labelledby={ids.tabId('substitute')} hidden={tab !== 'substitute'} className="pt-4">
          <SubstitutePanel seed={subSeed} />
        </div>
      </div>
    </div>
  );
}

/**
 * Surfaces when the reverse index is empty but there are works to index, or when
 * a loaded cost base carries works that are missing from the index (e.g. a large
 * second base imported past the auto-rebuild cap). Offers a one-click rebuild;
 * managers succeed, others get a clear message. Silent once every base is indexed.
 */
function IndexStatusNote() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const status = useQuery({
    queryKey: ['cost-explorer', 'status'],
    queryFn: getIndexStatus,
    staleTime: 60_000,
  });

  const rebuild = useMutation({
    mutationFn: reindex,
    onSuccess: (r) => {
      addToast({
        type: 'success',
        title: t('costExplorer.index.rebuilt', { defaultValue: 'Resource index rebuilt' }),
        message: t('costExplorer.index.rebuiltDetail', {
          defaultValue: '{{edges}} resource links across {{items}} works.',
          edges: r.edges_written,
          items: r.items_scanned,
        }),
      });
      queryClient.invalidateQueries({ queryKey: ['cost-explorer', 'status'] });
    },
    onError: (e) => {
      addToast({
        type: 'error',
        title: t('costExplorer.index.rebuildFailed', { defaultValue: 'Could not rebuild the index' }),
        message: getErrorMessage(e),
      });
    },
  });

  const data = status.data;
  const isEmpty = !!data && data.indexed_edges === 0 && data.cost_items > 0;
  const staleRegions = data?.unindexed_regions ?? [];
  const show = isEmpty || staleRegions.length > 0;
  if (!show) return null;

  const message = isEmpty
    ? t('costExplorer.index.empty', {
        defaultValue: 'The resource index is empty, so by-resources search has nothing to match yet. Rebuild it to index the loaded cost bases.',
      })
    : t('costExplorer.index.stale', {
        defaultValue:
          'Some loaded cost bases are not in the resource index yet ({{regions}}), so by-resources search will miss them. Rebuild to index them.',
        regions: staleRegions.join(', '),
      });

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-semantic-warning/30 bg-semantic-warning/10 px-3 py-2.5">
      <AlertTriangle className="h-4 w-4 shrink-0 text-semantic-warning" aria-hidden />
      <span className="min-w-0 flex-1 text-sm text-content-secondary">{message}</span>
      <Button size="sm" variant="secondary" onClick={() => rebuild.mutate()} disabled={rebuild.isPending}>
        <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${rebuild.isPending ? 'animate-spin' : ''}`} />
        {rebuild.isPending ? t('costExplorer.index.rebuilding', { defaultValue: 'Rebuilding...' }) : t('costExplorer.index.rebuild', { defaultValue: 'Rebuild index' })}
      </Button>
    </div>
  );
}
