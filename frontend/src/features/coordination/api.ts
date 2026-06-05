/**
 * API helpers for the Coordination Hub dashboard.
 *
 * Endpoints (mounted at /api/v1/coordination):
 *   GET /v1/coordination/projects/{pid}/dashboard
 *   GET /v1/coordination/projects/{pid}/trade-matrix
 *   GET /v1/coordination/projects/{pid}/timeline?days=N
 *   GET /v1/coordination/projects/{pid}/thresholds
 *   PUT /v1/coordination/projects/{pid}/thresholds/{metric}
 */

import { apiGet, apiPut } from '@/shared/lib/api';
import type {
  CoordinationDashboard,
  CoordinationThresholdsResponse,
  CoordinationThresholdUpdate,
  CoordinationTimelineResponse,
  ThresholdRow,
  TradeMatrixResponse,
} from './types';

/** Fetch the Coordination Hub KPI rollup for one project. */
export function fetchCoordinationDashboard(
  projectId: string,
): Promise<CoordinationDashboard> {
  return apiGet<CoordinationDashboard>(
    `/v1/coordination/projects/${projectId}/dashboard`,
  );
}

/** Fetch the trade-matrix payload for the heat-map. */
export function fetchTradeMatrix(
  projectId: string,
): Promise<TradeMatrixResponse> {
  return apiGet<TradeMatrixResponse>(
    `/v1/coordination/projects/${projectId}/trade-matrix`,
  );
}

/** Fetch the activity timeline. */
export function fetchCoordinationTimeline(
  projectId: string,
  days = 30,
): Promise<CoordinationTimelineResponse> {
  return apiGet<CoordinationTimelineResponse>(
    `/v1/coordination/projects/${projectId}/timeline?days=${days}`,
  );
}

/**
 * Fetch the project's alert thresholds together with their current
 * evaluated state (`alerts[]` = the metrics currently in breach, error
 * rows first). Drives the health banner above the KPI cards. Requires
 * `coordination.read`.
 */
export function fetchCoordinationThresholds(
  projectId: string,
): Promise<CoordinationThresholdsResponse> {
  return apiGet<CoordinationThresholdsResponse>(
    `/v1/coordination/projects/${projectId}/thresholds`,
  );
}

/**
 * Patch one threshold's warn/error value or its `enabled` flag. Requires
 * `coordination.write`; the backend re-evaluates and returns the updated
 * row with `current_value` + `level` filled in.
 */
export function updateCoordinationThreshold(
  projectId: string,
  metric: string,
  body: CoordinationThresholdUpdate,
): Promise<ThresholdRow> {
  return apiPut<ThresholdRow, CoordinationThresholdUpdate>(
    `/v1/coordination/projects/${projectId}/thresholds/${encodeURIComponent(metric)}`,
    body,
  );
}
