/**
 * API helpers for the Coordination Hub dashboard.
 *
 * Endpoints (mounted at /api/v1/coordination):
 *   GET /v1/coordination/projects/{pid}/dashboard
 *   GET /v1/coordination/projects/{pid}/trade-matrix
 *   GET /v1/coordination/projects/{pid}/timeline?days=N
 */

import { apiGet } from '@/shared/lib/api';
import type {
  CoordinationDashboard,
  CoordinationTimelineResponse,
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
