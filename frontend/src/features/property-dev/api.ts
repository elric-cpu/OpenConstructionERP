/**
 * API helpers for the Property Development module.
 *
 * Backed by /api/v1/property-dev/ — see backend/app/modules/property_dev/router.py
 */

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type DevelopmentSalesPhase = 'planning' | 'launch' | 'sales' | 'handover' | 'closed';
export type DevelopmentStatus = 'active' | 'paused' | 'completed';
export type PlotStatus =
  | 'planned'
  | 'reserved'
  | 'under_construction'
  | 'ready'
  | 'sold'
  | 'handed_over';
export type BuyerStatus =
  | 'lead'
  | 'reserved'
  | 'contracted'
  | 'completed'
  | 'cancelled';
export type SelectionStatus = 'draft' | 'submitted' | 'locked' | 'cancelled';
export type SnagSeverity = 'cosmetic' | 'minor' | 'major' | 'safety';
export type SnagStatus = 'open' | 'in_progress' | 'fixed' | 'wont_fix';
export type WarrantyStatus =
  | 'raised'
  | 'under_review'
  | 'accepted'
  | 'rejected'
  | 'closed';
export type WarrantyCategory = 'defect' | 'snag' | 'service';

export interface Development {
  id: string;
  project_id: string;
  code: string;
  name: string;
  location_address: string | null;
  total_plots: number;
  sales_phase: DevelopmentSalesPhase;
  launch_date: string | null;
  completion_date: string | null;
  marketing_brief: string | null;
  status: DevelopmentStatus;
  units: 'metric' | 'imperial';
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Plot {
  id: string;
  development_id: string;
  plot_number: string;
  house_type_id: string | null;
  house_type_variant_id: string | null;
  orientation: string | null;
  area_m2: number | string;
  garden_area_m2: number | string | null;
  price_base: number | string;
  currency: string;
  status: PlotStatus;
  reservation_deadline: string | null;
  construction_status_percent: number | string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface HouseType {
  id: string;
  development_id: string;
  code: string;
  name: string;
  bedrooms: number;
  bathrooms: number;
  total_area_m2: number | string;
  footprint_m2: number | string;
  levels: number;
  base_price: number | string;
  currency: string;
  bim_model_ref: string | null;
  thumbnail_url: string | null;
  description: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface HouseTypeVariant {
  id: string;
  house_type_id: string;
  code: string;
  name: string;
  modifier_pct: number | string;
  description: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Buyer {
  id: string;
  development_id: string;
  plot_id: string | null;
  portal_user_id: string | null;
  full_name: string;
  email: string;
  phone: string | null;
  language: string;
  status: BuyerStatus;
  contract_value: number | string;
  currency: string;
  contract_signed_at: string | null;
  deposit_paid_at: string | null;
  freeze_deadline: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface BuyerSelection {
  id: string;
  buyer_id: string;
  status: SelectionStatus;
  submitted_at: string | null;
  locked_at: string | null;
  total_options_value: number | string;
  notes: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface BuyerSelectionItem {
  id: string;
  selection_id: string;
  option_id: string;
  quantity: number;
  unit_price_snapshot: number | string;
  total_price: number | string;
  included_in_production: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Handover {
  id: string;
  plot_id: string;
  scheduled_at: string | null;
  completed_at: string | null;
  snag_count_at_handover: number;
  final_check_passed: boolean;
  keys_handed_over_at: string | null;
  customer_signature_ref: string | null;
  notes: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Snag {
  id: string;
  handover_id: string;
  location_in_plot: string | null;
  severity: SnagSeverity;
  description: string;
  status: SnagStatus;
  reported_at: string | null;
  fixed_at: string | null;
  fix_notes: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WarrantyClaim {
  id: string;
  plot_id: string;
  buyer_id: string;
  raised_at: string | null;
  category: WarrantyCategory;
  description: string;
  status: WarrantyStatus;
  accepted_at: string | null;
  closed_at: string | null;
  linked_service_ticket_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DevelopmentDashboard {
  development_id: string;
  total_plots: number;
  plots_by_status: Record<string, number>;
  buyers_by_status: Record<string, number>;
  contracted_value: number | string;
  open_snags: number;
  open_warranty_claims: number;
  completed_handovers: number;
  scheduled_handovers: number;
  sell_through_percent: number | string;
}

export interface CreateDevelopmentPayload {
  project_id: string;
  code: string;
  name?: string;
  location_address?: string;
  total_plots?: number;
  sales_phase?: DevelopmentSalesPhase;
}

export interface CreatePlotPayload {
  development_id: string;
  plot_number: string;
  house_type_id?: string;
  area_m2?: number;
  price_base?: number;
  currency?: string;
  status?: PlotStatus;
}

export interface CreateHouseTypePayload {
  development_id: string;
  code: string;
  name?: string;
  bedrooms?: number;
  bathrooms?: number;
  total_area_m2?: number;
  base_price?: number;
  currency?: string;
}

export interface CreateBuyerPayload {
  development_id: string;
  plot_id?: string;
  full_name?: string;
  email?: string;
  phone?: string;
  status?: BuyerStatus;
}

/**
 * Partial update payload for a buyer, mirroring the backend ``BuyerUpdate``
 * Pydantic schema. Every field is optional — only what's present in the
 * request body is mutated, and a ``status`` value is validated against the
 * FSM transition map (``allowedBuyerTransitions``) on the server before
 * the row is touched.
 */
export interface UpdateBuyerPayload {
  plot_id?: string | null;
  portal_user_id?: string | null;
  full_name?: string;
  email?: string;
  phone?: string | null;
  language?: string;
  status?: BuyerStatus;
  contract_value?: number | string;
  currency?: string;
  contract_signed_at?: string | null;
  deposit_paid_at?: string | null;
  freeze_deadline?: string | null;
  jurisdiction?: string;
  metadata?: Record<string, unknown>;
}

/**
 * Buyer status-transition map. Mirrors `_BUYER_TRANSITIONS` in
 * ``backend/app/modules/property_dev/service.py`` so the dropdown in
 * EditBuyerModal can render only the FSM-allowed next states. Server
 * remains the source of truth and rejects illegal transitions with 409.
 */
export const allowedBuyerTransitions: Record<BuyerStatus, BuyerStatus[]> = {
  lead: ['lead', 'reserved', 'cancelled'],
  reserved: ['reserved', 'contracted', 'cancelled', 'lead'],
  contracted: ['contracted', 'completed', 'cancelled'],
  completed: ['completed'],
  cancelled: ['cancelled'],
};

const BASE = '/v1/property-dev';

/* ── Developments ─────────────────────────────────────────────────────── */

export function listDevelopments(params?: {
  offset?: number;
  limit?: number;
}): Promise<Development[]> {
  const qs = new URLSearchParams();
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  const q = qs.toString();
  return apiGet<Development[]>(`${BASE}/developments/${q ? `?${q}` : ''}`);
}

export function createDevelopment(
  data: CreateDevelopmentPayload,
): Promise<Development> {
  return apiPost<Development>(`${BASE}/developments/`, data);
}

export function updateDevelopment(
  id: string,
  data: Partial<CreateDevelopmentPayload>,
): Promise<Development> {
  return apiPatch<Development>(`${BASE}/developments/${id}`, data);
}

export function deleteDevelopment(id: string): Promise<void> {
  return apiDelete(`${BASE}/developments/${id}`);
}

export function getDevelopmentDashboard(id: string): Promise<DevelopmentDashboard> {
  return apiGet<DevelopmentDashboard>(`${BASE}/developments/${id}/dashboard`);
}

/* ── Plots ────────────────────────────────────────────────────────────── */

export function listPlots(params: {
  development_id: string;
  status?: string;
  offset?: number;
  limit?: number;
}): Promise<Plot[]> {
  const qs = new URLSearchParams();
  qs.set('development_id', params.development_id);
  if (params.status) qs.set('status', params.status);
  if (params.offset !== undefined) qs.set('offset', String(params.offset));
  if (params.limit !== undefined) qs.set('limit', String(params.limit));
  return apiGet<Plot[]>(`${BASE}/plots/?${qs.toString()}`);
}

export function createPlot(data: CreatePlotPayload): Promise<Plot> {
  return apiPost<Plot>(`${BASE}/plots/`, data);
}

export function updatePlot(id: string, data: Partial<CreatePlotPayload>): Promise<Plot> {
  return apiPatch<Plot>(`${BASE}/plots/${id}`, data);
}

export function reservePlot(
  id: string,
  data: {
    full_name?: string;
    email?: string;
    phone?: string;
    language?: string;
    reservation_deadline?: string;
  },
): Promise<Plot> {
  return apiPost<Plot>(`${BASE}/plots/${id}/reserve`, data);
}

/* ── House Types & Variants ───────────────────────────────────────────── */

export function listHouseTypes(development_id: string): Promise<HouseType[]> {
  const qs = new URLSearchParams({ development_id });
  return apiGet<HouseType[]>(`${BASE}/house-types/?${qs.toString()}`);
}

export function createHouseType(data: CreateHouseTypePayload): Promise<HouseType> {
  return apiPost<HouseType>(`${BASE}/house-types/`, data);
}

export function listVariants(house_type_id: string): Promise<HouseTypeVariant[]> {
  const qs = new URLSearchParams({ house_type_id });
  return apiGet<HouseTypeVariant[]>(`${BASE}/house-type-variants/?${qs.toString()}`);
}

/* ── Buyers ───────────────────────────────────────────────────────────── */

export function listBuyers(params: {
  development_id: string;
  status?: string;
  offset?: number;
  limit?: number;
}): Promise<Buyer[]> {
  const qs = new URLSearchParams();
  qs.set('development_id', params.development_id);
  if (params.status) qs.set('status', params.status);
  if (params.offset !== undefined) qs.set('offset', String(params.offset));
  if (params.limit !== undefined) qs.set('limit', String(params.limit));
  return apiGet<Buyer[]>(`${BASE}/buyers/?${qs.toString()}`);
}

export function createBuyer(data: CreateBuyerPayload): Promise<Buyer> {
  return apiPost<Buyer>(`${BASE}/buyers/`, data);
}

export function contractBuyer(
  id: string,
  data: {
    contract_value: number;
    currency: string;
    contract_signed_at: string;
    deposit_paid_at?: string;
    freeze_deadline?: string;
  },
): Promise<Buyer> {
  return apiPost<Buyer>(`${BASE}/buyers/${id}/contract`, data);
}

/**
 * Partial-update a buyer (FSM-validated on the server).
 *
 * Calls ``PATCH /api/v1/property-dev/buyers/{id}`` with only the fields
 * the caller wants to change. Returns the updated buyer. The backend
 * raises HTTP 409 for illegal status transitions, 422 for validation
 * failures (bad currency, non-existent plot, …), and 403 if the caller
 * lacks ``property_dev.update`` — keep these as inline errors in the UI.
 */
export function updateBuyer(
  buyerId: string,
  payload: UpdateBuyerPayload,
): Promise<Buyer> {
  return apiPatch<Buyer>(`${BASE}/buyers/${buyerId}`, payload);
}

export function listJurisdictions(): Promise<string[]> {
  return apiGet<string[]>(`${BASE}/jurisdictions`);
}

/* ── Selections ───────────────────────────────────────────────────────── */

export function listSelections(buyer_id: string): Promise<BuyerSelection[]> {
  const qs = new URLSearchParams({ buyer_id });
  return apiGet<BuyerSelection[]>(`${BASE}/selections/?${qs.toString()}`);
}

/* ── Handovers ────────────────────────────────────────────────────────── */

export function listHandovers(plot_id: string): Promise<Handover[]> {
  const qs = new URLSearchParams({ plot_id });
  return apiGet<Handover[]>(`${BASE}/handovers/?${qs.toString()}`);
}

export function completeHandover(
  id: string,
  data: {
    completed_at: string;
    customer_signature_ref: string;
    keys_handed_over_at?: string;
    final_check_passed?: boolean;
    snag_count_at_handover?: number;
    notes?: string;
  },
): Promise<Handover> {
  return apiPost<Handover>(`${BASE}/handovers/${id}/complete`, data);
}

/* ── Snags ────────────────────────────────────────────────────────────── */

export function listSnags(params: {
  handover_id: string;
  status?: string;
}): Promise<Snag[]> {
  const qs = new URLSearchParams({ handover_id: params.handover_id });
  if (params.status) qs.set('status', params.status);
  return apiGet<Snag[]>(`${BASE}/snags/?${qs.toString()}`);
}

/* ── Warranty Claims ──────────────────────────────────────────────────── */

export function listWarrantyClaims(params: {
  buyer_id?: string;
  plot_id?: string;
  status?: string;
}): Promise<WarrantyClaim[]> {
  const qs = new URLSearchParams();
  if (params.buyer_id) qs.set('buyer_id', params.buyer_id);
  if (params.plot_id) qs.set('plot_id', params.plot_id);
  if (params.status) qs.set('status', params.status);
  return apiGet<WarrantyClaim[]>(`${BASE}/warranty-claims/?${qs.toString()}`);
}

export function createWarrantyClaim(data: {
  plot_id: string;
  buyer_id: string;
  description: string;
  category?: WarrantyCategory;
}): Promise<WarrantyClaim> {
  return apiPost<WarrantyClaim>(`${BASE}/warranty-claims/`, data);
}

export function acceptWarrantyClaim(id: string): Promise<WarrantyClaim> {
  return apiPost<WarrantyClaim>(`${BASE}/warranty/${id}/accept`, {});
}

export function rejectWarrantyClaim(id: string): Promise<WarrantyClaim> {
  return apiPost<WarrantyClaim>(`${BASE}/warranty/${id}/reject`, {});
}

export function closeWarrantyClaim(id: string): Promise<WarrantyClaim> {
  return apiPost<WarrantyClaim>(`${BASE}/warranty/${id}/close`, {});
}


/* ── R6: Lead / Reservation / SPA / PaymentSchedule / Instalment / ContractParty ── */

export type LeadSource =
  | 'web_form'
  | 'walk_in'
  | 'broker'
  | 'referral'
  | 'portal'
  | 'other';
export type LeadStatus =
  | 'new'
  | 'qualified'
  | 'viewing_scheduled'
  | 'visited'
  | 'quotation_sent'
  | 'negotiating'
  | 'converted'
  | 'lost'
  | 'disqualified';
export type ReservationStatus =
  | 'active'
  | 'expired'
  | 'converted'
  | 'cancelled'
  | 'refunded';
export type SpaStatus =
  | 'draft'
  | 'sent_for_signature'
  | 'partially_signed'
  | 'signed'
  | 'countersigned'
  | 'registered'
  | 'cancelled';
export type PaymentScheduleStatus =
  | 'active'
  | 'completed'
  | 'suspended'
  | 'cancelled';
export type InstalmentStatus =
  | 'pending'
  | 'due'
  | 'overdue'
  | 'paid'
  | 'waived'
  | 'cancelled';
export type ContractPartyRole =
  | 'primary'
  | 'co_owner'
  | 'guarantor'
  | 'power_of_attorney';

export interface Lead {
  id: string;
  development_id: string | null;
  tenant_id: string | null;
  source: LeadSource;
  lead_score: number | string;
  assigned_agent_user_id: string | null;
  status: LeadStatus;
  nurture_stage: string | null;
  full_name: string;
  email: string;
  phone: string | null;
  language: string;
  budget_min: number | string | null;
  budget_max: number | string | null;
  currency: string;
  preferred_house_type_id: string | null;
  notes: string | null;
  converted_to_buyer_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Reservation {
  id: string;
  plot_id: string;
  lead_id: string | null;
  buyer_id: string | null;
  tenant_id: string | null;
  reservation_number: string;
  deposit_amount: number | string;
  currency: string;
  deposit_paid_at: string | null;
  cooling_off_days: number;
  cooling_off_until: string | null;
  expires_at: string | null;
  status: ReservationStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SalesContract {
  id: string;
  contract_number: string;
  plot_id: string;
  reservation_id: string | null;
  tenant_id: string | null;
  signing_date: string | null;
  governing_law: string;
  language: string;
  total_price_breakdown: Record<string, unknown>;
  total_value: number | string;
  currency: string;
  e_sign_envelope_id: string | null;
  status: SpaStatus;
  parent_contract_id: string | null;
  revision_number: number;
  terms_version: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PaymentSchedule {
  id: string;
  sales_contract_id: string;
  tenant_id: string | null;
  currency: string;
  total_amount: number | string;
  late_fee_pct: number | string;
  grace_period_days: number;
  status: PaymentScheduleStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Instalment {
  id: string;
  schedule_id: string;
  sequence: number;
  milestone_label: string;
  milestone_event: string;
  due_date: string | null;
  amount: number | string;
  amount_paid: number | string;
  paid_at: string | null;
  status: InstalmentStatus;
  late_fee_accrued: number | string;
  invoice_ref: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ContractParty {
  id: string;
  sales_contract_id: string;
  buyer_id: string;
  ownership_pct: number | string;
  party_role: ContractPartyRole;
  signing_order: number;
  signed_at: string | null;
  signature_ref: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CreateLeadPayload {
  development_id?: string;
  source?: LeadSource;
  lead_score?: number | string;
  assigned_agent_user_id?: string;
  status?: LeadStatus;
  full_name?: string;
  email?: string;
  phone?: string;
  language?: string;
  budget_min?: number | string;
  budget_max?: number | string;
  currency?: string;
  preferred_house_type_id?: string;
  notes?: string;
}

export interface UpdateLeadPayload {
  source?: LeadSource;
  lead_score?: number | string;
  assigned_agent_user_id?: string;
  status?: LeadStatus;
  nurture_stage?: string;
  full_name?: string;
  email?: string;
  phone?: string | null;
  language?: string;
  budget_min?: number | string | null;
  budget_max?: number | string | null;
  currency?: string;
  notes?: string;
}

export interface LeadConvertToReservationPayload {
  plot_id: string;
  deposit_amount: number | string;
  currency: string;
  cooling_off_days?: number;
  expires_at?: string;
  create_buyer?: boolean;
}

export interface CreateReservationPayload {
  plot_id: string;
  lead_id?: string;
  buyer_id?: string;
  reservation_number?: string;
  deposit_amount: number | string;
  currency: string;
  cooling_off_days?: number;
  expires_at?: string;
}

export interface ConvertReservationToSpaPayload {
  contract_number?: string;
  signing_date: string;
  governing_law?: string;
  language?: string;
  total_value: number | string;
  currency: string;
  total_price_breakdown?: Record<string, unknown>;
  terms_version?: string;
}

export interface ContractPartyCreatePayload {
  sales_contract_id: string;
  buyer_id: string;
  ownership_pct: number | string;
  party_role?: ContractPartyRole;
  signing_order?: number;
  signature_ref?: string;
}

/**
 * FSM transition maps mirroring the backend service. Used by UI to
 * render only allowed next states. Server remains source-of-truth.
 */
export const allowedLeadTransitions: Record<LeadStatus, LeadStatus[]> = {
  new: ['new', 'qualified', 'lost', 'disqualified'],
  qualified: [
    'qualified',
    'viewing_scheduled',
    'quotation_sent',
    'negotiating',
    'lost',
    'disqualified',
  ],
  viewing_scheduled: ['viewing_scheduled', 'visited', 'lost', 'disqualified'],
  visited: [
    'visited',
    'quotation_sent',
    'negotiating',
    'converted',
    'lost',
    'disqualified',
  ],
  quotation_sent: ['quotation_sent', 'negotiating', 'converted', 'lost'],
  negotiating: ['negotiating', 'quotation_sent', 'converted', 'lost'],
  converted: ['converted'],
  lost: ['lost'],
  disqualified: ['disqualified'],
};

export const allowedSpaTransitions: Record<SpaStatus, SpaStatus[]> = {
  draft: ['draft', 'sent_for_signature', 'cancelled'],
  sent_for_signature: [
    'sent_for_signature',
    'partially_signed',
    'signed',
    'cancelled',
  ],
  partially_signed: ['partially_signed', 'signed', 'cancelled'],
  signed: ['signed', 'countersigned', 'cancelled'],
  countersigned: ['countersigned', 'registered', 'cancelled'],
  registered: ['registered'],
  cancelled: ['cancelled'],
};

/* ── Lead endpoints ────────────────────────────────────────────────── */

export function listLeads(params?: {
  development_id?: string;
  status?: LeadStatus;
  source?: LeadSource;
  assigned_agent_user_id?: string;
  offset?: number;
  limit?: number;
}): Promise<Lead[]> {
  const qs = new URLSearchParams();
  if (params?.development_id) qs.set('development_id', params.development_id);
  if (params?.status) qs.set('status', params.status);
  if (params?.source) qs.set('source', params.source);
  if (params?.assigned_agent_user_id)
    qs.set('assigned_agent_user_id', params.assigned_agent_user_id);
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  const q = qs.toString();
  return apiGet<Lead[]>(`${BASE}/leads/${q ? `?${q}` : ''}`);
}

export function createLead(data: CreateLeadPayload): Promise<Lead> {
  return apiPost<Lead>(`${BASE}/leads/`, data);
}

export function getLead(id: string): Promise<Lead> {
  return apiGet<Lead>(`${BASE}/leads/${id}`);
}

export function updateLead(id: string, data: UpdateLeadPayload): Promise<Lead> {
  return apiPatch<Lead>(`${BASE}/leads/${id}`, data);
}

export function deleteLead(id: string): Promise<void> {
  return apiDelete(`${BASE}/leads/${id}`);
}

export function convertLeadToReservation(
  id: string,
  data: LeadConvertToReservationPayload,
): Promise<Reservation> {
  return apiPost<Reservation>(
    `${BASE}/leads/${id}/convert-to-reservation`,
    data,
  );
}

/* ── Reservation endpoints ─────────────────────────────────────────── */

export function listReservations(params?: {
  plot_id?: string;
  development_id?: string;
  status?: ReservationStatus;
  offset?: number;
  limit?: number;
}): Promise<Reservation[]> {
  const qs = new URLSearchParams();
  if (params?.plot_id) qs.set('plot_id', params.plot_id);
  if (params?.development_id) qs.set('development_id', params.development_id);
  if (params?.status) qs.set('status', params.status);
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  const q = qs.toString();
  return apiGet<Reservation[]>(`${BASE}/reservations/${q ? `?${q}` : ''}`);
}

export function createReservation(
  data: CreateReservationPayload,
): Promise<Reservation> {
  return apiPost<Reservation>(`${BASE}/reservations/`, data);
}

export function getReservation(id: string): Promise<Reservation> {
  return apiGet<Reservation>(`${BASE}/reservations/${id}`);
}

export function cancelReservation(id: string): Promise<Reservation> {
  return apiPost<Reservation>(`${BASE}/reservations/${id}/cancel`, {});
}

export function expireReservation(id: string): Promise<Reservation> {
  return apiPost<Reservation>(`${BASE}/reservations/${id}/expire`, {});
}

export function expireOverdueReservations(): Promise<{
  expired_count: number;
  expired_ids: string[];
}> {
  return apiPost<{ expired_count: number; expired_ids: string[] }>(
    `${BASE}/reservations/expire-overdue`,
    {},
  );
}

export function convertReservationToSpa(
  id: string,
  data: ConvertReservationToSpaPayload,
): Promise<SalesContract> {
  return apiPost<SalesContract>(
    `${BASE}/reservations/${id}/convert-to-spa`,
    data,
  );
}

/* ── SalesContract (SPA) endpoints ────────────────────────────────── */

export function listSalesContracts(params: {
  plot_id: string;
  status?: SpaStatus;
}): Promise<SalesContract[]> {
  const qs = new URLSearchParams({ plot_id: params.plot_id });
  if (params.status) qs.set('status', params.status);
  return apiGet<SalesContract[]>(`${BASE}/sales-contracts/?${qs.toString()}`);
}

export function getSalesContract(id: string): Promise<SalesContract> {
  return apiGet<SalesContract>(`${BASE}/sales-contracts/${id}`);
}

export function sendSpaForSignature(
  id: string,
  data: { e_sign_envelope_id?: string } = {},
): Promise<SalesContract> {
  return apiPost<SalesContract>(
    `${BASE}/sales-contracts/${id}/send-for-signature`,
    data,
  );
}

export function signSalesContract(
  id: string,
  data: { signing_date?: string } = {},
): Promise<SalesContract> {
  return apiPost<SalesContract>(`${BASE}/sales-contracts/${id}/sign`, data);
}

export function cancelSalesContract(id: string): Promise<SalesContract> {
  return apiPost<SalesContract>(`${BASE}/sales-contracts/${id}/cancel`, {});
}

/* ── Tax / VAT / Stamp-duty quote ──────────────────────────────────── */

export interface TaxQuotePayload {
  jurisdiction?: string;
  region_subcode?: string;
  is_first_home?: boolean;
  is_additional_property?: boolean;
  vat_rate_class?: string;
  absd_buyer_profile?: string;
  emirate?: string;
  include_overdue?: boolean;
}

export interface TaxQuoteLine {
  line: string;
  amount: string;
}

export interface ContractTaxQuote {
  jurisdiction: string;
  region_subcode: string | null;
  currency: string;
  net: string;
  vat: string;
  stamp_duty: string;
  transfer_fee: string;
  registration_fee: string;
  absd: string;
  late_interest: string;
  subtotal_taxes: string;
  grand_total: string;
  breakdown: TaxQuoteLine[];
}

export function fetchContractTaxQuote(
  contractId: string,
  payload: TaxQuotePayload = {},
): Promise<ContractTaxQuote> {
  return apiPost<ContractTaxQuote>(
    `${BASE}/sales-contracts/${contractId}/tax-quote`,
    payload,
  );
}

/* ── Payment schedules + instalments ──────────────────────────────── */

export function getPaymentSchedule(id: string): Promise<PaymentSchedule> {
  return apiGet<PaymentSchedule>(`${BASE}/payment-schedules/${id}`);
}

export function activatePaymentSchedule(id: string): Promise<PaymentSchedule> {
  return apiPost<PaymentSchedule>(
    `${BASE}/payment-schedules/${id}/activate`,
    {},
  );
}

export function suspendPaymentSchedule(id: string): Promise<PaymentSchedule> {
  return apiPost<PaymentSchedule>(
    `${BASE}/payment-schedules/${id}/suspend`,
    {},
  );
}

export function listInstalments(params: {
  schedule_id?: string;
  sales_contract_id?: string;
  status?: InstalmentStatus;
}): Promise<Instalment[]> {
  const qs = new URLSearchParams();
  if (params.schedule_id) qs.set('schedule_id', params.schedule_id);
  if (params.sales_contract_id)
    qs.set('sales_contract_id', params.sales_contract_id);
  if (params.status) qs.set('status', params.status);
  return apiGet<Instalment[]>(`${BASE}/instalments/?${qs.toString()}`);
}

export function markInstalmentPaid(
  id: string,
  data: { amount: number | string; paid_at?: string; invoice_ref?: string },
): Promise<Instalment> {
  return apiPost<Instalment>(`${BASE}/instalments/${id}/mark-paid`, data);
}

export function issueInstalmentDemand(id: string): Promise<Instalment> {
  return apiPost<Instalment>(`${BASE}/instalments/${id}/issue-demand`, {});
}

export function waiveInstalment(
  id: string,
  data: { reason?: string } = {},
): Promise<Instalment> {
  return apiPost<Instalment>(`${BASE}/instalments/${id}/waive`, data);
}

export function accrueLateFees(): Promise<{
  touched_count: number;
  total_accrued: string;
}> {
  return apiPost<{ touched_count: number; total_accrued: string }>(
    `${BASE}/instalments/accrue-late-fees`,
    {},
  );
}

/* ── Contract parties (multi-buyer junction) ──────────────────────── */

export function listContractParties(
  sales_contract_id: string,
): Promise<ContractParty[]> {
  const qs = new URLSearchParams({ sales_contract_id });
  return apiGet<ContractParty[]>(`${BASE}/contract-parties/?${qs.toString()}`);
}

export function addContractParty(
  data: ContractPartyCreatePayload,
): Promise<ContractParty> {
  return apiPost<ContractParty>(`${BASE}/contract-parties/`, data);
}

export function updateContractParty(
  id: string,
  data: {
    ownership_pct?: number | string;
    party_role?: ContractPartyRole;
    signing_order?: number;
    signed_at?: string;
    signature_ref?: string;
  },
): Promise<ContractParty> {
  return apiPatch<ContractParty>(`${BASE}/contract-parties/${id}`, data);
}

export function removeContractParty(id: string): Promise<void> {
  return apiDelete(`${BASE}/contract-parties/${id}`);
}

/* ──────────────────────────────────────────────────────────────────────
 * Task #138 — Broker / Commission / Escrow / PriceMatrix / Phase / Block
 * Backed by backend/app/modules/property_dev/router.py
 * ──────────────────────────────────────────────────────────────────── */

export type KYCStatus = 'pending' | 'verified' | 'expired' | 'rejected';
export type CommissionState = 'accrued' | 'approved' | 'paid' | 'cancelled';
export type CommissionStructureType = 'flat' | 'percent' | 'ladder';
export type AccrualTrigger =
  | 'lead_qualified'
  | 'reservation_paid'
  | 'spa_signed'
  | 'handover_complete';
export type PayoutTerms = 'immediate' | 'net30' | 'net60' | 'per_milestone';
export type RegulatorRef =
  | 'rera_dubai'
  | 'rera_abu_dhabi'
  | 'maharera'
  | '214_FZ_RU'
  | 'cma_saudi'
  | 'section32_au'
  | 'other';
export type EscrowDirection = 'debit' | 'credit';
export type EscrowSourceType =
  | 'instalment'
  | 'refund'
  | 'draw_request'
  | 'bank_charge'
  | 'interest'
  | 'transfer';
export type ReconciliationState = 'unreconciled' | 'matched' | 'disputed';
export type PriceMatrixStatus = 'draft' | 'active' | 'expired' | 'archived';
export type PhaseStatus = 'planned' | 'under_construction' | 'completed';
export type BlockStatus = 'planned' | 'under_construction' | 'handed_over';

export interface Broker {
  id: string;
  tenant_id: string | null;
  name: string;
  license_number: string;
  jurisdiction: string;
  contact_email: string;
  contact_phone: string | null;
  default_commission_pct: string | number;
  kyc_status: KYCStatus;
  kyc_verified_at: string | null;
  active: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CommissionAgreement {
  id: string;
  broker_id: string;
  development_id: string | null;
  specific_plot_ids: string[] | null;
  structure_type: CommissionStructureType;
  structure: Record<string, unknown>;
  accrual_trigger: AccrualTrigger;
  payout_terms: PayoutTerms;
  withholding_tax_pct: string | number;
  currency: string;
  effective_from: string;
  effective_to: string | null;
  status: 'draft' | 'active' | 'expired' | 'cancelled';
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CommissionAccrual {
  id: string;
  agreement_id: string;
  broker_id: string;
  trigger_event: string;
  trigger_entity_type: string;
  trigger_entity_id: string | null;
  base_amount: string | number;
  commission_amount: string | number;
  currency: string;
  state: CommissionState;
  accrued_at: string | null;
  approved_at: string | null;
  paid_at: string | null;
  payment_ref: string | null;
  withholding_amount: string | number;
  net_payable: string | number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface EscrowAccount {
  id: string;
  development_id: string;
  regulator_ref: RegulatorRef;
  regulator_account_number: string;
  bank_name: string;
  iban: string;
  swift_bic: string;
  currency: string;
  opened_at: string;
  closed_at: string | null;
  is_active: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface EscrowBalance {
  escrow_account_id: string;
  currency: string;
  as_of_date: string | null;
  credit_total: string | number;
  debit_total: string | number;
  balance: string | number;
  transaction_count: number;
  unreconciled_count: number;
}

export interface EscrowTransaction {
  id: string;
  escrow_account_id: string;
  direction: EscrowDirection;
  amount: string | number;
  currency: string;
  source_type: EscrowSourceType;
  source_instalment_id: string | null;
  source_reference: string;
  bank_reference: string | null;
  transaction_date: string;
  reconciliation_state: ReconciliationState;
  reconciled_at: string | null;
  reconciled_by_user_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PriceMatrixRule {
  factor_type:
    | 'floor'
    | 'view'
    | 'orientation'
    | 'corner'
    | 'launch_discount'
    | 'phase_escalator';
  condition: Record<string, unknown>;
  multiplier: string | number;
}

export interface PriceMatrix {
  id: string;
  development_id: string;
  name: string;
  base_price_per_m2: string | number;
  currency: string;
  effective_from: string;
  effective_to: string | null;
  rules: PriceMatrixRule[];
  status: PriceMatrixStatus;
  version: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PriceMatrixPreview {
  plot_id: string;
  matrix_id: string | null;
  currency: string;
  base_price_per_m2: string | number;
  area_m2: string | number;
  base_price: string | number;
  applied_rules: Array<{
    factor_type: string;
    condition: Record<string, unknown>;
    multiplier: string;
  }>;
  combined_multiplier: string | number;
  final_price: string | number;
}

export interface Phase {
  id: string;
  development_id: string;
  code: string;
  name: string;
  sequence: number;
  planned_start: string | null;
  planned_end: string | null;
  status: PhaseStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Block {
  id: string;
  phase_id: string;
  code: string;
  name: string;
  levels_count: number;
  units_per_level: number;
  orientation: string | null;
  geo_coordinates: Record<string, unknown> | null;
  status: BlockStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RegulatorReport {
  development_id: string;
  regulator: 'RERA' | 'MAHARERA' | '214_FZ';
  quarter: string;
  generated_at: string;
  currency: string;
  summary: Record<string, unknown>;
  pdf_size_bytes: number;
  pdf_base64: string;
}

/* ── Brokers ──────────────────────────────────────────────────────── */

export function listBrokers(params?: {
  active_only?: boolean;
  jurisdiction?: string;
  offset?: number;
  limit?: number;
}): Promise<Broker[]> {
  const qs = new URLSearchParams();
  if (params?.active_only) qs.set('active_only', 'true');
  if (params?.jurisdiction) qs.set('jurisdiction', params.jurisdiction);
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  const q = qs.toString();
  return apiGet<Broker[]>(`${BASE}/brokers/${q ? `?${q}` : ''}`);
}

export function createBroker(data: {
  name: string;
  license_number: string;
  jurisdiction?: string;
  contact_email?: string;
  contact_phone?: string;
  default_commission_pct?: number;
}): Promise<Broker> {
  return apiPost<Broker>(`${BASE}/brokers/`, data);
}

export function getBroker(id: string): Promise<Broker> {
  return apiGet<Broker>(`${BASE}/brokers/${id}`);
}

export function updateBroker(
  id: string,
  data: Partial<Omit<Broker, 'id' | 'created_at' | 'updated_at'>>,
): Promise<Broker> {
  return apiPatch<Broker>(`${BASE}/brokers/${id}`, data);
}

export function verifyBrokerKyc(id: string): Promise<Broker> {
  return apiPost<Broker>(`${BASE}/brokers/${id}/verify-kyc`, {});
}

/* ── Commission Agreements ───────────────────────────────────────── */

export function listCommissionAgreements(params: {
  broker_id?: string;
  development_id?: string;
  on_date?: string;
}): Promise<CommissionAgreement[]> {
  const qs = new URLSearchParams();
  if (params.broker_id) qs.set('broker_id', params.broker_id);
  if (params.development_id) qs.set('development_id', params.development_id);
  if (params.on_date) qs.set('on_date', params.on_date);
  return apiGet<CommissionAgreement[]>(
    `${BASE}/commission-agreements/?${qs.toString()}`,
  );
}

export function createCommissionAgreement(data: {
  broker_id: string;
  structure_type: CommissionStructureType;
  structure: Record<string, unknown>;
  currency: string;
  effective_from: string;
  effective_to?: string;
  accrual_trigger?: AccrualTrigger;
  status?: string;
}): Promise<CommissionAgreement> {
  return apiPost<CommissionAgreement>(`${BASE}/commission-agreements/`, data);
}

/* ── Commission Accruals ─────────────────────────────────────────── */

export function listCommissionAccruals(params: {
  broker_id: string;
  state?: CommissionState;
}): Promise<CommissionAccrual[]> {
  const qs = new URLSearchParams({ broker_id: params.broker_id });
  if (params.state) qs.set('state', params.state);
  return apiGet<CommissionAccrual[]>(
    `${BASE}/commission-accruals/?${qs.toString()}`,
  );
}

export function approveCommissionAccrual(id: string): Promise<CommissionAccrual> {
  return apiPost<CommissionAccrual>(
    `${BASE}/commission-accruals/${id}/approve`,
    {},
  );
}

export function payCommissionAccrual(
  id: string,
  payment_ref: string,
): Promise<CommissionAccrual> {
  return apiPost<CommissionAccrual>(`${BASE}/commission-accruals/${id}/pay`, {
    payment_ref,
  });
}

/* ── Escrow Accounts + Transactions ──────────────────────────────── */

export function listEscrowAccounts(
  development_id: string,
): Promise<EscrowAccount[]> {
  const qs = new URLSearchParams({ development_id });
  return apiGet<EscrowAccount[]>(`${BASE}/escrow-accounts/?${qs.toString()}`);
}

export function createEscrowAccount(data: {
  development_id: string;
  regulator_ref: RegulatorRef;
  iban?: string;
  swift_bic?: string;
  bank_name?: string;
  regulator_account_number?: string;
  currency: string;
  opened_at: string;
}): Promise<EscrowAccount> {
  return apiPost<EscrowAccount>(`${BASE}/escrow-accounts/`, data);
}

export function getEscrowBalance(
  id: string,
  as_of_date?: string,
): Promise<EscrowBalance> {
  const qs = new URLSearchParams();
  if (as_of_date) qs.set('as_of_date', as_of_date);
  const q = qs.toString();
  return apiGet<EscrowBalance>(
    `${BASE}/escrow-accounts/${id}/balance${q ? `?${q}` : ''}`,
  );
}

export function listEscrowTransactions(params: {
  escrow_account_id: string;
  unreconciled_only?: boolean;
}): Promise<EscrowTransaction[]> {
  const qs = new URLSearchParams({ escrow_account_id: params.escrow_account_id });
  if (params.unreconciled_only) qs.set('unreconciled_only', 'true');
  return apiGet<EscrowTransaction[]>(
    `${BASE}/escrow-transactions/?${qs.toString()}`,
  );
}

export function createEscrowTransaction(data: {
  escrow_account_id: string;
  direction: EscrowDirection;
  amount: number | string;
  currency: string;
  source_type: EscrowSourceType;
  source_instalment_id?: string;
  source_reference?: string;
  transaction_date: string;
}): Promise<EscrowTransaction> {
  return apiPost<EscrowTransaction>(`${BASE}/escrow-transactions/`, data);
}

export function reconcileEscrowTransaction(
  id: string,
  bank_reference: string,
): Promise<EscrowTransaction> {
  return apiPost<EscrowTransaction>(
    `${BASE}/escrow-transactions/${id}/reconcile`,
    { bank_reference },
  );
}

/* ── Price Matrices ──────────────────────────────────────────────── */

export function listPriceMatrices(development_id: string): Promise<PriceMatrix[]> {
  const qs = new URLSearchParams({ development_id });
  return apiGet<PriceMatrix[]>(`${BASE}/price-matrices/?${qs.toString()}`);
}

export function createPriceMatrix(data: {
  development_id: string;
  name: string;
  base_price_per_m2: number | string;
  currency: string;
  effective_from: string;
  effective_to?: string;
  rules?: PriceMatrixRule[];
  status?: PriceMatrixStatus;
}): Promise<PriceMatrix> {
  return apiPost<PriceMatrix>(`${BASE}/price-matrices/`, data);
}

export function activatePriceMatrix(id: string): Promise<PriceMatrix> {
  return apiPost<PriceMatrix>(`${BASE}/price-matrices/${id}/activate`, {});
}

export function previewPriceOnPlot(
  matrix_id: string,
  plot_id: string,
  on_date?: string,
): Promise<PriceMatrixPreview> {
  const qs = new URLSearchParams();
  if (on_date) qs.set('on_date', on_date);
  const q = qs.toString();
  return apiGet<PriceMatrixPreview>(
    `${BASE}/price-matrices/${matrix_id}/preview-on-plot/${plot_id}${q ? `?${q}` : ''}`,
  );
}

export function bulkRecomputePrices(
  matrix_id: string,
): Promise<{ matrix_id: string; development_id: string; plots_updated: number; plots_unchanged: number }> {
  return apiPost(`${BASE}/price-matrices/${matrix_id}/bulk-recompute`, {});
}

/* ── Phases + Blocks ─────────────────────────────────────────────── */

export function listPhases(development_id: string): Promise<Phase[]> {
  const qs = new URLSearchParams({ development_id });
  return apiGet<Phase[]>(`${BASE}/phases/?${qs.toString()}`);
}

export function createPhase(data: {
  development_id: string;
  code: string;
  name?: string;
  sequence?: number;
  planned_start?: string;
  planned_end?: string;
}): Promise<Phase> {
  return apiPost<Phase>(`${BASE}/phases/`, data);
}

export function listBlocks(phase_id: string): Promise<Block[]> {
  const qs = new URLSearchParams({ phase_id });
  return apiGet<Block[]>(`${BASE}/blocks/?${qs.toString()}`);
}

export function createBlock(data: {
  phase_id: string;
  code: string;
  name?: string;
  levels_count?: number;
  units_per_level?: number;
  orientation?: string;
}): Promise<Block> {
  return apiPost<Block>(`${BASE}/blocks/`, data);
}

/* ── Regulator Reports ───────────────────────────────────────────── */

export function regulatorReportRERA(
  dev_id: string,
  quarter: string,
): Promise<RegulatorReport> {
  const qs = new URLSearchParams({ dev_id, quarter });
  return apiGet<RegulatorReport>(`${BASE}/regulator-reports/RERA?${qs.toString()}`);
}

export function regulatorReportMAHARERA(
  dev_id: string,
  quarter: string,
): Promise<RegulatorReport> {
  const qs = new URLSearchParams({ dev_id, quarter });
  return apiGet<RegulatorReport>(
    `${BASE}/regulator-reports/MAHARERA?${qs.toString()}`,
  );
}

export function regulatorReport214FZ(
  dev_id: string,
  quarter: string,
): Promise<RegulatorReport> {
  const qs = new URLSearchParams({ dev_id, quarter });
  return apiGet<RegulatorReport>(
    `${BASE}/regulator-reports/214-FZ?${qs.toString()}`,
  );
}
