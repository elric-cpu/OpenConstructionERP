import { describe, it, expect } from 'vitest';
import {
  emptyPageScales,
  defaultScaleConfig,
  scaleForPage,
  setPageScale,
  pageIsCalibrated,
  hydratePageScales,
  type PageScales,
} from './page-scales';

describe('page-scales (per-sheet scale model)', () => {
  it('uncalibrated pages fall back to the document default', () => {
    const ps = emptyPageScales();
    expect(scaleForPage(ps, 1).pixelsPerUnit).toBe(100);
    expect(scaleForPage(ps, 7).pixelsPerUnit).toBe(100);
    expect(pageIsCalibrated(ps, 1)).toBe(false);
  });

  it('setPageScale calibrates ONE page without touching others', () => {
    const ps0 = emptyPageScales();
    const ps1 = setPageScale(ps0, 3, { pixelsPerUnit: 25, unitLabel: 'm' });
    // Page 3 now has its own scale...
    expect(scaleForPage(ps1, 3).pixelsPerUnit).toBe(25);
    expect(pageIsCalibrated(ps1, 3)).toBe(true);
    // ...but other pages keep the default.
    expect(scaleForPage(ps1, 1).pixelsPerUnit).toBe(100);
    expect(pageIsCalibrated(ps1, 1)).toBe(false);
    // Immutable: the original is untouched.
    expect(pageIsCalibrated(ps0, 3)).toBe(false);
  });

  it('different sheets keep independent scales', () => {
    let ps = emptyPageScales();
    ps = setPageScale(ps, 1, { pixelsPerUnit: 144, unitLabel: 'm' }); // 1:50
    ps = setPageScale(ps, 3, { pixelsPerUnit: 14.4, unitLabel: 'm' }); // 1:500
    expect(scaleForPage(ps, 1).pixelsPerUnit).toBe(144);
    expect(scaleForPage(ps, 3).pixelsPerUnit).toBe(14.4);
    // A measurement on page 1 vs page 3 converts with its own ratio: the
    // SAME pixel length is a different real length on each sheet.
    const pxLen = 720;
    expect(pxLen / scaleForPage(ps, 1).pixelsPerUnit).toBeCloseTo(5, 6); // 5 m
    expect(pxLen / scaleForPage(ps, 3).pixelsPerUnit).toBeCloseTo(50, 6); // 50 m
  });

  describe('hydratePageScales (graceful migration)', () => {
    it('promotes a legacy single scale into the document default', () => {
      // Old document: only a single global scale, no per-page map.
      const legacy = { pixelsPerUnit: 50, unitLabel: 'm' };
      const ps = hydratePageScales(undefined, legacy);
      expect(ps.defaultScale.pixelsPerUnit).toBe(50);
      expect(ps.byPage).toEqual({});
      // Every page reads the legacy scale until re-calibrated, so existing
      // measurements keep the value they always had.
      expect(scaleForPage(ps, 1).pixelsPerUnit).toBe(50);
      expect(scaleForPage(ps, 9).pixelsPerUnit).toBe(50);
    });

    it('reads a new per-page model back as-is', () => {
      const saved: PageScales = {
        defaultScale: { pixelsPerUnit: 100, unitLabel: 'm' },
        byPage: { 2: { pixelsPerUnit: 25, unitLabel: 'm' } },
      };
      const ps = hydratePageScales(saved, undefined);
      expect(ps.defaultScale.pixelsPerUnit).toBe(100);
      expect(ps.byPage[2]!.pixelsPerUnit).toBe(25);
    });

    it('new model wins but borrows the legacy scale when its default is bad', () => {
      const saved = { byPage: { 2: { pixelsPerUnit: 25, unitLabel: 'm' } } };
      const legacy = { pixelsPerUnit: 60, unitLabel: 'm' };
      const ps = hydratePageScales(saved, legacy);
      expect(ps.defaultScale.pixelsPerUnit).toBe(60);
      expect(ps.byPage[2]!.pixelsPerUnit).toBe(25);
    });

    it('rejects malformed per-page entries', () => {
      const saved = {
        defaultScale: { pixelsPerUnit: 100, unitLabel: 'm' },
        byPage: {
          1: { pixelsPerUnit: 50, unitLabel: 'm' },
          2: { pixelsPerUnit: 'oops', unitLabel: 'm' }, // bad
          '-3': { pixelsPerUnit: 10, unitLabel: 'm' }, // bad page
        },
      };
      const ps = hydratePageScales(saved, undefined);
      expect(ps.byPage[1]!.pixelsPerUnit).toBe(50);
      expect(ps.byPage[2]).toBeUndefined();
      expect(ps.byPage[-3]).toBeUndefined();
    });

    it('falls back to the factory default with no inputs', () => {
      const ps = hydratePageScales(undefined, undefined);
      expect(ps.defaultScale).toEqual(defaultScaleConfig());
      expect(ps.byPage).toEqual({});
    });
  });
});
