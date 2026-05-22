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
 * * Single-column canvas with the Cesium viewer.
 * * HUD overlay (cursor lat/lon, altitude, scale bar, north arrow).
 *
 * No tileset sidebar in global mode — there is no project-scoped
 * map config to load.
 */

import { Suspense, lazy } from 'react';
import { useTranslation } from 'react-i18next';
import { Globe2 } from 'lucide-react';

import { useProjectContextStore } from '@/stores/useProjectContextStore';

import { GeoModePicker } from './GeoModePicker';
import { GeoOverlayHud } from './GeoOverlayHud';

const CesiumViewer = lazy(() =>
  import('./CesiumViewer').then((m) => ({ default: m.CesiumViewer })),
);

export function GeoHubPage() {
  const { t } = useTranslation();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);

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
              {t('geo_hub.title', { defaultValue: 'Geo Hub' })}
            </h1>
            <p className="text-2xs uppercase tracking-[0.14em] text-content-tertiary">
              {t('geo_hub.global_eyebrow', { defaultValue: 'Earth-scale view' })}
            </p>
          </div>
        </div>
        <p className="hidden flex-1 truncate text-xs text-content-secondary md:block">
          {t('geo_hub.global_subtitle', {
            defaultValue:
              'Map of every project anchor — drop into a project to see 3D Tiles, imagery, terrain, viewpoints and overlays.',
          })}
        </p>
        <div className="ml-auto">
          <GeoModePicker current="global" projectId={activeProjectId} />
        </div>
      </header>
      <main className="relative flex-1 overflow-hidden bg-slate-900">
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
            mode="global"
            overlay={
              <GeoOverlayHud
                cursorLat={null}
                cursorLon={null}
                altitudeM={null}
                active={false}
              />
            }
          />
        </Suspense>
      </main>
    </div>
  );
}

export default GeoHubPage;
