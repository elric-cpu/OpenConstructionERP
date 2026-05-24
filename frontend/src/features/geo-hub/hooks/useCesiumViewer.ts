// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Cesium viewer lifecycle hook.
 *
 * Wraps Cesium's ``Viewer`` constructor + ``destroy()`` cleanup so the
 * component code stays focused on event wiring + UI. The hook is
 * intentionally framework-light: a single ``useEffect`` body, no
 * external deps beyond React.
 */

import { useEffect, useRef, useState } from 'react';

import type { MapConfig } from '../types';

type ViewerHandle = {
  destroy: () => void;
};

type CesiumLike = {
  Viewer: new (
    container: HTMLElement,
    options?: Record<string, unknown>,
  ) => ViewerHandle;
  EllipsoidTerrainProvider: new () => unknown;
  UrlTemplateImageryProvider: new (options: Record<string, unknown>) => unknown;
  ImageryLayer: new (provider: unknown) => unknown;
};

/**
 * Hook return:
 *
 * * ``ref`` — pass to the container ``<div ref={ref} />``.
 * * ``status`` — `'pending'` while Cesium loads, `'loaded'` once the
 *   viewer is constructed, `'absent'` when CesiumJS is not installed.
 */
export function useCesiumViewer(_mapConfig?: MapConfig) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<'pending' | 'loaded' | 'absent'>(
    'pending',
  );

  useEffect(() => {
    let disposed = false;
    let viewer: ViewerHandle | null = null;

    (async () => {
      let cesium: CesiumLike | null = null;
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        cesium = (await import('cesium')) as any;
      } catch {
        cesium = null;
      }
      if (disposed) return;
      if (!cesium || !ref.current) {
        setStatus(cesium ? 'pending' : 'absent');
        return;
      }
      try {
        viewer = new cesium.Viewer(ref.current, {
          terrainProvider: new cesium.EllipsoidTerrainProvider(),
          // OSM base imagery — Cesium >= 1.107 falls back to Ion-backed
          // Bing Maps when baseLayer is unset, which silently 401s
          // without an ion token. Explicit OSM keeps the viewer working
          // out of the box per the architecture guide "no vendor lock-in".
          baseLayer: new cesium.ImageryLayer(
            new cesium.UrlTemplateImageryProvider({
              url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              credit: '© OpenStreetMap contributors',
              maximumLevel: 19,
            }),
          ),
          baseLayerPicker: false,
        });
        setStatus('loaded');
      } catch {
        setStatus('absent');
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
    };
  }, []);

  return { ref, status };
}
