import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import {
  useMeasurementPersistence,
  getDocumentIndex,
  removeFromStorage,
} from './useMeasurementPersistence';
import { emptyPageScales, type PageScales } from './data/page-scales';

// Keep these unit tests hermetic: the hook now calls the server (gated on a
// project + document UUID), so stub the API to return no rows. Each test then
// exercises the localStorage path deterministically.
vi.mock('@/features/takeoff/api', () => ({
  takeoffApi: {
    list: vi.fn().mockResolvedValue([]),
    bulkCreate: vi.fn().mockResolvedValue([]),
    update: vi.fn().mockResolvedValue({}),
  },
}));

// Mock measurements
const makeMeasurement = (id: string, page = 1) => ({
  id,
  type: 'distance' as const,
  points: [{ x: 0, y: 0 }, { x: 100, y: 0 }],
  value: 2.5,
  unit: 'm',
  label: 'D1',
  annotation: `Distance ${id}`,
  page,
  group: 'General',
});

const defaultScale = { pixelsPerUnit: 100, unitLabel: 'm' };
const basePageScales: PageScales = emptyPageScales();

// Stable identity (issue #238): measurements are keyed by project + a stable
// document UUID, never the filename. The composite localStorage key is
// ``oe_takeoff_<projectId>__<documentId>``.
const PROJECT = 'proj-1';
const DOC = 'doc-uuid-1';
const compositeKey = `oe_takeoff_${PROJECT}__${DOC}`;

