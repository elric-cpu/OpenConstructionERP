import { describe, it, expect } from 'vitest';
import {
  deriveGeometry,
  deriveRelations,
} from '../canonicalElementDetails';

describe('canonicalElementDetails.deriveGeometry', () => {
  it('returns null when bbox is missing', () => {
    expect(deriveGeometry(undefined)).toBeNull();
    expect(deriveGeometry(null)).toBeNull();
  });

  it('returns null for a fully-degenerate (zero-extent) box', () => {
    expect(
      deriveGeometry({
        min_x: 1,
        min_y: 1,
        min_z: 1,
        max_x: 1,
        max_y: 1,
        max_z: 1,
      }),
    ).toBeNull();
  });

  it('returns null for a NaN box', () => {
    expect(
      deriveGeometry({
        min_x: 0,
        min_y: 0,
        min_z: 0,
        max_x: Number.NaN,
        max_y: 1,
        max_z: 1,
      }),
    ).toBeNull();
  });

  it('derives W/D/H/footprint/volume/diagonal for a 2×3×4 box', () => {
    const g = deriveGeometry({
      min_x: 1,
      min_y: 2,
      min_z: 3,
      max_x: 3, // width 2
      max_y: 5, // depth 3
      max_z: 7, // height 4
    });
    expect(g).not.toBeNull();
    expect(g!.width).toBe(2);
    expect(g!.depth).toBe(3);
    expect(g!.height).toBe(4);
    expect(g!.footprint).toBe(6);
    expect(g!.bboxVolume).toBe(24);
    // sqrt(4 + 9 + 16) = sqrt(29) ≈ 5.385
    expect(g!.diagonal).toBeCloseTo(Math.sqrt(29), 3);
    expect(g!.center).toEqual({ x: 2, y: 3.5, z: 5 });
  });

  it('accepts a flat (zero-height) slab footprint', () => {
    const g = deriveGeometry({
      min_x: 0,
      min_y: 0,
      min_z: 0,
      max_x: 5,
      max_y: 4,
      max_z: 0,
    });
    expect(g).not.toBeNull();
    expect(g!.height).toBe(0);
    expect(g!.footprint).toBe(20);
    expect(g!.bboxVolume).toBe(0);
  });
});

describe('canonicalElementDetails.deriveRelations', () => {
  it('uses the top-level storey shortcut for Level', () => {
    const rels = deriveRelations({ storey: 'Level 02', properties: {} });
    expect(rels).toContainEqual({ key: 'Level', value: 'Level 02' });
  });

  it('mines properties (case-insensitive) and prefers them over metadata', () => {
    const rels = deriveRelations({
      properties: { Zone: 'Wet area', System: 'HVAC-01' },
      metadata: { zone: 'IGNORED', phase: 'New Construction' },
    });
    expect(rels).toContainEqual({ key: 'Zone', value: 'Wet area' });
    expect(rels).toContainEqual({ key: 'System', value: 'HVAC-01' });
    expect(rels).toContainEqual({ key: 'Phase', value: 'New Construction' });
  });

  it('skips empty / placeholder values', () => {
    const rels = deriveRelations({
      storey: '',
      properties: { zone: 'None', system: 'null', assembly: '   ' },
    });
    expect(rels).toHaveLength(0);
  });

  it('falls back to metadata when properties lack the key', () => {
    const rels = deriveRelations({
      properties: {},
      metadata: { workset: 'Shared Levels and Grids' },
    });
    expect(rels).toContainEqual({
      key: 'Workset',
      value: 'Shared Levels and Grids',
    });
  });
});
