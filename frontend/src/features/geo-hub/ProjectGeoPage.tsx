// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Project-scoped Geo Hub page — /projects/:projectId/geo.
 *
 * Renders the lazy-loaded Cesium viewer scoped to one project's
 * anchor, imagery, tilesets, overlays and viewpoints. Layout:
 *
 * ```
 *   ┌──── header (title · anchor · scope picker) ──────┐
 *   │                                                  │
 *   │  ┌── tileset rail ──┐┌── Cesium canvas ──────┐   │
 *   │  │ status / counts  ││  HUD overlay + empty  │   │
 *   │  │ per-tileset card ││  state when needed    │   │
 *   │  └──────────────────┘└───────────────────────┘   │
 *   └──────────────────────────────────────────────────┘
 * ```
 *
 * Three distinct empty states are decided centrally here so the
 * Cesium viewer stays oblivious of project semantics.
 */

import { Suspense, lazy, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { MapPinned, AlertTriangle } from 'lucide-react';

import { getMapConfig } from './api';
import { GeoEmptyState, type GeoEmptyKind } from './GeoEmptyState';
import { GeoModePicker } from './GeoModePicker';
import { GeoOverlayHud } from './GeoOverlayHud';
import { TilesetSidebar } from './TilesetSidebar';
import type { Tileset } from './types';

const CesiumViewer = lazy(() =>
  import('./CesiumViewer').then((m) => ({ default: m.CesiumViewer })),
);

/**
 * Decide which "empty" overlay should paint over the canvas, if any.
 * Returns null when the map has data to render.
 */
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

export function ProjectGeoPage() {
  const { t } = useTranslation();
  const { projectId } = useParams<{ projectId: string }>();

  const { data, error, isLoading } = useQuery({
    queryKey: ['geo-hub', 'map-config', projectId],
    queryFn: () => getMapConfig(projectId!),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });

  const [hiddenIds, setHiddenIds] = useState<Set<string>>(() => new Set());
  const [focusedId, setFocusedId] = useState<string | null>(null);

  const tilesets = data?.tilesets;
  const emptyKind = useMemo(
    () => emptyStateFor(Boolean(data?.anchor), tilesets),
    [data?.anchor, tilesets],
  );

  if (!projectId) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-sm text-semantic-error">
        {t('geo_hub.missing_project', {
          defaultValue: 'Project id missing from URL.',
        })}
      </div>
    );
  }

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
              'bg-oe-blue/10 text-oe-blue',
            ].join(' ')}
          >
            <MapPinned size={16} strokeWidth={2} />
          </span>
          <div>
            <h1 className="text-base font-semibold leading-tight text-content-primary">
              {t('geo_hub.project_title', { defaultValue: 'Project map' })}
            </h1>
            <p className="text-2xs uppercase tracking-[0.14em] text-content-tertiary">
              {data?.anchor
                ? t('geo_hub.anchor_set', { defaultValue: 'Anchored' })
                : t('geo_hub.anchor_missing', { defaultValue: 'Not yet anchored' })}
            </p>
          </div>
        </div>
        {data?.anchor && (
          <div className="hidden items-center gap-3 text-xs text-content-secondary md:flex">
            <span className="font-mono tabular-nums">
              {Number(data.anchor.lat).toFixed(4)},{' '}
              {Number(data.anchor.lon).toFixed(4)}
            </span>
            <span className="text-content-tertiary">
              EPSG:{data.anchor.epsg_code}
            </span>
          </div>
        )}
        <div className="ml-auto">
          <GeoModePicker current="project" projectId={projectId} />
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <TilesetSidebar
          tilesets={data?.tilesets}
          isLoading={isLoading}
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
          {!error && isLoading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center text-xs text-slate-300">
              {t('geo_hub.loading_config', {
                defaultValue: 'Loading geo configuration...',
              })}
            </div>
          )}
          {!error && data && (
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
                mode="project"
                mapConfig={data}
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

export default ProjectGeoPage;
