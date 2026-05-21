import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

/**
 * Six standard resource types — promoted to a first-class column in
 * v2940 so the M/L/E breakdown can be filtered and rolled up without
 * description-text inference.
 */
export type ResourceType =
  | 'material'
  | 'labor'
  | 'equipment'
  | 'operator'
  | 'subcontractor'
  | 'overhead';

/**
 * Optional, type-specific metadata fields the editor can attach to a
 * component. The server reads them when computing the typed total
 * (waste/burden uplift, fuel add-on); the FE persists them as-is in
 * the JSON `metadata` blob so adding new vocabulary doesn't require
 * a migration.
 */
export interface ComponentMetadata {
  // Material
  waste_pct?: number;
  vendor?: string;
  // Labor
  crew_size?: number;
  hours?: number;
  productivity?: number;
  base_wage?: number;
  burden_pct?: number;
  skill_level?: string;
  // Equipment
  rental_days?: number;
  hourly_rate?: number;
  fuel_cost?: number;
  // Generic
  notes?: string;
  resource_type?: ResourceType;
  [k: string]: unknown;
}

export interface AssemblyComponent {
  id: string;
  assembly_id: string;
  cost_item_id: string | null;
  catalog_resource_id: string | null;
  description: string;
  resource_type: ResourceType | null;
  factor: number;
  quantity: number;
  unit: string;
  unit_cost: number;
  total: number;
  sort_order: number;
  metadata: ComponentMetadata;
}

