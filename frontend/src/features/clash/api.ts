/**
 * API helpers for Clash Detection.
 *
 * Endpoints (mounted at /api/v1/clash):
 *   GET    /v1/clash/projects/{pid}/models
 *   GET    /v1/clash/projects/{pid}/runs/
 *   POST   /v1/clash/projects/{pid}/runs/
 *   GET    /v1/clash/projects/{pid}/runs/{rid}
 *   DELETE /v1/clash/projects/{pid}/runs/{rid}
 *   GET    /v1/clash/projects/{pid}/runs/{rid}/results
 *   PATCH  /v1/clash/projects/{pid}/runs/{rid}/results/{cid}
 *   POST   /v1/clash/projects/{pid}/runs/{rid}/export-bcf‌⁠‍
 */

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

export interface ClashModelOption {
  id: string;
  name: string;
  element_count: number;
  status: string | null;
}

export interface ClashMatrixCell {
  a: string;
  b: string;
  count: number;
  open_count: number;
}

export interface ClashLevelMatrixCell {
  a: number;
  b: number;
  count: number;
  open_count: number;
}

export interface ClashRunSummary {
  disciplines: string[];
  matrix: ClashMatrixCell[];
  /** Storey×storey grid — present on newer backends; optional so older
   *  payloads still type-check. */
  storeys?: number[];
  level_matrix?: ClashLevelMatrixCell[];
  by_status: Record<string, number>;
  by_type: Record<string, number>;
}

export interface ClashRun {
  id: string;
  project_id: string;
  name: string;
  model_ids: string[];
  tolerance_m: number;
  clearance_m: number;
  mode: string;
  discipline_filter: string[][] | null;
  status: string;
  error: string | null;
  element_count: number;
  total_clashes: number;
  summary: ClashRunSummary;
  created_by: string;
  created_at: string;
  completed_at: string | null;
}

export interface ClashRunListItem {
  id: string;
  name: string;
  status: string;
  model_ids: string[];
  element_count: number;
  total_clashes: number;
  created_at: string;
  completed_at: string | null;
}

export interface ClashResult {
  id: string;
  run_id: string;
  a_element_id: string;
  b_element_id: string;
  a_stable_id: string;
  b_stable_id: string;
  a_name: string;
  b_name: string;
  a_discipline: string;
  b_discipline: string;
  a_element_type?: string;
  b_element_type?: string;
  a_model_id: string;
  b_model_id: string;
  clash_type: string;
  penetration_m: number;
  distance_m: number;
  cx: number;
  cy: number;
  cz: number;
  status: string;
  assigned_to: string | null;
  bcf_topic_guid: string | null;
  /** Client-only: original ordinal within the loaded result set, assigned
   *  during the review-table filter pass for the # column / idx sort. */
  __idx?: number;
}

export interface ClashResultPage {
  items: ClashResult[];
  total: number;
  offset: number;
  limit: number;
}

/** One side of a Navisworks-style selection-set clash. A "set" is the
 *  union of the chosen element types and disciplines. */
export interface ClashSelectionSet {
  disciplines: string[];
  element_types: string[];
}

export interface ClashCategoryItem {
  value: string;
  count: number;
}

export interface ClashCategories {
  element_types: ClashCategoryItem[];
  disciplines: ClashCategoryItem[];
}

export interface ClashRunCreateBody {
  name?: string;
  model_ids: string[];
  tolerance_m: number;
  clearance_m: number;
  mode: string;
  discipline_filter?: string[][] | null;
  set_a?: ClashSelectionSet | null;
  set_b?: ClashSelectionSet | null;
}

export const clashApi = {
  models: (projectId: string) =>
    apiGet<ClashModelOption[]>(`/v1/clash/projects/${projectId}/models`),

  categories: (projectId: string, modelIds: string[]) => {
    const q = new URLSearchParams();
    modelIds.forEach((m) => q.append('model_ids', m));
    const qs = q.toString();
    return apiGet<ClashCategories>(
      `/v1/clash/projects/${projectId}/categories${qs ? `?${qs}` : ''}`,
    );
  },

  listRuns: (projectId: string) =>
    apiGet<ClashRunListItem[]>(`/v1/clash/projects/${projectId}/runs/`),

  createRun: (projectId: string, body: ClashRunCreateBody) =>
    apiPost<ClashRun, ClashRunCreateBody>(
      `/v1/clash/projects/${projectId}/runs/`,
      body,
    ),

  getRun: (projectId: string, runId: string) =>
    apiGet<ClashRun>(`/v1/clash/projects/${projectId}/runs/${runId}`),

  deleteRun: (projectId: string, runId: string) =>
    apiDelete(`/v1/clash/projects/${projectId}/runs/${runId}`),

  listResults: (
    projectId: string,
    runId: string,
    params: {
      status?: string;
      clash_type?: string;
      discipline?: string;
      offset?: number;
      limit?: number;
    } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.status) q.set('status', params.status);
    if (params.clash_type) q.set('clash_type', params.clash_type);
    if (params.discipline) q.set('discipline', params.discipline);
    q.set('offset', String(params.offset ?? 0));
    q.set('limit', String(params.limit ?? 100));
    return apiGet<ClashResultPage>(
      `/v1/clash/projects/${projectId}/runs/${runId}/results?${q.toString()}`,
    );
  },

  /**
   * Page the results endpoint at the backend maximum (500 rows/request)
   * until `min(total, cap)` rows are loaded, the server returns a short
   * page, or the abort signal fires. Returns the accumulated rows plus the
   * server-reported full `total` so callers can show "first N of M".
   *
   * The backend enforces `limit ∈ [1, 500]` — never request more than
   * `SERVER_PAGE` per call.
   */
  loadAllResults: async (
    projectId: string,
    runId: string,
    opts: { cap?: number; signal?: AbortSignal } = {},
  ): Promise<{ items: ClashResult[]; total: number; capped: boolean }> => {
    const SERVER_PAGE = 500;
    const cap = opts.cap ?? 2000;
    const items: ClashResult[] = [];
    let total = 0;
    let offset = 0;
    // First page also gives us the authoritative `total`.
    // Loop: stop when we hit the cap, exhaust `total`, or get a short page.
    for (;;) {
      if (opts.signal?.aborted) {
        throw new DOMException('Aborted', 'AbortError');
      }
      const remaining = cap - items.length;
      if (remaining <= 0) break;
      const pageLimit = Math.min(SERVER_PAGE, remaining);
      const q = new URLSearchParams();
      q.set('offset', String(offset));
      q.set('limit', String(pageLimit));
      const page = await apiGet<ClashResultPage>(
        `/v1/clash/projects/${projectId}/runs/${runId}/results?${q.toString()}`,
        { signal: opts.signal },
      );
      total = page.total;
      items.push(...page.items);
      offset += page.items.length;
      // Short page (server has no more rows) or we've reached the total.
      if (page.items.length < pageLimit) break;
      if (offset >= total) break;
    }
    return { items, total, capped: items.length < total };
  },

  updateResult: (
    projectId: string,
    runId: string,
    resultId: string,
    body: { status?: string; assigned_to?: string | null },
  ) =>
    apiPatch<ClashResult>(
      `/v1/clash/projects/${projectId}/runs/${runId}/results/${resultId}`,
      body,
    ),

  exportBcf: (
    projectId: string,
    runId: string,
    body: { result_ids?: string[] | null },
  ) =>
    apiPost<{ exported: number; skipped: number }>(
      `/v1/clash/projects/${projectId}/runs/${runId}/export-bcf`,
      body,
    ),
};
