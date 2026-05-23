// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Pure-side-effect React component that wires raster overlays into a
 * Cesium viewer.
 *
 * Responsibilities:
 *
 * * Renders each visible overlay as a ``SingleTileImageryProvider`` over
 *   the ``Rectangle`` bounding its four corner coordinates.
 * * Applies ``opacity`` and ``z_order`` per layer.
 * * Optionally clips an active overlay with a GeoJSON crop polygon
 *   (Cesium ``ClippingPolygonCollection`` when available — degrades
 *   gracefully on older runtimes where the API is absent).
 * * In ``editMode === 'corners'`` materialises four draggable corner
 *   handle entities and PATCHes the overlay on drop.
 * * In ``editMode === 'crop'`` listens for LEFT_CLICK to append polygon
 *   vertices, ENTER to close + PATCH, ESC to cancel.
 *
 * Receives the runtime via the ``cesium`` and ``viewer`` props (handed
 * down by the parent's ``onViewerReady`` callback). Renders nothing
 * visible itself; all painting happens through Cesium primitives.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';

import {
  listAnchors,
  listRasterOverlays,
  rasterOverlayImageUrl,
  updateRasterOverlay,
} from './api';
import type {
  CropPolygon,
  GeoRasterOverlay,
  GeoRasterOverlayPatch,
} from './types';

import type { OverlayEditMode } from './OverlayPanel';

// Minimum bbox dimension (in radians) below which Cesium's
// ``Rectangle.fromCartographicArray`` throws DeveloperError. ~1e-6 rad
// is ~10 cm at the equator — well below any sane raster footprint.
const MIN_BBOX_DIM_RAD = 1e-6;
// 200 m default fallback square when the overlay has no usable corners
// but the project does have a geo anchor.
const FALLBACK_HALF_SIZE_M = 100;
const METERS_PER_DEGREE = 111_320;

/**
 * Validate that an overlay's four corners can produce a non-degenerate
 * Cesium ``Rectangle``. Exposed so OverlayPanel can surface a soft
 * "Needs corners" badge without trying to render the layer.
 */
export function isOverlayDegenerate(o: GeoRasterOverlay): boolean {
  const corners = o.corners_geojson;
  if (!Array.isArray(corners) || corners.length !== 4) return true;
  for (const p of corners) {
    if (
      !Array.isArray(p) ||
      p.length !== 2 ||
      !Number.isFinite(p[0]) ||
      !Number.isFinite(p[1])
    ) {
      return true;
    }
  }
  // All four corners must be pairwise distinct.
  const seen = new Set<string>();
  for (const p of corners) {
    const key = `${p[0].toFixed(8)},${p[1].toFixed(8)}`;
    if (seen.has(key)) return true;
    seen.add(key);
  }
  const lons = corners.map((p) => p[0]);
  const lats = corners.map((p) => p[1]);
  const dLon = ((Math.max(...lons) - Math.min(...lons)) * Math.PI) / 180;
  const dLat = ((Math.max(...lats) - Math.min(...lats)) * Math.PI) / 180;
  return dLon < MIN_BBOX_DIM_RAD || dLat < MIN_BBOX_DIM_RAD;
}

interface OverlayLayerProps {
  projectId: string;
  cesium: unknown | null;
  viewer: unknown | null;
  activeOverlayId: string | null;
  editMode: OverlayEditMode;
  onSelectOverlay: (id: string | null) => void;
  onChangeEditMode: (mode: OverlayEditMode) => void;
}

/* eslint-disable @typescript-eslint/no-explicit-any */

export function OverlayLayer({
  projectId,
  cesium,
  viewer,
  activeOverlayId,
  editMode,
  onSelectOverlay: _onSelectOverlay,
  onChangeEditMode,
}: OverlayLayerProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const overlaysQuery = useQuery({
    queryKey: ['geo-hub', 'raster-overlays', projectId],
    queryFn: () => listRasterOverlays(projectId, { includeHidden: true }),
    enabled: Boolean(projectId),
    staleTime: 15_000,
  });
  const overlays = overlaysQuery.data ?? [];

  // Project anchor — only used to synthesise a 200 m × 200 m fallback
  // rectangle when an overlay has no usable corners. Cheap query; reuses
  // the same key as the rest of the geo-hub surface.
  const anchorsQuery = useQuery({
    queryKey: ['geo-hub', 'anchors', projectId],
    queryFn: () => listAnchors(projectId),
    enabled: Boolean(projectId),
    staleTime: 60_000,
  });
  const projectAnchor = anchorsQuery.data?.[0] ?? null;

  const patchMutation = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: GeoRasterOverlayPatch;
    }) => updateRasterOverlay(id, body),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ['geo-hub', 'raster-overlays', projectId],
      }),
    onError: (err) => {
      useToastStore.getState().addToast({
        type: 'error',
        title: t('geo.overlays.toast_patch_failed', {
          defaultValue: 'Could not save overlay change',
        }),
        message: getErrorMessage(err),
      });
    },
  });

  // Layer registry: Cesium ImageryLayer instances keyed by overlay id.
  const layerMapRef = useRef<Map<string, any>>(new Map());
  const cornerEntitiesRef = useRef<any[]>([]);
  const cropEntityRef = useRef<any | null>(null);
  // Ref not state — each polygon vertex comes from a Cesium event
  // handler that fires outside React's scheduling. Storing the array in
  // a ref avoids the render → effect → setState → render loop that
  // caused the "Maximum update depth exceeded" warning. The light
  // ``cropCount`` state is the ONLY render trigger and is only read by
  // the data-* attribute below (Playwright assertion + future UI badge).
  const cropPointsRef = useRef<[number, number][]>([]);
  const [cropCount, setCropCount] = useState(0);
  // One warn per overlay-id per session — Cesium DeveloperErrors get
  // re-thrown every render until the corners are fixed, so without
  // deduping the console fills with the same message hundreds of times.
  const loggedLayerErrorsRef = useRef<Set<string>>(new Set());

  // ── Imagery layer sync ───────────────────────────────────────────────
  useEffect(() => {
    if (!cesium || !viewer) return;
    const c: any = cesium;
    const v: any = viewer;
    const imageryLayers = v.scene?.imageryLayers ?? v.imageryLayers;
    if (!imageryLayers) return;

    const seen = new Set<string>();
    const sorted = [...overlays].sort(
      (a, b) => (a.z_order ?? 0) - (b.z_order ?? 0),
    );

    for (const o of sorted) {
      seen.add(o.id);
      if (!o.visible) {
        const existing = layerMapRef.current.get(o.id);
        if (existing) {
          try {
            imageryLayers.remove(existing, false);
          } catch {
            /* already removed */
          }
          layerMapRef.current.delete(o.id);
        }
        continue;
      }
      let layer = layerMapRef.current.get(o.id);
      // Degenerate corners → soft skip (no Cesium DeveloperError). If
      // the project has a geo anchor we synthesise a 200 m × 200 m
      // fallback rectangle so the user still sees the raster on the
      // globe; the OverlayPanel surfaces a "Needs corners" badge.
      const degenerate = isOverlayDegenerate(o);
      const rect = degenerate
        ? makeFallbackRectangle(c, projectAnchor)
        : makeRectangle(c, o);
      if (!rect) continue;

      // Re-create the layer when its signature changes (url, corners,
      // crop, fallback-vs-real). Cesium ImageryLayer is immutable on
      // those axes.
      const signature = `${layerSignature(o)}|fb:${degenerate ? '1' : '0'}`;
      if (layer && layer._oeSignature !== signature) {
        try {
          imageryLayers.remove(layer, false);
        } catch {
          /* already gone */
        }
        layer = null;
        layerMapRef.current.delete(o.id);
      }

      if (!layer) {
        try {
          const provider = new c.SingleTileImageryProvider({
            url: rasterOverlayImageUrl(o.id),
            rectangle: rect,
          });
          layer = imageryLayers.addImageryProvider(provider);
          layer._oeSignature = signature;
          // Apply ClippingPolygon when the runtime supports it and a
          // crop polygon is set on this overlay.
          applyCrop(c, layer, o.crop_polygon_geojson);
          layerMapRef.current.set(o.id, layer);
          // Successful add — drop the log-once flag so a later
          // regression on this same overlay will warn once again.
          loggedLayerErrorsRef.current.delete(o.id);
        } catch (err) {
          if (!loggedLayerErrorsRef.current.has(o.id)) {
            loggedLayerErrorsRef.current.add(o.id);
            // eslint-disable-next-line no-console
            console.warn('[geo_hub] overlay layer add failed', o.id, err);
          }
          continue;
        }
      }

      layer.alpha = Number(o.opacity);
    }

    // Remove layers for overlays that vanished from the list.
    for (const [id, layer] of layerMapRef.current.entries()) {
      if (!seen.has(id)) {
        try {
          imageryLayers.remove(layer, false);
        } catch {
          /* already removed */
        }
        layerMapRef.current.delete(id);
        loggedLayerErrorsRef.current.delete(id);
      }
    }
  }, [overlays, cesium, viewer, projectAnchor]);

  // Final cleanup: drop all overlay layers on unmount / viewer teardown.
  useEffect(() => {
    return () => {
      if (!cesium || !viewer) return;
      const v: any = viewer;
      const imageryLayers = v.scene?.imageryLayers ?? v.imageryLayers;
      for (const layer of layerMapRef.current.values()) {
        try {
          imageryLayers?.remove(layer, false);
        } catch {
          /* gone */
        }
      }
      layerMapRef.current.clear();
    };
  }, [cesium, viewer]);

  // ── Edit corners — draggable handles ─────────────────────────────────
  const active = useMemo(
    () => overlays.find((o) => o.id === activeOverlayId) ?? null,
    [activeOverlayId, overlays],
  );

  useEffect(() => {
    if (!cesium || !viewer) return;
    const c: any = cesium;
    const v: any = viewer;
    // Always clear previous handles first.
    for (const e of cornerEntitiesRef.current) {
      try {
        v.entities.remove(e);
      } catch {
        /* gone */
      }
    }
    cornerEntitiesRef.current = [];
    if (editMode !== 'corners' || !active) return;

    const corners = active.corners_geojson;
    if (!Array.isArray(corners) || corners.length !== 4) return;

    for (let i = 0; i < 4; i += 1) {
      const point = corners[i];
      if (!point) continue;
      const [lon, lat] = point;
      const ent = v.entities.add({
        position: c.Cartesian3.fromDegrees(lon, lat, 0),
        point: {
          pixelSize: 16,
          color: c.Color?.fromCssColorString?.('#0ea5e9') ?? c.Color.DODGERBLUE,
          outlineColor:
            c.Color?.fromCssColorString?.('#ffffff') ?? c.Color.WHITE,
          outlineWidth: 2,
          heightReference: c.HeightReference?.CLAMP_TO_GROUND ?? 0,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        properties: { _oeCornerIndex: i, _oeOverlayId: active.id },
      });
      cornerEntitiesRef.current.push(ent);
    }

    // Drag wiring — we use a tiny imperative state machine bound to a
    // ScreenSpaceEventHandler.
    let dragIndex: number | null = null;
    let handler: any = null;
    try {
      handler = new c.ScreenSpaceEventHandler(v.scene.canvas);
      const screenToCartographic = (pos: any) => {
        const ray = v.camera.getPickRay?.(pos);
        const hit = ray
          ? v.scene.globe?.pick?.(ray, v.scene)
          : v.scene.pickPosition?.(pos);
        if (!hit) return null;
        return c.Cartographic.fromCartesian(hit);
      };

      handler.setInputAction((m: any) => {
        const picked = v.scene.pick?.(m.position);
        const idx = picked?.id?.properties?._oeCornerIndex?.getValue?.();
        if (typeof idx === 'number') {
          dragIndex = idx;
          v.scene.screenSpaceCameraController.enableInputs = false;
        }
      }, c.ScreenSpaceEventType.LEFT_DOWN);

      handler.setInputAction((m: any) => {
        if (dragIndex === null) return;
        const cart = screenToCartographic(m.endPosition);
        if (!cart) return;
        const lon = c.Math.toDegrees(cart.longitude);
        const lat = c.Math.toDegrees(cart.latitude);
        const ent = cornerEntitiesRef.current[dragIndex];
        if (ent) {
          ent.position = c.Cartesian3.fromDegrees(lon, lat, 0);
        }
      }, c.ScreenSpaceEventType.MOUSE_MOVE);

      handler.setInputAction(() => {
        if (dragIndex === null) return;
        // Read every corner's position back out so we PATCH the full
        // array atomically (matches the backend's validate-4 rule).
        const nextCorners: [number, number][] = cornerEntitiesRef.current.map(
          (ent) => {
            const cart = c.Cartographic.fromCartesian(
              ent.position.getValue(v.clock?.currentTime),
            );
            return [
              c.Math.toDegrees(cart.longitude),
              c.Math.toDegrees(cart.latitude),
            ] as [number, number];
          },
        );
        dragIndex = null;
        v.scene.screenSpaceCameraController.enableInputs = true;
        patchMutation.mutate({
          id: active.id,
          body: { corners_geojson: nextCorners },
        });
      }, c.ScreenSpaceEventType.LEFT_UP);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[geo_hub] corner-drag handler failed', err);
    }

    return () => {
      try {
        handler?.destroy?.();
      } catch {
        /* gone */
      }
      try {
        v.scene.screenSpaceCameraController.enableInputs = true;
      } catch {
        /* gone */
      }
    };
  }, [active, editMode, cesium, viewer, patchMutation]);

  // ── Edit crop polygon ────────────────────────────────────────────────
  // NB: ``patchMutation`` is deliberately EXCLUDED from the dep array
  // — react-query rebuilds the mutation object every render, which used
  // to re-attach the keydown listener on every keystroke and (with the
  // old setCropPoints-driven re-renders) was the original culprit for
  // the "Maximum update depth exceeded" warning. The handler reads the
  // current mutation via a closure-captured ref so it stays fresh
  // without re-subscribing.
  const patchMutationRef = useRef(patchMutation);
  useEffect(() => {
    patchMutationRef.current = patchMutation;
  }, [patchMutation]);

  useEffect(() => {
    if (!cesium || !viewer || editMode !== 'crop' || !active) {
      cropPointsRef.current = [];
      setCropCount(0);
      // Clear any preview entity left behind from a previous session.
      if (cropEntityRef.current) {
        try {
          (viewer as any)?.entities?.remove(cropEntityRef.current);
        } catch {
          /* gone */
        }
        cropEntityRef.current = null;
      }
      return;
    }

    const c: any = cesium;
    const v: any = viewer;
    let handler: any = null;

    const refreshPreview = (pts: [number, number][]) => {
      if (cropEntityRef.current) {
        try {
          v.entities.remove(cropEntityRef.current);
        } catch {
          /* gone */
        }
        cropEntityRef.current = null;
      }
      if (pts.length === 0) return;
      const positions = c.Cartesian3.fromDegreesArray(pts.flat());
      cropEntityRef.current = v.entities.add({
        polyline: {
          positions,
          width: 2,
          clampToGround: true,
          material:
            c.Color?.fromCssColorString?.('#f59e0b') ?? c.Color.ORANGE,
        },
      });
    };

    try {
      handler = new c.ScreenSpaceEventHandler(v.scene.canvas);
      handler.setInputAction((m: any) => {
        const ray = v.camera.getPickRay?.(m.position);
        const hit = ray
          ? v.scene.globe?.pick?.(ray, v.scene)
          : v.scene.pickPosition?.(m.position);
        if (!hit) return;
        const cart = c.Cartographic.fromCartesian(hit);
        const lon = c.Math.toDegrees(cart.longitude);
        const lat = c.Math.toDegrees(cart.latitude);
        // Mutate the ref — NOT React state — so the Cesium event
        // handler doesn't trigger a render on every click.
        cropPointsRef.current = [...cropPointsRef.current, [lon, lat]];
        refreshPreview(cropPointsRef.current);
        // Light counter so JSX `data-crop-points` (Playwright probe)
        // stays in sync. One render per click, no loop.
        setCropCount(cropPointsRef.current.length);
      }, c.ScreenSpaceEventType.LEFT_CLICK);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[geo_hub] crop click handler failed', err);
    }

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        cropPointsRef.current = [];
        setCropCount(0);
        refreshPreview([]);
        onChangeEditMode('idle');
      }
      if (e.key === 'Enter') {
        const pts = cropPointsRef.current;
        if (pts.length < 3) {
          useToastStore.getState().addToast({
            type: 'warning',
            title: t('geo.overlays.crop_too_few', {
              defaultValue: 'Crop needs at least 3 points',
            }),
          });
          return;
        }
        const first = pts[0];
        if (!first) return;
        const closed: [number, number][] = [...pts, first];
        const polygon: CropPolygon = {
          type: 'Polygon',
          coordinates: [closed],
        };
        // PATCH is fired ONLY on ENTER (the "finish crop" action),
        // never on individual vertex clicks — matches the task brief
        // and stops a burst of in-flight requests.
        patchMutationRef.current.mutate({
          id: active.id,
          body: { crop_polygon_geojson: polygon },
        });
        cropPointsRef.current = [];
        setCropCount(0);
        refreshPreview([]);
        onChangeEditMode('idle');
      }
    };
    window.addEventListener('keydown', onKey);

    return () => {
      window.removeEventListener('keydown', onKey);
      try {
        handler?.destroy?.();
      } catch {
        /* gone */
      }
      if (cropEntityRef.current) {
        try {
          v.entities.remove(cropEntityRef.current);
        } catch {
          /* gone */
        }
        cropEntityRef.current = null;
      }
    };
    // Intentionally excludes patchMutation (see ref above) — keeps the
    // effect stable across every render.
  }, [active, editMode, cesium, viewer, onChangeEditMode, t]);

  // Render nothing visible — every change is a Cesium primitive.
  // The hidden node carries data-testid so Playwright can confirm the
  // overlay-layer plumbing is active without a screen reader penalty.
  return (
    <span
      aria-hidden="true"
      data-testid="geo-overlay-layer-marker"
      data-overlay-count={overlays.length}
      data-edit-mode={editMode}
      data-crop-points={cropCount}
      className="sr-only"
    />
  );
}

