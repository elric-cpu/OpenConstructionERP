// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Unit tests for the pure inspection-tool helpers behind the point-cloud
 * viewer's cross-section, measure and clip-box features.
 */
import { describe, expect, it } from 'vitest';
import {
  boxPlanes,
  computeMeasurement3D,
  deriveCloudBounds,
  formatLengthMm,
  formatMetersLabel,
  heightSlicePlanes,
  isWithinPlanes,
  planeDistance,
  scaleClipBox,
  slugifyForFilename,
} from './pointcloudTools';

describe('computeMeasurement3D', () => {
  it('computes straight-line, horizontal and vertical spread', () => {
    const m = computeMeasurement3D({ x: 0, y: 0, z: 0 }, { x: 3, y: 4, z: 0 });
    expect(m.distance).toBeCloseTo(5, 6);
    expect(m.horizontal).toBeCloseTo(3, 6);
    expect(m.vertical).toBeCloseTo(4, 6);
  });

  it('handles a purely vertical measurement', () => {
    const m = computeMeasurement3D({ x: 1, y: 1, z: 1 }, { x: 1, y: 3.5, z: 1 });
    expect(m.distance).toBeCloseTo(2.5, 6);
    expect(m.horizontal).toBeCloseTo(0, 6);
    expect(m.vertical).toBeCloseTo(2.5, 6);
  });
});

describe('formatLengthMm', () => {
  it('renders sub-metre lengths as whole millimetres', () => {
    expect(formatLengthMm(0.1234)).toBe('123 mm');
    expect(formatLengthMm(0.0005)).toBe('1 mm');
  });

  it('renders metre-and-above lengths with two decimals', () => {
    expect(formatLengthMm(1)).toBe('1.00 m');
    expect(formatLengthMm(12.3456)).toBe('12.35 m');
  });

  it('falls back gracefully for non-finite input', () => {
    expect(formatLengthMm(Number.NaN)).toBe('-');
  });
});

describe('formatMetersLabel', () => {
  it('always renders two-decimal metres', () => {
    expect(formatMetersLabel(0.5)).toBe('0.50 m');
    expect(formatMetersLabel(-3)).toBe('-3.00 m');
  });
});

describe('deriveCloudBounds', () => {
  it('centres the bbox on the wire center and derives the diagonal', () => {
    const bounds = deriveCloudBounds({
      bboxMin: [-1, -2, 0],
      bboxMax: [9, 8, 10],
      center: [4, 3, 5],
    });
    expect(bounds.localMin).toEqual({ x: -5, y: -5, z: -5 });
    expect(bounds.localMax).toEqual({ x: 5, y: 5, z: 5 });
    expect(bounds.diagonal).toBeCloseTo(Math.sqrt(300), 6);
    expect(bounds.zMin).toBe(-5);
    expect(bounds.zMax).toBe(5);
  });

  it('maps local (x, y, z) to world (x, z, -y) for the rotated viewer frame', () => {
    const bounds = deriveCloudBounds({
      bboxMin: [0, 0, 0],
      bboxMax: [2, 4, 6],
      center: [0, 0, 0],
    });
    // local x in [0,2] -> world x in [0,2]
    expect(bounds.worldMin.x).toBe(0);
    expect(bounds.worldMax.x).toBe(2);
    // local z in [0,6] -> world y in [0,6]
    expect(bounds.worldMin.y).toBe(0);
    expect(bounds.worldMax.y).toBe(6);
    // local y in [0,4] -> world z in [-4,0]
    expect(bounds.worldMin.z).toBe(-4);
    expect(bounds.worldMax.z).toBe(0);
  });

  it('never returns a zero diagonal for a degenerate (point) cloud', () => {
    const bounds = deriveCloudBounds({ bboxMin: [1, 1, 1], bboxMax: [1, 1, 1], center: [1, 1, 1] });
    expect(bounds.diagonal).toBe(1);
  });
});

