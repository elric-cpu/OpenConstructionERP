// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run a tender from a BOQ".
//
// Shows how a priced bill of quantities becomes a competitive tender. It starts
// in the BOQ, then stays in Tendering for the four moves that matter: create a
// package from the bill, invite subcontractors, compare the offers and award a
// winner. Awarding writes the agreed rates back into the BOQ and hands a draft
// purchase order to Procurement, so the loop closes without rekeying.
//
// Every content string is a key plus an inline English default. These live ONLY
// here and are never added to en.ts (only the framework chrome lives there).
// Module chips reuse existing translated nav/title keys so they localize for
// free. The package, distribution, comparison and award steps all open the
// Tendering module, which has no project-scoped route, so they use the plain
// `/tendering` path and rely on the active-project context set by "Go".

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'tender-from-boq',
  order: 20,
  category: 'tendering',
  icon: 'Handshake',
  titleKey: 'cases.tender_from_boq.title',
  titleDefault: 'Run a tender from a BOQ',
  descKey: 'cases.tender_from_boq.desc',
  descDefault:
    'Take a priced bill of quantities to market: package it, invite subcontractors, compare their bids and award a winner. Five steps, end to end.',
  estMinutes: 12,
  steps: [
    {
      id: 'boq',
      icon: 'Table2',
      titleKey: 'cases.tender_from_boq.step.boq.title',
      titleDefault: 'Open the priced BOQ',
      whatKey: 'cases.tender_from_boq.step.boq.what',
      whatDefault:
        'Open the bill you want to tender and check it is priced and validated. The tender package is built straight from this BOQ, so its positions and quantities become what bidders price.',
      whyKey: 'cases.tender_from_boq.step.boq.why',
      whyDefault:
        'The BOQ is the single scope every bidder works from. Sending one clean, priced bill means every offer prices the same thing, so the comparison later is fair.',
      moduleLabel: 'BOQ',
      moduleLabelKey: 'boq.title',
      to: '/projects/:projectId/boq',
    },
    {
      id: 'package',
      icon: 'Layers',
      titleKey: 'cases.tender_from_boq.step.package.title',
      titleDefault: 'Create the tender package',
      whatKey: 'cases.tender_from_boq.step.package.what',
      whatDefault:
        'In Tendering, create a new package, pick this BOQ as its source and set a submission deadline. The package carries the bill positions and quantities for bidders to price.',
      whyKey: 'cases.tender_from_boq.step.package.why',
      whyDefault:
        'A package turns your estimate into something you can issue. Pricing it from the BOQ keeps scope, quantities and budget tied to the estimate you already trust.',
      moduleLabel: 'Tendering',
      moduleLabelKey: 'tendering.title',
      to: '/tendering',
    },
    {
      id: 'distribute',
      icon: 'Send',
      titleKey: 'cases.tender_from_boq.step.distribute.title',
      titleDefault: 'Invite subcontractors',
      whatKey: 'cases.tender_from_boq.step.distribute.what',
      whatDefault:
        'Build the distribution list from your subcontractor directory or add firms by hand, then send the invitation. Each recipient shows as sent, pending or failed so nothing slips.',
      whyKey: 'cases.tender_from_boq.step.distribute.why',
      whyDefault:
        'More qualified bidders means stronger competition and better prices. Sending from one list keeps a clear record of who was invited and when.',
      moduleLabel: 'Tendering',
      moduleLabelKey: 'tendering.title',
      to: '/tendering',
    },
    {
      id: 'compare',
      icon: 'FileBarChart',
      titleKey: 'cases.tender_from_boq.step.compare.title',
      titleDefault: 'Compare the bids',
      whatKey: 'cases.tender_from_boq.step.compare.what',
      whatDefault:
        'As offers come in, line them up side by side against your budget. The comparison flags high and low outliers per position and the leveling matrix puts every bid on the same basis.',
      whyKey: 'cases.tender_from_boq.step.compare.why',
      whyDefault:
        'The cheapest total is not always the best bid. Comparing rate by rate against budget exposes gaps, errors and risky low offers before you commit.',
      moduleLabel: 'Tendering',
      moduleLabelKey: 'tendering.title',
      to: '/tendering',
    },
    {
      id: 'award',
      icon: 'Handshake',
      titleKey: 'cases.tender_from_boq.step.award.title',
      titleDefault: 'Award the winner',
      whatKey: 'cases.tender_from_boq.step.award.what',
      whatDefault:
        'Pick the winning bid and award it. The agreed rates write back into the BOQ, the losing bids are closed out and a draft purchase order is prepared in Procurement.',
      whyKey: 'cases.tender_from_boq.step.award.why',
      whyDefault:
        'Awarding closes the loop: your estimate is updated with real market rates and the hand-off to procurement starts at once, with no rekeying.',
      moduleLabel: 'Tendering',
      moduleLabelKey: 'tendering.title',
      to: '/tendering',
    },
  ],
};

export default playbook;
