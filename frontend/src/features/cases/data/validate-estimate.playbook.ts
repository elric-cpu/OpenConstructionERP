// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Check an estimate before you send it".
//
// A short quality gate: run the validation rules over a priced BOQ, fix what
// they flag, then produce the client-ready report. Every content string is a
// key plus an inline English default and lives only here.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'validate-estimate',
  order: 15,
  category: 'estimating',
  icon: 'Calculator',
  titleKey: 'cases.validate_estimate.title',
  titleDefault: 'Check an estimate before you send it',
  descKey: 'cases.validate_estimate.desc',
  descDefault:
    'Run the validation rules over a priced bill, clear the warnings and errors, then export a clean report you can hand to the client.',
  estMinutes: 8,
  steps: [
    {
      id: 'boq',
      icon: 'Table2',
      titleKey: 'cases.validate_estimate.step.boq.title',
      titleDefault: 'Open the priced bill',
      whatKey: 'cases.validate_estimate.step.boq.what',
      whatDefault:
        'Open the BOQ you are about to send and confirm every position carries a quantity and a rate. Empty cells and stray zeros are the first thing the validator looks for.',
      whyKey: 'cases.validate_estimate.step.boq.why',
      whyDefault:
        'A gap you miss becomes a gap the client finds. Reviewing the bill first means the validation pass confirms your work instead of surprising you.',
      moduleLabel: 'BOQ',
      moduleLabelKey: 'boq.title',
      to: '/projects/:projectId/boq',
    },
    {
      id: 'validate',
      icon: 'ShieldCheck',
      titleKey: 'cases.validate_estimate.step.validate.title',
      titleDefault: 'Run the validation rules',
      whatKey: 'cases.validate_estimate.step.validate.what',
      whatDefault:
        'Run the rule sets over the bill and read the traffic-light result. Each error and warning links back to the exact position so you can jump to it and fix the cause.',
      whyKey: 'cases.validate_estimate.step.validate.why',
      whyDefault:
        'Missing quantities, zero prices, duplicate positions and out-of-range rates are cheap to fix now and expensive to explain later. The score is your go or no-go.',
      moduleLabel: 'Validation',
      moduleLabelKey: 'validation.title',
      to: '/validation',
    },
    {
      id: 'report',
      icon: 'FileBarChart',
      titleKey: 'cases.validate_estimate.step.report.title',
      titleDefault: 'Export the report',
      whatKey: 'cases.validate_estimate.step.report.what',
      whatDefault:
        'Once the bill is green, export the summary and the detailed breakdown. The report carries the cost split and the validation result together.',
      whyKey: 'cases.validate_estimate.step.report.why',
      whyDefault:
        'A report backed by a passed validation is a report you can defend. It shows the client not just the number but that the number was checked.',
      moduleLabel: 'Reports',
      moduleLabelKey: 'nav.reporting',
      to: '/reports',
    },
  ],
};

export default playbook;
