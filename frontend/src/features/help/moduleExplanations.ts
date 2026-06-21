// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// How-it-works catalog — index.
//
// Flattens the per-domain catalog files into one ordered list and exposes the
// grouping helper the hub page renders from. Each domain lives in its own file
// under ./catalog/* so the catalog can be authored in parallel without merge
// conflicts.

import { HOW_IT_WORKS_CATEGORIES } from './types';
import type { HowItWorksCategory, ModuleExplanation } from './types';

import { overviewEstimatingModules } from './catalog/overview-estimating';
import { takeoffRealityModules } from './catalog/takeoff-reality';
import { costDataControlModules } from './catalog/cost-data-control';
import { coordinationModules } from './catalog/coordination';
import { commercialProcurementModules } from './catalog/commercial-procurement';
import { fieldResourcesModules } from './catalog/field-resources';
import { qualitySafetyModules } from './catalog/quality-safety';
import { communicationDocumentsModules } from './catalog/communication-documents';
import { realestateFinanceControlsModules } from './catalog/realestate-finance-controls';
import { automationIntegrationsAdminModules } from './catalog/automation-integrations-admin';

export const MODULE_EXPLANATIONS: ModuleExplanation[] = [
  ...overviewEstimatingModules,
  ...takeoffRealityModules,
  ...costDataControlModules,
  ...coordinationModules,
  ...commercialProcurementModules,
  ...fieldResourcesModules,
  ...qualitySafetyModules,
  ...communicationDocumentsModules,
  ...realestateFinanceControlsModules,
  ...automationIntegrationsAdminModules,
];

export { HOW_IT_WORKS_CATEGORIES };
export type { ModuleExplanation, HowItWorksCategory, CategoryId, HowToStep } from './types';

export interface CategoryGroup {
  category: HowItWorksCategory;
  modules: ModuleExplanation[];
}

/**
 * Group the given modules by category, preserving the canonical category
 * order and dropping empty categories.
 */
export function groupByCategory(
  mods: ModuleExplanation[] = MODULE_EXPLANATIONS,
): CategoryGroup[] {
  return HOW_IT_WORKS_CATEGORIES.map((category) => ({
    category,
    modules: mods.filter((m) => m.category === category.id),
  })).filter((g) => g.modules.length > 0);
}
