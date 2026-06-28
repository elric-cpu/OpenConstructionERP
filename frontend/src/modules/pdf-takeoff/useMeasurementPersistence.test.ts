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

  // ── Issue #276: server measurements must survive a setter identity change ──
  // The viewer used to pass inline-arrow setters whose identity changed on
  // every render. Those setters sat in the load effect's dependency array, so
  // a re-render WHILE the initial server fetch was in flight tore the effect
  // down (cancelled = true) and the resolved rows were dropped - the saved
  // takeoff silently failed to reappear. The hook now keeps the setters in
  // refs and depends only on the document identity, so an unstable setter can
  // no longer cancel an in-flight load.
  it('keeps server measurements when the setter identity changes mid-load (issue #276)', async () => {
    const { takeoffApi } = await import('@/features/takeoff/api');
    let resolveList: ((rows: unknown[]) => void) | null = null;
    (takeoffApi.list as unknown as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () =>
        new Promise((res) => {
          resolveList = res as unknown as (rows: unknown[]) => void;
        }),
    );

    const received: Array<Array<{ id: string }>> = [];
    const setPS = vi.fn();

    // Each render hands the hook brand-new inline-arrow setter closures (the
    // exact #276 trigger).
    const { rerender } = renderHook(() =>
      useMeasurementPersistence({
        fileName: 'race.pdf',
        documentId: DOC,
        measurements: [],
        setMeasurements: (ms) => {
          received.push(ms as Array<{ id: string }>);
        },
        pageScales: basePageScales,
        setPageScales: (ps) => setPS(ps),
        scale: defaultScale,
        projectId: PROJECT,
      }),
    );

    // Re-render twice while the server list promise is still pending.
    rerender();
    rerender();

    // The server now returns one measurement.
    await act(async () => {
      resolveList?.([
        {
          id: 's1', project_id: PROJECT, document_id: DOC, page: 1,
          type: 'distance', points: [{ x: 0, y: 0 }, { x: 10, y: 0 }],
          group_name: 'General', group_color: '#3B82F6', annotation: 'D1',
          measurement_value: 1, measurement_unit: 'm', depth: null,
          volume: null, perimeter: null, count_value: null,
          scale_pixels_per_unit: 100, linked_boq_position_id: null,
          is_deduction: false,
          metadata: { frontend_id: 'm1', scale_calibrated: false },
        },
      ]);
      await Promise.resolve();
    });

    await waitFor(() => expect(received.length).toBeGreaterThan(0));
    const last = received[received.length - 1]!;
    expect(last).toHaveLength(1);
    expect(last[0]!.id).toBe('m1');
  });

  // ── Issue #277: an uncalibrated page must not show a phantom calibration ──
  // A measurement drawn on a page still using the factory default carries the
  // default ratio (100 px/unit). Reconstructing per-page scale from the server
  // used to treat that as a real calibration, so the page came back showing
  // "Calibrated 1:N" instead of "Not calibrated". The page-scale model is now
  // only overwritten for pages that were genuinely calibrated.
  const serverRow = (over: Record<string, unknown>) => ({
    id: 's', project_id: PROJECT, document_id: DOC, page: 1, type: 'distance',
    points: [{ x: 0, y: 0 }, { x: 10, y: 0 }], group_name: 'General',
    group_color: '#3B82F6', annotation: '', measurement_value: 1,
    measurement_unit: 'm', depth: null, volume: null, perimeter: null,
    count_value: null, scale_pixels_per_unit: 100, linked_boq_position_id: null,
    is_deduction: false, metadata: { frontend_id: 'm' },
    ...over,
  });

  it('does not restore an uncalibrated default-scale page as calibrated (issue #277)', async () => {
    const { takeoffApi } = await import('@/features/takeoff/api');
    (takeoffApi.list as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      serverRow({
        page: 1, scale_pixels_per_unit: 100,
        metadata: { frontend_id: 'm1', scale_calibrated: false },
      }),
    ]);
    const setM = vi.fn();
    const setPS = vi.fn();
    renderHook(() =>
      useMeasurementPersistence({
        fileName: 'flat.pdf', documentId: DOC, measurements: [],
        setMeasurements: setM, pageScales: basePageScales, setPageScales: setPS,
        scale: defaultScale, projectId: PROJECT,
      }),
    );

    // Measurements still load from the server...
    await waitFor(() => expect(setM).toHaveBeenCalled());
    // ...but the page-scale model is NOT replaced with a phantom calibration:
    // an explicit ``scale_calibrated:false`` page stays on the default.
    expect(setPS).not.toHaveBeenCalled();
  });

  it('restores an explicitly calibrated page from the server (issue #277)', async () => {
    const { takeoffApi } = await import('@/features/takeoff/api');
    (takeoffApi.list as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      serverRow({
        id: 's2', page: 2, scale_pixels_per_unit: 25,
        metadata: { frontend_id: 'm1', scale_calibrated: true },
      }),
    ]);
    const setM = vi.fn();
    const setPS = vi.fn();
    renderHook(() =>
      useMeasurementPersistence({
        fileName: 'sheet.pdf', documentId: DOC, measurements: [],
        setMeasurements: setM, pageScales: basePageScales, setPageScales: setPS,
        scale: defaultScale, projectId: PROJECT,
      }),
    );

    await waitFor(() => expect(setPS).toHaveBeenCalled());
    const ps = setPS.mock.calls[0]![0] as PageScales;
    expect(ps.byPage[2]!.pixelsPerUnit).toBe(25);
    expect(ps.byPage[1]).toBeUndefined();
  });

  it('infers calibration for legacy rows (no flag) from the ratio (issue #277)', async () => {
    const { takeoffApi } = await import('@/features/takeoff/api');
    (takeoffApi.list as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      // Legacy row still on the factory default -> not calibrated.
      serverRow({ id: 'a', page: 1, scale_pixels_per_unit: 100, metadata: { frontend_id: 'a' } }),
      // Legacy row at a real ratio -> a genuine per-sheet calibration.
      serverRow({ id: 'b', page: 2, scale_pixels_per_unit: 50, metadata: { frontend_id: 'b' } }),
    ]);
    const setM = vi.fn();
    const setPS = vi.fn();
    renderHook(() =>
      useMeasurementPersistence({
        fileName: 'legacy.pdf', documentId: DOC, measurements: [],
        setMeasurements: setM, pageScales: basePageScales, setPageScales: setPS,
        scale: defaultScale, projectId: PROJECT,
      }),
    );

    await waitFor(() => expect(setPS).toHaveBeenCalled());
    const ps = setPS.mock.calls[0]![0] as PageScales;
    expect(ps.byPage[2]!.pixelsPerUnit).toBe(50);
    expect(ps.byPage[1]).toBeUndefined();
  });

  it('persists the page calibration flag on server sync (issue #277)', async () => {
    vi.useFakeTimers();
    const { takeoffApi } = await import('@/features/takeoff/api');
    (takeoffApi.bulkCreate as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);
    const calibrated: PageScales = {
      defaultScale,
      byPage: { 1: { pixelsPerUnit: 40, unitLabel: 'm' } },
    };
    renderHook(() =>
      useMeasurementPersistence({
        fileName: 'cal.pdf', documentId: DOC,
        measurements: [makeMeasurement('m1', 1)],
        setMeasurements: vi.fn(), pageScales: calibrated, setPageScales: vi.fn(),
        scale: { pixelsPerUnit: 40, unitLabel: 'm' }, projectId: PROJECT,
      }),
    );

    // Past the 3s server-sync debounce.
    act(() => {
      vi.advanceTimersByTime(3500);
    });
    expect(takeoffApi.bulkCreate).toHaveBeenCalled();
    const row = (takeoffApi.bulkCreate as unknown as ReturnType<typeof vi.fn>)
      .mock.calls[0]![0][0];
    expect(row.scale_pixels_per_unit).toBe(40);
    expect(row.metadata.scale_calibrated).toBe(true);

    vi.useRealTimers();
  });
});
