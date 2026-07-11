// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Interactive point-cloud viewer for the /pointcloud page.
 *
 * Downloads the server-decimated OEPC binary for one scan (see ./oepc.ts and
 * backend/app/modules/pointcloud/wire.py), drops the positions straight into a
 * THREE.Points geometry and renders with OrbitControls. Positions arrive
 * centre-relative so georeferenced clouds stay float32-precision-safe; the
 * world origin lives in the wire ``center``.
 *
 * Controls: color mode (RGB / height ramp / intensity / single color), point
 * size, density (re-requests with a different ``max_points`` cap) and re-fit.
 * The scan may still be processing server-side: 409 / 404 / 501 / 422 map to
 * friendly status panels instead of crashing the page.
 *
 * Inspection tools (all client-side, operating on the already-loaded
 * THREE.Points - see ./pointcloudTools.ts for the pure math behind each):
 *  - Cross-section: a world-Y height band rendered via clipping planes, plus
 *    a one-click top/plan view.
 *  - Measure: click two points to raycast-pick them and read straight-line /
 *    horizontal / vertical distance.
 *  - Clip box: an adjustable axis-aligned crop, also via clipping planes.
 *  - Elevation legend: a height-ramp gradient key shown in "height" color
 *    mode, with an optional pinned custom range.
 *  - Snapshot: exports the current canvas view as a PNG.
 * Cross-section and clip-box planes compose (a point must satisfy both) via
 * ``renderer.localClippingEnabled`` + ``material.clippingPlanes`` - no
 * geometry is rebuilt or CPU-filtered per point, so this stays smooth at
 * millions of points.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import {
  AlertCircle,
  ArrowDownToLine,
  Camera,
  Clock,
  Crop,
  Layers,
  Loader2,
  Maximize2,
  Minus,
  Pin,
  PinOff,
  Plus,
  RefreshCw,
  RotateCcw,
  Ruler,
  X,
} from 'lucide-react';
import { useThemeStore } from '@/stores/useThemeStore';
import { fetchScanPoints, ScanPointsError } from './api';
import { parseOepc, OepcParseError, type OepcCloud } from './oepc';
import {
  boxPlanes,
  computeMeasurement3D,
  deriveCloudBounds,
  formatLengthMm,
  formatMetersLabel,
  heightSlicePlanes,
  isWithinPlanes,
  scaleClipBox,
  slugifyForFilename,
  type BoxExtent,
  type Measurement3D,
  type PlaneEq,
} from './pointcloudTools';

export type ColorMode = 'rgb' | 'height' | 'intensity' | 'single';

type LoadPhase = 'loading' | 'ready' | 'error';
type ErrorKind = 'processing' | 'notfound' | 'reader' | 'decode' | 'generic';

/** Density presets: the server evenly decimates to at most this many points. */
const DENSITY_OPTIONS = [
  { value: 250_000, labelKey: 'pointcloud.density_fast', fallback: 'Fast (250K)' },
  { value: 1_500_000, labelKey: 'pointcloud.density_balanced', fallback: 'Balanced (1.5M)' },
  { value: 3_000_000, labelKey: 'pointcloud.density_high', fallback: 'High (3M)' },
  { value: 6_000_000, labelKey: 'pointcloud.density_max', fallback: 'Maximum (6M)' },
] as const;

/** Scene backgrounds matching the BIM viewer's light / dark pair. */
const BG_LIGHT = 0xf0f2f5;
const BG_DARK = 0x1a1a2e;

/** Fallback single color: the oe-blue accent. */
const SINGLE_COLOR = new THREE.Color(0x3b82f6);

/** Height-ramp stops, bottom to top (deep blue, cyan, green, yellow, red). */
const RAMP_STOPS: [number, number, number][] = [
  [0.19, 0.32, 0.93],
  [0.1, 0.74, 0.85],
  [0.18, 0.8, 0.35],
  [0.98, 0.83, 0.14],
  [0.94, 0.27, 0.18],
];

/** Sample the height ramp at t in [0, 1] into (r, g, b) 0-1 floats. */
function sampleRamp(t: number): [number, number, number] {
  const clamped = Math.min(1, Math.max(0, t));
  const scaled = clamped * (RAMP_STOPS.length - 1);
  const i = Math.min(RAMP_STOPS.length - 2, Math.floor(scaled));
  const f = scaled - i;
  const a = RAMP_STOPS[i] as [number, number, number];
  const b = RAMP_STOPS[i + 1] as [number, number, number];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

/** CSS gradient for the elevation legend, bottom (low/blue) to top
 *  (high/red) - built once from RAMP_STOPS so it stays in lockstep with
 *  `sampleRamp` above. */
const RAMP_GRADIENT_CSS = `linear-gradient(to top, ${RAMP_STOPS.map(
  ([r, g, b], i) =>
    `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}) ${
      (i / (RAMP_STOPS.length - 1)) * 100
    }%`,
).join(', ')})`;

/** High-visibility accent for the measure tool's line/markers/label -
 *  distinct from the oe-blue UI accent so it reads clearly against every
 *  color mode (RGB / height ramp / intensity / single color). */
const MEASURE_COLOR = 0xffd400;

/** Clip-box wireframe color - the oe-blue brand accent. */
const CLIP_BOX_COLOR = 0x3b82f6;

/** Build the per-vertex color buffer for the requested mode. `heightRange`
 *  optionally overrides the auto (bbox-derived) min/max used by the
 *  'height' ramp, letting the elevation legend's "pin range" control
 *  narrow or shift the ramp for extra contrast. */
function buildColors(
  cloud: OepcCloud,
  mode: ColorMode,
  heightRange?: { min: number; max: number } | null,
): Float32Array {
  const n = cloud.pointCount;
  const colors = new Float32Array(n * 3);

  if (mode === 'rgb' && cloud.rgb) {
    for (let i = 0; i < n * 3; i++) colors[i] = (cloud.rgb[i] ?? 0) / 255;
    return colors;
  }

  if (mode === 'intensity' && cloud.intensity) {
    for (let i = 0; i < n; i++) {
      const v = Math.min(1, Math.max(0, cloud.intensity[i] ?? 0));
      // Slight lift so the darkest points stay visible on both themes.
      const g = 0.08 + v * 0.92;
      colors[i * 3] = g;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = g;
    }
    return colors;
  }

  if (mode === 'height') {
    // Ramp on the data's vertical axis (z in scan space), using the wire bbox
    // converted into the centre-relative frame the positions live in, unless
    // the caller pinned a custom range.
    const zMin = heightRange ? heightRange.min : cloud.bboxMin[2] - cloud.center[2];
    const zMax = heightRange ? heightRange.max : cloud.bboxMax[2] - cloud.center[2];
    const span = zMax - zMin || 1;
    for (let i = 0; i < n; i++) {
      const t = ((cloud.positions[i * 3 + 2] ?? 0) - zMin) / span;
      const [r, g, b] = sampleRamp(t);
      colors[i * 3] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
    }
    return colors;
  }

  // Single-color fallback.
  for (let i = 0; i < n; i++) {
    colors[i * 3] = SINGLE_COLOR.r;
    colors[i * 3 + 1] = SINGLE_COLOR.g;
    colors[i * 3 + 2] = SINGLE_COLOR.b;
  }
  return colors;
}

