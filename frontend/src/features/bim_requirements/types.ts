/**
 * Types mirroring the backend `bim_requirements` Rules-as-Code endpoints
 * (`POST /api/v1/bim/requirements/preview-yaml/` and
 *  `POST /api/v1/bim/requirements/install-from-yaml/`).
 *
 * The backend ships RulePack objects loaded from YAML; the preview endpoint
 * returns the parsed pack plus optional dry-run validation results when a
 * `model_id` is supplied. Install persists the pack to the active project.
 *
 * Keep these types narrow and forgiving: server payloads evolve faster than
 * the UI ships, so unknown trailing fields must NOT break the renderer.
 */

export type RuleSeverity = 'error' | 'warning' | 'info';

export interface RulePackSelector {
  ifc_class?: string;
  properties?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface RulePackAssertion {
  property?: Record<string, unknown>;
  set_vs_set?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ParsedRule {
  id: string;
  name: string;
  severity: RuleSeverity;
  rationale?: string;
  rule_type?: string;
  selector?: RulePackSelector;
  assertion?: RulePackAssertion;
  failure_message?: string;
}

export interface RulePackAppliesTo {
  classifications?: string[];
  project_regions?: string[];
}

export interface ParsedRulePackMeta {
  id?: string;
  name?: string;
  description?: string;
  source?: string;
  version?: string;
  applies_to?: RulePackAppliesTo;
}

export interface ParsedRulePack {
  schema_version?: string;
  pack?: ParsedRulePackMeta;
  rules?: ParsedRule[];
}

export interface DryRunRuleResult {
  rule_id: string;
  pass_count: number;
  fail_count: number;
  total_count?: number;
  severity?: RuleSeverity;
}

export interface DryRunReport {
  total_rules?: number;
  total_pass?: number;
  total_fail?: number;
  results?: DryRunRuleResult[];
}

export interface PreviewYamlResponse {
  pack: ParsedRulePack;
  dry_run?: DryRunReport | null;
  errors?: string[];
}

export interface InstallYamlResponse {
  pack_id: string;
  installed_rule_count: number;
}
