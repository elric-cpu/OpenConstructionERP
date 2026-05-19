/**
 * ClipManager — interactive section box + single clipping plane (Navisworks /
 * Aconex grade) built on Three.js `renderer.localClippingEnabled` +
 * per-material `clippingPlanes`.
 *
 * Two independent, mutually-exclusive cut modes:
 *
 *   - **Section box** — six axis-aligned planes that carve a rectangular
 *     volume out of the model.  A wireframe `Box3` helper shows the live
 *     extent; the user shrinks/grows each face with the control sliders.
 *   - **Single plane** — one arbitrary half-space cut.  The user picks the
 *     axis (X / Y / Z) and slides the offset; the cut direction can be
 *     flipped to keep either side.
 *
 * Why a manager (not inline in BIMViewer): the cut planes have to be applied
 * to *every* material in the scene — placeholder boxes, COLLADA meshes, and
 * the BatchedMesh perf path — and re-applied whenever geometry streams in
 * after the user already enabled clipping.  Centralising that here keeps the
 * BIMViewer wrapper thin and mirrors how SceneManager / ElementManager own
 * their slice of Three.js state.
 *
 * Clean cut: the planes slice geometry exactly at the plane (no capping
 * surface).  Capping a soup of open/non-manifold IFC/RVT meshes reliably is
 * out of scope and would need a stencil pre-pass per frame — explicitly a
 * non-goal per the brief ("capping optional but at least clean cut").
 */

import * as THREE from 'three';
import type { SceneManager } from './SceneManager';

export type ClipMode = 'none' | 'box' | 'plane';
export type ClipAxis = 'x' | 'y' | 'z';

/** Normalised box extent in [0, 1] per face (1 = full model on that face). */
export interface ClipBoxExtent {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
}

export interface ClipPlaneState {
  axis: ClipAxis;
  /** Normalised offset in [0, 1] along the axis (0 = min, 1 = max). */
  offset: number;
  /** When true the kept half-space is flipped. */
  flipped: boolean;
}

export interface ClipManagerCallbacks {
  /** Fired whenever the active mode changes so the React layer can mirror it. */
  onModeChange?: (mode: ClipMode) => void;
}

const FULL_BOX: ClipBoxExtent = {
  minX: 0,
  maxX: 1,
  minY: 0,
  maxY: 1,
  minZ: 0,
  maxZ: 1,
};

/** Clamp helper — keeps the two faces of an axis from crossing over. */
function clamp01(v: number): number {
  if (v < 0) return 0;
  if (v > 1) return 1;
  return v;
}

export class ClipManager {
  private sceneManager: SceneManager;
  private callbacks: ClipManagerCallbacks;

  private _mode: ClipMode = 'none';
  private _boxExtent: ClipBoxExtent = { ...FULL_BOX };
  private _plane: ClipPlaneState = { axis: 'y', offset: 0.5, flipped: false };

  /** World-space bounding box of the loaded model. Recomputed lazily. */
  private modelBox = new THREE.Box3();
  private modelBoxValid = false;

