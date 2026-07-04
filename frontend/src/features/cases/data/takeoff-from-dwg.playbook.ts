// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Measure quantities from a DWG".
//
// Open a drawing, measure areas and lengths on it, then carry the measured
// quantities into a priced bill. Content strings are key plus inline English
// default and live only here.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'takeoff-from-dwg',
  order: 45,
  category: 'bim',
  icon: 'Ruler',
  titleKey: 'cases.takeoff_from_dwg.title',
  titleDefault: 'Measure quantities from a DWG',
  descKey: 'cases.takeoff_from_dwg.desc',
  descDefault:
    'Open a drawing, set the scale, measure the areas and lengths you need, then send the measured quantities into a bill to price.',
  estMinutes: 10,
  steps: [
    {
      id: 'open',
      icon: 'Ruler',
      titleKey: 'cases.takeoff_from_dwg.step.open.title',
      titleDefault: 'Open the drawing',
      whatKey: 'cases.takeoff_from_dwg.step.open.what',
      whatDefault:
        'Load the DWG and confirm the scale so a measured length reads in real metres. Pick the layers you want to measure over.',
      whyKey: 'cases.takeoff_from_dwg.step.open.why',
      whyDefault:
        'A wrong scale turns every measurement wrong by the same factor. Setting it once at the start is the cheapest check you can make.',
      moduleLabel: 'DWG take-off',
      moduleLabelKey: 'onboarding.mod_dwg_takeoff',
      to: '/dwg-takeoff',
    },
    {
      id: 'measure',
      icon: 'Ruler',
      titleKey: 'cases.takeoff_from_dwg.step.measure.title',
      titleDefault: 'Measure the work',
      whatKey: 'cases.takeoff_from_dwg.step.measure.what',
      whatDefault:
        'Draw the areas, lengths and counts you need. Group measurements so a wall run, a floor area and a door count each roll up under their own heading.',
      whyKey: 'cases.takeoff_from_dwg.step.measure.why',
      whyDefault:
        'Grouped measurements price cleanly and check easily. When a quantity looks wrong, you can trace it straight back to the shape you drew.',
      moduleLabel: 'Take-off',
      moduleLabelKey: 'nav.takeoff_overview',
      to: '/takeoff?tab=measurements',
    },
    {
      id: 'boq',
      icon: 'Table2',
      titleKey: 'cases.takeoff_from_dwg.step.boq.title',
      titleDefault: 'Price the quantities',
      whatKey: 'cases.takeoff_from_dwg.step.boq.what',
      whatDefault:
        'Send the measured quantities into a bill and apply rates. Each position keeps a link back to the measurement it came from.',
      whyKey: 'cases.takeoff_from_dwg.step.boq.why',
      whyDefault:
        'Measuring and pricing in one flow removes the rekeying that loses quantities. The bill stays tied to the drawing it was measured from.',
      moduleLabel: 'BOQ',
      moduleLabelKey: 'boq.title',
      to: '/projects/:projectId/boq',
    },
  ],
};

export default playbook;
