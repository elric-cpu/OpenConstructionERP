// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * ‌⁠‍Change-orders feature API client.
 *
 * Thin wrappers around the backend's approval-chain endpoints. Each
 * function returns the typed payload so callers can drop straight into
 * `useQuery` / `useMutation` without re-typing the response shape.
 *
 * Endpoints
 * ---------
 * - POST  /v1/changeorders/{id}/approval-chain   — start a chain
 * - POST  /v1/changeorders/{id}/advance-approval — record a decision
 * - GET   /v1/changeorders/{id}/approvals        — list rows in step order
 */

import { apiGet, apiPost } from '@/shared/lib/api';

/** One row in a change order's approval chain (mirrors backend `ApprovalRow`). */
export interface ApprovalRow {
  id: string;
  change_order_id: string;
  step_order: number;
  /** ``null`` when the assigned user has been deleted (FK is SET NULL). */
  approver_user_id: string | null;
  /** ``pending`` | ``approved`` | ``rejected``. */
  decision: 'pending' | 'approved' | 'rejected';
  decided_at: string | null;
  comments: string | null;
  created_at: string;
}

/** Body for ``POST /v1/changeorders/{id}/approval-chain``. */
export interface ApprovalStartBody {
  approver_user_ids: string[];
}

/** Body for ``POST /v1/changeorders/{id}/advance-approval``. */
export interface ApprovalAdvanceBody {
  decision: 'approved' | 'rejected';
  comments?: string;
}

/** Start a Procore-style multi-step approval chain on a change order. */
export function startApprovalChain(
  changeOrderId: string,
  approverUserIds: string[],
): Promise<ApprovalRow[]> {
  return apiPost<ApprovalRow[], ApprovalStartBody>(
    `/v1/changeorders/${changeOrderId}/approval-chain`,
    { approver_user_ids: approverUserIds },
  );
}

/**
 * Record the calling user's decision on the active chain step.
 *
 * The caller must be the approver assigned to ``current_approval_step``;
 * any other user receives 403. A rejection short-circuits the chain
 * (the CO flips to ``rejected`` and downstream steps stay pending);
 * the final approval flips the CO to ``approved`` and triggers the
 * usual budget / BOQ writeback.
 */
export function advanceApproval(
  changeOrderId: string,
  body: ApprovalAdvanceBody,
): Promise<ApprovalRow> {
  return apiPost<ApprovalRow, ApprovalAdvanceBody>(
    `/v1/changeorders/${changeOrderId}/advance-approval`,
    body,
  );
}

/** List approval rows for a change order, ordered by ``step_order``. */
export function getApprovals(changeOrderId: string): Promise<ApprovalRow[]> {
  return apiGet<ApprovalRow[]>(
    `/v1/changeorders/${changeOrderId}/approvals`,
  );
}
