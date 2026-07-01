// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Get 6D carbon from a BIM model".
//
// Walks a user through the 6D flow: import a converted BIM model, open Carbon,
// run Auto-enrich from BIM (it matches element materials to carbon factors and
// pulls quantities straight from the geometry, preview first then confirm),
// review the linked entries and their match confidence, and finish by setting a
// reduction target and generating a report. It makes the brand-new 6D
// auto-enrich feature learnable end to end.
//
// Every content string is a key plus an inline English default. These stay HERE
// and are never added to en.ts (only the framework chrome lives there). Module
// chips reuse existing translated nav keys so they localize for free.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'carbon-from-bim-6d',
  order: 30,
  icon: 'Layers',
  titleKey: 'cases.carbon_from_bim_6d.title',
  titleDefault: 'Get 6D carbon from a BIM model',
  descKey: 'cases.carbon_from_bim_6d.desc',
  descDefault:
    'Turn a converted BIM model into an embodied-carbon footprint. Auto-enrich pulls quantities from the geometry and matches materials to factors, then you set a reduction target and report. Five steps.',
  estMinutes: 12,
  steps: [
    {
      id: 'import-model',
      icon: 'Building2',
      titleKey: 'cases.carbon_from_bim_6d.step.import-model.title',
      titleDefault: 'Import a BIM model',
      whatKey: 'cases.carbon_from_bim_6d.step.import-model.what',
      whatDefault:
        'Open BIM and import the model for this project. Once it is converted, every element carries its material and its geometry quantities.',
      whyKey: 'cases.carbon_from_bim_6d.step.import-model.why',
      whyDefault:
        'The footprint is built from the model. A converted model gives each wall, slab and column a material and a measured quantity, which is exactly what the carbon match reads.',
      moduleLabel: 'BIM',
      moduleLabelKey: 'nav.bim',
      to: '/projects/:projectId/bim',
    },
    {
      id: 'inventory',
      icon: 'Layers',
      titleKey: 'cases.carbon_from_bim_6d.step.inventory.title',
      titleDefault: 'Open Carbon and start an inventory',
      whatKey: 'cases.carbon_from_bim_6d.step.inventory.what',
      whatDefault:
        'Open Carbon and create an inventory for the project, scoped cradle-to-gate or cradle-to-grave. This is the one snapshot every entry rolls up into.',
      whyKey: 'cases.carbon_from_bim_6d.step.inventory.why',
      whyDefault:
        'The inventory is the container for the footprint. Setting it up first gives the auto-enrich a place to write the embodied entries it proposes.',
      moduleLabel: 'Carbon',
      moduleLabelKey: 'nav.carbon',
      to: '/projects/:projectId/carbon',
    },
    {
      id: 'enrich',
      icon: 'Sparkles',
      titleKey: 'cases.carbon_from_bim_6d.step.enrich.title',
      titleDefault: 'Auto-enrich embodied carbon from BIM',
      whatKey: 'cases.carbon_from_bim_6d.step.enrich.what',
      whatDefault:
        'In the inventory, run Auto-enrich from BIM. Pick the model, preview the proposed entries, then confirm. It matches each element material to a carbon factor and pulls the quantity from the geometry. Nothing is written until you confirm.',
      whyKey: 'cases.carbon_from_bim_6d.step.enrich.why',
      whyDefault:
        'This is the 6D shortcut. Instead of adding materials by hand, you get a ready list of embodied entries straight from the model, each with a confidence score on its match.',
      moduleLabel: 'Carbon',
      moduleLabelKey: 'nav.carbon',
      to: '/projects/:projectId/carbon',
    },
    {
      id: 'review',
      icon: 'ClipboardCheck',
      titleKey: 'cases.carbon_from_bim_6d.step.review.title',
      titleDefault: 'Review the linked entries and confidence',
      whatKey: 'cases.carbon_from_bim_6d.step.review.what',
      whatDefault:
        'Go through the added entries. Each links back to its BIM element and carries a match confidence, so check the low-confidence rows and fix the factor or quantity where it looks off.',
      whyKey: 'cases.carbon_from_bim_6d.step.review.why',
      whyDefault:
        'AI proposes, you confirm. The confidence badge tells you where to look first, so the footprint you report is one you can stand behind.',
      moduleLabel: 'Carbon',
      moduleLabelKey: 'nav.carbon',
      to: '/projects/:projectId/carbon',
    },
    {
      id: 'target',
      icon: 'FileBarChart',
      titleKey: 'cases.carbon_from_bim_6d.step.target.title',
      titleDefault: 'Set a target and report',
      whatKey: 'cases.carbon_from_bim_6d.step.target.what',
      whatDefault:
        'Set a reduction target as a total or per square metre, then generate a report for the period in the framework you need. The target tracks live against the inventory.',
      whyKey: 'cases.carbon_from_bim_6d.step.target.why',
      whyDefault:
        'A number on its own does not drive change. A target shows the trajectory, and the report packages the footprint into a record you can share for disclosure and audit.',
      moduleLabel: 'Carbon',
      moduleLabelKey: 'nav.carbon',
      to: '/projects/:projectId/carbon',
    },
  ],
};

export default playbook;