function formatPoints(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface ToolToggleButtonProps {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  icon: typeof Layers;
  label: string;
  testId?: string;
}

/** Toggle-style button for the inspection-tools row - mirrors the "View"
 *  button styling already used for scan rows in PointCloudPage.tsx so the
 *  active/inactive states read consistently across the feature. */
function ToolToggleButton({ active, disabled, onClick, icon: Icon, label, testId }: ToolToggleButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      title={label}
      data-testid={testId}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        active
          ? 'border-oe-blue/40 bg-oe-blue/10 text-oe-blue'
          : 'border-border-light bg-surface-secondary text-content-secondary hover:bg-surface-tertiary hover:text-content-primary'
      }`}
    >
      <Icon size={14} />
      {label}
    </button>
  );
}

interface PointCloudViewerProps {
  scanId: string;
  /** Display label for the header, e.g. the scan source / format. */
  scanLabel?: string;
}

export function PointCloudViewer({ scanId, scanLabel }: PointCloudViewerProps) {
  const { t } = useTranslation();
  const resolvedTheme = useThemeStore((s) => s.resolved);

  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const pointsRef = useRef<THREE.Points | null>(null);
  /** Base point size derived from the cloud extent; the slider scales it. */
  const baseSizeRef = useRef(0.01);

  // ── Inspection-tools refs (cross-section, measure, clip box) ─────────────
  /** Identity of the last `cloud.positions` buffer we reset tool state for -
   *  lets the reset effect tell "genuinely new/refetched data" apart from
   *  the refit-clone `{...prev}` trick in handleRefit (same typed array). */
  const lastPositionsRef = useRef<Float32Array | null>(null);
  const boxHelperRef = useRef<THREE.Box3Helper | null>(null);
  const pendingPointRef = useRef<THREE.Vector3 | null>(null);
  const pendingMarkerRef = useRef<THREE.Mesh | null>(null);
  const measureLineRef = useRef<THREE.Line | null>(null);
  const measureMarkersRef = useRef<THREE.Mesh[]>([]);
  /** Current (possibly half-finished) measurement points in world space,
   *  read every animation frame to keep the floating label glued to the
   *  line's midpoint without triggering a React re-render per frame. */
  const measurePointsRef = useRef<THREE.Vector3[]>([]);
  const measureLabelRef = useRef<HTMLDivElement | null>(null);

  const [phase, setPhase] = useState<LoadPhase>('loading');
  const [errorKind, setErrorKind] = useState<ErrorKind>('generic');
  const [errorDetail, setErrorDetail] = useState('');
  const [progressBytes, setProgressBytes] = useState(0);
  const [cloud, setCloud] = useState<OepcCloud | null>(null);
  const [maxPoints, setMaxPoints] = useState<number>(1_500_000);
  const [colorMode, setColorMode] = useState<ColorMode>('single');
  const [sizeFactor, setSizeFactor] = useState(10);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [webglFailed, setWebglFailed] = useState(false);

  // ── Inspection-tools state ────────────────────────────────────────────
  const [sliceEnabled, setSliceEnabled] = useState(false);
  /** Both in metres ABOVE the cloud's lowest point (0 = bottom), not raw
   *  scan-frame coordinates - friendlier for "slice storey 2, 3m to 6m up". */
  const [sliceMin, setSliceMin] = useState(0);
  const [sliceMax, setSliceMax] = useState(0);
  const [clipEnabled, setClipEnabled] = useState(false);
  const [clipBox, setClipBox] = useState<BoxExtent | null>(null);
  const [measureEnabled, setMeasureEnabled] = useState(false);
  const [measureHasPending, setMeasureHasPending] = useState(false);
  const [measurement, setMeasurement] = useState<Measurement3D | null>(null);
  const [heightRangeOverride, setHeightRangeOverride] = useState<{ min: number; max: number } | null>(
    null,
  );
  const [legendPinned, setLegendPinned] = useState(false);

  // ── Scene lifecycle: one renderer per mount, disposed on unmount ─────────
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    // three.js (r163+) requires WebGL2 and throws when a context cannot be
    // created (e.g. headless Firefox / WebKit). Feature-detect first, then
    // guard the construction itself, so the page degrades to the notice below
    // instead of letting the throw reach the React error boundary.
    let renderer: THREE.WebGLRenderer;
    try {
      const probe = document.createElement('canvas').getContext('webgl2');
      if (probe == null) {
        setWebglFailed(true);
        return undefined;
      }
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    } catch {
      setWebglFailed(true);
      return undefined;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(container.clientWidth || 1, container.clientHeight || 1);
    renderer.domElement.style.display = 'block';
    // Cross-section + clip-box both work by assigning per-material
    // `clippingPlanes`, which the renderer ignores unless this is on.
    renderer.localClippingEnabled = true;
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(
      document.documentElement.classList.contains('dark') ? BG_DARK : BG_LIGHT,
    );

    const camera = new THREE.PerspectiveCamera(
      55,
      (container.clientWidth || 1) / (container.clientHeight || 1),
      0.01,
      10_000,
    );
    camera.position.set(8, 6, 8);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    rendererRef.current = renderer;
    sceneRef.current = scene;
    cameraRef.current = camera;
    controlsRef.current = controls;

    renderer.setAnimationLoop(() => {
      controls.update();
      renderer.render(scene, camera);

      // Keep the measure-tool label glued to the current measurement's
      // midpoint. Reads refs only (no React state) so this costs one
      // projection + a style write per frame, never a re-render.
      const label = measureLabelRef.current;
      if (label) {
        const [p0, p1] = measurePointsRef.current;
        const cont = containerRef.current;
        if (p0 && p1 && cont) {
          const mid = p0.clone().add(p1).multiplyScalar(0.5);
          mid.project(camera);
          if (mid.z < 1) {
            const x = (mid.x * 0.5 + 0.5) * cont.clientWidth;
            const y = (-mid.y * 0.5 + 0.5) * cont.clientHeight;
            label.style.transform = `translate(${x}px, ${y}px)`;
            label.style.visibility = 'visible';
          } else {
            label.style.visibility = 'hidden';
          }
        } else {
          label.style.visibility = 'hidden';
        }
      }
    });

    const observer = new ResizeObserver(() => {
      const w = container.clientWidth || 1;
      const h = container.clientHeight || 1;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      renderer.setAnimationLoop(null);
      controls.dispose();
      const points = pointsRef.current;
      if (points) {
        points.geometry.dispose();
        (points.material as THREE.Material).dispose();
        scene.remove(points);
        pointsRef.current = null;
      }
      // Inspection-tools scene objects: clip-box wireframe + any measurement
      // line/markers. Everything else the tools touch (clipping planes,
      // React state) needs no GPU disposal.
      if (boxHelperRef.current) {
        scene.remove(boxHelperRef.current);
        boxHelperRef.current.dispose();
        boxHelperRef.current = null;
      }
      if (measureLineRef.current) {
        scene.remove(measureLineRef.current);
        measureLineRef.current.geometry.dispose();
        (measureLineRef.current.material as THREE.Material).dispose();
        measureLineRef.current = null;
      }
      for (const marker of measureMarkersRef.current) {
        scene.remove(marker);
        marker.geometry.dispose();
        (marker.material as THREE.Material).dispose();
      }
      measureMarkersRef.current = [];
      if (pendingMarkerRef.current) {
        scene.remove(pendingMarkerRef.current);
        pendingMarkerRef.current.geometry.dispose();
        (pendingMarkerRef.current.material as THREE.Material).dispose();
        pendingMarkerRef.current = null;
      }
      pendingPointRef.current = null;
      measurePointsRef.current = [];
      // forceContextLoss() before dispose() so the browser reclaims the GL
      // context slot immediately; dispose() alone leaks the live context and
      // the ~8-16 context cap is hit after a few mounts (3D view unavailable).
      try {
        renderer.forceContextLoss();
      } catch {
        /* context already lost */
      }
      renderer.dispose();
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement);
      }
      rendererRef.current = null;
      sceneRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
    };
  }, []);

  // ── Theme: keep the scene background in sync with the app theme ──────────
  useEffect(() => {
    const scene = sceneRef.current;
    if (scene) scene.background = new THREE.Color(resolvedTheme === 'dark' ? BG_DARK : BG_LIGHT);
  }, [resolvedTheme, webglFailed]);

  // ── Fetch + parse the OEPC buffer, cancellable ────────────────────────────
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    setPhase('loading');
    setProgressBytes(0);

    fetchScanPoints(scanId, {
      maxPoints,
      signal: controller.signal,
      onProgress: (loaded) => {
        if (!cancelled) setProgressBytes(loaded);
      },
    })
      .then((buffer) => {
        if (cancelled) return;
        const parsed = parseOepc(buffer);
        setCloud(parsed);
        setColorMode((prev) => {
          // Keep a still-valid user choice; otherwise pick the richest channel.
          if (prev === 'rgb' && parsed.rgb) return prev;
          if (prev === 'intensity' && parsed.intensity) return prev;
          if (prev === 'height' || prev === 'single') return prev;
          return parsed.rgb ? 'rgb' : 'height';
        });
        setPhase('ready');
      })
      .catch((err: unknown) => {
        if (cancelled || (err instanceof DOMException && err.name === 'AbortError')) return;
        if (err instanceof ScanPointsError) {
          if (err.status === 409) setErrorKind('processing');
          else if (err.status === 404) setErrorKind('notfound');
          else if (err.status === 501) setErrorKind('reader');
          else if (err.status === 422) setErrorKind('decode');
          else setErrorKind('generic');
          setErrorDetail(err.message);
        } else if (err instanceof OepcParseError) {
          setErrorKind('decode');
          setErrorDetail(err.message);
        } else {
          setErrorKind('generic');
          setErrorDetail(err instanceof Error ? err.message : String(err));
        }
        setPhase('error');
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [scanId, maxPoints, reloadNonce]);

  // ── Rebuild the Points object when a new cloud lands ─────────────────────
  useEffect(() => {
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!scene || !camera || !controls || !cloud) return;

    const previous = pointsRef.current;
    if (previous) {
      previous.geometry.dispose();
      (previous.material as THREE.Material).dispose();
      scene.remove(previous);
      pointsRef.current = null;
    }
    if (cloud.pointCount === 0) return;

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(cloud.positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(buildColors(cloud, colorMode), 3));

    // Local-frame bbox (wire bbox is in the world frame; positions are
    // centre-relative), used for sizing, camera fit and the controls target.
    const min = new THREE.Vector3(
      cloud.bboxMin[0] - cloud.center[0],
      cloud.bboxMin[1] - cloud.center[1],
      cloud.bboxMin[2] - cloud.center[2],
    );
    const max = new THREE.Vector3(
      cloud.bboxMax[0] - cloud.center[0],
      cloud.bboxMax[1] - cloud.center[1],
      cloud.bboxMax[2] - cloud.center[2],
    );
    const diagonal = max.clone().sub(min).length() || 1;
    baseSizeRef.current = diagonal / 1000;

    const material = new THREE.PointsMaterial({
      size: baseSizeRef.current * (sizeFactor / 10),
      vertexColors: true,
      sizeAttenuation: true,
    });

    const points = new THREE.Points(geometry, material);
    // Scans are z-up; THREE is y-up. Rotate the object, not the data.
    points.rotation.x = -Math.PI / 2;
    scene.add(points);
    pointsRef.current = points;

    // Auto-fit: aim at the rotated bbox centre, back off along a 3/4 view.
    const centerLocal = min.clone().add(max).multiplyScalar(0.5);
    const target = centerLocal.clone().applyAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2);
    const distance = Math.max(diagonal * 0.9, 0.5);
    camera.position.set(
      target.x + distance * 0.7,
      target.y + distance * 0.55,
      target.z + distance * 0.7,
    );
    camera.near = Math.max(diagonal / 10_000, 0.001);
    camera.far = Math.max(diagonal * 20, 100);
    camera.updateProjectionMatrix();
    controls.target.copy(target);
    controls.update();
    // The data effect intentionally omits colorMode / sizeFactor: those are
    // applied in-place by the two effects below without a geometry rebuild.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cloud]);

  // ── In-place color recompute on mode change ───────────────────────────────
  useEffect(() => {
    const points = pointsRef.current;
    if (!points || !cloud || cloud.pointCount === 0) return;
    const attr = points.geometry.getAttribute('color') as THREE.BufferAttribute | undefined;
    if (!attr) return;
    (attr.array as Float32Array).set(buildColors(cloud, colorMode, heightRangeOverride));
    attr.needsUpdate = true;
  }, [cloud, colorMode, heightRangeOverride]);

  // ── In-place point-size update ────────────────────────────────────────────
  useEffect(() => {
    const points = pointsRef.current;
    if (!points) return;
    (points.material as THREE.PointsMaterial).size = baseSizeRef.current * (sizeFactor / 10);
  }, [sizeFactor, cloud]);

  const handleRefit = useCallback(() => {
    // Cheapest reliable re-fit: replay the data effect by cloning the cloud
    // reference (the typed arrays are shared, so this allocates nothing big).
    setCloud((prev) => (prev ? { ...prev } : prev));
  }, []);

  // ══════════════════════════════════════════════════════════════════════
  // Inspection tools: cross-section, measure, clip box, elevation legend,
  // snapshot. Everything below operates on the already-loaded THREE.Points
  // in-place (clipping planes / raycasts / a canvas capture) - no backend
  // calls, no geometry rebuilds.
  // ══════════════════════════════════════════════════════════════════════

  // Bounds derive from `cloud` alone, so this stays referentially stable
  // across renders that don't touch the cloud (e.g. dragging the size
  // slider), which in turn keeps `activePlaneEqs` below from recomputing
  // needlessly.
  const bounds = useMemo(() => {
    if (!cloud) return null;
    return deriveCloudBounds({ bboxMin: cloud.bboxMin, bboxMax: cloud.bboxMax, center: cloud.center });
  }, [cloud]);

  const heightSpan = bounds ? bounds.zMax - bounds.zMin : 0;
  const sliceStep = heightSpan > 0 ? Math.max(heightSpan / 500, 0.001) : 0.01;
  const legendRange = heightRangeOverride ?? (bounds ? { min: bounds.zMin, max: bounds.zMax } : null);

  // Every clip-plane equation currently in effect (slice + box, composed as
  // an intersection - a point must clear both to stay visible). Shared by
  // the GPU clipping-planes effect AND the measure tool's raycast filter, so
  // "what you can click" always matches "what you can see".
  const activePlaneEqs = useMemo<PlaneEq[]>(() => {
    if (!bounds) return [];
    const eqs: PlaneEq[] = [];
    if (sliceEnabled) {
      const lo = bounds.zMin + Math.min(sliceMin, sliceMax);
      const hi = bounds.zMin + Math.max(sliceMin, sliceMax);
      eqs.push(...heightSlicePlanes(lo, hi));
    }
    if (clipEnabled && clipBox) {
      eqs.push(...boxPlanes(clipBox));
    }
    return eqs;
  }, [bounds, sliceEnabled, sliceMin, sliceMax, clipEnabled, clipBox]);

  /** Drop the current measurement's scene objects (line, both markers, any
   *  half-finished pending marker) and reset the picking state. Pure ref
   *  bookkeeping - callers decide whether to also clear the numeric result. */
  const disposeMeasurementObjects = useCallback(() => {
    const scene = sceneRef.current;
    if (measureLineRef.current) {
      scene?.remove(measureLineRef.current);
      measureLineRef.current.geometry.dispose();
      (measureLineRef.current.material as THREE.Material).dispose();
      measureLineRef.current = null;
    }
    for (const marker of measureMarkersRef.current) {
      scene?.remove(marker);
      marker.geometry.dispose();
      (marker.material as THREE.Material).dispose();
    }
    measureMarkersRef.current = [];
    if (pendingMarkerRef.current) {
      scene?.remove(pendingMarkerRef.current);
      pendingMarkerRef.current.geometry.dispose();
      (pendingMarkerRef.current.material as THREE.Material).dispose();
      pendingMarkerRef.current = null;
    }
    pendingPointRef.current = null;
    measurePointsRef.current = [];
  }, []);

  /** Clear the measurement entirely (scene objects + the numeric readout) -
   *  wired to the panel's "Clear" button. */
  const clearMeasurement = useCallback(() => {
    disposeMeasurementObjects();
    setMeasurement(null);
    setMeasureHasPending(false);
  }, [disposeMeasurementObjects]);

  const addMeasureMarker = useCallback(
    (scene: THREE.Scene, p: THREE.Vector3): THREE.Mesh => {
      const radius = Math.max((bounds?.diagonal ?? 1) / 250, 0.004);
      const geometry = new THREE.SphereGeometry(radius, 12, 8);
      const material = new THREE.MeshBasicMaterial({
        color: MEASURE_COLOR,
        depthTest: false,
        transparent: true,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.copy(p);
      mesh.renderOrder = 998;
      scene.add(mesh);
      return mesh;
    },
    [bounds],
  );

  const buildMeasureLine = useCallback(
    (a: THREE.Vector3, b: THREE.Vector3): THREE.Line => {
      const diagonal = bounds?.diagonal ?? 1;
      const geometry = new THREE.BufferGeometry().setFromPoints([a, b]);
      const material = new THREE.LineDashedMaterial({
        color: MEASURE_COLOR,
        dashSize: Math.max(diagonal / 120, 0.01),
        gapSize: Math.max(diagonal / 240, 0.006),
        depthTest: false,
        transparent: true,
      });
      const line = new THREE.Line(geometry, material);
      line.computeLineDistances();
      line.renderOrder = 997;
      return line;
    },
    [bounds],
  );

  /** Raycast-pick against the loaded Points on a plain (non-drag) click and
   *  advance the two-click measurement state machine. Only ever invoked via
   *  `measureClickRef` (see the pointer-listener effect below), so it always
   *  runs with the LATEST closure over `activePlaneEqs` / `bounds`. */
  const handleMeasureClick = useCallback(
    (ev: PointerEvent) => {
      const container = containerRef.current;
      const camera = cameraRef.current;
      const points = pointsRef.current;
      const scene = sceneRef.current;
      if (!container || !camera || !points || !scene) return;

      const rect = container.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      const ndc = new THREE.Vector2(
        ((ev.clientX - rect.left) / rect.width) * 2 - 1,
        -((ev.clientY - rect.top) / rect.height) * 2 + 1,
      );

      const material = points.material as THREE.PointsMaterial;
      const raycaster = new THREE.Raycaster();
      // Sized off the current rendered point size so picking stays easy at
      // any point-size / density setting.
      raycaster.params.Points = { threshold: Math.max(material.size * 1.5, 1e-5) };
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObject(points);
      // THREE.Raycaster has no notion of GPU clipping planes, so a hit here
      // can land on a point the slice/clip box currently hides. Skip those -
      // otherwise you could "measure" a point that is not visibly there.
      const visible = hits.find(
        (h) => activePlaneEqs.length === 0 || isWithinPlanes(h.point, activePlaneEqs),
      );
      if (!visible) return;
      const hit = visible.point.clone();

      if (!pendingPointRef.current) {
        // Fresh pick: drop any earlier finished measurement and start over.
        disposeMeasurementObjects();
        setMeasurement(null);
        pendingPointRef.current = hit;
        pendingMarkerRef.current = addMeasureMarker(scene, hit);
        measurePointsRef.current = [hit];
        setMeasureHasPending(true);
        return;
      }

      const a = pendingPointRef.current;
      const b = hit;
      const markerA = pendingMarkerRef.current;
      pendingPointRef.current = null;
      pendingMarkerRef.current = null;
      setMeasureHasPending(false);

      const markerB = addMeasureMarker(scene, b);
      const line = buildMeasureLine(a, b);
      scene.add(line);
      measureLineRef.current = line;
      measureMarkersRef.current = markerA ? [markerA, markerB] : [markerB];
      measurePointsRef.current = [a, b];
      setMeasurement(computeMeasurement3D(a, b));
    },
    [activePlaneEqs, disposeMeasurementObjects, addMeasureMarker, buildMeasureLine],
  );

  /** DOM pointer listeners live outside React's render cycle, so they call
   *  through this ref rather than closing over a stale `handleMeasureClick`. */
  const measureClickRef = useRef(handleMeasureClick);
  useEffect(() => {
    measureClickRef.current = handleMeasureClick;
  });

  // ── Reset tool state when genuinely new/refetched data lands. Skips the
  //    handleRefit `{...prev}` clone (same `positions` buffer) so re-fitting
  //    the view never wipes an in-progress slice / clip / measurement. ─────
  useEffect(() => {
    if (!cloud || !bounds) return;
    if (lastPositionsRef.current === cloud.positions) return;
    lastPositionsRef.current = cloud.positions;

    setSliceEnabled(false);
    setSliceMin(0);
    setSliceMax(bounds.zMax - bounds.zMin);
    setClipEnabled(false);
    setClipBox(null);
    setHeightRangeOverride(null);
    setLegendPinned(false);
    disposeMeasurementObjects();
    setMeasurement(null);
    setMeasureHasPending(false);
  }, [cloud, bounds, disposeMeasurementObjects]);

  // ── Default the clip box to the full cloud bounds the first time it's
  //    enabled; later toggles keep whatever region the user set. ───────────
  useEffect(() => {
    if (clipEnabled && !clipBox && bounds) {
      setClipBox({ min: bounds.worldMin, max: bounds.worldMax });
    }
  }, [clipEnabled, clipBox, bounds]);

  // ── Apply the combined clip planes to the point material. Plane math is
  //    a handful of tiny objects, not a per-point loop - cheap even while a
  //    slider is being dragged. ─────────────────────────────────────────────
  useEffect(() => {
    const points = pointsRef.current;
    if (!points) return;
    const material = points.material as THREE.PointsMaterial;
    const planes = activePlaneEqs.map(
      (eq) => new THREE.Plane(new THREE.Vector3(eq.normal.x, eq.normal.y, eq.normal.z), eq.constant),
    );
    const previousCount = material.clippingPlanes?.length ?? 0;
    material.clippingPlanes = planes;
    // clippingPlanes count is baked into the compiled shader in some
    // three.js versions - force a recompile whenever it changes so a plane
    // being added/removed (not just moved) always takes effect.
    if (previousCount !== planes.length) material.needsUpdate = true;
  }, [cloud, activePlaneEqs]);

  // ── Clip-box wireframe: lazily built, then just re-pointed at the new
  //    Box3 extents (Box3Helper redraws itself from `.box` every frame). ───
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    if (!clipEnabled || !clipBox) {
      if (boxHelperRef.current) boxHelperRef.current.visible = false;
      return;
    }
    let helper = boxHelperRef.current;
    if (!helper) {
      helper = new THREE.Box3Helper(new THREE.Box3(), CLIP_BOX_COLOR);
      const material = helper.material as THREE.LineBasicMaterial;
      material.transparent = true;
      material.depthTest = false;
      material.opacity = 0.9;
      helper.renderOrder = 999;
      scene.add(helper);
      boxHelperRef.current = helper;
    }
    helper.box.min.set(clipBox.min.x, clipBox.min.y, clipBox.min.z);
    helper.box.max.set(clipBox.max.x, clipBox.max.y, clipBox.max.z);
    helper.visible = true;
  }, [clipEnabled, clipBox]);

  // ── Measure-tool pointer listeners: a plain click (down+up within a few
  //    px, no drag) picks a point; a real orbit-drag is ignored so measuring
  //    never fights OrbitControls, which stays enabled throughout. ─────────
  useEffect(() => {
    const renderer = rendererRef.current;
    if (!renderer || !measureEnabled) return undefined;
    const dom = renderer.domElement;
    let downX = 0;
    let downY = 0;
    let dragging = false;

    const onPointerDown = (ev: PointerEvent) => {
      if (ev.button !== 0) return;
      downX = ev.clientX;
      downY = ev.clientY;
      dragging = false;
    };
    const onPointerMove = (ev: PointerEvent) => {
      if ((ev.buttons & 1) === 0) return;
      if (Math.hypot(ev.clientX - downX, ev.clientY - downY) > 5) dragging = true;
    };
    const onPointerUp = (ev: PointerEvent) => {
      if (ev.button !== 0 || dragging) return;
      measureClickRef.current(ev);
    };

    dom.addEventListener('pointerdown', onPointerDown);
    dom.addEventListener('pointermove', onPointerMove);
    dom.addEventListener('pointerup', onPointerUp);
    return () => {
      dom.removeEventListener('pointerdown', onPointerDown);
      dom.removeEventListener('pointermove', onPointerMove);
      dom.removeEventListener('pointerup', onPointerUp);
      // Leaving measure mode drops only a half-finished pick, so re-entering
      // later starts clean; a completed measurement stays visible until the
      // user explicitly clears it or a new cloud loads.
      if (pendingMarkerRef.current) {
        sceneRef.current?.remove(pendingMarkerRef.current);
        pendingMarkerRef.current.geometry.dispose();
        (pendingMarkerRef.current.material as THREE.Material).dispose();
        pendingMarkerRef.current = null;
      }
      pendingPointRef.current = null;
      setMeasureHasPending(false);
    };
  }, [measureEnabled]);

  const handleTopView = useCallback(() => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls || !bounds) return;
    const { worldCenter, diagonal } = bounds;
    const distance = Math.max(diagonal * 0.9, 0.5);
    // A tiny XZ nudge (not a true 0,distance,0 vertical) keeps OrbitControls'
    // spherical coordinates well-defined so the user can orbit away from the
    // plan view afterwards without a gimbal-lock jump.
    const tilt = distance * 0.02;
    camera.position.set(worldCenter.x + tilt, worldCenter.y + distance, worldCenter.z);
    camera.near = Math.max(diagonal / 10_000, 0.001);
    camera.far = Math.max(diagonal * 20, 100);
    camera.updateProjectionMatrix();
    controls.target.set(worldCenter.x, worldCenter.y, worldCenter.z);
    controls.update();
  }, [bounds]);

  const handleClipReset = useCallback(() => {
    if (!bounds) return;
    setClipBox({ min: bounds.worldMin, max: bounds.worldMax });
  }, [bounds]);

  const handleClipScale = useCallback(
    (factor: number) => {
      setClipBox((prev) => {
        if (!prev || !bounds) return prev;
        const minHalfExtent = Math.max(bounds.diagonal * 0.01, 1e-4);
        return scaleClipBox(prev, factor, { min: bounds.worldMin, max: bounds.worldMax }, minHalfExtent);
      });
    },
    [bounds],
  );

  const handleSnapshot = useCallback(() => {
    const renderer = rendererRef.current;
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    if (!renderer || !scene || !camera) return;
    // Render synchronously right before capture instead of keeping
    // `preserveDrawingBuffer` on for the whole session (that flag has a real
    // perf cost on some GPUs); a render-then-read in the same tick is
    // guaranteed to see the fresh frame before the browser presents/clears it.
    renderer.render(scene, camera);
    const url = renderer.domElement.toDataURL('image/png');
    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const link = document.createElement('a');
    link.href = url;
    link.download = `pointcloud-${slugifyForFilename(scanLabel || scanId)}-${stamp}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, [scanLabel, scanId]);

  const handleToggleLegendPin = useCallback(() => {
    setLegendPinned((prev) => {
      const next = !prev;
      setHeightRangeOverride(next && bounds ? { min: bounds.zMin, max: bounds.zMax } : null);
      return next;
    });
  }, [bounds]);

  const colorOptions = useMemo(
    () => [
      {
        value: 'rgb' as const,
        label: t('pointcloud.color_rgb', { defaultValue: 'True color (RGB)' }),
        disabled: !cloud?.rgb,
      },
      {
        value: 'height' as const,
        label: t('pointcloud.color_height', { defaultValue: 'Height ramp' }),
        disabled: false,
      },
      {
        value: 'intensity' as const,
        label: t('pointcloud.color_intensity', { defaultValue: 'Intensity' }),
        disabled: !cloud?.intensity,
      },
      {
        value: 'single' as const,
        label: t('pointcloud.color_single', { defaultValue: 'Single color' }),
        disabled: false,
      },
    ],
    [cloud, t],
  );

  const errorTitle = useMemo(() => {
    switch (errorKind) {
      case 'processing':
        return t('pointcloud.viewer_processing_title', { defaultValue: 'Scan is still processing' });
      case 'notfound':
        return t('pointcloud.viewer_notfound_title', { defaultValue: 'Scan not available' });
      case 'reader':
        return t('pointcloud.viewer_reader_title', { defaultValue: 'Point-cloud reader not installed' });
      case 'decode':
        return t('pointcloud.viewer_decode_title', { defaultValue: 'Could not decode this scan' });
      default:
        return t('pointcloud.viewer_error_title', { defaultValue: 'Could not load points' });
    }
  }, [errorKind, t]);

  const errorDescription = useMemo(() => {
    switch (errorKind) {
      case 'processing':
        return t('pointcloud.viewer_processing_desc', {
          defaultValue:
            'The upload has not finished yet. The viewer opens as soon as the scan reaches the uploaded state.',
        });
      case 'notfound':
        return t('pointcloud.viewer_notfound_desc', {
          defaultValue: 'The scan was removed or you no longer have access to it.',
        });
      case 'reader':
        return t('pointcloud.viewer_reader_desc', {
          defaultValue:
            "This scan's format needs an optional server-side reader that is not installed. LAS, LAZ and COPC work out of the box; E57 needs the 'pointcloud' extra installed on the server.",
        });
      case 'decode':
        return t('pointcloud.viewer_decode_desc', {
          defaultValue: 'The file could not be decoded into points. Re-export the scan and upload again.',
        });
      default:
        return errorDetail;
    }
  }, [errorKind, errorDetail, t]);

  return (
    <div className="space-y-3">
      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
        <div>
          <label
            htmlFor="pointcloud-color-mode"
            className="mb-1 block text-2xs font-semibold uppercase tracking-wider text-content-tertiary"
          >
            {t('pointcloud.viewer_color_mode', { defaultValue: 'Color by' })}
          </label>
          <select
            id="pointcloud-color-mode"
            className="rounded-lg border border-border-light bg-surface-secondary px-2.5 py-1.5 text-sm text-content-primary focus:outline-none focus:ring-1 focus:ring-oe-blue"
            value={colorMode}
            onChange={(e) => setColorMode(e.target.value as ColorMode)}
            disabled={phase !== 'ready'}
            data-testid="pointcloud-color-mode"
          >
            {colorOptions.map((o) => (
              <option key={o.value} value={o.value} disabled={o.disabled}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label
            htmlFor="pointcloud-density"
            className="mb-1 block text-2xs font-semibold uppercase tracking-wider text-content-tertiary"
          >
            {t('pointcloud.viewer_density', { defaultValue: 'Density' })}
          </label>
          <select
            id="pointcloud-density"
            className="rounded-lg border border-border-light bg-surface-secondary px-2.5 py-1.5 text-sm text-content-primary focus:outline-none focus:ring-1 focus:ring-oe-blue"
            value={maxPoints}
            onChange={(e) => setMaxPoints(Number(e.target.value))}
            disabled={phase === 'loading'}
            data-testid="pointcloud-density"
          >
            {DENSITY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {t(o.labelKey, { defaultValue: o.fallback })}
              </option>
            ))}
          </select>
        </div>

        <div className="min-w-[150px]">
          <label
            htmlFor="pointcloud-point-size"
            className="mb-1 block text-2xs font-semibold uppercase tracking-wider text-content-tertiary"
          >
            {t('pointcloud.viewer_point_size', { defaultValue: 'Point size' })}
          </label>
          <input
            id="pointcloud-point-size"
            type="range"
            min={2}
            max={60}
            step={1}
            value={sizeFactor}
            onChange={(e) => setSizeFactor(Number(e.target.value))}
            disabled={phase !== 'ready'}
            className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-surface-tertiary accent-oe-blue"
            data-testid="pointcloud-point-size"
          />
        </div>

        <button
          type="button"
          onClick={handleRefit}
          disabled={phase !== 'ready' || !cloud || cloud.pointCount === 0}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border-light bg-surface-secondary px-3 py-1.5 text-sm text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary disabled:cursor-not-allowed disabled:opacity-40"
          title={t('pointcloud.viewer_refit', { defaultValue: 'Fit view' })}
        >
          <Maximize2 size={14} />
          {t('pointcloud.viewer_refit', { defaultValue: 'Fit view' })}
        </button>

        <button
          type="button"
          onClick={handleSnapshot}
          disabled={phase !== 'ready' || !cloud || cloud.pointCount === 0}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border-light bg-surface-secondary px-3 py-1.5 text-sm text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary disabled:cursor-not-allowed disabled:opacity-40"
          title={t('pointcloud.snapshot', { defaultValue: 'Snapshot' })}
          data-testid="pointcloud-snapshot"
        >
          <Camera size={14} />
          {t('pointcloud.snapshot', { defaultValue: 'Snapshot' })}
        </button>

        <div className="ml-auto self-center text-xs tabular-nums text-content-tertiary">
          {phase === 'ready' && cloud
            ? t('pointcloud.viewer_points_shown', {
                defaultValue: '{{points}} points shown',
                points: formatPoints(cloud.pointCount),
              })
            : null}
        </div>
      </div>

      {/* ── Inspection tools ───────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-2xs font-semibold uppercase tracking-wider text-content-tertiary">
          {t('pointcloud.tools_label', { defaultValue: 'Tools' })}
        </span>
        <ToolToggleButton
          active={sliceEnabled}
          disabled={phase !== 'ready' || !cloud || cloud.pointCount === 0}
          onClick={() => setSliceEnabled((v) => !v)}
          icon={Layers}
          label={t('pointcloud.tool_slice', { defaultValue: 'Cross-section' })}
          testId="pointcloud-tool-slice"
        />
        <ToolToggleButton
          active={measureEnabled}
          disabled={phase !== 'ready' || !cloud || cloud.pointCount === 0}
          onClick={() => setMeasureEnabled((v) => !v)}
          icon={Ruler}
          label={t('pointcloud.tool_measure', { defaultValue: 'Measure' })}
          testId="pointcloud-tool-measure"
        />
        <ToolToggleButton
          active={clipEnabled}
          disabled={phase !== 'ready' || !cloud || cloud.pointCount === 0}
          onClick={() => setClipEnabled((v) => !v)}
          icon={Crop}
          label={t('pointcloud.tool_clip', { defaultValue: 'Clip box' })}
          testId="pointcloud-tool-clip"
        />
      </div>

      {sliceEnabled && bounds && (
        <div
          className="flex flex-wrap items-end gap-x-4 gap-y-2 rounded-lg border border-border-light bg-surface-secondary/60 p-3"
          data-testid="pointcloud-slice-panel"
        >
          <div className="min-w-[160px] flex-1">
            <label
              htmlFor="pointcloud-slice-min"
              className="mb-1 block text-2xs font-semibold uppercase tracking-wider text-content-tertiary"
            >
              {t('pointcloud.slice_min_height', { defaultValue: 'Min height' })}
              <span className="ml-1 font-normal normal-case text-content-quaternary">
                {formatMetersLabel(sliceMin)}
              </span>
            </label>
            <input
              id="pointcloud-slice-min"
              type="range"
              min={0}
              max={heightSpan}
              step={sliceStep}
              value={sliceMin}
              onChange={(e) => setSliceMin(Math.min(Number(e.target.value), sliceMax))}
              className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-surface-tertiary accent-oe-blue"
              data-testid="pointcloud-slice-min"
            />
          </div>
          <div className="min-w-[160px] flex-1">
            <label
              htmlFor="pointcloud-slice-max"
              className="mb-1 block text-2xs font-semibold uppercase tracking-wider text-content-tertiary"
            >
              {t('pointcloud.slice_max_height', { defaultValue: 'Max height' })}
              <span className="ml-1 font-normal normal-case text-content-quaternary">
                {formatMetersLabel(sliceMax)}
              </span>
            </label>
            <input
              id="pointcloud-slice-max"
              type="range"
              min={0}
              max={heightSpan}
              step={sliceStep}
              value={sliceMax}
              onChange={(e) => setSliceMax(Math.max(Number(e.target.value), sliceMin))}
              className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-surface-tertiary accent-oe-blue"
              data-testid="pointcloud-slice-max"
            />
          </div>
          <button
            type="button"
            onClick={handleTopView}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border-light bg-surface-secondary px-3 py-1.5 text-sm text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary"
            title={t('pointcloud.slice_top_view', { defaultValue: 'Top / plan view' })}
            data-testid="pointcloud-top-view"
          >
            <ArrowDownToLine size={14} />
            {t('pointcloud.slice_top_view', { defaultValue: 'Top / plan view' })}
          </button>
          <p className="w-full text-2xs text-content-quaternary">
            {t('pointcloud.slice_hint', {
              defaultValue: 'Show only points between the two heights - useful to read one storey at a time.',
            })}
          </p>
        </div>
      )}

      {(measureEnabled || measurement) && (
        <div
          className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border-light bg-surface-secondary/60 p-3"
          data-testid="pointcloud-measure-panel"
        >
          {measurement ? (
            <>
              <span className="text-sm font-medium text-content-primary">
                {t('pointcloud.measure_distance', { defaultValue: 'Distance' })}:{' '}
                {formatLengthMm(measurement.distance)}
              </span>
              <span className="text-xs text-content-tertiary">
                {t('pointcloud.measure_readout', {
                  defaultValue: 'Horizontal {{h}} · Vertical {{v}}',
                  h: formatLengthMm(measurement.horizontal),
                  v: formatLengthMm(measurement.vertical),
                })}
              </span>
              <button
                type="button"
                onClick={clearMeasurement}
                className="ml-auto inline-flex items-center gap-1 text-xs text-content-tertiary underline hover:text-danger"
                data-testid="pointcloud-measure-clear"
              >
                <X size={12} />
                {t('pointcloud.measure_clear', { defaultValue: 'Clear' })}
              </button>
            </>
          ) : (
            <span className="text-xs text-content-tertiary">
              {measureHasPending
                ? t('pointcloud.measure_hint_pending', {
                    defaultValue: 'Click a second point to complete the measurement.',
                  })
                : t('pointcloud.measure_hint_start', {
                    defaultValue: 'Click two points on the cloud to measure the distance between them.',
                  })}
            </span>
          )}
        </div>
      )}

      {clipEnabled && (
        <div
          className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border-light bg-surface-secondary/60 p-3"
          data-testid="pointcloud-clip-panel"
        >
          <span className="text-xs text-content-tertiary">
            {t('pointcloud.clip_hint', {
              defaultValue: 'Adjust the box to isolate one room or zone; points outside are hidden.',
            })}
          </span>
          <div className="ml-auto flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => handleClipScale(1 / 1.15)}
              disabled={!clipBox}
              aria-label={t('pointcloud.clip_shrink', { defaultValue: 'Shrink' })}
              title={t('pointcloud.clip_shrink', { defaultValue: 'Shrink' })}
              className="inline-flex items-center justify-center rounded-lg border border-border-light bg-surface-secondary p-1.5 text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary disabled:cursor-not-allowed disabled:opacity-40"
              data-testid="pointcloud-clip-shrink"
            >
              <Minus size={14} />
            </button>
            <button
              type="button"
              onClick={() => handleClipScale(1.15)}
              disabled={!clipBox}
              aria-label={t('pointcloud.clip_grow', { defaultValue: 'Grow' })}
              title={t('pointcloud.clip_grow', { defaultValue: 'Grow' })}
              className="inline-flex items-center justify-center rounded-lg border border-border-light bg-surface-secondary p-1.5 text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary disabled:cursor-not-allowed disabled:opacity-40"
              data-testid="pointcloud-clip-grow"
            >
              <Plus size={14} />
            </button>
            <button
              type="button"
              onClick={handleClipReset}
              disabled={!bounds}
              aria-label={t('pointcloud.clip_reset', { defaultValue: 'Reset' })}
              title={t('pointcloud.clip_reset', { defaultValue: 'Reset' })}
              className="inline-flex items-center justify-center rounded-lg border border-border-light bg-surface-secondary p-1.5 text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary disabled:cursor-not-allowed disabled:opacity-40"
              data-testid="pointcloud-clip-reset"
            >
              <RotateCcw size={14} />
            </button>
          </div>
        </div>
      )}

      {/* ── Canvas + status overlays ─────────────────────────────────────── */}
      <div
        ref={containerRef}
        className="relative h-[480px] w-full overflow-hidden rounded-xl border border-border-light bg-surface-secondary"
        data-testid="pointcloud-viewer-canvas"
        aria-label={
          scanLabel
            ? t('pointcloud.viewer_canvas_aria_named', {
                defaultValue: '3D point cloud viewer for {{name}}',
                name: scanLabel,
              })
            : t('pointcloud.viewer_canvas_aria', { defaultValue: '3D point cloud viewer' })
        }
      >
        {webglFailed && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
            <AlertCircle size={22} className="text-danger" />
            <p className="text-sm font-medium text-content-primary">
              {t('pointcloud.viewer_webgl_title', { defaultValue: '3D rendering unavailable' })}
            </p>
            <p className="max-w-md text-xs text-content-tertiary">
              {t('pointcloud.viewer_webgl_desc', {
                defaultValue: 'Point Cloud viewer requires a WebGL2-capable browser. Update your browser or enable hardware acceleration.',
              })}
            </p>
          </div>
        )}

        {!webglFailed && phase === 'loading' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-surface-primary/40 backdrop-blur-[2px]">
            <Loader2 size={22} className="animate-spin text-oe-blue" />
            <p className="text-sm text-content-secondary">
              {t('pointcloud.viewer_loading', { defaultValue: 'Streaming points...' })}
            </p>
            {progressBytes > 0 && (
              <p className="text-2xs tabular-nums text-content-quaternary">
                {formatBytes(progressBytes)}
              </p>
            )}
          </div>
        )}

        {!webglFailed && phase === 'error' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
            {errorKind === 'processing' ? (
              <Clock size={22} className="text-oe-blue" />
            ) : (
              <AlertCircle size={22} className="text-danger" />
            )}
            <p className="text-sm font-medium text-content-primary">{errorTitle}</p>
            <p className="max-w-md text-xs text-content-tertiary">{errorDescription}</p>
            <button
              type="button"
              onClick={() => setReloadNonce((n) => n + 1)}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-border-light bg-surface-secondary px-3 py-1.5 text-sm text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary"
            >
              <RefreshCw size={13} />
              {t('pointcloud.viewer_retry', { defaultValue: 'Try again' })}
            </button>
          </div>
        )}

        {!webglFailed && phase === 'ready' && cloud && cloud.pointCount === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
            <AlertCircle size={22} className="text-content-quaternary" />
            <p className="text-sm text-content-secondary">
              {t('pointcloud.viewer_empty', { defaultValue: 'The scan decoded to zero points.' })}
            </p>
          </div>
        )}

        {/* ── Elevation legend: only meaningful in the height-ramp mode ──── */}
        {!webglFailed && phase === 'ready' && cloud && cloud.pointCount > 0 && colorMode === 'height' && legendRange && (
          <div
            className="absolute bottom-3 left-3 z-10 flex items-start gap-2 rounded-lg border border-border-light bg-surface-primary/90 p-2 shadow-md backdrop-blur-sm"
            data-testid="pointcloud-elevation-legend"
          >
            <div className="flex flex-col items-center gap-1">
              <span className="text-2xs tabular-nums text-content-secondary">
                {formatMetersLabel(legendRange.max)}
              </span>
              <div className="h-24 w-3 rounded-full" style={{ background: RAMP_GRADIENT_CSS }} />
              <span className="text-2xs tabular-nums text-content-secondary">
                {formatMetersLabel(legendRange.min)}
              </span>
            </div>
            <div className="flex flex-col items-start gap-1">
              <span className="text-2xs font-semibold uppercase tracking-wider text-content-tertiary">
                {t('pointcloud.legend_title', { defaultValue: 'Elevation' })}
              </span>
              <button
                type="button"
                onClick={handleToggleLegendPin}
                aria-pressed={legendPinned}
                className="inline-flex items-center gap-1 text-2xs text-content-tertiary hover:text-oe-blue"
                data-testid="pointcloud-legend-pin"
              >
                {legendPinned ? <Pin size={11} /> : <PinOff size={11} />}
                {t('pointcloud.legend_pin', { defaultValue: 'Pin range' })}
              </button>
              {legendPinned && (
                <div className="flex flex-col gap-1">
                  <input
                    type="number"
                    step={0.1}
                    value={Number(legendRange.max.toFixed(2))}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      if (Number.isFinite(v)) {
                        setHeightRangeOverride((prev) => ({ min: prev?.min ?? legendRange.min, max: v }));
                      }
                    }}
                    aria-label={t('pointcloud.legend_max_label', { defaultValue: 'Ramp maximum height in metres' })}
                    className="w-16 rounded border border-border-light bg-surface-secondary px-1 py-0.5 text-2xs tabular-nums text-content-primary"
                  />
                  <input
                    type="number"
                    step={0.1}
                    value={Number(legendRange.min.toFixed(2))}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      if (Number.isFinite(v)) {
                        setHeightRangeOverride((prev) => ({ min: v, max: prev?.max ?? legendRange.max }));
                      }
                    }}
                    aria-label={t('pointcloud.legend_min_label', { defaultValue: 'Ramp minimum height in metres' })}
                    className="w-16 rounded border border-border-light bg-surface-secondary px-1 py-0.5 text-2xs tabular-nums text-content-primary"
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Measure-tool floating label: position updated imperatively
             every frame (see the animation loop) so it stays glued to the
             line's midpoint without a per-frame React re-render. ────────── */}
        {measurement && (
          <div
            ref={measureLabelRef}
            className="pointer-events-none absolute left-0 top-0 z-10 -translate-x-1/2 -translate-y-[130%] whitespace-nowrap rounded-md bg-black/80 px-2 py-1 text-2xs font-medium text-white shadow-lg"
            data-testid="pointcloud-measure-label"
          >
            <div>{formatLengthMm(measurement.distance)}</div>
            <div className="text-[10px] font-normal text-white/75">
              {t('pointcloud.measure_readout', {
                defaultValue: 'Horizontal {{h}} · Vertical {{v}}',
                h: formatLengthMm(measurement.horizontal),
                v: formatLengthMm(measurement.vertical),
              })}
            </div>
          </div>
        )}
      </div>

      <p className="text-2xs text-content-quaternary">
        {t('pointcloud.viewer_hint', {
          defaultValue: 'Drag to orbit, right-drag to pan, scroll to zoom. Density re-requests a finer or coarser server-side decimation.',
        })}
      </p>
    </div>
  );
}

export default PointCloudViewer;