describe('useMeasurementPersistence', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns empty state when no fileName', () => {
    const setM = vi.fn();
    const setPS = vi.fn();
    const { result } = renderHook(() =>
      useMeasurementPersistence({
        fileName: null,
        documentId: null,
        measurements: [],
        setMeasurements: setM,
        pageScales: basePageScales,
        setPageScales: setPS,
        scale: defaultScale,
      }),
    );
    expect(result.current.hasPersistedData).toBe(false);
    expect(result.current.savedDocumentCount).toBe(0);
  });

  it('saveNow persists under the project+document composite key', () => {
    const m1 = makeMeasurement('m1');
    const setM = vi.fn();
    const setPS = vi.fn();
    const { result } = renderHook(() =>
      useMeasurementPersistence({
        fileName: 'test.pdf',
        documentId: DOC,
        measurements: [m1],
        setMeasurements: setM,
        pageScales: basePageScales,
        setPageScales: setPS,
        scale: defaultScale,
        projectId: PROJECT,
      }),
    );

    act(() => {
      result.current.saveNow();
    });

    // Keyed by project+document, NOT by filename (issue #238).
    expect(localStorage.getItem('oe_takeoff_test.pdf')).toBeNull();
    const raw = localStorage.getItem(compositeKey);
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw!);
    expect(parsed.measurements).toHaveLength(1);
    expect(parsed.measurements[0].id).toBe('m1');
    expect(parsed.pageScales.defaultScale.pixelsPerUnit).toBe(100);
    expect(parsed.scale.pixelsPerUnit).toBe(100);
    expect(parsed.savedAt).toBeGreaterThan(0);
    expect(getDocumentIndex()).toContain(compositeKey);
  });

  it('persists locally (not under a composite key) when there is no document UUID', () => {
    const m1 = makeMeasurement('m1');
    const setM = vi.fn();
    const setPS = vi.fn();
    // A freshly dropped local file: documentId null. It must persist locally
    // but never under the project+document key (it isn't a server document).
    const { result } = renderHook(() =>
      useMeasurementPersistence({
        fileName: 'dropped.pdf',
        documentId: null,
        measurements: [m1],
        setMeasurements: setM,
        pageScales: basePageScales,
        setPageScales: setPS,
        scale: defaultScale,
        projectId: PROJECT,
      }),
    );

    act(() => {
      result.current.saveNow();
    });

    const raw = localStorage.getItem('oe_takeoff_local__dropped.pdf');
    expect(raw).toBeTruthy();
    expect(JSON.parse(raw!).measurements).toHaveLength(1);
    // A local-only drop is not added to the synced-document index.
    expect(getDocumentIndex()).toEqual([]);
  });

  it('migrates a legacy single-scale document into the page-scale default', async () => {
    // Pre-populate localStorage in the OLD format (filename key, only ``scale``).
    const m1 = makeMeasurement('m1');
    const savedScale = { pixelsPerUnit: 50, unitLabel: 'm' };
    localStorage.setItem(
      'oe_takeoff_plan.pdf',
      JSON.stringify({ measurements: [m1], scale: savedScale, savedAt: Date.now() }),
    );

    const setM = vi.fn();
    const setPS = vi.fn();
    renderHook(() =>
      useMeasurementPersistence({
        fileName: 'plan.pdf',
        documentId: DOC,
        measurements: [],
        setMeasurements: setM,
        pageScales: basePageScales,
        setPageScales: setPS,
        scale: defaultScale,
        projectId: PROJECT,
      }),
    );

    // The load path is async (server first, then localStorage); the legacy
    // filename key is read and migrated into the composite key.
    await waitFor(() => expect(setM).toHaveBeenCalledWith([m1]));
    const ps = setPS.mock.calls[0]![0] as PageScales;
    expect(ps.defaultScale.pixelsPerUnit).toBe(50);
    expect(ps.byPage).toEqual({});
    // The legacy entry was rewritten under the composite key.
    const migrated = localStorage.getItem(compositeKey);
    expect(migrated).toBeTruthy();
    expect(JSON.parse(migrated!).measurements[0].id).toBe('m1');
  });

  it('reads back a new per-page scale document under the composite key', async () => {
    const m1 = makeMeasurement('m1', 3);
    const pageScales: PageScales = {
      defaultScale: { pixelsPerUnit: 100, unitLabel: 'm' },
      byPage: { 3: { pixelsPerUnit: 25, unitLabel: 'm' } },
    };
    localStorage.setItem(
      compositeKey,
      JSON.stringify({ measurements: [m1], pageScales, scale: defaultScale, savedAt: Date.now() }),
    );
    localStorage.setItem('oe_takeoff_index', JSON.stringify([compositeKey]));

    const setM = vi.fn();
    const setPS = vi.fn();
    renderHook(() =>
      useMeasurementPersistence({
        fileName: 'multi.pdf',
        documentId: DOC,
        measurements: [],
        setMeasurements: setM,
        pageScales: basePageScales,
        setPageScales: setPS,
        scale: defaultScale,
        projectId: PROJECT,
      }),
    );

    await waitFor(() => expect(setPS).toHaveBeenCalled());
    const ps = setPS.mock.calls[0]![0] as PageScales;
    expect(ps.defaultScale.pixelsPerUnit).toBe(100);
    expect(ps.byPage[3]!.pixelsPerUnit).toBe(25);
  });

  it('clearPersisted removes data under the composite key', () => {
    const setM = vi.fn();
    const setPS = vi.fn();
    localStorage.setItem(
      compositeKey,
      JSON.stringify({ measurements: [], scale: defaultScale, savedAt: Date.now() }),
    );
    localStorage.setItem('oe_takeoff_index', JSON.stringify([compositeKey]));

    const { result } = renderHook(() =>
      useMeasurementPersistence({
        fileName: 'test.pdf',
        documentId: DOC,
        measurements: [],
        setMeasurements: setM,
        pageScales: basePageScales,
        setPageScales: setPS,
        scale: defaultScale,
        projectId: PROJECT,
      }),
    );

    act(() => {
      result.current.clearPersisted();
    });

    expect(localStorage.getItem(compositeKey)).toBeNull();
    expect(getDocumentIndex()).not.toContain(compositeKey);
  });

  it('getDocumentIndex returns list of saved documents', () => {
    expect(getDocumentIndex()).toEqual([]);

    localStorage.setItem('oe_takeoff_index', JSON.stringify(['a', 'b']));
    expect(getDocumentIndex()).toEqual(['a', 'b']);
  });

  it('removeFromStorage removes a specific project+document', () => {
    const keyA = `oe_takeoff_${PROJECT}__${DOC}`;
    const keyB = `oe_takeoff_${PROJECT}__doc-2`;
    localStorage.setItem(keyA, '{}');
    localStorage.setItem(keyB, '{}');
    localStorage.setItem('oe_takeoff_index', JSON.stringify([keyA, keyB]));

    removeFromStorage(PROJECT, DOC);

    expect(localStorage.getItem(keyA)).toBeNull();
    expect(getDocumentIndex()).toEqual([keyB]);
  });

  it('auto-saves on measurement changes (debounced) under the composite key', () => {
    vi.useFakeTimers();
    const m1 = makeMeasurement('m1');
    const setM = vi.fn();
    const setPS = vi.fn();

    renderHook(() =>
      useMeasurementPersistence({
        fileName: 'auto.pdf',
        documentId: DOC,
        measurements: [m1],
        setMeasurements: setM,
        pageScales: basePageScales,
        setPageScales: setPS,
        scale: defaultScale,
        projectId: PROJECT,
      }),
    );

    // Before debounce
    expect(localStorage.getItem(compositeKey)).toBeNull();

    // After 500ms debounce
    act(() => {
      vi.advanceTimersByTime(600);
    });
    const raw = localStorage.getItem(compositeKey);
    expect(raw).toBeTruthy();
    expect(JSON.parse(raw!).measurements).toHaveLength(1);

    vi.useRealTimers();
  });

  it('savedDocumentCount reflects storage index size', () => {
    localStorage.setItem('oe_takeoff_index', JSON.stringify(['a', 'b', 'c']));
    const setM = vi.fn();
    const setPS = vi.fn();

    const { result } = renderHook(() =>
      useMeasurementPersistence({
        fileName: null,
        documentId: null,
        measurements: [],
        setMeasurements: setM,
        pageScales: basePageScales,
        setPageScales: setPS,
        scale: defaultScale,
      }),
    );

    expect(result.current.savedDocumentCount).toBe(3);
  });

  it('handles corrupt localStorage gracefully', async () => {
    localStorage.setItem(compositeKey, '{invalid json');
    localStorage.setItem('oe_takeoff_index', JSON.stringify([compositeKey]));

    const setM = vi.fn();
    const setPS = vi.fn();
    await act(async () => {
      renderHook(() =>
        useMeasurementPersistence({
          fileName: 'bad.pdf',
          documentId: DOC,
          measurements: [],
          setMeasurements: setM,
          pageScales: basePageScales,
          setPageScales: setPS,
          scale: defaultScale,
          projectId: PROJECT,
        }),
      );
      // Flush the async load (server -> localStorage fallback).
      await Promise.resolve();
    });

    // Should not call setMeasurements with corrupt data
    expect(setM).not.toHaveBeenCalled();
  });

  // ── Issue #242: two PDFs that share a filename must not share measurements ──
  // The pre-#238 build keyed measurements by filename, so uploading a second
  // PDF whose name matched an earlier one surfaced the earlier file's
  // measurements (cross-document bleed). Identity is now project + a stable
  // document UUID, so two same-named documents are fully isolated and the
  // shared filename key is never written.
  it('isolates two same-named PDFs by document UUID (issue #242)', () => {
    const fileName = 'Floor Plan.pdf';
    const docA = 'doc-uuid-A';
    const docB = 'doc-uuid-B';
    const setM = vi.fn();
    const setPS = vi.fn();

    // Draw + save a measurement against document A.
    const { result: a } = renderHook(() =>
      useMeasurementPersistence({
        fileName,
        documentId: docA,
        measurements: [makeMeasurement('a1')],
        setMeasurements: setM,
        pageScales: basePageScales,
        setPageScales: setPS,
        scale: defaultScale,
        projectId: PROJECT,
      }),
    );
    act(() => {
      a.current.saveNow();
    });

    // Draw + save a different measurement against document B - same filename,
    // same project, different upload.
    const { result: b } = renderHook(() =>
      useMeasurementPersistence({
        fileName,
        documentId: docB,
        measurements: [makeMeasurement('b1')],
        setMeasurements: setM,
        pageScales: basePageScales,
        setPageScales: setPS,
        scale: defaultScale,
        projectId: PROJECT,
      }),
    );
    act(() => {
      b.current.saveNow();
    });

    const keyA = `oe_takeoff_${PROJECT}__${docA}`;
    const keyB = `oe_takeoff_${PROJECT}__${docB}`;
    // Each document keeps its own namespace; neither sees the other's work.
    expect(JSON.parse(localStorage.getItem(keyA)!).measurements[0].id).toBe('a1');
    expect(JSON.parse(localStorage.getItem(keyB)!).measurements[0].id).toBe('b1');
    // Nothing was ever written under a filename-derived key (the old bug).
    expect(localStorage.getItem('oe_takeoff_Floor Plan.pdf')).toBeNull();
    expect(localStorage.getItem('oe_takeoff_Floor_Plan.pdf')).toBeNull();
    // Both documents are tracked independently in the index.
    expect(getDocumentIndex()).toEqual(expect.arrayContaining([keyA, keyB]));
  });

  // ── Issue #242: a freshly dropped local file never syncs to the server ──
  // A drop with no server document UUID must stay local-only (no bulkCreate),
  // so the "uploaded PDF vanishes on refresh" path can only ever be backed by
  // a real server document, never a client-only blob the server never saw.
  it('does not server-sync a local drop that has no document UUID (issue #242)', async () => {
    vi.useFakeTimers();
    const { takeoffApi } = await import('@/features/takeoff/api');
    const setM = vi.fn();
    const setPS = vi.fn();

    renderHook(() =>
      useMeasurementPersistence({
        fileName: 'dropped.pdf',
        documentId: null,
        measurements: [makeMeasurement('m1')],
        setMeasurements: setM,
        pageScales: basePageScales,
        setPageScales: setPS,
        scale: defaultScale,
        projectId: PROJECT,
      }),
    );

    // Past the 3s server-sync debounce: still no server write, because identity
    // (project + document UUID) is incomplete.
    act(() => {
      vi.advanceTimersByTime(3500);
    });
    expect(takeoffApi.bulkCreate).not.toHaveBeenCalled();

    vi.useRealTimers();
  });
});
