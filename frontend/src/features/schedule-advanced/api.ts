/**
 * API helpers for the Schedule Advanced (Last Planner / CPM) module.
 *
 * Backed by /api/v1/schedule-advanced/ — see
 * backend/app/modules/schedule_advanced/router.py
 */

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type MasterStatus = 'active' | 'archived';
export type PhaseStatus = 'in_planning' | 'pulled' | 'active' | 'completed';
export type LookAheadStatus = 'draft' | 'reviewed' | 'published';
export type ConstraintType =
  | 'info'
  | 'material'
  | 'labor'
  | 'equipment'
  | 'permit'
  | 'predecessor'
  | 'weather'
  | 'other';
export type ConstraintStatus =
  | 'open'
  | 'in_progress'
  | 'cleared'
  | 'escalated'
  | 'cannot_clear';
export type CommitmentStatus =
  | 'planned'
  | 'committed'
  | 'in_progress'
  | 'completed'
  | 'at_risk'
  | 'missed';
export type WeeklyStatus = 'draft' | 'committed' | 'in_progress' | 'closed';
export type BaselineStatus = 'active' | 'superseded' | 'archived';
export type RNCCategory =
  | 'manpower'
  | 'material'
  | 'equipment'
  | 'info'
  | 'weather'
  | 'predecessor'
  | 'changes'
  | 'quality'
  | 'other';

