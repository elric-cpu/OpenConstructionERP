// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * useFederatedGeometryLoader — React Query hook that loads the GLB
 * geometry for every member of a BIM federation in parallel.
 *
 * Slice 3 of BIM Federations.
 *
 * The hook first fetches the federation detail (member list, origin
 * offset) via ``GET /api/v1/bim-hub/federations/{id}``, then fires N
 * parallel ``GET /api/v1/bim-hub/models/{model_id}/geometry/`` requests
 * via ``useQueries``. Per-member error state is surfaced verbatim so
 * the viewer can show "Model X failed to load" without poisoning the
 * other members.
 *
 * Auth: the JWT lives in ``useAuthStore`` and is attached via the same
 * ``Authorization: Bearer`` header pattern used by ``apiGet`` — but the
 * geometry endpoint returns binary (not JSON) so we hand-roll the
 * fetch instead of routing through ``apiGet``.
 */
import { useMemo } from 'react';
import { useQuery, useQueries } from '@tanstack/react-query';

import { apiGet } from '@/shared/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';

/* ── Types ─────────────────────────────────────────────────────────── */

export interface FederationMemberLite {
  id: string;
  federation_id: string;
  bim_model_id: string;
  discipline: string;
  visible: boolean;
  z_order: number;
  color_hint: string | null;
}

export interface FederationDetail {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  origin_offset: { x?: number; y?: number; z?: number };
  shared_units: string;
  member_count: number;
  members: FederationMemberLite[];
}

export interface LoadedMember {
  modelId: string;
  discipline: string;
  /** GLB bytes — owned by the caller; the viewer is responsible for
   * releasing the underlying ArrayBuffer when done. */
  buffer: ArrayBuffer;
  /** Origin offset to apply to the member root group. */
  originOffset: { x: number; y: number; z: number };
  /** Display name (best-effort; bim_model_id slice when not resolvable). */
  modelName: string;
}

export interface MemberLoadError {
  modelId: string;
  error: Error;
}

export interface UseFederatedGeometryLoaderResult {
  detail: FederationDetail | undefined;
  members: LoadedMember[];
  errors: MemberLoadError[];
  isLoading: boolean;
  isDetailLoading: boolean;
  detailError: Error | null;
}

/* ── Fetcher ───────────────────────────────────────────────────────── */

interface FetchMemberGeometryArgs {
  modelId: string;
  discipline: string;
  originOffset: { x: number; y: number; z: number };
}

async function fetchMemberGeometry(
  args: FetchMemberGeometryArgs,
): Promise<LoadedMember> {
  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = {
    Accept: 'model/gltf-binary, application/octet-stream',
    'X-DDC-Client': 'OE/1.0',
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const url = `/api/v1/bim-hub/models/${encodeURIComponent(args.modelId)}/geometry/`;
  const resp = await fetch(url, { headers });
  if (!resp.ok) {
    let detail = '';
    try {
      const ct = resp.headers.get('content-type') ?? '';
      if (ct.includes('application/json')) {
        const body = (await resp.json()) as { detail?: string };
        detail = body?.detail ?? '';
      } else {
        detail = (await resp.text()).slice(0, 240);
      }
    } catch {
      /* ignore */
    }
    throw new Error(
      detail
        ? `Geometry fetch failed (${resp.status}): ${detail}`
        : `Geometry fetch failed: ${resp.status}`,
    );
  }
  const buffer = await resp.arrayBuffer();
  return {
    modelId: args.modelId,
    discipline: args.discipline,
    buffer,
    originOffset: args.originOffset,
    // Caller can override with a friendly name from the model detail; we
    // pass a stable placeholder here and let the viewer's legend layer
    // resolve the proper label on a follow-up cycle.
    modelName: args.modelId.slice(0, 8),
  };
}

/* ── Hook ──────────────────────────────────────────────────────────── */

export function useFederatedGeometryLoader(
  federationId: string,
): UseFederatedGeometryLoaderResult {
  const detailQuery = useQuery({
    queryKey: ['federation-detail-for-viewer', federationId],
    queryFn: () =>
      apiGet<FederationDetail>(`/v1/bim-hub/federations/${federationId}`),
    enabled: !!federationId,
  });

  const detail = detailQuery.data;
  const memberList = detail?.members ?? [];

  // Derive the per-member fetch args once per detail change. The offset
  // is a constant for the federation (applied uniformly to every member)
  // but we attach it to each member's args so the fetcher result is
  // self-contained.
  const memberArgs = useMemo<FetchMemberGeometryArgs[]>(() => {
    if (!detail) return [];
    const offset = {
      x: detail.origin_offset?.x ?? 0,
      y: detail.origin_offset?.y ?? 0,
      z: detail.origin_offset?.z ?? 0,
    };
    return memberList.map((m) => ({
      modelId: m.bim_model_id,
      discipline: m.discipline,
      originOffset: offset,
    }));
  }, [detail, memberList]);

  const geometryQueries = useQueries({
    queries: memberArgs.map((args) => ({
      queryKey: ['federation-member-geometry', args.modelId],
      queryFn: () => fetchMemberGeometry(args),
      enabled: !!args.modelId,
      retry: false,
      // 5 minutes — GLB blobs are immutable; the user re-uploading a
      // model creates a new model id, so caching by id is safe.
      staleTime: 5 * 60 * 1000,
    })),
  });

  const members: LoadedMember[] = [];
  const errors: MemberLoadError[] = [];
  for (let i = 0; i < geometryQueries.length; i++) {
    const q = geometryQueries[i];
    const args = memberArgs[i];
    if (!q || !args) continue;
    if (q.data) members.push(q.data);
    if (q.error)
      errors.push({
        modelId: args.modelId,
        error: q.error instanceof Error ? q.error : new Error(String(q.error)),
      });
  }

  const isLoading =
    detailQuery.isLoading ||
    (geometryQueries.length > 0 &&
      geometryQueries.some((q) => q.isLoading));

  return {
    detail,
    members,
    errors,
    isLoading,
    isDetailLoading: detailQuery.isLoading,
    detailError:
      detailQuery.error instanceof Error
        ? detailQuery.error
        : detailQuery.error
          ? new Error(String(detailQuery.error))
          : null,
  };
}

export default useFederatedGeometryLoader;
