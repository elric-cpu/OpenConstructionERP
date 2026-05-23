/**
 * WalkMode tests — exercise the keyboard-driven first-person controller
 * without booting WebGL or a real PointerLock.
 *
 * Strategy: mock the entire `PointerLockControls` module. jsdom doesn't
 * implement `Element.requestPointerLock`, so we replace the class with
 * a stub that records `lock()` / `unlock()` calls and exposes
 * `moveForward` / `moveRight` against a passed-in camera.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';

const lockSpy = vi.fn();
const unlockSpy = vi.fn();
const moveForwardSpy = vi.fn();
const moveRightSpy = vi.fn();

vi.mock('three/examples/jsm/controls/PointerLockControls.js', () => {
  class FakePointerLockControls {
    private listeners: Record<string, ((e: unknown) => void)[]> = {};
    constructor(public camera: THREE.Camera, public domElement: HTMLElement) {}
    lock(): void {
      lockSpy();
      this.dispatch('lock');
    }
    unlock(): void {
      unlockSpy();
      this.dispatch('unlock');
    }
    moveForward(d: number): void {
      moveForwardSpy(d);
      // Mirror real PointerLockControls behaviour against the camera so
      // our integration test can assert position delta.
      const dir = new THREE.Vector3();
      this.camera.getWorldDirection(dir);
      dir.y = 0;
      dir.normalize();
      this.camera.position.addScaledVector(dir, d);
    }
    moveRight(d: number): void {
      moveRightSpy(d);
      const dir = new THREE.Vector3();
      this.camera.getWorldDirection(dir);
      const right = new THREE.Vector3().crossVectors(dir, new THREE.Vector3(0, 1, 0));
      right.normalize();
      this.camera.position.addScaledVector(right, d);
    }
    addEventListener(type: string, fn: (e: unknown) => void): void {
      (this.listeners[type] ??= []).push(fn);
    }
    removeEventListener(type: string, fn: (e: unknown) => void): void {
      const list = this.listeners[type];
      if (!list) return;
      const i = list.indexOf(fn);
      if (i >= 0) list.splice(i, 1);
    }
    private dispatch(type: string): void {
      const list = this.listeners[type];
      if (list) for (const fn of list) fn({ type });
    }
    dispose(): void {
      this.listeners = {};
    }
  }
  return { PointerLockControls: FakePointerLockControls };
});

import { WalkMode } from '../WalkMode';

function pressKey(code: string): void {
  window.dispatchEvent(new KeyboardEvent('keydown', { code }));
}
function releaseKey(code: string): void {
  window.dispatchEvent(new KeyboardEvent('keyup', { code }));
}

describe('WalkMode', () => {
  let camera: THREE.PerspectiveCamera;
  let renderer: THREE.WebGLRenderer;
  let dom: HTMLElement;
  let wm: WalkMode;

  beforeEach(() => {
    lockSpy.mockClear();
    unlockSpy.mockClear();
    moveForwardSpy.mockClear();
    moveRightSpy.mockClear();
    camera = new THREE.PerspectiveCamera();
    // Make sure camera looks down -Z so moveForward translates along -Z.
    camera.position.set(0, 0, 5);
    camera.lookAt(0, 0, 0);
    renderer = { domElement: document.createElement('canvas') } as unknown as THREE.WebGLRenderer;
    dom = document.createElement('div');
    wm = new WalkMode({ camera, renderer, domElement: dom });
  });

  afterEach(() => {
    wm.dispose();
  });

  it('enable() requests pointer lock and reports isEnabled=true', () => {
    wm.enable();
    expect(wm.isEnabled()).toBe(true);
    expect(lockSpy).toHaveBeenCalledTimes(1);
  });

  it('disable() releases pointer lock', () => {
    wm.enable();
    wm.disable();
    expect(wm.isEnabled()).toBe(false);
    expect(unlockSpy).toHaveBeenCalled();
  });

  it('WASD keydown integrates into camera position over time', () => {
    wm.enable();
    const startZ = camera.position.z;
    pressKey('KeyW');
    // 0.5 s at the default 2 m/s should translate ~1 m along -Z.
    wm.tick(0.5);
    expect(moveForwardSpy).toHaveBeenCalledWith(1);
    expect(camera.position.z).toBeLessThan(startZ);
    releaseKey('KeyW');
    // After key-up, further ticks should NOT call moveForward.
    moveForwardSpy.mockClear();
    wm.tick(0.5);
    expect(moveForwardSpy).not.toHaveBeenCalled();
  });

  it('setFlightSpeed scales the per-tick movement', () => {
    wm.enable();
    wm.setFlightSpeed(10); // 10 m/s
    pressKey('KeyD');
    wm.tick(0.5);
    expect(moveRightSpy).toHaveBeenCalledWith(5); // 10 × 0.5
    releaseKey('KeyD');
    expect(wm.getFlightSpeed()).toBe(10);
  });

  it('throws if OrbitControls is still enabled when enable() is called', () => {
    const orbit = { enabled: true };
    const wmGuarded = new WalkMode({ camera, renderer, domElement: dom, orbitControls: orbit });
    expect(() => wmGuarded.enable()).toThrow(/OrbitControls/);
    expect(wmGuarded.isEnabled()).toBe(false);
    wmGuarded.dispose();
  });

  it('does NOT throw if OrbitControls reference is disabled', () => {
    const orbit = { enabled: false };
    const wmGuarded = new WalkMode({ camera, renderer, domElement: dom, orbitControls: orbit });
    expect(() => wmGuarded.enable()).not.toThrow();
    expect(wmGuarded.isEnabled()).toBe(true);
    wmGuarded.dispose();
  });

  it('dispose() removes window keydown/keyup listeners', () => {
    wm.enable();
    wm.dispose();
    // After dispose, pressing keys + ticking does nothing.
    pressKey('KeyW');
    moveForwardSpy.mockClear();
    wm.tick(0.5);
    expect(moveForwardSpy).not.toHaveBeenCalled();
    releaseKey('KeyW');
  });

  it('Space/E/PageUp move the camera up, Q/PageDown/Ctrl move it down', () => {
    wm.enable();
    const startY = camera.position.y;
    pressKey('Space');
    wm.tick(0.5);
    expect(camera.position.y).toBeCloseTo(startY + 1, 6);
    releaseKey('Space');
    pressKey('KeyQ');
    wm.tick(0.5);
    expect(camera.position.y).toBeCloseTo(startY, 6);
    releaseKey('KeyQ');
    // E mirrors Space, PageDown mirrors Q.
    pressKey('KeyE');
    wm.tick(0.5);
    expect(camera.position.y).toBeCloseTo(startY + 1, 6);
    releaseKey('KeyE');
    pressKey('PageDown');
    wm.tick(0.5);
    expect(camera.position.y).toBeCloseTo(startY, 6);
    releaseKey('PageDown');
  });

  it('Shift acts as a sprint modifier (3× speed) instead of moving down', () => {
    wm.enable();
    wm.setFlightSpeed(2);
    pressKey('KeyW');
    pressKey('ShiftLeft');
    wm.tick(0.5);
    // 2 m/s * 3 (sprint) * 0.5 s = 3 m
    expect(moveForwardSpy).toHaveBeenLastCalledWith(3);
    releaseKey('ShiftLeft');
    moveForwardSpy.mockClear();
    wm.tick(0.5);
    // Without sprint: 2 * 0.5 = 1 m
    expect(moveForwardSpy).toHaveBeenLastCalledWith(1);
    releaseKey('KeyW');
  });
});
