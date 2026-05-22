// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Per-development Geo Hub page — /property-dev/developments/:devId/geo.
 *
 * Same chrome as ``ProjectGeoPage`` but scoped to a single property_dev
 * development. The backing event ``property_dev.development.created``
 * subscriber already places the development on the project map, so this
 * page is mostly a convenience entry point inside the property_dev UX.
 */

import { Suspense, lazy, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Boxes, AlertTriangle } from 'lucide-react';

import { apiGet } from '@/shared/lib/api';

import { getMapConfig } from './api';
import { GeoEmptyState, type GeoEmptyKind } from './GeoEmptyState';
import { GeoModePicker } from './GeoModePicker';
import { GeoOverlayHud } from './GeoOverlayHud';
import { TilesetSidebar } from './TilesetSidebar';
import type { Tileset } from './types';

interface DevelopmentSummary {
  id: string;
  project_id: string;
  name: string;
}

const CesiumViewer = lazy(() =>
  import('./CesiumViewer').then((m) => ({ default: m.CesiumViewer })),
);

function emptyStateFor(
  hasAnchor: boolean,
  tilesets: Tileset[] | undefined,
): GeoEmptyKind | null {
  if (!hasAnchor) return 'no_anchor';
  const list = tilesets ?? [];
  if (list.length === 0) return 'no_tilesets';
  const allFailed = list.every((t) => t.status === 'failed' || t.status === 'obsolete');
  if (allFailed) return 'all_failed';
  return null;
}

export function DevelopmentGeoPage() {
  const { t } = useTranslation();
  const { devId } = useParams<{ devId: string }>();

  const development = useQuery({
    queryKey: ['property-dev', 'development', devId],
    queryFn: () =>
      apiGet<DevelopmentSummary>(`/v1/property-dev/developments/${devId}`),
    enabled: Boolean(devId),
    staleTime: 60_000,
  });

  const mapConfig = useQuery({
    queryKey: ['geo-hub', 'map-config', development.data?.project_id],
    queryFn: () => getMapConfig(development.data!.project_id),
    enabled: Boolean(development.data?.project_id),
    staleTime: 30_000,
  });

  const [hiddenIds, setHiddenIds] = useState<Set<string>>(() => new Set());
  const [focusedId, setFocusedId] = useState<string | null>(null);

  const tilesets = mapConfig.data?.tilesets;
  const emptyKind = useMemo(
    () => emptyStateFor(Boolean(mapConfig.data?.anchor), tilesets),
    [mapConfig.data?.anchor, tilesets],
  );

  const projectId = development.data?.project_id ?? null;
  const loading = development.isLoading || mapConfig.isLoading;
  const error = development.error || mapConfig.error;

  return (
    <div className="flex h-full w-full flex-col">
      <header
        className={[
          'flex items-center gap-4 border-b border-border bg-surface-primary',
          'px-5 py-3',
        ].join(' ')}
      >
        <div className="flex items-center gap-2.5">
          <span
            className={[
              'inline-flex h-8 w-8 items-center justify-center rounded-md',
              'bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-300',
            ].join(' ')}
          >
            <Boxes size={16} strokeWidth={2} />
          </span>
          <div>
            <h1 className="text-base font-semibold leading-tight text-content-primary">
              {t('geo_hub.development_title', {
                defaultValue: 'Development map',
              })}
            </h1>
            {development.data && (
              <p className="text-2xs uppercase tracking-[0.14em] text-content-tertiary">
                {development.data.name}
              </p>
            )}
          </div>
        </div>
        <div className="ml-auto">
          <GeoModePicker
            current="development"
            projectId={projectId}
            developmentId={devId ?? null}
          />
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <TilesetSidebar
          tilesets={mapConfig.data?.tilesets}
          isLoading={loading}
          hiddenIds={hiddenIds}
          focusedId={focusedId}
          onToggleVisibility={(id) =>
            setHiddenIds((prev) => {
              const next = new Set(prev);
              if (next.has(id)) next.delete(id);
              else next.add(id);
              return next;
            })
          }
          onFocus={(ts) => setFocusedId(ts.id)}
        />
        <main className="relative flex-1 overflow-hidden bg-slate-900">
          {error && (
            <div className="absolute inset-0 z-20 flex items-center justify-center p-6">
              <div className="inline-flex max-w-md items-start gap-3 rounded-lg border border-red-300/40 bg-red-950/60 px-4 py-3 text-sm text-red-100 shadow-md backdrop-blur-md">
                <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-300" />
                <span>
                  {t('geo_hub.load_failed', {
                    defaultValue: 'Could not load geo data for this project.',
                  })}
                </span>
              </div>
            </div>
          )}
          {!error && loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center text-xs text-slate-300">
              {t('geo_hub.loading_config', {
                defaultValue: 'Loading geo configuration...',
              })}
            </div>
          )}
          {!error && mapConfig.data && (
            <Suspense
              fallback={
                <div className="flex h-full items-center justify-center text-sm text-slate-300">
                  {t('geo_hub.loading_viewer', {
                    defaultValue: 'Loading Cesium viewer (~3 MB)...',
                  })}
                </div>
              }
            >
              <CesiumViewer
                mode="development"
                mapConfig={mapConfig.data}
                overlay={
                  <>
                    <GeoOverlayHud
                      cursorLat={null}
                      cursorLon={null}
                      altitudeM={null}
                      active={false}
                    />
                    {emptyKind && (
                      <GeoEmptyState kind={emptyKind} projectId={projectId} />
                    )}
                  </>
                }
              />
            </Suspense>
          )}
        </main>
      </div>
    </div>
  );
}

export default DevelopmentGeoPage;
