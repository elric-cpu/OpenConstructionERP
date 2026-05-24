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
 *   │  ┌─ Cesium canvas (full width) ────────────────┐ │
 *   │  │ ┌─ tileset overlay (top-left, self-sized, │ │ │
 *   │  │ │ collapsible) ─┐                         │ │ │
 *   │  │ └────────────────┘                        │ │ │
 *   │  │ HUD + empty state + Cesium controls       │ │ │
 *   │  └─────────────────────────────────────────────┘ │
 *   └──────────────────────────────────────────────────┘
 * ```
 *
 * Three distinct empty states are decided centrally here so the
 * Cesium viewer stays oblivious of project semantics.
 */

import { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { MapPinned, AlertTriangle, ServerCrash } from 'lucide-react';

import { ApiError } from '@/shared/lib/api';
import { projectsApi } from '@/features/projects/api';

import { AnchorAdjustPanel } from './AnchorAdjustPanel';
import {
  fetchDiaryPhotoPins,
  fetchHsePins,
  fetchPunchlistPins,
  getMapConfig,
} from './api';
import type { GeoCameraState, GeoCursorCoords } from './CesiumViewer';
import { GeoEmptyState, type GeoEmptyKind } from './GeoEmptyState';
import { GeoModePicker } from './GeoModePicker';
import { GeoOverlayHud } from './GeoOverlayHud';
import { OverlayLayer } from './OverlayLayer';
import { OverlayPanel, type OverlayEditMode } from './OverlayPanel';
import { TilesetSidebar } from './TilesetSidebar';
import type { GeoPinBundle, Tileset } from './types';

const CesiumViewer = lazy(() =>
  import('./CesiumViewer').then((m) => ({ default: m.CesiumViewer })),
);

// Persisted across reloads so the user's preferred chrome density
// survives navigation. Versioned (`v1`) so a future incompatible rename
// never resurrects with stale boolean semantics.
const TILESETS_COLLAPSED_LS_KEY = 'oe.geo_hub.tilesets_collapsed.v1';

function readTilesetsCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(TILESETS_COLLAPSED_LS_KEY) === '1';
  } catch {
    return false;
  }
}

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
  // Deep-link context — ``?model=<bim_model_or_federation_id>`` focuses the
  // camera onto the matching tileset's boundingSphere once it loads.
  // ``?plot=<plot_id>``, ``?dev_id=<development_id>``, ``?phase=...`` and
  // ``?block=...`` further scope what the viewer should highlight.
  const [searchParams] = useSearchParams();
  const focusedModelId = searchParams.get('model');
  const focusedPlotId = searchParams.get('plot');
  const focusedDevId = searchParams.get('dev_id') ?? searchParams.get('development');
  const phaseFilter = searchParams.get('phase');
  const blockFilter = searchParams.get('block');

  const { data, error, isLoading } = useQuery({
    queryKey: ['geo-hub', 'map-config', projectId],
    queryFn: () => getMapConfig(projectId!),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });

  // Cross-module pin layers — three independent queries so a hiccup on
  // one module doesn't black out the others. Each falls back to an
  // empty list on failure so the map still renders the tilesets.
  const hsePinsQuery = useQuery({
    queryKey: ['geo-hub', 'hse-pins', projectId],
    queryFn: () => fetchHsePins(projectId!),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });
  const punchlistPinsQuery = useQuery({
    queryKey: ['geo-hub', 'punchlist-pins', projectId],
    queryFn: () => fetchPunchlistPins(projectId!),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });
  const diaryPinsQuery = useQuery({
    queryKey: ['geo-hub', 'diary-photo-pins', projectId],
    queryFn: () => fetchDiaryPhotoPins(projectId!),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });
  // Project record for the drift indicator — we need the typed
  // address text to compare against the cached anchor.address. Stale
  // for 5 minutes (project addresses don't change every render and
  // re-fetching here would race the anchor refetch on edits).
  const projectQuery = useQuery({
    queryKey: ['projects', 'detail', projectId],
    queryFn: () => projectsApi.get(projectId!),
    enabled: Boolean(projectId),
    staleTime: 5 * 60_000,
  });
  const projectAddressText = useMemo<string | null>(() => {
    const addr = projectQuery.data?.address;
    if (!addr) return null;
    const parts = [
      addr.street,
      addr.city,
      addr.state,
      addr.postal_code,
      addr.country,
    ];
    const line = parts
      .filter((p): p is string => typeof p === 'string' && p.trim() !== '')
      .join(', ');
    return line || null;
  }, [projectQuery.data?.address]);

  const pins = useMemo<GeoPinBundle>(
    () => ({
      hse: hsePinsQuery.data ?? [],
      punchlist: punchlistPinsQuery.data ?? [],
      diary: diaryPinsQuery.data ?? [],
    }),
    [hsePinsQuery.data, punchlistPinsQuery.data, diaryPinsQuery.data],
  );

  const [hiddenIds, setHiddenIds] = useState<Set<string>>(() => new Set());
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [panelCollapsed, setPanelCollapsed] = useState<boolean>(
    readTilesetsCollapsed,
  );
  // Raster overlay editing state — lifted here so OverlayPanel and
  // OverlayLayer agree on which overlay is being edited and in which mode.
  const [activeOverlayId, setActiveOverlayId] = useState<string | null>(
    null,
  );
  const [overlayEditMode, setOverlayEditMode] =
    useState<OverlayEditMode>('idle');
  // "Drag to adjust" toggle for the anchor — when on, the page captures
  // the next click on the map and PATCHes the anchor's lat/lon.
  const [anchorDragMode, setAnchorDragMode] = useState<boolean>(false);
  // Cesium runtime ref, populated by ``CesiumViewer.onViewerReady`` so
  // the overlay layer can attach its imagery + interaction handlers.
  const [cesiumRuntime, setCesiumRuntime] = useState<
    { cesium: unknown; viewer: unknown } | null
  >(null);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(
        TILESETS_COLLAPSED_LS_KEY,
        panelCollapsed ? '1' : '0',
      );
    } catch {
      /* localStorage disabled / quota full — UX still works in-memory */
    }
  }, [panelCollapsed]);
  // Live HUD state, fed by ``CesiumViewer`` via ``onMouseMove`` /
  // ``onCameraChange``. ``null`` cursor → HUD shows em-dashes; ``null``
  // camera → north arrow stays at 0°.
  const [cursorCoords, setCursorCoords] = useState<GeoCursorCoords | null>(
    null,
  );
  const [cameraState, setCameraState] = useState<GeoCameraState | null>(null);

  // Apply optional ?phase / ?block / ?dev_id deep-link filters to the
  // tileset list. The map-config endpoint already returns the project's
  // full set; we narrow client-side so deep-links from PropDev or BIM
  // can show just the relevant slice. Each filter is matched against
  // ``Tileset.metadata`` keys; falls through to "no match" when fields
  // are absent. When none of the filters are present this is a no-op.
  const allTilesets = data?.tilesets;
  const tilesets = useMemo(() => {
    if (!allTilesets) return allTilesets;
    if (!phaseFilter && !blockFilter && !focusedDevId) return allTilesets;
    return allTilesets.filter((ts) => {
      const meta = ts.metadata as Record<string, unknown> | undefined;
      if (!meta || typeof meta !== 'object') return false;
      if (phaseFilter && meta['phase_id'] !== phaseFilter) return false;
      if (blockFilter && meta['block_id'] !== blockFilter) return false;
      if (focusedDevId && meta['development_id'] !== focusedDevId) return false;
      return true;
    });
  }, [allTilesets, phaseFilter, blockFilter, focusedDevId]);
  const emptyKind = useMemo(
    () => emptyStateFor(Boolean(data?.anchor), tilesets),
    [data?.anchor, tilesets],
  );

  // Resolve ``?model=...`` to a Tileset.id by matching either the
  // polymorphic ``source_id`` (bim_model / federation) or the
  // ``metadata.cad_import_id`` stamped by the canonical-tileset
  // packager. Also honors ``?plot=...`` by matching ``metadata.plot_id``.
  // Falls back to ``null`` so the viewer skips flyTo() when no deep link
  // is in flight.
  const focusedTilesetId = useMemo<string | null>(() => {
    const list = tilesets;
    if (!list || list.length === 0) return null;
    if (!focusedModelId && !focusedPlotId) return null;
    const hit = list.find((ts) => {
      if (focusedModelId) {
        if (ts.source_id === focusedModelId) return true;
        const meta = ts.metadata as Record<string, unknown> | undefined;
        if (meta && typeof meta === 'object') {
          const cad = meta['cad_import_id'];
          if (typeof cad === 'string' && cad === focusedModelId) return true;
          const fed = meta['federation_id'];
          if (typeof fed === 'string' && fed === focusedModelId) return true;
        }
      }
      if (focusedPlotId) {
        const meta = ts.metadata as Record<string, unknown> | undefined;
        if (meta && typeof meta === 'object') {
          if (meta['plot_id'] === focusedPlotId) return true;
        }
      }
      return false;
    });
    return hit?.id ?? null;
  }, [focusedModelId, focusedPlotId, tilesets]);

  // 404 from /api/v1/geo-hub/map-config means either project doesn't
  // exist (user follows a broken deep-link) or backend is stale. Either
  // way the actionable hint is different from the generic error — we
  // expose it so the page can render the right banner.
  const isStaleBackend =
    error instanceof ApiError && error.status === 404;

  // Compose the viewer's map config with the filtered tileset list so
  // the Cesium scene only loads what the deep-link asked for. Cheap —
  // we only override one field on the existing bundle when filtered.
  const viewerMapConfig = useMemo(() => {
    if (!data) return data;
    if (tilesets === allTilesets) return data;
    return { ...data, tilesets: tilesets ?? [] };
  }, [data, tilesets, allTilesets]);

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
    // Full-bleed layout — negate AppLayout's <main> padding (px-4 pt-6 pb-4 sm:px-7)
    // so the map fills the viewport, then claim exactly viewport-minus-header
    // height so the Cesium canvas never spills past the visible browser area.
    <div className="-mx-4 -mt-6 -mb-4 flex h-[calc(100vh-var(--oe-header-height,52px))] w-[calc(100%+2rem)] flex-col sm:-mx-7 sm:w-[calc(100%+3.5rem)]">
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
        <p className="hidden flex-1 truncate text-xs text-content-tertiary md:block">
          {t('geo_hub.project_subtitle', {
            defaultValue:
              'Drag to rotate · scroll to zoom · click a pin to inspect',
          })}
        </p>
        <div className="ml-auto">
          <GeoModePicker current="project" projectId={projectId} />
        </div>
      </header>
      {/* Full-width canvas — the tileset rail is overlay-mounted on top
          (via CesiumViewer's ``overlay`` slot) so the map gets the full
          viewport width. Empty / loading / error states share that slot
          so they also paint above the canvas. */}
      <main className="relative flex-1 overflow-hidden bg-slate-900">
        {error && (
          <div className="absolute inset-0 z-30 flex items-center justify-center p-6">
            {isStaleBackend ? (
              <div className="inline-flex max-w-md items-start gap-3 rounded-lg border border-amber-300/40 bg-amber-950/60 px-4 py-3 text-sm text-amber-100 shadow-md backdrop-blur-md">
                <ServerCrash size={16} className="mt-0.5 shrink-0 text-amber-300" />
                <span>
                  {t('geo_hub.project_stale_backend', {
                    defaultValue:
                      'The geo service is starting up or out of date. Reload in a moment, or contact your admin to restart the backend.',
                  })}
                </span>
              </div>
            ) : (
              <div className="inline-flex max-w-md items-start gap-3 rounded-lg border border-red-300/40 bg-red-950/60 px-4 py-3 text-sm text-red-100 shadow-md backdrop-blur-md">
                <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-300" />
                <span>
                  {t('geo_hub.load_failed', {
                    defaultValue: 'Could not load geo data for this project.',
                  })}
                </span>
              </div>
            )}
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
              mapConfig={viewerMapConfig}
              pins={pins}
              focusedTilesetId={focusedTilesetId}
              onMouseMove={setCursorCoords}
              onCameraChange={setCameraState}
              onViewerReady={setCesiumRuntime}
              overlay={
                <>
                  <GeoOverlayHud
                    cursorLat={cursorCoords?.lat ?? null}
                    cursorLon={cursorCoords?.lon ?? null}
                    altitudeM={cameraState?.cameraAltitudeM ?? null}
                    headingDeg={cameraState?.headingDeg ?? null}
                    active
                  />
                  <TilesetSidebar
                    variant="overlay"
                    collapsed={panelCollapsed}
                    onToggleCollapsed={() => setPanelCollapsed((v) => !v)}
                    tilesets={tilesets}
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
                  <OverlayPanel
                    projectId={projectId}
                    activeOverlayId={activeOverlayId}
                    editMode={overlayEditMode}
                    onSelectOverlay={(id) => {
                      setActiveOverlayId(id);
                      if (id === null) setOverlayEditMode('idle');
                    }}
                    onChangeEditMode={setOverlayEditMode}
                  />
                  <OverlayLayer
                    projectId={projectId}
                    cesium={cesiumRuntime?.cesium ?? null}
                    viewer={cesiumRuntime?.viewer ?? null}
                    activeOverlayId={activeOverlayId}
                    editMode={overlayEditMode}
                    onSelectOverlay={setActiveOverlayId}
                    onChangeEditMode={setOverlayEditMode}
                  />
                  {emptyKind && (
                    <GeoEmptyState kind={emptyKind} projectId={projectId} />
                  )}
                  {data?.anchor && !emptyKind && (
                    <AnchorAdjustPanel
                      projectId={projectId}
                      anchor={data.anchor}
                      dragMode={anchorDragMode}
                      onToggleDragMode={() => setAnchorDragMode((v) => !v)}
                      projectAddressText={projectAddressText}
                    />
                  )}
                </>
              }
            />
          </Suspense>
        )}
      </main>
    </div>
  );
}

export default ProjectGeoPage;
