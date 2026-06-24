// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// API client for the change-intelligence layer. These endpoints turn the many
// change-adjacent modules (change orders, variations, MoC, correspondence,
// approvals) into one read surface that answers three questions a project team
// keeps asking: what to act on first, who owes the next action and by when, and
// what the approved changes have committed in cost and schedule. Money is
// carried on the wire as a string (the Decimal rendered losslessly), so it is
// passed straight to MoneyDisplay and never coerced with toFixed here.

import { apiGet, apiPost } from '@/shared/lib/api';

const CI_BASE = '/v1/change-intelligence';
const CR_BASE = '/v1/cost-recovery';

// --- Action coordination ("what to act on first") --------------------------

export type Urgency = 'overdue' | 'due_soon' | 'upcoming' | 'no_date';

export interface CoordinationStep {
  ref_id: string;
  kind: string;
  title: string;
  ball_in_court: string;
  urgency: Urgency;
  days_to_due: number | null;
  recommended_action: string;
  reason: string;
  rank_score: number;
}

export interface CoordinationPlan {
  project_id: string;
  generated_at: string;
  total: number;
  overdue_count: number;
  due_soon_count: number;
  steps: CoordinationStep[];
}

export function getCoordinationPlan(projectId: string): Promise<CoordinationPlan> {
  return apiGet<CoordinationPlan>(`${CI_BASE}/projects/${projectId}/coordination`);
}

// --- Cycle time ("waiting on whom") ----------------------------------------

export interface PartyLoad {
  party: string;
  open_count: number;
  overdue_count: number;
  oldest_age_days: number;
  total_age_days: number;
  avg_age_days: number;
}

export interface ItemAging {
  id: string;
  kind: string;
  code: string;
  title: string;
  status: string;
  party: string;
  age_days: number;
  stale_days: number | null;
  response_due_date: string | null;
  overdue: boolean;
  days_to_due: number | null;
}

export interface CycleTimeBoard {
  project_id: string;
  as_of: string;
  total_open: number;
  total_overdue: number;
  unassigned_open: number;
  parties: PartyLoad[];
  items: ItemAging[];
}

export function getCycleTimeBoard(projectId: string): Promise<CycleTimeBoard> {
  return apiGet<CycleTimeBoard>(`${CI_BASE}/projects/${projectId}/cycle-time`);
}

// --- Approved-change impact (committed cost and schedule) ------------------

export interface KindImpact {
  kind: string;
  count: number;
  total_cost: string;
  total_days: number;
}

export interface CurrencyImpact {
  currency: string;
  total_cost: string;
  count: number;
}

export interface ImpactProjection {
  project_id: string;
  approved_count: number;
  total_schedule_delta_days: number;
  primary_currency: string;
  primary_currency_cost: string;
  by_kind: KindImpact[];
  by_currency: CurrencyImpact[];
}

export function getImpactProjection(projectId: string): Promise<ImpactProjection> {
  return apiGet<ImpactProjection>(`${CI_BASE}/projects/${projectId}/impact`);
}

// --- Correspondence digest ("who owes the next reply") ---------------------

export type Awaiting = 'us' | 'them' | 'none';

export interface ThreadDigest {
  thread_key: string;
  subject: string;
  message_count: number;
  participants: string[];
  first_at: string | null;
  last_at: string | null;
  last_direction: string;
  last_sender: string;
  awaiting: Awaiting;
  is_open: boolean;
}

export interface CommsDigest {
  project_id: string;
  generated_at: string;
  thread_count: number;
  open_count: number;
  awaiting_us_count: number;
  threads: ThreadDigest[];
}

export function getCommsDigest(projectId: string): Promise<CommsDigest> {
  return apiGet<CommsDigest>(`${CI_BASE}/projects/${projectId}/comms-digest`);
}

// --- Change-request clarifier co-pilot -------------------------------------

export interface ClarificationGap {
  field: string;
  question: string;
  severity: string;
}

export interface ClauseSuggestion {
  standard: string;
  clause_ref: string;
  rationale: string;
}

export interface ClarifiedRequest {
  title: string;
  normalized_summary: string;
  detected_classification: string;
  missing: ClarificationGap[];
  clause_suggestions: ClauseSuggestion[];
  suggested_route: string;
  completeness: number;
}

export function clarifyChangeNote(
  note: string,
  contractStandard = '',
): Promise<ClarifiedRequest> {
  return apiPost<ClarifiedRequest>(`${CI_BASE}/clarify`, {
    note,
    contract_standard: contractStandard,
  });
}

// --- Cost recovery / liability ---------------------------------------------

export interface BackCharge {
  id: string;
  project_id: string;
  source_ref: string;
  responsible_party: string;
  description: string;
  basis: string;
  gross_amount: string;
  chargeable_pct: string;
  chargeable_amount: string;
  currency: string;
  status: string;
  recovered_amount: string;
  outstanding: string;
  is_open: boolean;
  agreed_at: string | null;
  recovered_at: string | null;
}

export interface PartyRecovery {
  party: string;
  currency: string;
  item_count: number;
  open_count: number;
  gross_total: string;
  chargeable_total: string;
  recovered_total: string;
  outstanding_total: string;
}

export interface CurrencyRecovery {
  currency: string;
  item_count: number;
  chargeable_total: string;
  recovered_total: string;
  outstanding_total: string;
}

export interface RecoveryLedger {
  project_id: string;
  item_count: number;
  open_count: number;
  primary_currency: string;
  primary_outstanding: string;
  by_party: PartyRecovery[];
  by_currency: CurrencyRecovery[];
}

export function getRecoveryLedger(projectId: string): Promise<RecoveryLedger> {
  return apiGet<RecoveryLedger>(`${CR_BASE}/projects/${projectId}/recovery-ledger`);
}

export function listBackCharges(projectId: string): Promise<BackCharge[]> {
  return apiGet<BackCharge[]>(`${CR_BASE}/projects/${projectId}/back-charges`);
}
