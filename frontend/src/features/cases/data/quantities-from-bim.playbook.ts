// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Get quantities from a BIM model".
//
// Import a converted model, read the element quantities, carry them into a bill
// and validate the result. No IfcOpenShell: the model arrives as canonical data
// through the converter. Content strings are key plus inline English default.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'quantities-from-bim',
  order: 40,
  category: 'bim',
  icon: 'Box',
  titleKey: 'cases.quantities_from_bim.title',
  titleDefault: 'Get quantities from a BIM model',
  descKey: 'cases.quantities_from_bim.desc',
  descDefault:
    'Load a converted model, read the element quantities straight off the geometry, carry them into a bill and validate the result.',
  estMinutes: 12,
  steps: [
    {
      id: 'import',
      icon: 'Box',
      titleKey: 'cases.quantities_from_bim.step.import.title',
      titleDefault: 'Open the model',
      whatKey: 'cases.quantities_from_bim.step.import.what',
      whatDefault:
        'Open the converted model in the viewer and browse the elements by category and level. Areas, volumes and lengths come from the geometry, not a manual count.',
      whyKey: 'cases.quantities_from_bim.step.import.why',
      whyDefault:
        'Quantities read off the model are quantities you can trace to an element. When the design changes, you re-read rather than re-measure.',
      moduleLabel: 'BIM',
      moduleLabelKey: 'nav.bim_viewer',
      to: '/projects/:projectId/bim',
    },
    {
      id: 'boq',
      icon: 'Table2',
      titleKey: 'cases.quantities_from_bim.step.boq.title',
      titleDefault: 'Carry them into a bill',
      whatKey: 'cases.quantities_from_bim.step.boq.what',
      whatDefault:
        'Map the element quantities onto bill positions and apply your rates. Each position keeps a link back to the model elements it came from.',
      whyKey: 'cases.quantities_from_bim.step.boq.why',
      whyDefault:
        'The link from a priced line back to the model is the audit trail. Anyone can see where a number came from and check it against the design.',
      moduleLabel: 'BOQ',
      moduleLabelKey: 'boq.title',
      to: '/projects/:projectId/boq',
    },
    {
      id: 'validate',
      icon: 'ShieldCheck',
      titleKey: 'cases.quantities_from_bim.step.validate.title',
      titleDefault: 'Validate the take-off',
      whatKey: 'cases.quantities_from_bim.step.validate.what',
      whatDefault:
        'Run the validation rules to check the mapped quantities are complete and consistent, and that classification is present where it is required.',
      whyKey: 'cases.quantities_from_bim.step.validate.why',
      whyDefault:
        'A model can be complete and still miss what you need to price. Validation catches the unmapped element and the missing property before it reaches the client.',
      moduleLabel: 'Validation',
      moduleLabelKey: 'validation.title',
      to: '/validation',
    },
  ],
};

export default playbook;
