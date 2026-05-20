/**
 * API helpers + types for the HSE Advanced module.
 *
 * Endpoints are prefixed with /v1/hse-advanced/.
 */

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

/* -- Shared types --------------------------------------------------------- */

export type InvestigationStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled';
export type IncidentSeverity = 'minor' | 'moderate' | 'major' | 'severe' | 'critical';
export type PermitStatus = 'draft' | 'pending' | 'active' | 'expired' | 'closed' | 'cancelled';
export type CAPAStatus = 'open' | 'in_progress' | 'completed' | 'verified' | 'closed' | 'overdue';
export type AuditStatus = 'planned' | 'in_progress' | 'completed' | 'cancelled';
export type CertificationStatus = 'valid' | 'expiring' | 'expired';

/* -- Incident Investigation ----------------------------------------------- */

export interface FiveWhys {
  why1?: string;
  why2?: string;
  why3?: string;
  why4?: string;
  why5?: string;
}

export interface IncidentInvestigation {
  id: string;
  project_id: string;
  incident_id?: string | null;
  investigation_number: string;
  title: string;
  incident_date: string;
  severity: IncidentSeverity;
  status: InvestigationStatus;
  lead_investigator?: string | null;
  immediate_cause?: string | null;
  root_cause?: string | null;
  contributing_factors?: string[];
  five_whys?: FiveWhys | null;
  linked_capa_ids?: string[];
  created_at: string;
  updated_at: string;
}

/* -- Job Safety Analysis -------------------------------------------------- */

export interface JSAStep {
  id?: string;
  step_order: number;
  task: string;
  hazards: string;
  controls: string;
}

export interface JobSafetyAnalysis {
  id: string;
  project_id: string;
  jsa_number: string;
  title: string;
  task_description: string;
  location?: string | null;
  prepared_by?: string | null;
  approved_by?: string | null;
  approved_date?: string | null;
  steps: JSAStep[];
  created_at: string;
  updated_at: string;
}

/* -- Permit to Work ------------------------------------------------------- */

export interface PermitSignature {
  role: string;
  name: string;
  signed_at?: string | null;
}

export interface PermitToWork {
  id: string;
  project_id: string;
  permit_number: string;
  permit_type: string;
  title: string;
  scope: string;
  location?: string | null;
  hazards?: string[];
  controls?: string[];
  signatures?: PermitSignature[];
  issued_to?: string | null;
  issued_at?: string | null;
  expires_at?: string | null;
  status: PermitStatus;
  created_at: string;
  updated_at: string;
}

/* -- Toolbox Talk --------------------------------------------------------- */

export interface ToolboxAttendance {
  id?: string;
  worker_id?: string | null;
  worker_name: string;
  signed_at?: string | null;
}

export interface ToolboxTopic {
  id: string;
  title: string;
  description?: string | null;
  category?: string | null;
}

export interface ToolboxTalk {
  id: string;
  project_id: string;
  talk_number: string;
  title: string;
  topic_id?: string | null;
  topic_title?: string | null;
  presenter?: string | null;
  talk_date: string;
  duration_minutes?: number | null;
  location?: string | null;
  summary?: string | null;
  attendance: ToolboxAttendance[];
  created_at: string;
  updated_at: string;
}

/* -- PPE Issue ------------------------------------------------------------ */

