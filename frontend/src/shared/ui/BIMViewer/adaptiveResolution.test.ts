// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, expect, it } from 'vitest';

import { AdaptiveResolution, type AdaptiveResolutionOptions } from './adaptiveResolution';

// emaAlpha: 1 makes the smoothed frame time equal the latest sample, so the
// state transitions are deterministic and easy to reason about in tests.
function mk(overrides: AdaptiveResolutionOptions = {}) {
  return new AdaptiveResolution({
    minScale: 0.5,
    maxScale: 1,
    step: 0.25,
    warmupFrames: 2,
    cooldownFrames: 3,
    emaAlpha: 1,
    ...overrides,
  });
}

function feed(ar: AdaptiveResolution, frameMs: number, n: number): number {
  let s = ar.scale;
  for (let i = 0; i < n; i += 1) s = ar.sample(frameMs);
  return s;
}

const SLOW = 50; // 20 fps -> above the 25 ms target -> shrink
const FAST = 8; // 125 fps -> below the recover threshold -> grow

describe('AdaptiveResolution', () => {
  it('starts at the ceiling scale', () => {
    expect(mk().scale).toBe(1);
    expect(mk({ maxScale: 2 }).scale).toBe(2);
  });

  it('holds the scale during the warm-up window even when frames are slow', () => {
    const ar = mk();
    feed(ar, SLOW, 2); // exactly warmupFrames
    expect(ar.scale).toBe(1);
  });

  it('shrinks the scale under sustained slow frames, clamped to minScale', () => {
    const ar = mk();
    expect(feed(ar, SLOW, 40)).toBe(0.5);
    // Never drops below the floor no matter how long it stays slow.
    expect(feed(ar, SLOW, 40)).toBe(0.5);
  });

  it('recovers the scale when frames get fast again, clamped to maxScale', () => {
    const ar = mk();
    feed(ar, SLOW, 40); // driven down to 0.5
    expect(ar.scale).toBe(0.5);
    expect(feed(ar, FAST, 40)).toBe(1);
  });

  it('changes the scale at most once per cooldown window', () => {
    const ar = mk();
    ar.sample(SLOW); // warm-up 1
    ar.sample(SLOW); // warm-up 2
    ar.sample(SLOW); // cooldown 1
    ar.sample(SLOW); // cooldown 2
    expect(ar.scale).toBe(1); // no change yet - still inside cooldown
    ar.sample(SLOW); // cooldown 3 -> one step down
    expect(ar.scale).toBe(0.75);
  });

  it('ignores non-finite and non-positive frame times', () => {
    const ar = mk();
    const before = ar.scale;
    ar.sample(Number.NaN);
    ar.sample(0);
    ar.sample(-5);
    ar.sample(Number.POSITIVE_INFINITY);
    expect(ar.scale).toBe(before);
    // Those bad samples did not consume the warm-up budget either.
    feed(ar, SLOW, 2);
    expect(ar.scale).toBe(1);
  });

  it('reset() restores the ceiling scale', () => {
    const ar = mk();
    feed(ar, SLOW, 40);
    expect(ar.scale).toBe(0.5);
    ar.reset();
    expect(ar.scale).toBe(1);
    expect(ar.smoothedFrameMs).toBe(0);
  });

  it('does not upshift a device that only ever meets the target loosely', () => {
    // Frames right at ~30 fps (33 ms): above recover (17 ms) so no growth,
    // below is false too since 33 > 25 target -> it should shrink, not grow.
    const ar = mk();
    const s = feed(ar, 33, 20);
    expect(s).toBeLessThan(1);
  });
});
