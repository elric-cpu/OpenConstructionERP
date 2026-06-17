import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { QueryClientContext } from '@tanstack/react-query';
import { takeoffApi, type MeasurementCreate, type MeasurementResponse } from '@/features/takeoff/api';
import {
  type PageScales,
  hydratePageScales,
  scaleForPage,
} from './data/page-scales';

/* ── Types (mirrored from TakeoffViewerModule) ──────────────────────── */

interface Point {
  x: number;
  y: number;
}

interface Measurement {
  id: string;
  type: 'distance' | 'polyline' | 'area' | 'volume' | 'count'
    | 'cloud' | 'arrow' | 'text' | 'rectangle' | 'highlight';
  points: Point[];
  value: number;
  unit: string;
  label: string;
  annotation: string;
  page: number;
  group: string;
  depth?: number;
  area?: number;
  text?: string;
  color?: string;
  width?: number;
  height?: number;
  /** Opening deduction (area void). Stored as positive gross area; the
   *  rollup subtracts it. Round-trips so a void survives a server sync. */
  isDeduction?: boolean;
  /** Server-side ID (set after first sync). */
  serverId?: string;
  /** BOQ link metadata carried through persistence. */
  linkedPositionId?: string;
  linkedPositionOrdinal?: string;
  linkedBoqId?: string;
  linkedPositionLabel?: string;
  /** AI-suggested but unconfirmed (issue #194): excluded from server sync
   *  and localStorage until the user accepts it (which clears the flag). */
  suggested?: boolean;
  /** Recognition confidence 0..1 on AI-sourced measurements. */
  confidence?: number;
}

interface ScaleConfig {
  pixelsPerUnit: number;
  unitLabel: string;
}

interface PersistedDocument {
  measurements: Measurement[];
  /** New per-page scale model. Optional so an older document (which only
   *  carried ``scale``) still parses; ``hydratePageScales`` migrates it. */
  pageScales?: PageScales;
  /** Legacy single document-wide scale. Kept for backward-compatible reads
   *  (and still written so a downgrade to an older build keeps working). */
  scale: ScaleConfig;
  savedAt: number;
}

/* ── localStorage helpers (fallback) ─────────────────────────────────── */

const STORAGE_PREFIX = 'oe_takeoff_';
const INDEX_KEY = 'oe_takeoff_index';

/**
 * Stable storage key for a document's measurements (issue #238).
 *
 * Identity is ``project_id`` + a stable document UUID, never the PDF
 * filename: two same-named PDFs (in one project, or across projects via the
 * old filename-only key) used to collide in one namespace. The composite
 * ``<projectId>__<documentId>`` key isolates them. Both halves are sanitised
 * so a stray char in an id can never break the key shape.
 */
function compositeKey(projectId: string, documentId: string): string {
  const safe = (s: string) => s.replace(/[^a-zA-Z0-9._-]/g, '_');
  return `${STORAGE_PREFIX}${safe(projectId)}__${safe(documentId)}`;
}

/**
 * Legacy filename-only key. Read-only: used once on load to migrate a
 * user's locally-saved measurements into the new composite key so an
 * upgrade doesn't lose them. Never written to any more.
 */
function legacyDocKey(fileName: string): string {
  return `${STORAGE_PREFIX}${fileName.replace(/[^a-zA-Z0-9._-]/g, '_')}`;
}

function readKey(key: string): PersistedDocument | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedDocument;
  } catch {
    return null;
  }
}

/**
 * One-time read of the legacy ``oe_takeoff_<filename>`` key. Returns the
 * parsed document if present so the caller can migrate it into the new
 * composite key. Read-only - it does not delete the legacy entry (a
 * downgrade to an older build would still find it).
 */
function loadLegacyFromStorage(fileName: string | null): PersistedDocument | null {
  if (!fileName) return null;
  return readKey(legacyDocKey(fileName));
}

function saveToStorage(projectId: string, documentId: string, data: PersistedDocument): void {
  try {
    const key = compositeKey(projectId, documentId);
    localStorage.setItem(key, JSON.stringify(data));
    const index = getDocumentIndex();
    if (!index.includes(key)) {
      index.push(key);
      localStorage.setItem(INDEX_KEY, JSON.stringify(index));
    }
  } catch {
    // localStorage full — silently fail
  }
}

export function removeFromStorage(projectId: string, documentId: string): void {
  try {
    const key = compositeKey(projectId, documentId);
    localStorage.removeItem(key);
    const index = getDocumentIndex().filter((n) => n !== key);
    localStorage.setItem(INDEX_KEY, JSON.stringify(index));
  } catch {
    // ignore
  }
}