  /** The six box planes (reused across updates — never reallocated). */
  private boxPlanes: THREE.Plane[] = [
    new THREE.Plane(new THREE.Vector3(1, 0, 0), 0),
    new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0),
    new THREE.Plane(new THREE.Vector3(0, 1, 0), 0),
    new THREE.Plane(new THREE.Vector3(0, -1, 0), 0),
    new THREE.Plane(new THREE.Vector3(0, 0, 1), 0),
    new THREE.Plane(new THREE.Vector3(0, 0, -1), 0),
  ];
  private singlePlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);

  /** Live wireframe box that visualises the section volume. */
  private boxHelper: THREE.LineSegments | null = null;

  constructor(sceneManager: SceneManager, callbacks: ClipManagerCallbacks = {}) {
    this.sceneManager = sceneManager;
    this.callbacks = callbacks;
    // Local clipping is opt-in per renderer; turning it on once is harmless
    // when no planes are assigned (the default state).
    this.sceneManager.renderer.localClippingEnabled = true;
  }

  get mode(): ClipMode {
    return this._mode;
  }

  getBoxExtent(): ClipBoxExtent {
    return { ...this._boxExtent };
  }

  getPlaneState(): ClipPlaneState {
    return { ...this._plane };
  }

  /** Recompute the model bounding box from current scene content. Skips
   *  helpers / lights / grid the same way SceneManager.zoomToFit does. */
  private ensureModelBox(): void {
    if (this.modelBoxValid) return;
    this.sceneManager.scene.updateMatrixWorld(true);
    const box = new THREE.Box3();
    const tmp = new THREE.Box3();
    this.sceneManager.scene.traverse((obj) => {
      if (
        obj instanceof THREE.GridHelper ||
        obj instanceof THREE.AxesHelper ||
        obj instanceof THREE.Light ||
        obj instanceof THREE.Camera ||
        obj === this.boxHelper
      ) {
        return;
      }
      if (obj instanceof THREE.Mesh && obj.geometry) {
        if (!obj.geometry.boundingBox) obj.geometry.computeBoundingBox();
        tmp.setFromObject(obj);
        if (!tmp.isEmpty() && Number.isFinite(tmp.min.x)) box.union(tmp);
      }
    });
    if (!box.isEmpty()) {
      this.modelBox.copy(box);
      this.modelBoxValid = true;
    }
  }

  /** Invalidate the cached model box — call after geometry (re)loads so the
   *  next clip update fits the new model rather than the old footprint. */
  invalidateModelBox(): void {
    this.modelBoxValid = false;
    if (this._mode !== 'none') {
      // Geometry that streamed in after clipping was enabled has fresh
      // materials with no clippingPlanes set — re-apply so the new meshes
      // are also cut.
      this.apply();
    }
  }

  /** Switch cut mode. Passing the current mode again is a no-op. */
  setMode(mode: ClipMode): void {
    if (this._mode === mode) return;
    this._mode = mode;
    this.apply();
    this.callbacks.onModeChange?.(mode);
  }

  /** Reset extents/plane to defaults AND disable clipping entirely. */
  reset(): void {
    this._boxExtent = { ...FULL_BOX };
    this._plane = { axis: 'y', offset: 0.5, flipped: false };
    this.setMode('none');
  }

  /** Update one or more box faces (normalised 0..1). Opposing faces are
   *  clamped so they can never cross (min always ≤ max with a 1 % gap). */
  setBoxExtent(patch: Partial<ClipBoxExtent>): void {
    const gap = 0.01;
    const next: ClipBoxExtent = { ...this._boxExtent, ...patch };
    next.minX = clamp01(next.minX);
    next.maxX = clamp01(next.maxX);
    next.minY = clamp01(next.minY);
    next.maxY = clamp01(next.maxY);
    next.minZ = clamp01(next.minZ);
    next.maxZ = clamp01(next.maxZ);
    if (next.minX > next.maxX - gap) next.minX = next.maxX - gap;
    if (next.minY > next.maxY - gap) next.minY = next.maxY - gap;
    if (next.minZ > next.maxZ - gap) next.minZ = next.maxZ - gap;
    next.minX = clamp01(next.minX);
    next.minY = clamp01(next.minY);
    next.minZ = clamp01(next.minZ);
    this._boxExtent = next;
    if (this._mode === 'box') this.apply();
  }

  /** Update the single-plane state (axis / offset / flipped). */
  setPlaneState(patch: Partial<ClipPlaneState>): void {
    this._plane = {
      ...this._plane,
      ...patch,
      offset:
        patch.offset !== undefined ? clamp01(patch.offset) : this._plane.offset,
    };
    if (this._mode === 'plane') this.apply();
  }

  /** Recompute plane constants from the current model box + state and assign
   *  the active plane set to every material in the scene. */
  private apply(): void {
    this.ensureModelBox();

    if (this._mode === 'none' || !this.modelBoxValid) {
      this.assignPlanes(null);
      this.removeBoxHelper();
      this.sceneManager.requestRender();
      return;
    }

    const min = this.modelBox.min;
    const max = this.modelBox.max;
    const sx = max.x - min.x;
    const sy = max.y - min.y;
    const sz = max.z - min.z;

    if (this._mode === 'box') {
      const e = this._boxExtent;
      const x0 = min.x + sx * e.minX;
      const x1 = min.x + sx * e.maxX;
      const y0 = min.y + sy * e.minY;
      const y1 = min.y + sy * e.maxY;
      const z0 = min.z + sz * e.minZ;
      const z1 = min.z + sz * e.maxZ;

      // Each plane keeps the half-space its normal points INTO.
      // +X face: normal (1,0,0), keep x ≥ x0  → constant = -x0
      this.boxPlanes[0]!.set(new THREE.Vector3(1, 0, 0), -x0);
      this.boxPlanes[1]!.set(new THREE.Vector3(-1, 0, 0), x1);
      this.boxPlanes[2]!.set(new THREE.Vector3(0, 1, 0), -y0);
      this.boxPlanes[3]!.set(new THREE.Vector3(0, -1, 0), y1);
      this.boxPlanes[4]!.set(new THREE.Vector3(0, 0, 1), -z0);
      this.boxPlanes[5]!.set(new THREE.Vector3(0, 0, -1), z1);

      this.assignPlanes(this.boxPlanes);
      this.updateBoxHelper(
        new THREE.Box3(
          new THREE.Vector3(x0, y0, z0),
          new THREE.Vector3(x1, y1, z1),
        ),
      );
    } else {
      // Single plane.
      const axis = this._plane.axis;
      const normal = new THREE.Vector3(
        axis === 'x' ? 1 : 0,
        axis === 'y' ? 1 : 0,
        axis === 'z' ? 1 : 0,
      );
      const lo = axis === 'x' ? min.x : axis === 'y' ? min.y : min.z;
      const span = axis === 'x' ? sx : axis === 'y' ? sy : sz;
      const cut = lo + span * this._plane.offset;
      if (this._plane.flipped) normal.negate();
      // Keep the half-space the normal points into → constant = -n·p where
      // p is any point on the plane (here the axis-aligned cut coordinate).
      const constant = this._plane.flipped ? cut : -cut;
      this.singlePlane.set(normal, constant);
      this.assignPlanes([this.singlePlane]);
      this.removeBoxHelper();
    }

    this.sceneManager.requestRender();
  }

  /** Walk every mesh and set (or clear) its material clippingPlanes. */
  private assignPlanes(planes: THREE.Plane[] | null): void {
    this.sceneManager.scene.traverse((obj) => {
      if (obj === this.boxHelper) return;
      if (!(obj instanceof THREE.Mesh) && !(obj instanceof THREE.BatchedMesh)) {
        return;
      }
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
      for (const mat of mats) {
        if (!mat) continue;
        mat.clippingPlanes = planes;
        mat.clipShadows = false;
        mat.needsUpdate = true;
      }
    });
  }

  private ensureBoxHelper(): THREE.LineSegments {
    if (this.boxHelper) return this.boxHelper;
    // Unit cube edges; scaled/positioned per-update to match the section box.
    const geom = new THREE.BoxGeometry(1, 1, 1);
    const edges = new THREE.EdgesGeometry(geom);
    geom.dispose();
    const mat = new THREE.LineBasicMaterial({
      color: 0x2979ff,
      transparent: true,
      opacity: 0.9,
      depthTest: false,
    });
    const seg = new THREE.LineSegments(edges, mat);
    seg.renderOrder = 1000;
    // The helper itself must never be clipped by the planes it visualises.
    mat.clippingPlanes = null;
    this.sceneManager.scene.add(seg);
    this.boxHelper = seg;
    return seg;
  }

  private updateBoxHelper(box: THREE.Box3): void {
    const helper = this.ensureBoxHelper();
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    helper.scale.set(
      Math.max(size.x, 1e-4),
      Math.max(size.y, 1e-4),
      Math.max(size.z, 1e-4),
    );
    helper.position.copy(center);
    helper.visible = true;
  }

  private removeBoxHelper(): void {
    if (!this.boxHelper) return;
    this.boxHelper.visible = false;
  }

  /** Dispose all GPU resources and detach planes from every material. */
  dispose(): void {
    this.assignPlanes(null);
    if (this.boxHelper) {
      this.sceneManager.scene.remove(this.boxHelper);
      this.boxHelper.geometry.dispose();
      (this.boxHelper.material as THREE.Material).dispose();
      this.boxHelper = null;
    }
  }
}
