// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Pure, THREE-free helpers for the point-cloud viewer's inspection tools:
 * cross-section height slice, point-to-point measurement, and the
 * axis-aligned clip box. Kept side-effect-free and dependency-free (plain
 * numbers/objects in, plain numbers/objects out) so they are trivial to unit
 * test without booting a WebGL context; PointCloudViewer.tsx is the only
 * place that turns this data into real THREE.Plane / THREE.Vector3 objects
 * and owns their scene lifecycle.
 *
 * Frame note: PointCloudViewer rotates the loaded THREE.Points object by
 * -90 deg about X so a Z-up scan renders in three.js's Y-up world (see the
 * `points.rotation.x = -Math.PI / 2` assignment there). That rotation maps a
 * centre-relative local point (x, y, z) to the world-space point
 * (x, z, -y) — every function here that deals in "world space" (clip boxes,
 * the plan-view camera target, raycast hits) uses that mapping.
 */

/** A plain 3D point/vector - deliberately not a THREE.Vector3 so this module
 *  has zero runtime dependency on three.js. */
export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface Measurement3D {
  /** Straight-line distance between the two picked points, in metres. */
  distance: number;
  /** Distance projected onto the horizontal (XZ) plane, in metres. */
  horizontal: number;
  /** Absolute vertical (Y) difference, in metres. */
  vertical: number;
}

/** Compute the straight-line / horizontal / vertical spread between two
 *  world-space points (Y is up, matching the viewer's rotated frame). */
export function computeMeasurement3D(a: Vec3, b: Vec3): Measurement3D {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const dz = b.z - a.z;
  return {
    distance: Math.sqrt(dx * dx + dy * dy + dz * dz),
    horizontal: Math.sqrt(dx * dx + dz * dz),
    vertical: Math.abs(dy),
  };
}

/** Format a length for on-screen display at millimetre precision: whole
 *  millimetres under one metre, two-decimal metres at or above one metre. */
export function formatLengthMm(metres: number): string {
  if (!Number.isFinite(metres)) return '-';
  const abs = Math.abs(metres);
  if (abs >= 1) return `${metres.toFixed(2)} m`;
  return `${Math.round(metres * 1000)} mm`;
}

/** Format a length as whole metres with two decimals - used for the
 *  elevation legend / slice sliders, where mm precision is not meaningful
 *  (heights typically span whole buildings). */
export function formatMetersLabel(metres: number): string {
  if (!Number.isFinite(metres)) return '-';
  return `${metres.toFixed(2)} m`;
}

export interface CloudBoundsInput {
  bboxMin: readonly [number, number, number];
  bboxMax: readonly [number, number, number];
  center: readonly [number, number, number];
}

export interface DerivedBounds {
  /** Bounds in the centre-relative LOCAL frame the raw positions live in
   *  (pre-rotation - same frame the height-ramp colouring already uses). */
  localMin: Vec3;
  localMax: Vec3;
  /** Bounds in the rotated WORLD frame the camera / raycaster / clip boxes
   *  operate in (post `points.rotation.x = -PI/2`). */
  worldMin: Vec3;
  worldMax: Vec3;
  worldCenter: Vec3;
  /** Local-frame bounding diagonal, in metres. Never zero (floors at 1) so
   *  callers can divide by it safely. */
  diagonal: number;
  /** Local-frame Z span (= world-frame Y span): the scan's vertical extent. */
  zMin: number;
  zMax: number;
}

/** Derive every bounds/frame value the viewer's new tools need from the
 *  wire header's bbox + center. Pure number math - safe to call every
 *  render via useMemo. */
