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

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Globe2, Download } from 'lucide-react';

import type { GeoPinBundle, MapConfig } from './types';

type ViewerMode = 'global' | 'project' | 'development';

/** Live cursor coordinates lifted from a ScreenSpaceEventHandler pick. */
export interface GeoCursorCoords {
  /** Latitude in degrees (-90..90). */
  lat: number;
  /** Longitude in degrees (-180..180). */
  lon: number;
  /** Surface elevation in metres above the WGS-84 ellipsoid at the pick. */
  altitudeM: number;
}

/** Live camera state lifted from ``viewer.camera.changed``. */
export interface GeoCameraState {
  /** Heading clockwise from north in degrees (0..360). */
  headingDeg: number;
  /** Camera eye altitude above the ellipsoid in metres. */
  cameraAltitudeM: number;
}

interface CesiumViewerProps {
  mode: ViewerMode;
  mapConfig?: MapConfig;
  /**
   * Cross-module geo pin layers (HSE incidents / punch-list items /
   * Daily Diary geo-tagged photos). Rendered as point entities in a
   * dedicated effect so refetches don't tear down the Cesium viewer.
   */
  pins?: GeoPinBundle;
  /**
   * Optional overlay rendered above the Cesium canvas (HUD, empty
   * states, custom badges). Rendered inside the same relative wrapper
   * so absolute-positioned children compose naturally.
   *
   * Purely a chrome hook — does not touch viewer lifecycle.
   */
  overlay?: ReactNode;
  /**
   * Called when the pointer moves over the globe. Receives the picked
   * surface coordinates, or ``null`` when the pointer is off-globe or
   * pick fails. Throttled with ``requestAnimationFrame`` so React state
   * doesn't thrash on every MOUSE_MOVE event.
   */
  onMouseMove?: (coords: GeoCursorCoords | null) => void;
  /**
   * Called when the camera changes. Receives the current heading
   * (degrees clockwise from north) and the eye altitude over the
   * ellipsoid. Cesium debounces the underlying event itself.
   */
  onCameraChange?: (state: GeoCameraState) => void;
}

/** Stable signature for the viewer effect: rebuild only when the
 * inputs that actually matter for the Cesium scene change. Without
 * this, React Query produces a fresh ``mapConfig`` reference every
 * refetch (every 30 s on stale revalidation) which would tear down
 * the entire Cesium viewer — wiping camera state and forcing the
 * ~3 MB runtime to reinitialise.
 */
function _viewerSignature(
  mode: ViewerMode,
  mapConfig?: MapConfig,
): string {
  if (!mapConfig) return `${mode}|nil`;
  const anchor = mapConfig.anchor
    ? `${mapConfig.anchor.lat},${mapConfig.anchor.lon},${mapConfig.anchor.alt}`
    : 'nil';
  const tilesets = (mapConfig.tilesets ?? [])
    .filter((t) => t.status === 'ready' && t.tileset_json_uri)
    .map((t) => `${t.id}:${t.tileset_json_uri}`)
    .sort()
    .join(';');
  return `${mode}|${mapConfig.project_id ?? ''}|${anchor}|${tilesets}`;
}

interface CesiumEntityLike {
  id: unknown;
}

interface CesiumEntityCollectionLike {
  add: (entity: Record<string, unknown>) => CesiumEntityLike;
  remove: (entity: CesiumEntityLike) => boolean;
  removeAll: () => void;
  values: CesiumEntityLike[];
}

interface CesiumCartesian2Like {
  x: number;
  y: number;
}

interface CesiumCartesian3Like {
  x: number;
  y: number;
  z: number;
}

interface CesiumCartographicLike {
  longitude: number;
  latitude: number;
  height: number;
}

interface CesiumEventLike {
  addEventListener: (cb: () => void) => () => void;
  removeEventListener: (cb: () => void) => void;
}

interface CesiumScreenSpaceEventHandlerLike {
  setInputAction: (
    cb: (movement: { endPosition?: CesiumCartesian2Like; position?: CesiumCartesian2Like }) => void,
    eventType: number,
  ) => void;
  removeInputAction: (eventType: number) => void;
  destroy: () => void;
}

type CesiumViewerInstance = {
  destroy: () => void;
  camera: {
    flyTo: (options: { destination: unknown }) => void;
    changed: CesiumEventLike;
    heading: number;
    positionCartographic: CesiumCartographicLike;
  };
  scene: {
    primitives: { add: (p: unknown) => unknown };
    canvas: HTMLCanvasElement;
    pickPosition?: (windowPosition: CesiumCartesian2Like) => CesiumCartesian3Like | undefined;
    globe?: {
      pick?: (ray: unknown, scene: unknown) => CesiumCartesian3Like | undefined;
    };
  };
  camera_changedFrustum?: unknown;
  entities: CesiumEntityCollectionLike;
  shadows: boolean;
};