describe('heightSlicePlanes + boxPlanes + isWithinPlanes', () => {
  it('keeps points inside a height band and rejects points outside it', () => {
    const planes = heightSlicePlanes(1, 3);
    expect(isWithinPlanes({ x: 0, y: 2, z: 0 }, planes)).toBe(true);
    expect(isWithinPlanes({ x: 0, y: 0.5, z: 0 }, planes)).toBe(false);
    expect(isWithinPlanes({ x: 0, y: 3.5, z: 0 }, planes)).toBe(false);
  });

  it('keeps points inside an axis-aligned box and rejects points outside it', () => {
    const planes = boxPlanes({ min: { x: -1, y: -1, z: -1 }, max: { x: 1, y: 1, z: 1 } });
    expect(planes).toHaveLength(6);
    expect(isWithinPlanes({ x: 0, y: 0, z: 0 }, planes)).toBe(true);
    expect(isWithinPlanes({ x: 2, y: 0, z: 0 }, planes)).toBe(false);
    expect(isWithinPlanes({ x: 0, y: 0, z: -2 }, planes)).toBe(false);
  });

  it('combines slice + box planes as an intersection (AND), not a union', () => {
    const planes = [
      ...heightSlicePlanes(0, 10),
      ...boxPlanes({ min: { x: -1, y: -1, z: -1 }, max: { x: 1, y: 1, z: 1 } }),
    ];
    // Y = 0.5 satisfies both the slice band [0,10] and the box's Y range
    // [-1,1], isolating X as the only reason this point should fail.
    expect(isWithinPlanes({ x: 5, y: 0.5, z: 0 }, planes)).toBe(false);
    // Inside both the slice band and the box on every axis.
    expect(isWithinPlanes({ x: 0, y: 0.5, z: 0 }, planes)).toBe(true);
  });

  it('planeDistance is signed and zero exactly on the plane', () => {
    const [minPlane] = heightSlicePlanes(2, 8);
    expect(planeDistance({ x: 0, y: 2, z: 0 }, minPlane)).toBeCloseTo(0, 6);
    expect(planeDistance({ x: 0, y: 5, z: 0 }, minPlane)).toBeCloseTo(3, 6);
  });
});

describe('scaleClipBox', () => {
  const fullBox = { min: { x: -10, y: -10, z: -10 }, max: { x: 10, y: 10, z: 10 } };

  it('grows a box around its centre without exceeding the full bounds', () => {
    const box = { min: { x: -1, y: -1, z: -1 }, max: { x: 1, y: 1, z: 1 } };
    const grown = scaleClipBox(box, 5, fullBox, 0.01);
    expect(grown.min.x).toBe(-5);
    expect(grown.max.x).toBe(5);
    // Growing further should clamp to the full bounds, not overshoot them.
    const grownAgain = scaleClipBox(grown, 10, fullBox, 0.01);
    expect(grownAgain.min.x).toBe(-10);
    expect(grownAgain.max.x).toBe(10);
  });

  it('shrinks a box around its centre without collapsing past the minimum half-extent', () => {
    const box = { min: { x: -4, y: -4, z: -4 }, max: { x: 4, y: 4, z: 4 } };
    const shrunk = scaleClipBox(box, 0.1, fullBox, 1);
    expect(shrunk.min.x).toBeCloseTo(-1, 6);
    expect(shrunk.max.x).toBeCloseTo(1, 6);
  });

  it('preserves an off-centre box position while scaling', () => {
    const box = { min: { x: 2, y: 2, z: 2 }, max: { x: 4, y: 4, z: 4 } };
    const grown = scaleClipBox(box, 2, fullBox, 0.01);
    // centre stays at 3, half-extent doubles from 1 to 2.
    expect(grown.min.x).toBe(1);
    expect(grown.max.x).toBe(5);
  });
});

describe('slugifyForFilename', () => {
  it('lower-cases and hyphenates a scan label', () => {
    expect(slugifyForFilename('Ground Floor Scan')).toBe('ground-floor-scan');
  });

  it('strips punctuation and collapses repeated separators', () => {
    expect(slugifyForFilename('  Roof -- North!! ')).toBe('roof-north');
  });

  it('falls back to "scan" when nothing usable survives', () => {
    expect(slugifyForFilename('***')).toBe('scan');
    expect(slugifyForFilename('')).toBe('scan');
  });
});
