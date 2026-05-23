// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Geo Hub — all-projects global map.
 *
 * Lazy-loaded; this is the first module page so Suspense is the only
 * boundary needed.
 *
 * Chrome layout matches the project / development pages:
 *
 * * Top toolbar with title + scope segmented control + live counter.
 * * Left rail listing anchored projects (clickable → fly camera).
 * * Cesium canvas with HUD overlay (cursor lat/lon, altitude, scale bar,
 *   north arrow).
 * * Glass-panel empty state when no projects are anchored anywhere — so
 *   the user is never left staring at a blank globe wondering what to
 *   do next.
 * * Visible error banner when the anchored-projects endpoint fails so
 *   the user understands the page isn't broken — only the data fetch.
 *
 * No tileset sidebar in global mode — there is no project-scoped
 * map config to load.
 */

import { Suspense, lazy, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  Globe2,
  MapPin,
  ArrowUpRight,
  AlertTriangle,
  RefreshCw,
  Loader2,
  Info,
  ServerCrash,
} from 'lucide-react';

import { ApiError } from '@/shared/lib/api';
import { useProjectContextStore } from '@/stores/useProjectContextStore';

import { fetchAnchoredProjects } from './api';
import type { GeoCameraState, GeoCursorCoords } from './CesiumViewer';
import { GeoModePicker } from './GeoModePicker';
import { GeoOverlayHud } from './GeoOverlayHud';
import type { AnchoredProject, GeoPinBundle } from './types';

const CesiumViewer = lazy(() =>
  import('./CesiumViewer').then((m) => ({ default: m.CesiumViewer })),
);

/**
 * Glass-panel empty state for "no anchored projects anywhere".
 *
 * Distinct from ``GeoEmptyState`` (which is project-scoped). Lives in
 * this file because it's only used by the global view and needs to
 * compose with the left rail of the global layout.
 */
function GlobalNoProjectsEmpty() {
  const { t } = useTranslation();
  return (
    <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center p-6">
      <div
        className={[
          'pointer-events-auto relative w-full max-w-md overflow-hidden',
          'rounded-xl border border-white/10 bg-slate-900/70 p-6 text-slate-100',
          'shadow-xl backdrop-blur-md ring-1 ring-white/5',
        ].join(' ')}
        role="status"
      >
        <div
          aria-hidden
          className={[
            'pointer-events-none absolute -inset-px rounded-xl bg-gradient-to-br',
            'from-emerald-500/30 to-teal-500/20 opacity-60 blur-2xl',
            'ring-1 ring-emerald-400/20',
          ].join(' ')}
        />
        <div className="relative">
          <div
            className={[
              'mb-4 inline-flex h-10 w-10 items-center justify-center rounded-md',
              'bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/30',
            ].join(' ')}
          >
            <MapPin size={18} strokeWidth={2} />
          </div>
          <h3 className="text-base font-semibold text-white">
            {t('geo_hub.empty.global_no_projects_title', {
              defaultValue: 'No anchored projects yet',
            })}
          </h3>
          <p className="mt-1.5 text-sm leading-relaxed text-slate-300">
            {t('geo_hub.empty.global_no_projects_description', {
              defaultValue:
                'Anchor a project to a real-world coordinate to see it here. From any project page open the Geo tab and click Set project anchor.',
            })}
          </p>
          <Link
            to="/projects"
            className={[
              'mt-5 inline-flex items-center gap-1.5 rounded-md',
              'bg-white px-3 py-1.5 text-xs font-semibold text-slate-900',
              'shadow-sm transition hover:bg-slate-100',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60',
            ].join(' ')}
          >
            {t('geo_hub.empty.global_no_projects_cta', {
              defaultValue: 'Browse projects',
            })}
            <ArrowUpRight size={13} strokeWidth={2.25} />
          </Link>
        </div>
      </div>
    </div>
  );
}

/**
 * Left rail of the global Geo Hub — lists every anchored project with
 * coords. Clicking ``Focus`` flies the viewer's camera; ``Open`` deep
 * links into the project-scoped map.
 *
 * Status rendering covers loading, error and empty cases so the user
 * always knows why the rail is showing what it is.
 */