export interface PPEIssue {
  id: string;
  project_id: string;
  ppe_number: string;
  item_type: string;
  item_description?: string | null;
  size?: string | null;
  quantity: number;
  issued_to_id?: string | null;
  issued_to_name: string;
  issued_at: string;
  return_by?: string | null;
  expires_at?: string | null;
  returned_at?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

/* -- Safety Audit & Findings --------------------------------------------- */

export type FindingSeverity = 'observation' | 'minor' | 'major' | 'critical';

export interface SafetyAuditFinding {
  id: string;
  audit_id: string;
  finding_number?: string | null;
  description: string;
  severity: FindingSeverity;
  area?: string | null;
  recommendation?: string | null;
  capa_id?: string | null;
}

export interface SafetyAudit {
  id: string;
  project_id: string;
  audit_number: string;
  title: string;
  audit_type?: string | null;
  auditor?: string | null;
  audit_date: string;
  scope?: string | null;
  status: AuditStatus;
  score?: number | null;
  findings_count?: number;
  findings?: SafetyAuditFinding[];
  created_at: string;
  updated_at: string;
}

/* -- Corrective Action (CAPA) -------------------------------------------- */

export interface CorrectiveAction {
  id: string;
  project_id: string;
  capa_number: string;
  title: string;
  description: string;
  source_type?: string | null;
  source_id?: string | null;
  assigned_to?: string | null;
  due_date?: string | null;
  closed_date?: string | null;
  status: CAPAStatus;
  effectiveness_check?: string | null;
  created_at: string;
  updated_at: string;
}

/* -- Safety Certification ------------------------------------------------- */

export interface SafetyCertification {
  id: string;
  project_id: string;
  cert_number: string;
  worker_id?: string | null;
  worker_name: string;
  certification_type: string;
  issuer?: string | null;
  issued_at: string;
  expires_at?: string | null;
  status: CertificationStatus;
  created_at: string;
  updated_at: string;
}

/* -- Endpoints ------------------------------------------------------------ */

const BASE = '/v1/hse-advanced';

export const fetchInvestigations = (projectId: string) =>
  apiGet<IncidentInvestigation[] | { items: IncidentInvestigation[] }>(
    `${BASE}/investigations/?project_id=${projectId}`,
  );

export const fetchInvestigation = (id: string) =>
  apiGet<IncidentInvestigation>(`${BASE}/investigations/${id}`);

export const createInvestigation = (
  payload: Partial<IncidentInvestigation> & { project_id: string; title: string },
) => apiPost<IncidentInvestigation>(`${BASE}/investigations/`, payload);

export const updateInvestigation = (id: string, payload: Partial<IncidentInvestigation>) =>
  apiPatch<IncidentInvestigation>(`${BASE}/investigations/${id}`, payload);

export const deleteInvestigation = (id: string) => apiDelete(`${BASE}/investigations/${id}`);

export const fetchJSAs = (projectId: string) =>
  apiGet<JobSafetyAnalysis[] | { items: JobSafetyAnalysis[] }>(
    `${BASE}/jsa/?project_id=${projectId}`,
  );

export const createJSA = (
  payload: Partial<JobSafetyAnalysis> & { project_id: string; title: string },
) => apiPost<JobSafetyAnalysis>(`${BASE}/jsa/`, payload);

export const fetchPermits = (projectId: string) =>
  apiGet<PermitToWork[] | { items: PermitToWork[] }>(`${BASE}/permits/?project_id=${projectId}`);

export const createPermit = (payload: Partial<PermitToWork> & { project_id: string; title: string }) =>
  apiPost<PermitToWork>(`${BASE}/permits/`, payload);

export const fetchToolboxTalks = (projectId: string) =>
  apiGet<ToolboxTalk[] | { items: ToolboxTalk[] }>(
    `${BASE}/toolbox-talks/?project_id=${projectId}`,
  );

export const createToolboxTalk = (
  payload: Partial<ToolboxTalk> & { project_id: string; title: string },
) => apiPost<ToolboxTalk>(`${BASE}/toolbox-talks/`, payload);

export const fetchToolboxTopics = () =>
  apiGet<ToolboxTopic[] | { items: ToolboxTopic[] }>(`${BASE}/toolbox-topics/`);

export const fetchPPEIssues = (projectId: string) =>
  apiGet<PPEIssue[] | { items: PPEIssue[] }>(`${BASE}/ppe-issues/?project_id=${projectId}`);

export const createPPEIssue = (
  payload: Partial<PPEIssue> & { project_id: string; issued_to_name: string; item_type: string },
) => apiPost<PPEIssue>(`${BASE}/ppe-issues/`, payload);

export const fetchAudits = (projectId: string) =>
  apiGet<SafetyAudit[] | { items: SafetyAudit[] }>(`${BASE}/audits/?project_id=${projectId}`);

export const createAudit = (payload: Partial<SafetyAudit> & { project_id: string; title: string }) =>
  apiPost<SafetyAudit>(`${BASE}/audits/`, payload);

export const fetchCAPAs = (projectId: string) =>
  apiGet<CorrectiveAction[] | { items: CorrectiveAction[] }>(
    `${BASE}/capas/?project_id=${projectId}`,
  );

export const createCAPA = (
  payload: Partial<CorrectiveAction> & { project_id: string; title: string; description: string },
) => apiPost<CorrectiveAction>(`${BASE}/capas/`, payload);

export const fetchCertifications = (projectId: string) =>
  apiGet<SafetyCertification[] | { items: SafetyCertification[] }>(
    `${BASE}/certifications/?project_id=${projectId}`,
  );

/* -- OSHA 300 CSV + slim corrective-action FSM (T6 / v3086) --------------- */

/** Strict FSM target states for the slim incident-scoped CorrectiveAction. */
export type CATargetStatus = 'pending' | 'in_progress' | 'verified' | 'closed';

export interface CATransitionRequest {
  to_status: CATargetStatus;
  verification_notes?: string;
}

export interface CorrectiveActionRow {
  id: string;
  incident_id: string;
  description: string;
  assigned_to_user_id?: string | null;
  due_date?: string | null;
  status: CATargetStatus;
  verified_by_user_id?: string | null;
  verified_at?: string | null;
  verification_notes?: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Trigger an OSHA Form 300 CSV download for a project + calendar year.
 *
 * The endpoint streams ``text/csv; charset=utf-8`` with a
 * ``Content-Disposition: attachment`` header, so we hand the URL to the
 * browser via a synthetic ``<a download>`` click rather than going
 * through ``apiGet``: that lets the browser show its own save dialog and
 * respect the server-supplied filename.
 */
export function downloadOsha300Csv(projectId: string, year: number): void {
  const url = `/api${BASE}/osha-300-log.csv?project_id=${encodeURIComponent(
    projectId,
  )}&year=${encodeURIComponent(String(year))}`;
  const a = document.createElement('a');
  a.href = url;
  a.rel = 'noopener';
  // Suggested filename — the server's Content-Disposition wins when the
  // browser honours it, but this keeps in-page text readable.
  a.download = `osha-300-${year}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export const fetchCorrectiveActions = (params: {
  projectId?: string;
  incidentId?: string;
  status?: CATargetStatus;
}) => {
  const qs = new URLSearchParams();
  if (params.projectId) qs.set('project_id', params.projectId);
  if (params.incidentId) qs.set('incident_id', params.incidentId);
  if (params.status) qs.set('status', params.status);
  return apiGet<CorrectiveActionRow[] | { items: CorrectiveActionRow[] }>(
    `${BASE}/corrective-actions/?${qs.toString()}`,
  );
};

export const transitionCorrectiveAction = (
  caId: string,
  body: CATransitionRequest,
) =>
  apiPost<CorrectiveActionRow>(
    `${BASE}/corrective-actions/${caId}/transition`,
    body,
  );

/* -- Helpers -------------------------------------------------------------- */

/** Days between today and a target date string (YYYY-MM-DD or ISO). Negative if past. */
export function daysUntil(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const target = new Date(dateStr);
  if (Number.isNaN(target.getTime())) return null;
  const now = new Date();
  const target0 = new Date(target.getFullYear(), target.getMonth(), target.getDate()).getTime();
  const today0 = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round((target0 - today0) / 86_400_000);
}
