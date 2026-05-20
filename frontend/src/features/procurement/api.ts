/**
 * Procurement API clients — typed wrappers over fetch.
 *
 * Wave 2 / T4 introduces two read endpoints (3-way match status + supplier
 * scorecard) that the procurement UI surfaces. The existing list / create
 * calls still live inline in `ProcurementPage.tsx`; this module is a
 * landing pad for the new clients and any future additions.‌⁠‍
 */

import { apiGet } from '@/shared/lib/api';

/* ── 3-way match status ───────────────────────────────────────────────── */

export type POLineMatchTag =
  | 'ok'
  | 'partial'
  | 'over_received'
  | 'over_invoiced'
  | 'unmatched';

export interface POLineMatchStatus {
  line_id: string;
  description: string;
  ordered_qty: string;
  received_qty: string;
  invoiced_qty: string;
  match_status: POLineMatchTag;
}

export interface POMatchStatusResponse {
  po_id: string;
  po_number: string;
  overall_status: POLineMatchTag;
  lines: POLineMatchStatus[];
}

export function getPOMatchStatus(poId: string): Promise<POMatchStatusResponse> {
  return apiGet<POMatchStatusResponse>(`/v1/procurement/${poId}/match-status/`);
}

/* ── Supplier scorecard ───────────────────────────────────────────────── */

export interface SupplierScorecardResponse {
  supplier_contact_id: string;
  supplier_name: string | null;
  project_id: string | null;
  period_days: number;
  total_po_count: number;
  total_po_value: string;
  currency: string;
  on_time_delivery_pct: number;
  qty_variance_pct: number;
  gr_rejection_rate: number;
  total_gr_count: number;
}

export function getSupplierScorecard(
  contactId: string,
  options: { projectId?: string; periodDays?: number } = {},
): Promise<SupplierScorecardResponse> {
  const params = new URLSearchParams();
  if (options.projectId) params.set('project_id', options.projectId);
  if (options.periodDays) params.set('period_days', String(options.periodDays));
  const qs = params.toString();
  const suffix = qs ? `?${qs}` : '';
  return apiGet<SupplierScorecardResponse>(
    `/v1/procurement/suppliers/${contactId}/scorecard/${suffix}`,
  );
}
