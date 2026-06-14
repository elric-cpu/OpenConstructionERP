/**
 * Per-page (per-sheet) scale model for the PDF takeoff viewer.
 *
 * A multi-sheet drawing set has a DIFFERENT scale per sheet: the floor
 * plan on page 1 may be 1:50 while the site plan on page 3 is 1:500.
 * Storing a single document-wide scale made every measurement on a page
 * whose scale differed from the calibrated one wrong. This module keeps a
 * scale per 1-indexed page, with a single ``defaultScale`` applied to any
 * page that has not been calibrated yet.
 *
 * The shape is pure data so it round-trips through localStorage and is
 * unit-testable without mounting the viewer. It deliberately mirrors the
 * DWG side (``features/dwg-takeoff/lib/calibration-store``), which already
 * keeps an independent scale per paper-space layout.
 */

import type { ScaleConfig } from './scale-helpers';

/** Page-keyed scale map. Keys are 1-indexed page numbers as numbers. */
export interface PageScales {
  /** Scale used for any page without its own calibration. */
  defaultScale: ScaleConfig;
  /** Per-page overrides. A page present here was calibrated on that page. */
  byPage: Record<number, ScaleConfig>;
}

/** The factory default scale used before any calibration (1px ~ 0.01 m).
 *  Matches the viewer's historical initial ``{ pixelsPerUnit: 100 }``. */
export function defaultScaleConfig(): ScaleConfig {
  return { pixelsPerUnit: 100, unitLabel: 'm' };
}

/** Build an empty page-scale model with the factory default. */
export function emptyPageScales(): PageScales {
  return { defaultScale: defaultScaleConfig(), byPage: {} };
}

/**
 * Resolve the effective scale for a page: its own calibration when it has
 * one, otherwise the document default. This is the single accessor every
 * measurement-conversion path should use so a page never silently borrows
 * a neighbouring sheet's scale.
 */
export function scaleForPage(ps: PageScales, page: number): ScaleConfig {
  const own = ps.byPage[page];
  return own ?? ps.defaultScale;
}

/** True when the given page has its own calibration (vs. the default). */
export function pageIsCalibrated(ps: PageScales, page: number): boolean {
  return Object.prototype.hasOwnProperty.call(ps.byPage, page);
}

/**
 * Return a NEW model with ``page`` calibrated to ``scale``. The default is
 * left untouched so other uncalibrated pages keep falling back to it. We do
 * NOT mutate the input (React state must stay immutable).
 */
export function setPageScale(
  ps: PageScales,
  page: number,
  scale: ScaleConfig,
): PageScales {
  return {
    defaultScale: ps.defaultScale,
    byPage: { ...ps.byPage, [page]: scale },
  };
}

/* ── localStorage (de)serialisation with graceful migration ──────────── */

function isFiniteScale(v: unknown): v is ScaleConfig {
  if (!v || typeof v !== 'object') return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.pixelsPerUnit === 'number' &&
    Number.isFinite(o.pixelsPerUnit) &&
    typeof o.unitLabel === 'string'
  );
}

/**
 * Hydrate a {@link PageScales} from whatever a persisted document carried.
 *
 * Graceful migration is the whole point here: an existing document was
 * saved with a single ``scale`` (one global ``ScaleConfig``). We treat that
 * legacy scale as the document DEFAULT so every page keeps reading the same
 * number it always did until the user re-calibrates an individual sheet -
 * existing data never breaks. A document saved with the new ``pageScales``
 * shape is read back as-is.
 *
 * @param pageScales The new-format payload, if present.
 * @param legacyScale The old single-scale payload, if present.
 */
export function hydratePageScales(
  pageScales: unknown,
  legacyScale: unknown,
): PageScales {
  // New format wins when valid.
  if (pageScales && typeof pageScales === 'object') {
    const o = pageScales as Record<string, unknown>;
    const def = isFiniteScale(o.defaultScale)
      ? o.defaultScale
      : isFiniteScale(legacyScale)
        ? legacyScale
        : defaultScaleConfig();
    const byPage: Record<number, ScaleConfig> = {};
    if (o.byPage && typeof o.byPage === 'object') {
      for (const [k, v] of Object.entries(o.byPage as Record<string, unknown>)) {
        const page = Number(k);
        if (Number.isInteger(page) && page >= 1 && isFiniteScale(v)) {
          byPage[page] = v;
        }
      }
    }
    return { defaultScale: def, byPage };
  }

  // Legacy single-scale document: promote it to the default for all pages.
  if (isFiniteScale(legacyScale)) {
    return { defaultScale: legacyScale, byPage: {} };
  }

  return emptyPageScales();
}
