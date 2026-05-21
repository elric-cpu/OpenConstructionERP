/**
 * WalkMode — first-person walk-through navigation built on
 * three.js `PointerLockControls`.
 *
 * Controls (mirrors BIMcollab / Navisworks walk mode):
 *   - mouse drag (while locked) → look
 *   - W/A/S/D / arrow keys      → walk
 *   - Space                     → up (fly)
 *   - Shift                     → down (fly)
 *   - ESC                       → release pointer-lock (handled by browser)
 *
 * Speed: a velocity multiplier (metres / second) is exposed via
 * `setFlightSpeed`.  Default = 2 m/s; recommended UI range is
 * `bboxDiagonal / 50` … `bboxDiagonal / 5`, computed by the toolbar.
 *
 * Coexistence with OrbitControls: the caller is responsible for disabling
 * OrbitControls BEFORE calling `enable()`.  If `args.orbitControls` is
 * provided and `.enabled === true`, `enable()` throws — that flips a
 * bug we'd otherwise hit at runtime (camera fights between the two
 * controllers, tearing every frame).
 */

import * as THREE from 'three';
import { PointerLockControls } from 'three/examples/jsm/controls/PointerLockControls.js';

export interface WalkModeArgs {
  camera: THREE.Camera;
  renderer: THREE.WebGLRenderer;
  domElement: HTMLElement;
  /** Optional OrbitControls reference. If supplied, `enable()` checks that
   *  it has been disabled by the caller and throws if not. */
  orbitControls?: { enabled: boolean };
}

const DEFAULT_SPEED = 2; // m/s

export class WalkMode {
  private camera: THREE.Camera;
  // Renderer kept on the API for symmetry with SectionBox / MeasureTool;
  // WalkMode itself drives the PointerLockControls which holds its own
  // domElement reference. Underscored to silence noUnusedLocals.
  private _renderer: THREE.WebGLRenderer;
  private domElement: HTMLElement;
  private orbitControls?: { enabled: boolean };

  private controls: PointerLockControls | null = null;
  private _enabled = false;
  private _locked = false;
  private flightSpeed = DEFAULT_SPEED;

  /** Active WASD key state. Polled inside `tick()`. */
  private keys: Record<string, boolean> = {
    forward: false,
    backward: false,
    left: false,
    right: false,
    up: false,
    down: false,
  };

  private animId: number | null = null;
  private lastTickMs = 0;

  /** Bound listener references so removeEventListener can target them. */
  private onKeyDown = (e: KeyboardEvent): void => this.handleKey(e, true);
  private onKeyUp = (e: KeyboardEvent): void => this.handleKey(e, false);
  private onLock = (): void => {
    this._locked = true;
  };
  private onUnlock = (): void => {
    this._locked = false;
  };

  constructor(args: WalkModeArgs) {
    this.camera = args.camera;
    this._renderer = args.renderer;
    this.domElement = args.domElement;
    this.orbitControls = args.orbitControls;
    void this._renderer;
  }

  isEnabled(): boolean {
    return this._enabled;
  }

  isLocked(): boolean {
    return this._locked;
  }

  setFlightSpeed(speed: number): void {
    if (!Number.isFinite(speed) || speed <= 0) return;
    this.flightSpeed = speed;
  }

  getFlightSpeed(): number {
    return this.flightSpeed;
  }

  enable(): void {
    if (this._enabled) return;
    if (this.orbitControls && this.orbitControls.enabled) {
      throw new Error(
        'WalkMode.enable(): OrbitControls is still active — disable it first to avoid camera-fight rendering bugs.',
      );
    }
    this.controls = new PointerLockControls(this.camera, this.domElement);
    this._enabled = true;

    window.addEventListener('keydown', this.onKeyDown);
    window.addEventListener('keyup', this.onKeyUp);
    this.controls.addEventListener('lock', this.onLock);
    this.controls.addEventListener('unlock', this.onUnlock);

    // Request pointer lock immediately so the user can start looking
    // without a second click. In jsdom this is a no-op stub.
    try {
      this.controls.lock();
    } catch {
      // Some browsers throw if called without a user gesture; the
      // caller can call lock() again on the next user click.
    }

    this.lastTickMs = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.startLoop();
  }

  disable(): void {
    if (!this._enabled) return;
    this._enabled = false;
    this.stopLoop();

    window.removeEventListener('keydown', this.onKeyDown);
    window.removeEventListener('keyup', this.onKeyUp);

    if (this.controls) {
      try {
        this.controls.unlock();
      } catch {
        // Ignore — already unlocked or in test env without pointer lock.
      }
      this.controls.removeEventListener('lock', this.onLock);
      this.controls.removeEventListener('unlock', this.onUnlock);
      // Dispose if available (newer three.js exposes it).
      const c = this.controls as unknown as { dispose?: () => void };
      if (typeof c.dispose === 'function') c.dispose();
      this.controls = null;
    }
    this._locked = false;
    // Reset key state so a leftover key-up arriving after disable()
    // does not poison the next enable().
    for (const k of Object.keys(this.keys)) this.keys[k] = false;
  }

  dispose(): void {
    this.disable();
  }

  /** Integrate the current WASD/space/shift state into the camera position.
   *  Exposed for tests; production code drives this from the internal RAF
   *  loop. `deltaSeconds` is clamped to a sane upper bound so a tab that
   *  was backgrounded does not teleport the camera on resume. */
  tick(deltaSeconds: number): void {
    if (!this._enabled || !this.controls) return;
    // Clamp to 1 s so a backgrounded tab doesn't teleport on resume, but
    // still permits half-second test ticks without scaling them down.
    const dt = Math.min(Math.max(deltaSeconds, 0), 1);
    if (dt === 0) return;
    const distance = this.flightSpeed * dt;

    // Forward/back/left/right are camera-relative; up/down are world-Y.
    if (this.keys.forward) this.controls.moveForward(distance);
    if (this.keys.backward) this.controls.moveForward(-distance);
    if (this.keys.right) this.controls.moveRight(distance);
    if (this.keys.left) this.controls.moveRight(-distance);
    if (this.keys.up) this.camera.position.y += distance;
    if (this.keys.down) this.camera.position.y -= distance;
  }

  private startLoop(): void {
    if (this.animId !== null) return;
    const step = (now: number): void => {
      if (!this._enabled) return;
      const dt = (now - this.lastTickMs) / 1000;
      this.lastTickMs = now;
      this.tick(dt);
      this.animId =
        typeof requestAnimationFrame === 'function'
          ? requestAnimationFrame(step)
          : null;
    };
    this.animId =
      typeof requestAnimationFrame === 'function'
        ? requestAnimationFrame(step)
        : null;
  }

  private stopLoop(): void {
    if (this.animId !== null && typeof cancelAnimationFrame === 'function') {
      cancelAnimationFrame(this.animId);
    }
    this.animId = null;
  }

  private handleKey(e: KeyboardEvent, pressed: boolean): void {
    switch (e.code) {
      case 'KeyW':
      case 'ArrowUp':
        this.keys.forward = pressed;
        break;
      case 'KeyS':
      case 'ArrowDown':
        this.keys.backward = pressed;
        break;
      case 'KeyA':
      case 'ArrowLeft':
        this.keys.left = pressed;
        break;
      case 'KeyD':
      case 'ArrowRight':
        this.keys.right = pressed;
        break;
      case 'Space':
        this.keys.up = pressed;
        break;
      case 'ShiftLeft':
      case 'ShiftRight':
        this.keys.down = pressed;
        break;
      default:
        break;
    }
  }
}