export interface MasterSchedule {
  id: string;
  project_id: string;
  name: string;
  baseline_date?: string | null;
  planned_start?: string | null;
  planned_finish?: string | null;
  status: MasterStatus;
  notes: string;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PhasePlan {
  id: string;
  master_schedule_id: string;
  name: string;
  planned_start?: string | null;
  planned_finish?: string | null;
  milestone_target_id?: string | null;
  pulled_status: PhaseStatus;
  pull_session_at?: string | null;
  facilitator_id?: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface LookAheadPlan {
  id: string;
  master_schedule_id: string;
  period_start: string;
  period_end: string;
  window_weeks: number;
  generated_at?: string | null;
  status: LookAheadStatus;
  created_at: string;
  updated_at: string;
}

export interface Constraint {
  id: string;
  look_ahead_id?: string | null;
  task_ref: string;
  constraint_type: ConstraintType;
  description: string;
  owner_user_id?: string | null;
  target_clear_date?: string | null;
  cleared_at?: string | null;
  cleared_by?: string | null;
  status: ConstraintStatus;
  created_at: string;
  updated_at: string;
}

export interface WeeklyWorkPlan {
  id: string;
  master_schedule_id: string;
  week_start_date: string;
  week_end_date: string;
  generated_at?: string | null;
  facilitator_id?: string | null;
  status: WeeklyStatus;
  ppc_percent?: string | number | null;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface Commitment {
  id: string;
  week_plan_id: string;
  task_ref: string;
  worker_or_crew: string;
  promised_qty: string | number;
  unit: string;
  planned_start?: string | null;
  planned_finish?: string | null;
  status: CommitmentStatus;
  made_by_user_id?: string | null;
  made_at?: string | null;
  completed_at?: string | null;
  actual_qty?: string | number | null;
  created_at: string;
  updated_at: string;
}

export interface RNC {
  id: string;
  commitment_id: string;
  category: RNCCategory;
  description: string;
  recorded_at?: string | null;
  recorded_by?: string | null;
  root_cause_notes: string;
  created_at: string;
  updated_at: string;
}

export interface Baseline {
  id: string;
  master_schedule_id: string;
  name: string;
  captured_at?: string | null;
  captured_by?: string | null;
  snapshot: Record<string, unknown> | Array<Record<string, unknown>>;
  notes: string;
  status: BaselineStatus;
  created_at: string;
  updated_at: string;
}

export interface BaselineDeltaEntry {
  task_ref: string;
  planned_start_baseline?: string | null;
  planned_start_current?: string | null;
  planned_finish_baseline?: string | null;
  planned_finish_current?: string | null;
  schedule_variance_days: number;
}

export interface BaselineDelta {
  baseline_id: string;
  current_master_id: string;
  entries: BaselineDeltaEntry[];
  total_tasks: number;
  delayed_tasks: number;
  accelerated_tasks: number;
}

export interface ScheduleCalendar {
  id: string;
  project_id: string;
  name: string;
  work_days: number[];
  work_hours_per_day: string | number;
  holidays: string[];
  special_shifts: Record<string, unknown>;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface PPC {
  week_start_date?: string | null;
  total_commitments: number;
  completed_commitments: number;
  ppc_percent: string | number;
}

export interface LPSDashboard {
  project_id: string;
  ppc_trend: PPC[];
  open_constraints: number;
  constraints_by_type: Record<string, number>;
  rnc_pareto: Record<string, number>;
  active_master_schedules: number;
  active_baselines: number;
  current_week_commitments: number;
}

/* ── Master schedules ─────────────────────────────────────────────────── */

export function listMasterSchedules(params: {
  project_id: string;
  status?: string;
  limit?: number;
}): Promise<MasterSchedule[]> {
  const qs = new URLSearchParams();
  qs.set('project_id', params.project_id);
  if (params.status) qs.set('status', params.status);
  if (params.limit !== undefined) qs.set('limit', String(params.limit));
  return apiGet<MasterSchedule[]>(
    `/v1/schedule-advanced/master-schedules/?${qs.toString()}`,
  );
}

export function createMasterSchedule(data: {
  project_id: string;
  name: string;
  planned_start?: string;
  planned_finish?: string;
  notes?: string;
}): Promise<MasterSchedule> {
  return apiPost<MasterSchedule>(
    '/v1/schedule-advanced/master-schedules/',
    data,
  );
}

export function updateMasterSchedule(
  masterId: string,
  data: {
    name?: string;
    planned_start?: string | null;
    planned_finish?: string | null;
    baseline_date?: string | null;
    status?: MasterStatus;
    notes?: string | null;
  },
): Promise<MasterSchedule> {
  return apiPatch<MasterSchedule>(
    `/v1/schedule-advanced/master-schedules/${masterId}`,
    data,
  );
}

export function deleteMasterSchedule(masterId: string): Promise<void> {
  return apiDelete(`/v1/schedule-advanced/master-schedules/${masterId}`);
}

export function projectDashboard(projectId: string): Promise<LPSDashboard> {
  return apiGet<LPSDashboard>(
    `/v1/schedule-advanced/dashboard/project/${projectId}`,
  );
}

/* ── Phase plans ──────────────────────────────────────────────────────── */

export function listPhasePlans(masterScheduleId: string): Promise<PhasePlan[]> {
  return apiGet<PhasePlan[]>(
    `/v1/schedule-advanced/phase-plans/?master_schedule_id=${encodeURIComponent(
      masterScheduleId,
    )}`,
  );
}

export function createPhasePlan(data: {
  master_schedule_id: string;
  name: string;
  planned_start?: string;
  planned_finish?: string;
  notes?: string;
  pulled_status?: PhaseStatus;
}): Promise<PhasePlan> {
  return apiPost<PhasePlan>('/v1/schedule-advanced/phase-plans/', data);
}

export function updatePhasePlan(
  phaseId: string,
  data: {
    name?: string;
    planned_start?: string | null;
    planned_finish?: string | null;
    notes?: string | null;
  },
): Promise<PhasePlan> {
  return apiPatch<PhasePlan>(
    `/v1/schedule-advanced/phase-plans/${phaseId}`,
    data,
  );
}

export function deletePhasePlan(phaseId: string): Promise<void> {
  return apiDelete(`/v1/schedule-advanced/phase-plans/${phaseId}`);
}

/**
 * Standard construction-phase templates. Day-counts are conservative
 * defaults — users edit each phase after seeding.
 */
export const PHASE_TEMPLATES: Record<
  'residential' | 'commercial' | 'infrastructure',
  { name: string; days: number }[]
> = {
  residential: [
    { name: 'Site preparation', days: 14 },
    { name: 'Foundation', days: 28 },
    { name: 'Structure', days: 56 },
    { name: 'Roofing', days: 14 },
    { name: 'MEP rough-in', days: 35 },
    { name: 'Drywall and finishes', days: 42 },
    { name: 'Handover', days: 7 },
  ],
  commercial: [
    { name: 'Demolition', days: 14 },
    { name: 'Site preparation', days: 21 },
    { name: 'Foundation', days: 42 },
    { name: 'Structure', days: 90 },
    { name: 'Building envelope', days: 35 },
    { name: 'MEP rough-in', days: 56 },
    { name: 'Interior fit-out', days: 70 },
    { name: 'Commissioning', days: 21 },
    { name: 'Handover', days: 7 },
  ],
  infrastructure: [
    { name: 'Site survey and clearing', days: 21 },
    { name: 'Earthworks', days: 56 },
    { name: 'Subgrade and drainage', days: 42 },
    { name: 'Base layers', days: 28 },
    { name: 'Surfacing', days: 21 },
    { name: 'Signage and markings', days: 14 },
    { name: 'Final inspection', days: 7 },
  ],
};

/**
 * Seed the standard construction phases for a master schedule in one call.
 * Used by the "Apply template" affordance on the Phase Plans tab.
 */
export async function applyPhaseTemplate(
  masterScheduleId: string,
  template: keyof typeof PHASE_TEMPLATES,
  planStart?: string,
): Promise<PhasePlan[]> {
  const phases = PHASE_TEMPLATES[template];
  const startBase = planStart ? new Date(planStart) : new Date();
  const created: PhasePlan[] = [];
  let cursor = new Date(startBase);
  for (const p of phases) {
    const phaseStart = new Date(cursor);
    const phaseEnd = new Date(cursor);
    phaseEnd.setDate(phaseEnd.getDate() + p.days);
    const c = await createPhasePlan({
      master_schedule_id: masterScheduleId,
      name: p.name,
      planned_start: phaseStart.toISOString().slice(0, 10),
      planned_finish: phaseEnd.toISOString().slice(0, 10),
    });
    created.push(c);
    cursor = phaseEnd;
  }
  return created;
}

export function pullPhase(phaseId: string): Promise<PhasePlan> {
  return apiPost<PhasePlan>(
    `/v1/schedule-advanced/phase-plans/${phaseId}/pull`,
    {},
  );
}

export function startPhase(phaseId: string): Promise<PhasePlan> {
  return apiPost<PhasePlan>(
    `/v1/schedule-advanced/phase-plans/${phaseId}/start`,
    {},
  );
}

export function completePhase(phaseId: string): Promise<PhasePlan> {
  return apiPost<PhasePlan>(
    `/v1/schedule-advanced/phase-plans/${phaseId}/complete`,
    {},
  );
}

/* ── Look-aheads ──────────────────────────────────────────────────────── */

export function listLookAheads(
  masterScheduleId: string,
): Promise<LookAheadPlan[]> {
  return apiGet<LookAheadPlan[]>(
    `/v1/schedule-advanced/look-aheads/?master_schedule_id=${encodeURIComponent(
      masterScheduleId,
    )}`,
  );
}

export function createLookAhead(data: {
  master_schedule_id: string;
  period_start: string;
  period_end: string;
  window_weeks?: number;
}): Promise<LookAheadPlan> {
  return apiPost<LookAheadPlan>('/v1/schedule-advanced/look-aheads/', data);
}

export function publishLookAhead(lookAheadId: string): Promise<LookAheadPlan> {
  return apiPost<LookAheadPlan>(
    `/v1/schedule-advanced/look-aheads/${lookAheadId}/publish`,
    {},
  );
}

/* ── Constraints ──────────────────────────────────────────────────────── */

export function listConstraints(lookAheadId: string): Promise<Constraint[]> {
  return apiGet<Constraint[]>(
    `/v1/schedule-advanced/constraints/?look_ahead_id=${encodeURIComponent(
      lookAheadId,
    )}`,
  );
}

export function createConstraint(data: {
  look_ahead_id?: string;
  task_ref: string;
  constraint_type: ConstraintType;
  description?: string;
  target_clear_date?: string;
}): Promise<Constraint> {
  return apiPost<Constraint>('/v1/schedule-advanced/constraints/', data);
}

export function clearConstraint(id: string): Promise<Constraint> {
  return apiPost<Constraint>(
    `/v1/schedule-advanced/constraints/${id}/clear`,
    {},
  );
}

export function escalateConstraint(id: string): Promise<Constraint> {
  return apiPost<Constraint>(
    `/v1/schedule-advanced/constraints/${id}/escalate`,
    {},
  );
}

export function deleteConstraint(id: string): Promise<void> {
  return apiDelete(`/v1/schedule-advanced/constraints/${id}`);
}

/* ── Weekly work plans + commitments ──────────────────────────────────── */

export function listWeeklyPlans(
  masterScheduleId: string,
  limit = 52,
): Promise<WeeklyWorkPlan[]> {
  return apiGet<WeeklyWorkPlan[]>(
    `/v1/schedule-advanced/weekly-work-plans/?master_schedule_id=${encodeURIComponent(
      masterScheduleId,
    )}&limit=${limit}`,
  );
}

export function createWeeklyPlan(data: {
  master_schedule_id: string;
  week_start_date: string;
  week_end_date: string;
}): Promise<WeeklyWorkPlan> {
  return apiPost<WeeklyWorkPlan>(
    '/v1/schedule-advanced/weekly-work-plans/',
    data,
  );
}

export function commitWeeklyPlan(id: string): Promise<WeeklyWorkPlan> {
  return apiPost<WeeklyWorkPlan>(
    `/v1/schedule-advanced/weekly-work-plans/${id}/commit`,
    {},
  );
}

export function closeWeeklyPlan(id: string): Promise<WeeklyWorkPlan> {
  return apiPost<WeeklyWorkPlan>(
    `/v1/schedule-advanced/weekly-work-plans/${id}/close`,
    {},
  );
}

export function listCommitments(weekPlanId: string): Promise<Commitment[]> {
  return apiGet<Commitment[]>(
    `/v1/schedule-advanced/commitments/?week_plan_id=${encodeURIComponent(
      weekPlanId,
    )}`,
  );
}

export function createCommitment(data: {
  week_plan_id: string;
  task_ref: string;
  worker_or_crew?: string;
  promised_qty?: string;
  unit?: string;
}): Promise<Commitment> {
  return apiPost<Commitment>('/v1/schedule-advanced/commitments/', data);
}

export function commitCommitment(id: string): Promise<Commitment> {
  return apiPost<Commitment>(
    `/v1/schedule-advanced/commitments/${id}/commit`,
    {},
  );
}

export function completeCommitment(
  id: string,
  actualQty?: string,
): Promise<Commitment> {
  return apiPost<Commitment>(
    `/v1/schedule-advanced/commitments/${id}/complete`,
    actualQty != null && actualQty !== '' ? { actual_qty: actualQty } : {},
  );
}

/**
 * Mark a commitment missed. The backend requires a paired
 * Reason-for-Non-Completion (LPS RNC) so ``category`` is mandatory.
 */
export function missCommitment(
  id: string,
  rnc: { category: RNCCategory; description?: string; root_cause_notes?: string },
): Promise<Commitment> {
  return apiPost<Commitment>(
    `/v1/schedule-advanced/commitments/${id}/miss`,
    { commitment_id: id, ...rnc },
  );
}

/* ── Baselines ────────────────────────────────────────────────────────── */

export function listBaselines(masterScheduleId: string): Promise<Baseline[]> {
  return apiGet<Baseline[]>(
    `/v1/schedule-advanced/baselines/?master_schedule_id=${encodeURIComponent(
      masterScheduleId,
    )}`,
  );
}

export function captureBaseline(data: {
  master_schedule_id: string;
  name: string;
  notes?: string;
}): Promise<Baseline> {
  return apiPost<Baseline>('/v1/schedule-advanced/baselines/capture', {
    ...data,
    snapshot: {},
  });
}

export function baselineDelta(
  baselineId: string,
  currentTasks: Array<Record<string, unknown>> = [],
): Promise<BaselineDelta> {
  return apiPost<BaselineDelta>(
    `/v1/schedule-advanced/baselines/${baselineId}/delta`,
    currentTasks,
  );
}