interface CesiumLike {
  Viewer: new (
    container: HTMLElement,
    options?: Record<string, unknown>,
  ) => CesiumViewerInstance;
  Cartesian3: {
    fromDegrees: (lon: number, lat: number, alt: number) => unknown;
  };
  Cartographic: {
    fromCartesian: (cartesian: CesiumCartesian3Like) => CesiumCartographicLike;
  };
  Color: {
    RED: unknown;
    ORANGE: unknown;
    DODGERBLUE: unknown;
    WHITE: unknown;
    fromCssColorString?: (css: string) => unknown;
  };
  EllipsoidTerrainProvider: new () => unknown;
  Cesium3DTileset: {
    fromUrl: (url: string) => Promise<unknown>;
  };
  ScreenSpaceEventHandler: new (canvas: HTMLCanvasElement) => CesiumScreenSpaceEventHandlerLike;
  ScreenSpaceEventType: {
    MOUSE_MOVE: number;
  };
  Math: {
    toDegrees: (radians: number) => number;
    TWO_PI: number;
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

export function CesiumViewer({
  mode,
  mapConfig,
  pins,
  overlay,
  onMouseMove,
  onCameraChange,
}: CesiumViewerProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<CesiumViewerInstance | null>(null);
  const cesiumRef = useRef<CesiumLike | null>(null);
  // Track every entity we created for pin layers so the dedicated pins
  // effect can incrementally remove/re-add without tearing down user
  // entities created by other future code paths.
  const pinEntitiesRef = useRef<CesiumEntityLike[]>([]);
  // Latest callback refs so the viewer effect doesn't have to re-run
  // when only the parent's handler identity changes.
  const onMouseMoveRef = useRef(onMouseMove);
  const onCameraChangeRef = useRef(onCameraChange);
  onMouseMoveRef.current = onMouseMove;
  onCameraChangeRef.current = onCameraChange;
  const [cesiumStatus, setCesiumStatus] = useState<
    'pending' | 'loaded' | 'absent'
  >('pending');

  // Stable string signature of the viewer-relevant inputs. Re-running
  // the effect on every parent re-render (React Query returns a new
  // ``mapConfig`` object reference on each refetch) would destroy and
  // re-create the entire Cesium viewer — wiping camera state and
  // re-downloading the 3 MB runtime.
  const signature = useMemo(
    () => _viewerSignature(mode, mapConfig),
    [mode, mapConfig],
  );

  useEffect(() => {
    let disposed = false;
    let viewer: CesiumViewerInstance | null = null;
    let inputHandler: CesiumScreenSpaceEventHandlerLike | null = null;
    let removeCameraListener: (() => void) | null = null;
    let rafHandle: number | null = null;
    let pendingMouse: CesiumCartesian2Like | null = null;
    let lastMouseEmitWasNull = false;

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
        cesiumRef.current = cesium;
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

        // ───── Live HUD wiring ──────────────────────────────────────
        // MOUSE_MOVE fires on every pixel of pointer motion. We batch
        // through a single rAF so React only sees ~60 fps updates even
        // when the browser pumps 1000 Hz mice. The latest endPosition
        // wins; intermediate moves are coalesced.
        try {
          if (
            typeof cesium.ScreenSpaceEventHandler === 'function' &&
            cesium.ScreenSpaceEventType &&
            v.scene?.canvas
          ) {
            inputHandler = new cesium.ScreenSpaceEventHandler(v.scene.canvas);

            const flushMouse = () => {
              rafHandle = null;
              const cb = onMouseMoveRef.current;
              const pos = pendingMouse;
              pendingMouse = null;
              if (!cb || !viewer) return;
              if (!pos) {
                if (!lastMouseEmitWasNull) {
                  lastMouseEmitWasNull = true;
                  cb(null);
                }
                return;
              }
              const picked = viewer.scene.pickPosition?.(pos);
              if (!picked) {
                if (!lastMouseEmitWasNull) {
                  lastMouseEmitWasNull = true;
                  cb(null);
                }
                return;
              }
              try {
                const carto = cesium.Cartographic.fromCartesian(picked);
                const lat = cesium.Math.toDegrees(carto.latitude);
                const lon = cesium.Math.toDegrees(carto.longitude);
                if (
                  !Number.isFinite(lat) ||
                  !Number.isFinite(lon) ||
                  !Number.isFinite(carto.height)
                ) {
                  if (!lastMouseEmitWasNull) {
                    lastMouseEmitWasNull = true;
                    cb(null);
                  }
                  return;
                }
                lastMouseEmitWasNull = false;
                cb({ lat, lon, altitudeM: carto.height });
              } catch {
                if (!lastMouseEmitWasNull) {
                  lastMouseEmitWasNull = true;
                  cb(null);
                }
              }
            };

            const scheduleFlush = () => {
              if (rafHandle !== null) return;
              rafHandle = window.requestAnimationFrame(flushMouse);
            };

            inputHandler.setInputAction((movement) => {
              if (movement?.endPosition) {
                pendingMouse = movement.endPosition;
                scheduleFlush();
              }
            }, cesium.ScreenSpaceEventType.MOUSE_MOVE);

            // Pointer leaving the canvas should reset the HUD to "—".
            const canvas = v.scene.canvas;
            const handlePointerLeave = () => {
              pendingMouse = null;
              scheduleFlush();
            };
            canvas.addEventListener('pointerleave', handlePointerLeave);
            canvas.addEventListener('pointerout', handlePointerLeave);
            // Wrap destroy() so cleanup also removes the DOM listeners
            // we attached above.
            const originalDestroy = inputHandler.destroy.bind(inputHandler);
            inputHandler.destroy = () => {
              try {
                canvas.removeEventListener('pointerleave', handlePointerLeave);
                canvas.removeEventListener('pointerout', handlePointerLeave);
              } catch {
                /* canvas already detached — ignore */
              }
              originalDestroy();
            };
          }
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn('[geo_hub] mouse-move HUD wiring failed', err);
        }

        // Camera change → heading + altitude. The underlying Cesium
        // event already debounces (only fires when camera state
        // actually changed past a threshold), so no rAF needed here.
        try {
          if (v.camera?.changed?.addEventListener) {
            const emitCamera = () => {
              const cb = onCameraChangeRef.current;
              if (!cb || !viewer) return;
              try {
                const headingRad = viewer.camera.heading;
                let headingDeg = cesium.Math.toDegrees(headingRad);
                // Normalise to [0, 360).
                headingDeg = ((headingDeg % 360) + 360) % 360;
                const cameraAltitudeM = viewer.camera.positionCartographic.height;
                if (
                  Number.isFinite(headingDeg) &&
                  Number.isFinite(cameraAltitudeM)
                ) {
                  cb({ headingDeg, cameraAltitudeM });
                }
              } catch {
                /* camera not yet ready — skip this tick */
              }
            };
            removeCameraListener = v.camera.changed.addEventListener(emitCamera);
            // Emit once immediately so the HUD doesn't read "—" until
            // the user nudges the camera.
            emitCamera();
          }
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn('[geo_hub] camera-change HUD wiring failed', err);
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
      if (rafHandle !== null) {
        try {
          window.cancelAnimationFrame(rafHandle);
        } catch {
          /* already cancelled — ignore */
        }
        rafHandle = null;
      }
      if (removeCameraListener) {
        try {
          removeCameraListener();
        } catch {
          /* listener already gone — ignore */
        }
        removeCameraListener = null;
      }
      if (inputHandler) {
        try {
          inputHandler.destroy();
        } catch {
          /* already destroyed — ignore */
        }
        inputHandler = null;
      }
      if (viewer) {
        try {
          viewer.destroy();
        } catch {
          /* viewer already gone — ignore */
        }
      }
      viewerRef.current = null;
      cesiumRef.current = null;
      pinEntitiesRef.current = [];
    };
    // ``signature`` collapses ``mapConfig`` into a stable string that
    // only changes when something the viewer actually renders changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  // Stable signature for the pin layers — derived from the ids of each
  // pin so a refetch with identical content does not re-run the effect.
  const pinSignature = useMemo(() => {
    if (!pins) return 'nil';
    const hse = pins.hse.map((p) => p.incident_id).join(',');
    const punch = pins.punchlist.map((p) => p.item_id).join(',');
    const diary = pins.diary.map((p) => p.photo_id).join(',');
    return `hse:${hse}|pl:${punch}|dp:${diary}`;
  }, [pins]);

  // Incremental pin rendering — runs AFTER the viewer effect (and
  // whenever ``pins`` or the viewer status flip). We remove only the
  // entities we added ourselves so the viewer's other entities (added
  // by other future code paths) are not impacted.
  useEffect(() => {
    const v = viewerRef.current;
    const cesium = cesiumRef.current;
    if (!v || !cesium || cesiumStatus !== 'loaded') return;

    // Remove previously-added pin entities.
    for (const ent of pinEntitiesRef.current) {
      try {
        v.entities.remove(ent);
      } catch {
        /* entity may have been swept by viewer destroy — ignore */
      }
    }
    pinEntitiesRef.current = [];

    if (!pins) return;

    const addPin = (
      lon: number,
      lat: number,
      color: unknown,
      label: string,
      tag: string,
    ): void => {
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) return;
      try {
        const ent = v.entities.add({
          position: cesium.Cartesian3.fromDegrees(lon, lat, 0),
          point: {
            pixelSize: 12,
            color,
            outlineColor: cesium.Color.WHITE,
            outlineWidth: 2,
            // Heights above the terrain surface so points are visible
            // even where the model dips below the ellipsoid.
            heightReference: 1, // Cesium.HeightReference.CLAMP_TO_GROUND
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          label: {
            text: label,
            font: '12px sans-serif',
            pixelOffset: { x: 0, y: -18 },
            fillColor: cesium.Color.WHITE,
            outlineColor: cesium.Color.fromCssColorString?.('#000') ?? cesium.Color.WHITE,
            outlineWidth: 2,
            style: 2, // Cesium.LabelStyle.FILL_AND_OUTLINE
            showBackground: true,
            backgroundColor: cesium.Color.fromCssColorString?.('rgba(15,23,42,0.75)'),
            scale: 0.85,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          properties: { _oeGeoHubPinTag: tag },
        });
        pinEntitiesRef.current.push(ent);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('[geo_hub] pin add failed', tag, err);
      }
    };

    for (const p of pins.hse) {
      addPin(
        p.lon,
        p.lat,
        cesium.Color.RED,
        p.title ? `HSE: ${p.title}` : `HSE ${p.incident_number}`,
        `hse:${p.incident_id}`,
      );
    }
    for (const p of pins.punchlist) {
      addPin(
        p.lon,
        p.lat,
        cesium.Color.ORANGE,
        `Punch: ${p.title}`,
        `punch:${p.item_id}`,
      );
    }
    for (const p of pins.diary) {
      addPin(
        p.lon,
        p.lat,
        cesium.Color.DODGERBLUE,
        p.is_drone ? 'Drone photo' : p.is_360 ? '360° photo' : 'Diary photo',
        `diary:${p.photo_id}`,
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pinSignature, cesiumStatus]);

  return (
    <div className="relative h-full w-full">
      <div
        ref={containerRef}
        data-testid="geo-hub-cesium-container"
        className="h-full w-full bg-slate-900"
      />
      {cesiumStatus === 'pending' && (
        <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-slate-950/40 text-sm text-slate-200 backdrop-blur-sm">
          <div className="relative">
            <Globe2
              size={28}
              strokeWidth={1.5}
              className="text-emerald-300/80 animate-pulse"
            />
            <span
              aria-hidden
              className="absolute -inset-2 rounded-full bg-emerald-400/10 blur-xl"
            />
          </div>
          <span className="font-medium tracking-wide">
            {t('geo_hub.cesium_loading', {
              defaultValue: 'Loading Cesium...',
            })}
          </span>
          <span className="text-xs text-slate-400">
            {t('geo_hub.cesium_loading_hint', {
              defaultValue: 'Streaming the 3D globe runtime (~3 MB).',
            })}
          </span>
        </div>
      )}
      {cesiumStatus === 'absent' && (
        <div className="absolute inset-0 z-20 flex items-center justify-center p-6">
          <div className="relative w-full max-w-md overflow-hidden rounded-xl border border-white/10 bg-slate-900/70 p-6 text-center text-slate-100 shadow-xl backdrop-blur-md ring-1 ring-white/5">
            <div
              aria-hidden
              className="pointer-events-none absolute -inset-px rounded-xl bg-gradient-to-br from-amber-500/30 to-orange-500/20 opacity-60 blur-2xl ring-1 ring-amber-400/20"
            />
            <div className="relative">
              <div className="mx-auto mb-4 inline-flex h-10 w-10 items-center justify-center rounded-md bg-amber-500/15 text-amber-300 ring-1 ring-amber-400/30">
                <Download size={18} strokeWidth={2} />
              </div>
              <h3 className="text-base font-semibold text-white">
                {t('geo_hub.cesium_not_installed_title', {
                  defaultValue: 'CesiumJS is not installed',
                })}
              </h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-300">
                {t('geo_hub.cesium_not_installed', {
                  defaultValue:
                    'CesiumJS is not installed in this build. Geo viewer is in degraded mode.',
                })}
              </p>
              <code className="mt-4 inline-block rounded-sm bg-slate-800/80 px-2 py-1 font-mono text-xs text-slate-200 ring-1 ring-white/10">
                npm install cesium
              </code>
            </div>
          </div>
        </div>
      )}
      {/* Overlay slot — HUD, empty states, badges. Mounted last so it
          paints over the canvas; ``cesium`` canvas listens for input
          via its own event handlers and is therefore unaffected by
          ``pointer-events-none`` placement of HUD chrome above it. */}
      {overlay}
    </div>
  );
}

export default CesiumViewer;