function AnchoredProjectsRail({
  projects,
  isLoading,
  isError,
  onRetry,
  focusedProjectId,
  onFocus,
}: {
  projects: AnchoredProject[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  focusedProjectId: string | null;
  onFocus: (project: AnchoredProject) => void;
}) {
  const { t } = useTranslation();
  return (
    <aside
      className={[
        'flex w-72 shrink-0 flex-col border-r border-border',
        'bg-surface-primary',
      ].join(' ')}
      aria-label={t('geo_hub.rail.aria', {
        defaultValue: 'Anchored projects',
      })}
    >
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-content-secondary">
            {t('geo_hub.rail.title', { defaultValue: 'Anchored projects' })}
          </h2>
          <p className="mt-0.5 text-2xs text-content-tertiary">
            {isLoading
              ? t('geo_hub.rail.counter_loading', { defaultValue: 'Loading…' })
              : isError
                ? t('geo_hub.rail.counter_error', {
                    defaultValue: 'Failed to load',
                  })
                : t('geo_hub.rail.counter', {
                    defaultValue: '{{count}} on the map',
                    count: projects.length,
                  })}
          </p>
        </div>
        {isError && (
          <button
            type="button"
            onClick={onRetry}
            className={[
              'inline-flex items-center gap-1 rounded-md border border-border px-2 py-1',
              'text-2xs font-medium text-content-secondary',
              'hover:bg-surface-secondary hover:text-content-primary',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue',
            ].join(' ')}
            aria-label={t('common.retry', { defaultValue: 'Retry' })}
          >
            <RefreshCw size={12} strokeWidth={2} />
            {t('common.retry', { defaultValue: 'Retry' })}
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="flex items-center justify-center gap-2 px-4 py-8 text-2xs text-content-tertiary">
            <Loader2 size={14} className="animate-spin" />
            <span>
              {t('geo_hub.rail.loading_long', {
                defaultValue: 'Fetching anchored projects…',
              })}
            </span>
          </div>
        )}
        {!isLoading && isError && (
          <div className="m-3 rounded-md border border-red-300/40 bg-red-50 px-3 py-3 text-2xs text-red-900 dark:bg-red-950/40 dark:text-red-100">
            <div className="flex items-start gap-2">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" />
              <div className="space-y-1">
                <div className="font-semibold">
                  {t('geo_hub.rail.error_title', {
                    defaultValue: 'Could not load projects',
                  })}
                </div>
                <div className="opacity-80">
                  {t('geo_hub.rail.error_hint', {
                    defaultValue:
                      'Globe is still navigable. The project list will repopulate once the backend responds.',
                  })}
                </div>
              </div>
            </div>
          </div>
        )}
        {!isLoading && !isError && projects.length === 0 && (
          <div className="px-4 py-8 text-center text-2xs text-content-tertiary">
            {t('geo_hub.rail.empty_inline', {
              defaultValue:
                'No anchored projects yet. The empty-state card on the globe explains how to add one.',
            })}
          </div>
        )}
        {!isLoading && !isError && projects.length > 0 && (
          <ul className="m-2 space-y-1">
            {projects.map((p) => {
              const isFocused = focusedProjectId === p.project_id;
              return (
                <li key={p.project_id}>
                  <div
                    className={[
                      'group rounded-md border px-3 py-2 transition-colors',
                      isFocused
                        ? 'border-emerald-400/60 bg-emerald-50 dark:bg-emerald-950/30'
                        : 'border-transparent hover:border-border hover:bg-surface-secondary',
                    ].join(' ')}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        aria-hidden
                        className={[
                          'inline-block h-2 w-2 shrink-0 rounded-full',
                          isFocused
                            ? 'bg-emerald-500 ring-2 ring-emerald-300/50'
                            : 'bg-emerald-500/80',
                        ].join(' ')}
                      />
                      <button
                        type="button"
                        onClick={() => onFocus(p)}
                        className={[
                          'min-w-0 flex-1 truncate text-left text-xs font-medium',
                          'text-content-primary hover:text-oe-blue',
                          'focus:outline-none focus-visible:underline',
                        ].join(' ')}
                        title={t('geo_hub.rail.focus_hint', {
                          defaultValue: 'Fly camera to this project',
                        })}
                      >
                        {p.project_name}
                      </button>
                      <Link
                        to={`/projects/${p.project_id}/geo`}
                        className={[
                          'inline-flex shrink-0 items-center gap-0.5 rounded',
                          'px-1.5 py-0.5 text-2xs font-medium text-oe-blue',
                          'opacity-0 transition group-hover:opacity-100',
                          'hover:bg-oe-blue/10',
                          'focus:outline-none focus:opacity-100 focus-visible:ring-2 focus-visible:ring-oe-blue',
                        ].join(' ')}
                        title={t('geo_hub.rail.open_hint', {
                          defaultValue: 'Open project map',
                        })}
                      >
                        {t('common.open', { defaultValue: 'Open' })}
                        <ArrowUpRight size={11} strokeWidth={2.25} />
                      </Link>
                    </div>
                    <div className="ml-4 mt-1 flex items-center gap-2 font-mono text-2xs text-content-tertiary">
                      <span className="tabular-nums">
                        {Number(p.lat).toFixed(4)},{' '}
                        {Number(p.lon).toFixed(4)}
                      </span>
                      {p.region_code && (
                        <span className="rounded bg-surface-tertiary px-1 py-px uppercase tracking-wider">
                          {p.region_code}
                        </span>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}

export function GeoHubPage() {
  const { t } = useTranslation();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const [cursorCoords, setCursorCoords] = useState<GeoCursorCoords | null>(
    null,
  );
  const [cameraState, setCameraState] = useState<GeoCameraState | null>(null);
  // When the user clicks a project in the rail we ask the viewer to fly
  // to it. This is the same mechanism used by ``focusedTilesetId`` in
  // the project view — the viewer reacts to the prop, the page owns it.
  const [focusedProjectId, setFocusedProjectId] = useState<string | null>(
    null,
  );

  // One pin per anchored project the user can access — degrades to an
  // empty list on backend failure so the globe still renders. The
  // visible failure banner / rail status keeps the user informed.
  const projectsQuery = useQuery({
    queryKey: ['geo-hub', 'anchored-projects'],
    queryFn: () => fetchAnchoredProjects(),
    staleTime: 60_000,
    retry: 1,
  });

  const projects = projectsQuery.data ?? [];
  const pins = useMemo<GeoPinBundle>(
    () => ({
      hse: [],
      punchlist: [],
      diary: [],
      projects,
    }),
    [projects],
  );

  // 404 from /api/v1/geo-hub/projects means the running backend is older
  // than this frontend bundle (or the module didn't load). Surface a
  // separate, dev-friendly hint instead of the generic fetch-failed
  // banner so the user (or dev) knows to restart / update the backend.
  const isStaleBackend =
    projectsQuery.error instanceof ApiError &&
    projectsQuery.error.status === 404;

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
              'bg-emerald-500/10 text-emerald-600 dark:text-emerald-300',
            ].join(' ')}
          >
            <Globe2 size={16} strokeWidth={2} />
          </span>
          <div>
            <h1 className="text-base font-semibold text-content-primary leading-tight">
              {t('geo_hub.global_title', {
                defaultValue: 'Geo Hub — Global view',
              })}
            </h1>
            <p className="text-2xs uppercase tracking-[0.14em] text-content-tertiary">
              {t('geo_hub.global_eyebrow', {
                defaultValue: 'All your projects on a 3D globe',
              })}
            </p>
          </div>
        </div>
        <p className="hidden flex-1 truncate text-xs text-content-secondary md:block">
          {t('geo_hub.global_subtitle_v2', {
            defaultValue:
              'Drag to rotate · scroll to zoom · click a project pin to open. Click a project in the left list to fly the camera.',
          })}
        </p>
        <div className="ml-auto">
          <GeoModePicker current="global" projectId={activeProjectId} />
        </div>
      </header>

      {/* Stale-backend banner — distinct from the generic fetch-failed
          banner because the user fix is different: restart / update the
          backend (or wait for it to come back up). */}
      {projectsQuery.isError && isStaleBackend && (
        <div className="border-b border-amber-300/40 bg-amber-50 px-5 py-2 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
          <div className="flex items-center gap-2">
            <ServerCrash size={13} className="shrink-0" />
            <span className="flex-1">
              {t('geo_hub.global_stale_backend', {
                defaultValue:
                  'The geo service is starting up or out of date. Reload in a moment, or contact your admin to restart the backend.',
              })}
            </span>
            <button
              type="button"
              onClick={() => projectsQuery.refetch()}
              className={[
                'inline-flex items-center gap-1 rounded-md border border-amber-300/50 px-2 py-0.5',
                'font-medium hover:bg-amber-100 dark:hover:bg-amber-900/40',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400',
              ].join(' ')}
            >
              <RefreshCw size={11} strokeWidth={2} />
              {t('common.retry', { defaultValue: 'Retry' })}
            </button>
          </div>
        </div>
      )}

      {/* Generic failure banner — visible up top so the user understands the rail
          status before scanning the canvas. Inline-dismissable retry. */}
      {projectsQuery.isError && !isStaleBackend && (
        <div className="border-b border-red-300/40 bg-red-50 px-5 py-2 text-xs text-red-900 dark:bg-red-950/40 dark:text-red-100">
          <div className="flex items-center gap-2">
            <AlertTriangle size={13} className="shrink-0" />
            <span className="flex-1">
              {t('geo_hub.global_fetch_failed', {
                defaultValue:
                  'Could not load anchored projects from the server. The globe is fully navigable; reload to retry.',
              })}
            </span>
            <button
              type="button"
              onClick={() => projectsQuery.refetch()}
              className={[
                'inline-flex items-center gap-1 rounded-md border border-red-300/50 px-2 py-0.5',
                'font-medium hover:bg-red-100 dark:hover:bg-red-900/40',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400',
              ].join(' ')}
            >
              <RefreshCw size={11} strokeWidth={2} />
              {t('common.retry', { defaultValue: 'Retry' })}
            </button>
          </div>
        </div>
      )}

      {/* First-load help banner — appears while the anchored-projects
          query is still in flight so the user is never staring at a blank
          slate wondering what's going on. Disappears as soon as we
          either resolve pins or hit an error state (which renders its
          own banner above). */}
      {projectsQuery.isLoading && !projectsQuery.isError && (
        <div className="border-b border-emerald-300/40 bg-emerald-50/70 px-5 py-2 text-xs text-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-100">
          <div className="flex items-center gap-2">
            <Info size={13} className="shrink-0" />
            <span className="flex-1">
              {t('geo_hub.global_first_load_hint', {
                defaultValue:
                  'Looking for your projects on the globe... If nothing appears, anchor a project from its settings page → Geo anchor.',
              })}
            </span>
          </div>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <AnchoredProjectsRail
          projects={projects}
          isLoading={projectsQuery.isLoading}
          isError={projectsQuery.isError}
          onRetry={() => projectsQuery.refetch()}
          focusedProjectId={focusedProjectId}
          onFocus={(p) => setFocusedProjectId(p.project_id)}
        />
        <main className="relative flex-1 overflow-hidden bg-slate-900">
          <Suspense
            fallback={
              <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-slate-300">
                <Loader2 size={20} className="animate-spin text-emerald-300" />
                <span className="font-medium">
                  {t('geo_hub.loading_viewer_title', {
                    defaultValue: 'Loading 3D globe runtime',
                  })}
                </span>
                <span className="text-xs text-slate-400">
                  {t('geo_hub.loading_viewer_hint', {
                    defaultValue: 'Streaming Cesium chunks (~3 MB) — first load only.',
                  })}
                </span>
              </div>
            }
          >
            <CesiumViewer
              mode="global"
              pins={pins}
              focusedProject={
                focusedProjectId
                  ? projects.find((p) => p.project_id === focusedProjectId) ?? null
                  : null
              }
              onMouseMove={setCursorCoords}
              onCameraChange={setCameraState}
              overlay={
                <>
                  <GeoOverlayHud
                    cursorLat={cursorCoords?.lat ?? null}
                    cursorLon={cursorCoords?.lon ?? null}
                    altitudeM={cameraState?.cameraAltitudeM ?? null}
                    headingDeg={cameraState?.headingDeg ?? null}
                    active
                  />
                  {/* Empty-state card only when the fetch succeeded and we
                      really do have zero anchored projects — never on
                      error, never while loading. */}
                  {!projectsQuery.isLoading &&
                    !projectsQuery.isError &&
                    projects.length === 0 && <GlobalNoProjectsEmpty />}
                </>
              }
            />
          </Suspense>
        </main>
      </div>
    </div>
  );
}

export default GeoHubPage;