// ── helpers ────────────────────────────────────────────────────────────

function makeRectangle(c: any, o: GeoRasterOverlay): any | null {
  if (!Array.isArray(o.corners_geojson) || o.corners_geojson.length !== 4) {
    return null;
  }
  const lons = o.corners_geojson.map((p) => p[0]);
  const lats = o.corners_geojson.map((p) => p[1]);
  const west = Math.min(...lons);
  const east = Math.max(...lons);
  const south = Math.min(...lats);
  const north = Math.max(...lats);
  if (
    !Number.isFinite(west) ||
    !Number.isFinite(east) ||
    !Number.isFinite(south) ||
    !Number.isFinite(north)
  ) {
    return null;
  }
  try {
    return c.Rectangle.fromDegrees(west, south, east, north);
  } catch {
    return null;
  }
}

/**
 * Synthesise a 200 m × 200 m square Rectangle centred on the project
 * anchor. Used as the "Center on globe" fallback when an overlay has no
 * usable corners but the project does have a geo anchor — preferable to
 * dropping the overlay silently.
 */
function makeFallbackRectangle(
  c: any,
  anchor: { lat: string; lon: string } | null,
): any | null {
  if (!anchor) return null;
  const lat = Number(anchor.lat);
  const lon = Number(anchor.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  const dLat = FALLBACK_HALF_SIZE_M / METERS_PER_DEGREE;
  // Cos(lat) shrinks degrees of longitude towards the poles — without
  // this the fallback square would distort into a wide rectangle at
  // high latitudes.
  const dLon =
    FALLBACK_HALF_SIZE_M /
    (METERS_PER_DEGREE * Math.max(Math.cos((lat * Math.PI) / 180), 1e-6));
  try {
    return c.Rectangle.fromDegrees(lon - dLon, lat - dLat, lon + dLon, lat + dLat);
  } catch {
    return null;
  }
}

function applyCrop(c: any, layer: any, polygon: CropPolygon | null): void {
  if (!polygon) return;
  if (typeof c.ClippingPolygon !== 'function') return;
  try {
    const ring = polygon.coordinates?.[0];
    if (!ring || ring.length < 3) return;
    const positions = c.Cartesian3.fromDegreesArray(ring.flat());
    const cp = new c.ClippingPolygon({ positions });
    if (typeof c.ClippingPolygonCollection === 'function') {
      const coll = new c.ClippingPolygonCollection({ polygons: [cp] });
      layer.clippingPolygons = coll;
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[geo_hub] crop polygon clip failed', err);
  }
}

function layerSignature(o: GeoRasterOverlay): string {
  const corners = (o.corners_geojson ?? [])
    .map((p) => `${p[0].toFixed(7)},${p[1].toFixed(7)}`)
    .join('|');
  const crop = o.crop_polygon_geojson
    ? `crop:${(o.crop_polygon_geojson.coordinates?.[0] ?? [])
        .map((p) => `${p[0].toFixed(7)},${p[1].toFixed(7)}`)
        .join('|')}`
    : 'nocrop';
  return `${o.raster_blob_url ?? ''}|${corners}|${crop}|z:${o.z_order}`;
}

export default OverlayLayer;
