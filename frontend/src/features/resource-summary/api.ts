// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Typed client for the Resource Summary module (/api/v1/resource-summary).
//
// The endpoint rolls every position's stored resource split up into one
// procurement statement. Money and quantities arrive as Decimal strings (the
// backend never routes a precision-critical figure through a float); the UI
// formats them for display but never does arithmetic on them.

import { API_BASE, apiGet, apiPost, getAuthToken, triggerDownload } from '@/shared/lib/api';

// ── Wire types ────────────────────────────────────────────────────────────────

export interface ResourceStatementLine {
  kind: string;
  /** Stable i18n key for the category label, e.g. price_breakdown.kind.material. */
  kind_i18n_key: string;
  name: string;
  unit: string;
  /** Total procurement quantity across the estimate (Decimal string, 4dp). */
  quantity: string;
  /** Total cost across the estimate (Decimal string, 2dp). */
  cost: string;
  /** How many positions demand this resource. */
  position_count: number;
}

export interface ResourceStatementGroup {
  kind: string;
  kind_i18n_key: string;
  label: string;
  line_count: number;
  total_cost: string;
  /** Labour only: total hours across the estimate (Decimal string). Null otherwise. */
  total_hours: string | null;
  lines: ResourceStatementLine[];
}

export interface ResourceStatementResponse {
  project_id: string;
  generated_at: string;
  currency: string;
  labor_hours: string;
  total_cost: string;
  line_count: number;
  position_count: number;
  groups: ResourceStatementGroup[];
}

export interface ResourceSnapshotSummary {
  id: string;
  generated_at: string;
  currency: string;
  total_cost: string;
  line_count: number;
}

// ── Calls ─────────────────────────────────────────────────────────────────────

const BASE = '/v1/resource-summary';

/** Fetch the aggregated procurement statement for a project. */
export function getResourceStatement(projectId: string): Promise<ResourceStatementResponse> {
  return apiGet<ResourceStatementResponse>(`${BASE}/projects/${encodeURIComponent(projectId)}`);
}

/** Freeze the current statement as a stored snapshot (manager permission). */
export function saveResourceSnapshot(projectId: string): Promise<ResourceSnapshotSummary> {
  return apiPost<ResourceSnapshotSummary>(`${BASE}/projects/${encodeURIComponent(projectId)}/snapshots`, {});
}

/** List a project's saved statements, most recent first. */
export function listResourceSnapshots(projectId: string): Promise<ResourceSnapshotSummary[]> {
  return apiGet<ResourceSnapshotSummary[]>(`${BASE}/projects/${encodeURIComponent(projectId)}/snapshots`);
}

/**
 * Download the procurement statement as CSV.
 *
 * The endpoint is JWT-Bearer-only (resource_summary.read), so a plain anchor
 * would navigate without the Authorization header and return 401. We fetch it
 * with the token, then hand the blob to triggerDownload.
 */
export async function downloadResourceStatementCsv(projectId: string): Promise<void> {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}${BASE}/projects/${encodeURIComponent(projectId)}/csv`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`Export failed (${response.status})`);
  }
  const blob = await response.blob();
  triggerDownload(blob, resourceStatementCsvName(projectId));
}

// ── Pure helpers (unit-tested) ─────────────────────────────────────────────────

/** Deterministic download filename for a project's procurement statement CSV. */
export function resourceStatementCsvName(projectId: string): string {
  const safe = String(projectId || 'project').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 12) || 'project';
  return `resource-statement-${safe}.csv`;
}

/** True when a statement carries no aggregated lines (nothing to procure yet). */
export function isEmptyStatement(statement: Pick<ResourceStatementResponse, 'groups'> | null | undefined): boolean {
  if (!statement || !Array.isArray(statement.groups)) return true;
  return statement.groups.every((group) => !group.lines || group.lines.length === 0);
}

/**
 * A currency the MoneyDisplay can format, or undefined when the estimate has no
 * currency set yet (MoneyDisplay then surfaces the gap rather than guessing).
 */
export function statementCurrency(
  statement: Pick<ResourceStatementResponse, 'currency'> | null | undefined,
): string | undefined {
  const code = statement?.currency?.trim();
  return code ? code : undefined;
}

/** Accent class per canonical resource kind, with a neutral default for unknowns. */
export function kindAccentClass(kind: string): string {
  switch (kind) {
    case 'labor':
      return 'text-oe-blue';
    case 'material':
      return 'text-semantic-success';
    case 'machinery':
      return 'text-semantic-warning';
    case 'equipment':
      return 'text-content-secondary';
    case 'subcontractor':
      return 'text-oe-blue';
    default:
      return 'text-content-tertiary';
  }
}
