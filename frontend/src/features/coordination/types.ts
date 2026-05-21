/**
 * TypeScript types for the Coordination Hub dashboard.
 *
 * Mirror of the Pydantic schemas under
 * ``backend/app/modules/coordination_hub/schemas.py``. Kept hand-written
 * (rather than openapi-generated) because the dashboard is a presentation
 * surface — the wire shape is small, stable, and we want the inline JSDoc
 * for the editor tooltip.
 */

/** Per-category federation rollup. */
export interface FederationStats {
  count: number;
  total_members: number;
  total_elements: number;
}

/** Run-to-run movement for the open clash queue. */
export interface ClashDelta {
  new: number;
  resolved: number;
  reopened: number;
}

/** Clash rollup — open / resolved / ignored + last-run delta. */
export interface ClashStats {
  open_count: number;
  resolved_count: number;
  ignored_count: number;
  delta_since_last_run: ClashDelta;
  /** ISO-8601 — `null` until a run completes for this project. */
  last_run_at: string | null;
}

/** BIM requirement / rule-pack rollup. */
export interface RulePackStats {
  installed_count: number;
  last_check_pass_count: number;
  last_check_fail_count: number;
  last_check_at: string | null;
}

/** Smart-view inventory split by scope. */
export interface SmartViewStats {
  user_count: number;
  project_count: number;
}

/** BCF I/O activity over the last 30 days. */
export interface BCFActivityStats {
  topics_exported_30d: number;
  topics_imported_30d: number;
  last_export_at: string | null;
}

/** Full payload returned by `GET /coordination/projects/:id/dashboard`. */
export interface CoordinationDashboard {
  project_id: string;
  currency: string;
  /** ISO-8601 — server-side timestamp the rollup was assembled at. */
  as_of: string;
  federations: FederationStats;
  clashes: ClashStats;
  rule_packs: RulePackStats;
  smart_views: SmartViewStats;
  bcf_activity: BCFActivityStats;
  open_cost_impact_total: number;
}

/** Canonical 6-trade taxonomy. Matches `schemas.CANONICAL_TRADES`. */
export type CanonicalTrade =
  | 'arch'
  | 'struct'
  | 'mep'
  | 'landscape'
  | 'civil'
  | 'other';

/** One discipline-pair cell in the trade matrix. */
export interface TradeMatrixCell {
  row: CanonicalTrade;
  col: CanonicalTrade;
  count: number;
  open: number;
  resolved: number;
}

/** Full payload returned by `GET /coordination/projects/:id/trade-matrix`. */
export interface TradeMatrixResponse {
  project_id: string;
  trades: CanonicalTrade[];
  cells: TradeMatrixCell[];
}

/** One activity-stream entry. */
export interface CoordinationTimelineEvent {
  /** ISO-8601. */
  ts: string;
  /** Discriminant — drives the icon + summary template. */
  type:
    | 'clash_run'
    | 'federation_created'
    | 'rule_pack_installed'
    | 'bcf_export'
    | string;
  summary: string;
  user_id: string | null;
  /** Deep-link route (e.g. `/clash?run=…`). May be null. */
  target: string | null;
}

/** Full payload returned by `GET /coordination/projects/:id/timeline`. */
export interface CoordinationTimelineResponse {
  project_id: string;
  events: CoordinationTimelineEvent[];
}