export function getDocumentIndex(): string[] {
  try {
    const raw = localStorage.getItem(INDEX_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

/* ── Unit canonicalization ───────────────────────────────────────────── */

/**
 * Map the display-glyph unit the viewer emits (`m²` / `m³` via the
 * superscript U+00B2 / U+00B3) to the canonical BOQ unit string
 * (`m2` / `m3`).
 *
 * Even though the backend now accepts the superscript form verbatim
 * (D-TKC-001 backend pairing), cross-module quantity sync — bim_hub
 * `_sync_boq_quantity_from_links`, BOQ linking, the catalogue/cost
 * matchers — keys on the canonical `m`/`m2`/`m3`/`pcs` vocabulary.
 * Persisting the canonical form keeps the server copy aligned with the
 * Export-to-BOQ / link-to-position paths (which already canonicalize),
 * and {@link displayUnit} restores the glyph on round-trip so the UI is
 * unchanged.
 */
function canonicalUnit(unit: string): string {
  switch (unit) {
    case 'm²':
      return 'm2';
    case 'm³':
      return 'm3';
    default:
      return unit || 'm';
  }
}

/** Inverse of {@link canonicalUnit}: restore the superscript display
 *  glyph from the canonical stored unit so a server round-trip renders
 *  identically to a freshly-drawn measurement. */
function displayUnit(unit: string): string {
  switch (unit) {
    case 'm2':
      return 'm²';
    case 'm3':
      return 'm³';
    default:
      return unit;
  }
}

/* ── Convert between frontend Measurement and backend API format ─────── */

function toApiFormat(
  m: Measurement,
  projectId: string,
  documentId: string,
  pageScales?: PageScales,
): MeasurementCreate {
  // Area measurements carry the polygon area in `m.value`; volume
  // measurements carry the area separately in `m.area`. Persist the
  // canonical dimension fields so bim_hub quantity sync / BOQ linking
  // can pick the right quantity instead of guessing from the unit
  // string alone (D-TKC-031).
  const areaValue =
    m.type === 'area' ? m.value : m.type === 'volume' ? (m.area ?? null) : null;
  // Per-page scale: send the scale of THIS measurement's page, not a single
  // document-wide ratio, so a sheet at 1:500 and a sheet at 1:50 each get
  // their own px-per-unit for the server-side B8 recompute.
  const scale = pageScales ? scaleForPage(pageScales, m.page) : undefined;
  const ppu =
    scale && scale.pixelsPerUnit > 0 ? scale.pixelsPerUnit : null;
  return {
    project_id: projectId,
    document_id: documentId,
    page: m.page,
    type: m.type,
    group_name: m.group || 'General',
    group_color: m.color || '#3B82F6',
    annotation: m.annotation || m.label || null,
    points: m.points,
    measurement_value: m.value || null,
    measurement_unit: canonicalUnit(m.unit),
    depth: m.depth ?? null,
    volume: m.type === 'volume' ? m.value : null,
    perimeter: m.type === 'polyline' ? m.value : null,
    count_value: m.type === 'count' ? Math.round(m.value) : null,
    // Send the calibration so the server-side recompute can verify the
    // client value against the raw geometry (Audit B8) instead of
    // trusting it blindly.
    scale_pixels_per_unit: ppu,
    // Opening deduction only applies to an area; the server enforces this
    // too but we keep the payload honest.
    is_deduction: m.type === 'area' ? Boolean(m.isDeduction) : false,
    linked_boq_position_id: m.linkedPositionId ?? null,
    metadata: {
      text: m.text,
      width: m.width,
      height: m.height,
      area: areaValue ?? undefined,
      frontend_id: m.id,
      linked_boq_id: m.linkedBoqId,
      linked_position_ordinal: m.linkedPositionOrdinal,
      linked_position_label: m.linkedPositionLabel,
    },
  };
}

/**
 * Geometry signature for a synced measurement: the set of fields a
 * reshape can change that feed the server-side recompute (Audit B8). When
 * this string changes for a row that already has a `serverId`, the row was
 * edited in-canvas and must be PATCHed so the server re-derives the billed
 * quantity. Annotation / color / group edits are intentionally excluded -
 * those are handled by the existing flows and do not move the quantity.
 */
function geometrySignature(m: Measurement): string {
  return JSON.stringify({
    p: m.points,
    d: m.depth ?? null,
    c: m.type === 'count' ? Math.round(m.value) : null,
    t: m.type,
    // The deduction flag flips a measurement between gross and void without
    // changing its geometry; include it so toggling it triggers a PATCH and
    // the server row stays in sync.
    x: m.type === 'area' ? Boolean(m.isDeduction) : false,
  });
}

/** Build the reshape PATCH body: just the geometry-bearing fields. The
 *  server recomputes `measurement_value` / `volume` / `perimeter` from
 *  these, so a client cannot inflate a quantity through this path. */
function toApiUpdate(m: Measurement, scale?: ScaleConfig): Partial<MeasurementCreate> {
  const ppu = scale && scale.pixelsPerUnit > 0 ? scale.pixelsPerUnit : null;
  return {
    points: m.points,
    type: m.type,
    scale_pixels_per_unit: ppu,
    depth: m.depth ?? null,
    count_value: m.type === 'count' ? Math.round(m.value) : null,
    is_deduction: m.type === 'area' ? Boolean(m.isDeduction) : false,
  };
}

function fromApiFormat(r: MeasurementResponse): Measurement {
  const meta = r.metadata || {};
  return {
    id: (meta.frontend_id as string) || r.id,
    serverId: r.id,
    type: r.type as Measurement['type'],
    points: r.points as Point[],
    value: r.measurement_value ?? r.count_value ?? 0,
    unit: displayUnit(r.measurement_unit),
    label: r.annotation || '',
    annotation: r.annotation || '',
    page: r.page,
    group: r.group_name,
    depth: r.depth ?? undefined,
    // Prefer the dedicated metadata.area; fall back to the canonical
    // server `volume`/`measurement_value` so an area survives even when
    // it was persisted before the dedicated field existed (D-TKC-031).
    area:
      (meta.area as number) ??
      (r.type === 'area' ? r.measurement_value ?? undefined : undefined),
    text: (meta.text as string) ?? undefined,
    color: r.group_color || undefined,
    width: (meta.width as number) ?? undefined,
    height: (meta.height as number) ?? undefined,
    isDeduction: r.is_deduction ?? undefined,
    linkedPositionId: r.linked_boq_position_id ?? undefined,
    linkedBoqId: (meta.linked_boq_id as string) ?? undefined,
    linkedPositionOrdinal: (meta.linked_position_ordinal as string) ?? undefined,
    linkedPositionLabel: (meta.linked_position_label as string) ?? undefined,
  };
}

/**
 * Reconstruct a {@link PageScales} from server measurements.
 *
 * Each row carries the ``scale_pixels_per_unit`` of the page it was drawn
 * on, so we take the most-recently-seen positive ratio per page as that
 * page's scale and the most common ratio across all pages as the document
 * default. Returns ``null`` when no row carries a usable ratio (the caller
 * then keeps whatever it already had). This restores per-page calibration
 * for a project opened on a device that has no localStorage copy.
 */
function pageScalesFromServer(rows: MeasurementResponse[]): PageScales | null {
  const byPage: Record<number, ScaleConfig> = {};
  const ratioFreq = new Map<number, number>();
  for (const r of rows) {
    const ppu = r.scale_pixels_per_unit;
    if (typeof ppu !== 'number' || !Number.isFinite(ppu) || ppu <= 0) continue;
    // Scale is metric-canonical (always metres); only the ratio differs per
    // page. Track frequency to pick the document default.
    byPage[r.page] = { pixelsPerUnit: ppu, unitLabel: 'm' };
    ratioFreq.set(ppu, (ratioFreq.get(ppu) ?? 0) + 1);
  }
  if (Object.keys(byPage).length === 0) return null;
  let bestRatio = 100;
  let bestCount = -1;
  for (const [ratio, count] of ratioFreq.entries()) {
    if (count > bestCount) {
      bestCount = count;
      bestRatio = ratio;
    }
  }
  return { defaultScale: { pixelsPerUnit: bestRatio, unitLabel: 'm' }, byPage };
}

/* ── Hook ─────────────────────────────────────────────────────────────── */

interface UseMeasurementPersistenceOptions {
  /** Display-only filename. Used for the legacy-key migration on load and
   *  for the unsaved-changes UX; NEVER used as a storage or server key. */
  fileName: string | null;
  /** Stable document UUID (issue #238). Measurement identity is
   *  ``projectId`` + this id. ``null`` when no server document exists yet
   *  (a freshly dropped local file) - in that state we persist locally only
   *  and do NOT sync to the server. */
  documentId: string | null;
  measurements: Measurement[];
  setMeasurements: (measurements: Measurement[]) => void;
  /** Per-page (per-sheet) scale model. Persisted whole; a legacy
   *  single-scale document is migrated into the default on load. */
  pageScales: PageScales;
  setPageScales: (pageScales: PageScales) => void;
  /** The current page's effective scale, sent as ``scale_pixels_per_unit``
   *  on measurements so the server B8 recompute uses the same ratio.
   *  (Per-measurement page scale is resolved from ``pageScales``.) */
  scale: ScaleConfig;
  /** Active project ID for backend sync. */
  projectId?: string | null;
}

interface UseMeasurementPersistenceResult {
  hasPersistedData: boolean;
  saveNow: () => void;
  clearPersisted: () => void;
  savedDocumentCount: number;
  /** Whether data is being synced to the server. */
  syncing: boolean;
  /** Whether server sync has been done at least once. */
  syncedToServer: boolean;
}

export function useMeasurementPersistence({
  fileName,
  documentId,
  measurements,
  setMeasurements,
  pageScales,
  setPageScales,
  scale,
  projectId,
}: UseMeasurementPersistenceOptions): UseMeasurementPersistenceResult {
  // Server identity (issue #238): both a project AND a stable document UUID
  // must be present before we touch the server or use the composite local
  // key. Filename alone never qualifies.
  const canSync = Boolean(projectId && documentId);
  // Local-storage key. With a server UUID this is the project+document
  // composite (shared with the server-load path). A freshly dropped local
  // file has no UUID yet, so it gets a stable local-only key derived from
  // its filename - persisted locally, never synced - which migrates into
  // the composite key once a real UUID arrives.
  const localKey =
    projectId && documentId
      ? compositeKey(projectId, documentId)
      : fileName
        ? `${STORAGE_PREFIX}local__${fileName.replace(/[^a-zA-Z0-9._-]/g, '_')}`
        : null;
  // Identity used to detect when a *different* document is opened (so the
  // load effect re-runs). Filename is included so two unsynced local drops
  // with different names don't share a load.
  const identity = `${projectId ?? ''}|${documentId ?? ''}|${fileName ?? ''}`;

  const hasPersistedRef = useRef(false);
  const lastIdentityRef = useRef<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncedToServer, setSyncedToServer] = useState(false);
  const serverSyncRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Reshape-PATCH tracking (#194 Feature 1). `geometrySigRef` remembers the
  // last geometry we know the server has for each `serverId`, so we only
  // PATCH a row whose geometry actually changed. `patchTimerRef` debounces
  // and `inFlightPatchRef` coalesces rapid reshapes of the same row
  // (last-write-wins) so mid-drag churn never floods the network.
  const geometrySigRef = useRef<Map<string, string>>(new Map());
  const patchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightPatchRef = useRef<Set<string>>(new Set());
  // Read the QueryClient directly from context — ``useContext`` returns
  // ``undefined`` instead of throwing when the provider is absent (e.g. in
  // unit tests that render the hook in isolation). When present, we use
  // it to broadcast a refresh to the unified Markups hub.
  const qc = useContext(QueryClientContext);

  // Load persisted data when the document identity changes — try server
  // first (keyed by the stable document UUID, issue #238), fallback to
  // localStorage.
  useEffect(() => {
    if (!fileName || identity === lastIdentityRef.current) return;
    lastIdentityRef.current = identity;

    let cancelled = false;

    async function loadData() {
      // Try server first, but only with BOTH a project and a stable document
      // UUID. Filename is never sent as the document key any more.
      if (canSync && projectId && documentId) {
        try {
          const serverData = await takeoffApi.list(projectId, documentId);
          if (!cancelled && serverData.length > 0) {
            hasPersistedRef.current = true;
            setSyncedToServer(true);
            const mapped = serverData.map(fromApiFormat);
            // Seed the geometry baseline so a fresh load never re-PATCHes
            // rows that already match the server (#194).
            geometrySigRef.current = new Map(
              mapped
                .filter((m) => m.serverId)
                .map((m) => [m.serverId as string, geometrySignature(m)]),
            );
            // Reconstruct the per-page scale from the per-measurement ratios
            // the server stored. The localStorage copy (set below on next
            // save) is authoritative when present, but for a project loaded
            // on a fresh device this is the only place the calibration lives.
            const fromServer = pageScalesFromServer(serverData);
            if (fromServer) setPageScales(fromServer);
            setMeasurements(mapped);
            return;
          }
        } catch {
          // Server unavailable — fall through to localStorage
        }
      }

      // Fallback to localStorage (the composite project+document key, or the
      // local-only key for an unsynced fresh drop).
      if (!cancelled) {
        let data = localKey ? readKey(localKey) : null;
        // Back-compat (issue #238): nothing under the new composite key yet?
        // A user upgrading from a filename-keyed build still has their
        // measurements under ``oe_takeoff_<filename>``. Read it once and
        // rewrite it under the composite key so they don't lose local work.
        // Read-only on the legacy key (a downgrade still finds it).
        if (!data && projectId && documentId) {
          const legacy = loadLegacyFromStorage(fileName);
          if (legacy) {
            data = legacy;
            saveToStorage(projectId, documentId, legacy);
          }
        }
        if (data) {
          hasPersistedRef.current = true;
          setMeasurements(data.measurements);
          // Graceful migration: a document saved before per-page scale only
          // carried ``data.scale``; hydratePageScales promotes it to the
          // document default so every page reads the same number it always
          // did until the user re-calibrates an individual sheet.
          setPageScales(hydratePageScales(data.pageScales, data.scale));
        } else {
          hasPersistedRef.current = false;
        }
      }
    }

    loadData();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity, setMeasurements, setPageScales]);

  // Auto-save to localStorage with debounce (500ms). Keyed by the stable
  // project+document composite (issue #238), or a local-only key for an
  // unsynced fresh drop.
  useEffect(() => {
    if (!localKey) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      // Never persist AI suggestions: only confirmed measurements are saved.
      // Persist BOTH the new per-page model and the legacy single ``scale``
      // (the current page's, as a best-effort default) so a downgrade to an
      // older build that only reads ``scale`` still finds a usable value.
      const payload: PersistedDocument = {
        measurements: measurements.filter((m) => !m.suggested),
        pageScales,
        scale,
        savedAt: Date.now(),
      };
      if (projectId && documentId) {
        saveToStorage(projectId, documentId, payload);
      } else {
        // Local-only key (fresh drop, no server UUID yet) - written directly
        // and not added to the document index (it isn't a synced document).
        try {
          localStorage.setItem(localKey, JSON.stringify(payload));
        } catch {
          // localStorage full — silently fail
        }
      }
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [localKey, projectId, documentId, measurements, pageScales, scale]);

  // Auto-sync to server with debounce (3s). Both measurement and annotation
  // types persist now (v2.6.7) — backend schema accepts the full set.
  // Gated on a stable document UUID + project (issue #238): a filename alone
  // never triggers server sync, so an unsynced local drop stays local-only.
  useEffect(() => {
    if (!canSync || !projectId || !documentId) return;
    if (measurements.length === 0) return;
    const serverMeasurements = measurements;

    if (serverSyncRef.current) clearTimeout(serverSyncRef.current);
    serverSyncRef.current = setTimeout(async () => {
      setSyncing(true);
      try {
        const toCreate = serverMeasurements
          // Suggested-but-unconfirmed measurements are excluded; accepting a
          // suggestion clears `suggested` and the next tick syncs it (#194).
          .filter((m) => !m.serverId && !m.suggested)
          // Per-page scale: toApiFormat resolves each row's own page scale
          // from pageScales, so a multi-sheet set syncs correct ratios. The
          // document_id sent is the stable UUID, never the filename (#238).
          .map((m) => toApiFormat(m, projectId, documentId, pageScales));

        if (toCreate.length > 0) {
          const created = await takeoffApi.bulkCreate(toCreate);
          // Update serverId on created measurements
          setMeasurements(measurements.map((m) => {
            if (m.serverId) return m;
            const match = created.find((c) =>
              (c.metadata?.frontend_id as string) === m.id
            );
            if (!match) return m;
            // Seed the reshape baseline for the freshly-synced row so a
            // later in-canvas edit PATCHes, but a no-op tick does not (#194).
            geometrySigRef.current.set(match.id, geometrySignature(m));
            return { ...m, serverId: match.id };
          }));
          // Surface the new measurements in the unified Markups hub.
          qc?.invalidateQueries({ queryKey: ['unified-markups'] });
        }
        setSyncedToServer(true);
      } catch {
        // Server sync failed — data safe in localStorage
      } finally {
        setSyncing(false);
      }
    }, 3000);

    return () => {
      if (serverSyncRef.current) clearTimeout(serverSyncRef.current);
    };
  }, [canSync, projectId, documentId, measurements, setMeasurements, pageScales]);

  // Reshape PATCH (#194 Feature 1). When a measurement that already has a
  // `serverId` has its geometry changed in-canvas, PATCH just that row so
  // the server re-derives the billed quantity (Audit B8). Debounced 400ms
  // off the last change; mid-drag churn never reaches the network because
  // the viewer only commits points on mouseup. Coalesced per `serverId`:
  // if a row is already in-flight we skip it this tick and the changed
  // signature keeps it dirty for the next pass (last-write-wins per row).
  // Gated on canSync (#238): a serverId only exists after a sync, but gate
  // explicitly so a stale row can't PATCH once the document id is gone.
  useEffect(() => {
    if (!canSync) return;
    if (measurements.length === 0) return;

    // Find synced rows whose geometry drifted from the server baseline.
    const dirty = measurements.filter((m) => {
      if (!m.serverId || m.suggested) return false;
      const prevSig = geometrySigRef.current.get(m.serverId);
      // No baseline yet (e.g. a row hydrated before its baseline seeded)
      // -> record the current signature without firing a PATCH.
      if (prevSig === undefined) {
        geometrySigRef.current.set(m.serverId, geometrySignature(m));
        return false;
      }
      return prevSig !== geometrySignature(m);
    });
    if (dirty.length === 0) return;

    if (patchTimerRef.current) clearTimeout(patchTimerRef.current);
    patchTimerRef.current = setTimeout(async () => {
      const reconciled: { frontendId: string; value: number; area?: number }[] = [];
      await Promise.all(
        dirty.map(async (m) => {
          const serverId = m.serverId!;
          if (inFlightPatchRef.current.has(serverId)) return; // coalesce
          inFlightPatchRef.current.add(serverId);
          const sig = geometrySignature(m);
          try {
            // Per-page scale: PATCH with the measurement's own page scale so
            // the server B8 recompute uses the ratio that sheet was drawn at.
            const updated = await takeoffApi.update(
              serverId,
              toApiUpdate(m, scaleForPage(pageScales, m.page)),
            );
            // Mark this geometry as known-on-server so we don't re-PATCH it.
            geometrySigRef.current.set(serverId, sig);
            // Overwrite the optimistic value with the server-authoritative
            // recompute so the displayed quantity can never exceed what the
            // geometry justifies.
            const serverValue =
              updated.measurement_value ?? updated.volume ?? updated.count_value ?? m.value;
            reconciled.push({
              frontendId: m.id,
              value: serverValue,
              area: (updated.metadata?.area as number) ?? updated.measurement_value ?? undefined,
            });
          } catch {
            // PATCH failed - keep the optimistic value + the localStorage
            // copy (the 500ms effect above already persisted it). Leave the
            // signature stale so the next tick retries.
          } finally {
            inFlightPatchRef.current.delete(serverId);
          }
        }),
      );

      if (reconciled.length > 0) {
        setMeasurements(
          measurements.map((m) => {
            const r = reconciled.find((x) => x.frontendId === m.id);
            if (!r) return m;
            return {
              ...m,
              value: r.value,
              ...(m.type === 'volume' && r.area !== undefined ? { area: r.area } : {}),
            };
          }),
        );
        qc?.invalidateQueries({ queryKey: ['unified-markups'] });
      }
    }, 400);

    return () => {
      if (patchTimerRef.current) clearTimeout(patchTimerRef.current);
    };
  }, [canSync, projectId, documentId, measurements, setMeasurements, pageScales, qc]);

  const saveNow = useCallback(() => {
    if (!localKey) return;
    const payload: PersistedDocument = { measurements, pageScales, scale, savedAt: Date.now() };
    if (projectId && documentId) {
      saveToStorage(projectId, documentId, payload);
    } else {
      try {
        localStorage.setItem(localKey, JSON.stringify(payload));
      } catch {
        // localStorage full — silently fail
      }
    }
  }, [localKey, projectId, documentId, measurements, pageScales, scale]);

  const clearPersisted = useCallback(() => {
    if (projectId && documentId) {
      removeFromStorage(projectId, documentId);
    } else if (localKey) {
      try {
        localStorage.removeItem(localKey);
      } catch {
        // ignore
      }
    }
    hasPersistedRef.current = false;
  }, [projectId, documentId, localKey]);

  return {
    hasPersistedData: hasPersistedRef.current,
    saveNow,
    clearPersisted,
    savedDocumentCount: getDocumentIndex().length,
    syncing,
    syncedToServer,
  };
}