export interface Assembly {
  id: string;
  code: string;
  name: string;
  description: string;
  unit: string;
  category: string;
  classification: Record<string, string>;
  total_rate: number;
  currency: string;
  bid_factor: number;
  regional_factors: Record<string, string>;
  is_template: boolean;
  project_id: string | null;
  owner_id: string | null;
  is_active: boolean;
  component_count: number;
  usage_count: number;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface AssemblyExport {
  code: string;
  name: string;
  description: string;
  unit: string;
  category: string;
  classification: Record<string, string>;
  currency: string;
  bid_factor: number;
  regional_factors: Record<string, string>;
  tags: string[];
  components: Array<{
    description: string;
    factor: number;
    quantity: number;
    unit: string;
    unit_cost: number;
    sort_order: number;
  }>;
}

export interface AssemblySearchResponse {
  items: Assembly[];
  total: number;
  limit: number;
  offset: number;
}

export interface AssemblyStats {
  total: number;
  most_used: Array<{ name: string; usage_count: number }>;
  by_category: Record<string, number>;
}

export interface AssemblyWithComponents extends Assembly {
  components: AssemblyComponent[];
}

export interface CreateAssemblyData {
  code: string;
  name: string;
  unit: string;
  category?: string;
  classification?: Record<string, string>;
  currency?: string;
  bid_factor?: number;
  project_id?: string;
}

export interface CreateComponentData {
  cost_item_id?: string;
  catalog_resource_id?: string;
  description: string;
  resource_type?: ResourceType;
  factor: number;
  quantity: number;
  unit: string;
  unit_cost: number;
  metadata?: ComponentMetadata;
}

export interface AIGenerateRequest {
  description: string;
  region?: string;
  unit?: string;
}

export interface AIGeneratedComponent {
  name: string;
  code: string;
  unit: string;
  quantity: number;
  unit_rate: number;
  total: number;
  type: string;
  sort_order: number;
  cost_item_id?: string;
}

export interface AIGeneratedAssembly {
  name: string;
  code: string;
  unit: string;
  category: string;
  components: AIGeneratedComponent[];
  total_rate: number;
  source_items_count: number;
  confidence: number;
  description: string;
  region: string;
}

// ── Assembly Library templates (v3.13.0 — Slice 1) ──────────────────────

/** One catalogue-agnostic component inside a library template. */
export interface AssemblyTemplateComponent {
  cost_match_query: string;
  factor: number;
  unit: string;
  role: string;
  description: string;
}

/** A row from the platform-wide Assembly Library. */
export interface AssemblyTemplate {
  id: string;
  name: string;
  name_translations: Record<string, string>;
  category: string;
  unit: string;
  components: AssemblyTemplateComponent[];
  classification: Record<string, string>;
  tags: string[];
  is_builtin: boolean;
  component_count: number;
  created_at: string;
  updated_at: string;
}

export interface AssemblyTemplateSearchResponse {
  items: AssemblyTemplate[];
  total: number;
  limit: number;
  offset: number;
}

export interface AppliedTemplateComponent {
  description: string;
  cost_match_query: string;
  matched_cost_item_id: string | null;
  matched_description: string;
  matched_code: string;
  factor: number;
  scaled_quantity: number;
  unit: string;
  unit_rate: number;
  total: number;
  role: string;
  match_confidence: number;
  match_channel: string;
}

export interface AppliedTemplateResponse {
  template_id: string;
  template_name: string;
  project_id: string;
  boq_position_id: string | null;
  quantity: number;
  unit: string;
  currency: string;
  components: AppliedTemplateComponent[];
  total_rate: number;
  grand_total: number;
  unresolved_components: string[];
  warnings: string[];
}

export interface ApplyTemplatePayload {
  project_id: string;
  boq_position_id?: string;
  quantity: number;
  region?: string;
  language?: string;
}

export const assembliesApi = {
  list: (params?: Record<string, string>) =>
    apiGet<AssemblySearchResponse>(`/v1/assemblies/?${new URLSearchParams(params)}`),
  get: (id: string) => apiGet<AssemblyWithComponents>(`/v1/assemblies/${id}`),
  create: (data: CreateAssemblyData) => apiPost<Assembly>('/v1/assemblies/', data),
  update: (id: string, data: Partial<CreateAssemblyData>) =>
    apiPatch<Assembly>(`/v1/assemblies/${id}`, data),
  delete: (id: string) => apiDelete(`/v1/assemblies/${id}`),
  addComponent: (assemblyId: string, data: CreateComponentData) =>
    apiPost<AssemblyComponent>(`/v1/assemblies/${assemblyId}/components/`, data),
  updateComponent: (assemblyId: string, componentId: string, data: Partial<CreateComponentData>) =>
    apiPatch<AssemblyComponent>(`/v1/assemblies/${assemblyId}/components/${componentId}`, data),
  deleteComponent: (assemblyId: string, componentId: string) =>
    apiDelete(`/v1/assemblies/${assemblyId}/components/${componentId}`),
  applyToBoq: (assemblyId: string, boqId: string, quantity: number) =>
    apiPost(`/v1/assemblies/${assemblyId}/apply-to-boq/`, { boq_id: boqId, quantity }),
  aiGenerate: (data: AIGenerateRequest) =>
    apiPost<AIGeneratedAssembly>('/v1/assemblies/ai-generate/', data),
  reorderComponents: (assemblyId: string, componentIds: string[]) =>
    apiPost(`/v1/assemblies/${assemblyId}/reorder-components/`, { component_ids: componentIds }),
  exportAssembly: (assemblyId: string) =>
    apiGet<AssemblyExport>(`/v1/assemblies/${assemblyId}/export/`),
  importAssembly: (data: AssemblyExport) =>
    apiPost<Assembly>('/v1/assemblies/import/', { assembly: data }),
  updateTags: (assemblyId: string, tags: string[]) =>
    apiPatch<Assembly>(`/v1/assemblies/${assemblyId}/tags/`, { tags }),
  getStats: () => apiGet<AssemblyStats>(`/v1/assemblies/stats/`),

  // Assembly Library templates
  listTemplates: (params?: Record<string, string>) =>
    apiGet<AssemblyTemplateSearchResponse>(
      `/v1/assemblies/templates/?${new URLSearchParams(params)}`
    ),
  getTemplate: (id: string) =>
    apiGet<AssemblyTemplate>(`/v1/assemblies/templates/${id}`),
  applyTemplate: (id: string, body: ApplyTemplatePayload) =>
    apiPost<AppliedTemplateResponse>(`/v1/assemblies/templates/${id}/apply`, body),
};