export function deriveCloudBounds(input: CloudBoundsInput): DerivedBounds {
  const localMin: Vec3 = {
    x: input.bboxMin[0] - input.center[0],
    y: input.bboxMin[1] - input.center[1],
    z: input.bboxMin[2] - input.center[2],
  };
  const localMax: Vec3 = {
    x: input.bboxMax[0] - input.center[0],
    y: input.bboxMax[1] - input.center[1],
    z: input.bboxMax[2] - input.center[2],
  };
  const dx = localMax.x - localMin.x;
  const dy = localMax.y - localMin.y;
  const dz = localMax.z - localMin.z;
  const diagonal = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;

  // local (x, y, z) -> world (x, z, -y); see the module docstring.
  // `|| 0` normalises a -0 result (e.g. when localMax.y is exactly 0) to
  // plain 0 - numerically identical, but keeps displayed/compared values
  // (legend labels, box-extent tests) from ever showing a stray sign.
  const worldMin: Vec3 = { x: localMin.x, y: localMin.z, z: -localMax.y || 0 };
  const worldMax: Vec3 = { x: localMax.x, y: localMax.z, z: -localMin.y || 0 };
  const worldCenter: Vec3 = {
    x: (worldMin.x + worldMax.x) / 2,
    y: (worldMin.y + worldMax.y) / 2,
    z: (worldMin.z + worldMax.z) / 2,
  };

  return {
    localMin,
    localMax,
    worldMin,
    worldMax,
    worldCenter,
    diagonal,
    zMin: localMin.z,
    zMax: localMax.z,
  };
}

/** A clipping-plane equation: points with `normal . p + constant >= 0` are
 *  kept, everything else is clipped away (matches THREE.Plane semantics so
 *  the viewer can build a real THREE.Plane from this with one call). */
export interface PlaneEq {
  normal: Vec3;
  constant: number;
}

export interface BoxExtent {
  min: Vec3;
  max: Vec3;
}

/** The two inward-facing planes for a world-Y height band [minY, maxY]. */
export function heightSlicePlanes(minY: number, maxY: number): [PlaneEq, PlaneEq] {
  return [
    { normal: { x: 0, y: 1, z: 0 }, constant: -minY },
    { normal: { x: 0, y: -1, z: 0 }, constant: maxY },
  ];
}

/** The six inward-facing planes of an axis-aligned world-space box. */
export function boxPlanes(box: BoxExtent): PlaneEq[] {
  return [
    { normal: { x: 1, y: 0, z: 0 }, constant: -box.min.x },
    { normal: { x: -1, y: 0, z: 0 }, constant: box.max.x },
    { normal: { x: 0, y: 1, z: 0 }, constant: -box.min.y },
    { normal: { x: 0, y: -1, z: 0 }, constant: box.max.y },
    { normal: { x: 0, y: 0, z: 1 }, constant: -box.min.z },
    { normal: { x: 0, y: 0, z: -1 }, constant: box.max.z },
  ];
}

/** Signed distance from a point to a plane equation (>= 0 means kept). */
export function planeDistance(p: Vec3, plane: PlaneEq): number {
  return p.x * plane.normal.x + p.y * plane.normal.y + p.z * plane.normal.z + plane.constant;
}

/** Whether a point survives every active clip plane - used to keep the
 *  measure tool's raycast picks consistent with what is actually visible
 *  (GPU clipping planes are invisible to THREE.Raycaster, which would
 *  otherwise happily "measure" a point hidden by an active slice/clip box). */
export function isWithinPlanes(p: Vec3, planes: readonly PlaneEq[]): boolean {
  return planes.every((plane) => planeDistance(p, plane) >= 0);
}

const AXES = ['x', 'y', 'z'] as const;

/** Scale a clip box by `factor` around its own centre (>1 grows, <1
 *  shrinks), clamped to stay within `fullBox` and never collapse below
 *  `minHalfExtent` on any axis. Pure - callers own the resulting state. */
export function scaleClipBox(
  box: BoxExtent,
  factor: number,
  fullBox: BoxExtent,
  minHalfExtent: number,
): BoxExtent {
  const min: Vec3 = { x: 0, y: 0, z: 0 };
  const max: Vec3 = { x: 0, y: 0, z: 0 };
  for (const axis of AXES) {
    const center = (box.min[axis] + box.max[axis]) / 2;
    const half = Math.max(((box.max[axis] - box.min[axis]) / 2) * factor, minHalfExtent);
    min[axis] = Math.max(fullBox.min[axis], center - half);
    max[axis] = Math.min(fullBox.max[axis], center + half);
  }
  return { min, max };
}

/** Turn a free-text scan label into a filesystem/URL-safe filename fragment
 *  for the PNG snapshot download; falls back to "scan" when nothing usable
 *  survives (e.g. a label that is entirely punctuation/CJK-only would still
 *  produce something reasonable via the fallback). */
export function slugifyForFilename(label: string): string {
  const slug = label
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || 'scan';
}
