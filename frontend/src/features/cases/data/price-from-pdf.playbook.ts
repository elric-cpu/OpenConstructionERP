// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Price a building from a PDF".
//
// The reference playbook. It walks a user from a raw PDF drawing all the way to
// a priced, validated estimate they can export, crossing five modules in the
// order a real estimator works them. Every content string is a key plus an
// inline English default - these stay HERE and are never added to en.ts (only
// the framework chrome lives there). Module chips reuse existing translated
// nav/title keys so they localize for free.
//
// To add another case, copy this file to ./<slug>.playbook.ts, give it a fresh
// id and a new `order`, and default-export it. It is picked up automatically.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'price-from-pdf',
  order: 10,
  icon: 'FileSpreadsheet',
  titleKey: 'cases.price_from_pdf.title',
  titleDefault: 'Price a building from a PDF',
  descKey: 'cases.price_from_pdf.desc',
  descDefault:
    'Start from a PDF drawing and finish with a priced, validated estimate you can export. Five steps, end to end.',
  estMinutes: 15,
  steps: [
    {
      id: 'upload',
      icon: 'Upload',
      titleKey: 'cases.price_from_pdf.step.upload.title',
      titleDefault: 'Upload the PDF drawing',
      whatKey: 'cases.price_from_pdf.step.upload.what',
      whatDefault:
        'Open the project files and drag in the PDF plan you want to price. The file is stored against the project so every later step can reach it.',
      whyKey: 'cases.price_from_pdf.step.upload.why',
      whyDefault:
        'Everything downstream works from this one source drawing. Getting it into the project first keeps the takeoff, the estimate and the exports tied to the same document.',
      moduleLabel: 'Documents',
      moduleLabelKey: 'nav.project_files',
      to: '/projects/:projectId/files',
    },
    {
      id: 'takeoff',
      icon: 'Ruler',
      titleKey: 'cases.price_from_pdf.step.takeoff.title',
      titleDefault: 'Measure quantities on the PDF',
      whatKey: 'cases.price_from_pdf.step.takeoff.what',
      whatDefault:
        'Open the PDF in Takeoff and measure areas, lengths and counts. Let the auto-measure tools find repeated items, then confirm what looks right.',
      whyKey: 'cases.price_from_pdf.step.takeoff.why',
      whyDefault:
        'Quantities are the backbone of any estimate. Measuring straight off the drawing means the numbers you price later trace back to something you can point at.',
      moduleLabel: 'Takeoff',
      moduleLabelKey: 'nav.pdf_measurements',
      to: '/takeoff?tab=measurements',
    },
    {
      id: 'boq',
      icon: 'Table2',
      titleKey: 'cases.price_from_pdf.step.boq.title',
      titleDefault: 'Build the priced BOQ',
      whatKey: 'cases.price_from_pdf.step.boq.what',
      whatDefault:
        'Turn the measured quantities into bill positions, then apply unit rates from the cost database or your own assemblies to get a live total.',
      whyKey: 'cases.price_from_pdf.step.boq.why',
      whyDefault:
        'The Bill of Quantities is the priced estimate. This is where quantities meet money, with rates and assemblies rolling up into a total you can defend.',
      moduleLabel: 'BOQ',
      moduleLabelKey: 'boq.title',
      to: '/projects/:projectId/boq',
    },
    {
      id: 'validate',
      icon: 'ShieldCheck',
      titleKey: 'cases.price_from_pdf.step.validate.title',
      titleDefault: 'Validate the estimate',
      whatKey: 'cases.price_from_pdf.step.validate.what',
      whatDefault:
        'Run the validation rules over the bill. Check for missing quantities, zero prices and duplicates, plus structure rules such as DIN 276 where they apply.',
      whyKey: 'cases.price_from_pdf.step.validate.why',
      whyDefault:
        'Catching gaps and errors before the estimate leaves your desk is far cheaper than after. The traffic-light report shows exactly what to fix and where.',
      moduleLabel: 'Validation',
      moduleLabelKey: 'validation.title',
      to: '/validation',
    },
    {
      id: 'export',
      icon: 'FileBarChart',
      titleKey: 'cases.price_from_pdf.step.export.title',
      titleDefault: 'Export the priced bill',
      whatKey: 'cases.price_from_pdf.step.export.what',
      whatDefault:
        'Generate the output you need from Reports: a PDF summary, an Excel sheet, or a GAEB file to hand on for tendering.',
      whyKey: 'cases.price_from_pdf.step.export.why',
      whyDefault:
        'The estimate only delivers value once it is in a form others can use. Exporting in an open format keeps the numbers portable and the data yours.',
      moduleLabel: 'Reports',
      moduleLabelKey: 'nav.reports',
      to: '/reports',
    },
  ],
};

export default playbook;
