// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * CesiumJS viewer wrapper.
 *
 * Lazy-loaded — the dynamic import that lands this module also pulls
 * the Cesium runtime. Keeping the bundle isolated is enforced by the
 * Vite ``manualChunks`` rule in ``vite.config.ts`` which routes
 * ``node_modules/cesium*`` to its own ``vendor-cesium`` chunk.
 *
 * Defensive guards:
 *
 * * Cesium is imported via ``import('cesium')`` so a missing optional
 *   dependency (the community installer does not auto-install Cesium)
 *   never crashes the rest of the app. When Cesium is absent we render
 *   a friendly install hint instead.
 * * ``viewer.destroy()`` is wired to the effect cleanup — no DOM leak
 *   on route change.
 * * Tileset loading falls back silently when ``tileset_json_uri`` is
 *   absent so a freshly-anchored project doesn't error out.
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { MapConfig } from './types';

type ViewerMode = 'global' | 'project' | 'development';

interface CesiumViewerProps {
  mode: ViewerMode;
  mapConfig?: MapConfig;
}

interface CesiumLike {
  Viewer: new (
    container: HTMLElement,
    options?: Record<string, unknown>,
  ) => {
    destroy: () => void;
    camera: {
      flyTo: (options: { destination: unknown }) => void;
    };
    scene: {
      primitives: { add: (p: unknown) => unknown };
    };
    shadows: boolean;
  };
  Cartesian3: {
    fromDegrees: (lon: number, lat: number, alt: number) => unknown;
  };
  EllipsoidTerrainProvider: new () => unknown;
  Cesium3DTileset: {
    fromUrl: (url: string) => Promise<unknown>;
  };
}

async function loadCesium(): Promise<CesiumLike | null> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mod = (await import('cesium')) as any;
    // Cesium ships the runtime constructors on the module namespace itself
    // when imported via ESM. If the bundler resolved something that does not
    // expose ``Viewer``, the viewer init will throw — degrade gracefully and
    // log a diagnostic so we don't silently fall into "CesiumJS is not
    // installed" mode while the package is actually present.
    if (mod && typeof mod.Viewer !== 'function') {
      // eslint-disable-next-line no-console
      console.warn('[geo_hub] cesium import resolved but Viewer constructor is missing', Object.keys(mod || {}).slice(0, 10));
      return null;
    }
    return mod as CesiumLike;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[geo_hub] cesium dynamic import failed', err);
    return null;
  }
}

export function CesiumViewer({ mode, mapConfig }: CesiumViewerProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<ReturnType<CesiumLike['Viewer']['prototype']['destroy']> | null>(
    null,
  ) as { current: { destroy: () => void } | null };
  const [cesiumStatus, setCesiumStatus] = useState<
    'pending' | 'loaded' | 'absent'
  >('pending');

  useEffect(() => {
    let disposed = false;
    let viewer: { destroy: () => void } | null = null;

    (async () => {
      const cesium = await loadCesium();
      if (!cesium || disposed) {
        setCesiumStatus(cesium ? 'loaded' : 'absent');
        return;
      }
      const container = containerRef.current;
      if (!container) {
        setCesiumStatus('absent');
        return;
      }
      try {
        // Default to the ellipsoid terrain provider — zero-cost, no
        // ion key required. Enterprise customers wire their own ion
        // token via the Terrain admin page; we surface it through
        // the map-config bundle for them.
        const v = new cesium.Viewer(container, {
          terrainProvider: new cesium.EllipsoidTerrainProvider(),
          baseLayerPicker: false,
          timeline: mode === 'project' || mode === 'development',
          animation: mode === 'project' || mode === 'development',
          shouldAnimate: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: true,
          sceneModePicker: false,
        });
        viewer = v;
        viewerRef.current = v;
        v.shadows = true;

        if (mapConfig?.anchor) {
          const lat = Number(mapConfig.anchor.lat);
          const lon = Number(mapConfig.anchor.lon);
          const alt = Number(mapConfig.anchor.alt || 200);
          v.camera.flyTo({
            destination: cesium.Cartesian3.fromDegrees(
              lon, lat, Math.max(alt + 500, 1500),
            ),
          });
        }
        if (mapConfig?.tilesets) {
          for (const ts of mapConfig.tilesets) {
            if (ts.status !== 'ready' || !ts.tileset_json_uri) continue;
            try {
              const tileset = await cesium.Cesium3DTileset.fromUrl(
                ts.tileset_json_uri,
              );
              if (disposed) break;
              v.scene.primitives.add(tileset);
            } catch (err) {
              // One bad tileset must not kill the viewer.
              // eslint-disable-next-line no-console
              console.warn('[geo_hub] Tileset load failed', ts.id, err);
            }
          }
        }
        setCesiumStatus('loaded');
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('[geo_hub] Cesium viewer init failed', err);
        setCesiumStatus('absent');
      }
    })();

    return () => {
      disposed = true;
      if (viewer) {
        try {
          viewer.destroy();
        } catch {
          /* viewer already gone — ignore */
        }
      }
      viewerRef.current = null;
    };
  }, [mode, mapConfig]);

  return (
    <div className="relative h-full w-full">
      <div
        ref={containerRef}
        data-testid="geo-hub-cesium-container"
        className="h-full w-full bg-slate-900"
      />
      {cesiumStatus === 'pending' && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-slate-300">
          {t('geo_hub.cesium_loading', {
            defaultValue: 'Loading Cesium...',
          })}
        </div>
      )}
      {cesiumStatus === 'absent' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center text-sm text-slate-300">
          <p>
            {t('geo_hub.cesium_not_installed', {
              defaultValue:
                'CesiumJS is not installed in this build. Geo viewer is in degraded mode.',
            })}
          </p>
          <code className="rounded bg-slate-700 px-2 py-1 text-xs">
            npm install cesium
          </code>
        </div>
      )}
    </div>
  );
}

export default CesiumViewer;
