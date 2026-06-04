/**
 * API helpers for Payroll.
 *
 * All endpoints are prefixed with /v1/payroll/ and are manager-scoped.
 * Money is returned as Decimal-as-string; the UI parses with Number(...)
 * only for display.
 */

import { apiGet, apiPatch, apiPost } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type PayrollStatus = 'draft' | 'approved';

export interface PayrollEntry {
  id: string;
  batch_id: string;
  resource_id: string | null;
  worker: string;
  work_date: string | null;
  hours: string;
  rate: string;
  amount: string;
  currency: string;
  source: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PayrollBatch {
  id: string;
  project_id: string;
  period_label: string;
  period_start: string | null;
  period_end: string | null;
  status: PayrollStatus;
  currency: string;
  total_hours: string;
  total_amount: string;
  entry_count: number;
  notes: string;
  created_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PayrollBatchDetail extends PayrollBatch {
  entries: PayrollEntry[];
}

export interface LabourCost {
  project_id: string;
  currency: string;
  labour_cost: string;
  total_hours: string;
}

export interface GenerateBatchPayload {
  date_from?: string | null;
  date_to?: string | null;
  period_label?: string | null;
  notes?: string;
}

/* ── API functions ─────────────────────────────────────────────────────── */

export async function fetchPayrollBatches(projectId: string): Promise<PayrollBatch[]> {
  if (!projectId) return [];
  const res = await apiGet<PayrollBatch[]>(
    `/v1/payroll/projects/${encodeURIComponent(projectId)}/batches/`,
  );
  return Array.isArray(res) ? res : [];
}

export async function fetchPayrollBatch(batchId: string): Promise<PayrollBatchDetail> {
  return apiGet<PayrollBatchDetail>(`/v1/payroll/batches/${encodeURIComponent(batchId)}`);
}

export async function generatePayrollBatch(
  projectId: string,
  payload: GenerateBatchPayload,
): Promise<PayrollBatchDetail> {
  return apiPost<PayrollBatchDetail, GenerateBatchPayload>(
    `/v1/payroll/projects/${encodeURIComponent(projectId)}/batches/`,
    payload,
  );
}

export async function fetchLabourCost(projectId: string): Promise<LabourCost | null> {
  if (!projectId) return null;
  return apiGet<LabourCost>(
    `/v1/payroll/projects/${encodeURIComponent(projectId)}/labour-cost/`,
  );
}

/**
 * Finalize (approve) a draft batch: transitions it to `approved` and posts its
 * labour cost to the project budget. Idempotent - calling twice on an
 * already-approved batch returns the unchanged batch.
 */
export async function finalizeBatch(batchId: string): Promise<PayrollBatchDetail> {
  return apiPatch<PayrollBatchDetail>(
    `/v1/payroll/batches/${encodeURIComponent(batchId)}/finalize/`,
  );
}
