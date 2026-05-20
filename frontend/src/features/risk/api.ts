/**
 * API helpers for the Risk Register module.
 *
 * Endpoints (mounted at /api/v1/risk):
 *   POST   /v1/risk/projects/{project_id}/simulate
 *     — Run a Monte Carlo (PERT) simulation across the project's risks.
 *
 * The result is also persisted on every risk row's ``last_simulation``
 * JSON column server-side so a page refresh keeps the drill-down.‌⁠‍
 */

import { apiPost } from '@/shared/lib/api';

/** Mode flag controlling which PERT triple(s) the simulator samples. */
export type RiskSimulateMode = 'cost' | 'schedule' | 'both';

/** POST body for ``/v1/risk/projects/{id}/simulate``. */
export interface RiskSimulateRequest {
  /** Number of Monte Carlo iterations. Backend clamps to [1000, 100000]. */
  iterations?: number;
  mode?: RiskSimulateMode;
}

/** One bin in the contingency histogram (10-bin equal-width by default). */
export interface RiskHistogramBin {
  lower: number;
  upper: number;
  count: number;
}

/** One bar in the tornado / sensitivity chart, sorted desc by contribution. */
export interface RiskTornadoEntry {
  risk_id: string;
  code: string;
  /** Mean probability-weighted contribution to the project contingency. */
  contribution: number;
}

/** Result of a Monte Carlo simulation, mirroring the backend Pydantic model. */
export interface RiskSimulationResult {
  iterations: number;
  risk_count: number;
  mode: RiskSimulateMode;
  p50_cost: number | null;
  p80_cost: number | null;
  p95_cost: number | null;
  p50_schedule_days: number | null;
  p80_schedule_days: number | null;
  p95_schedule_days: number | null;
  histogram_bins: RiskHistogramBin[];
  tornado: RiskTornadoEntry[];
  /** Project currency (data-driven; "" means unknown — render currency-less). */
  currency: string;
}

/**
 * Trigger a Monte Carlo simulation for ``projectId``.
 *
 * The backend permission required is ``risk.read`` (re-used from the
 * existing risk endpoints). Returns the full result snapshot — the
 * caller can render histogram + tornado directly without an extra
 * fetch.‌⁠‍
 */
export async function simulateRisk(
  projectId: string,
  body: RiskSimulateRequest = {},
): Promise<RiskSimulationResult> {
  const payload: RiskSimulateRequest = {
    iterations: body.iterations ?? 10000,
    mode: body.mode ?? 'both',
  };
  return apiPost<RiskSimulationResult, RiskSimulateRequest>(
    `/v1/risk/projects/${projectId}/simulate`,
    payload,
  );
}
