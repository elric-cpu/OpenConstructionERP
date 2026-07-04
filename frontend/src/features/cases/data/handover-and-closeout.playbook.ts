// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Hand over and close out".
//
// Finish the job cleanly: clear the punch list, confirm inspections and open
// NCRs are closed, assemble the documents and issue the handover. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'handover-and-closeout',
  order: 70,
  category: 'handover',
  icon: 'ShieldCheck',
  titleKey: 'cases.handover_and_closeout.title',
  titleDefault: 'Hand over and close out',
  descKey: 'cases.handover_and_closeout.desc',
  descDefault:
    'Finish cleanly: clear the punch list, confirm inspections and open non-conformances are closed, gather the documents and issue the handover.',
  estMinutes: 12,
  steps: [
    {
      id: 'punch',
      icon: 'ListChecks',
      titleKey: 'cases.handover_and_closeout.step.punch.title',
      titleDefault: 'Clear the punch list',
      whatKey: 'cases.handover_and_closeout.step.punch.what',
      whatDefault:
        'Walk the works, log every outstanding snag with a location and photo, assign it and track it to done.',
      whyKey: 'cases.handover_and_closeout.step.punch.why',
      whyDefault:
        'The punch list is the gap between practically finished and actually finished. A short, closed list is what unlocks the final payment.',
      moduleLabel: 'Punch list',
      moduleLabelKey: 'nav.punchlist',
      to: '/punchlist',
    },
    {
      id: 'quality',
      icon: 'ClipboardCheck',
      titleKey: 'cases.handover_and_closeout.step.quality.title',
      titleDefault: 'Confirm quality is closed',
      whatKey: 'cases.handover_and_closeout.step.quality.what',
      whatDefault:
        'Check that the required inspections passed and no non-conformance is left open. Any hold or witness point should be signed off.',
      whyKey: 'cases.handover_and_closeout.step.quality.why',
      whyDefault:
        'An open NCR at handover is a liability you carry into occupation. Confirming closure is what makes the handover pack complete and honest.',
      moduleLabel: 'Inspections',
      moduleLabelKey: 'inspections.title',
      to: '/projects/:projectId/inspections',
    },
    {
      id: 'documents',
      icon: 'FolderOpen',
      titleKey: 'cases.handover_and_closeout.step.documents.title',
      titleDefault: 'Assemble the documents',
      whatKey: 'cases.handover_and_closeout.step.documents.what',
      whatDefault:
        'Gather the as-built drawings, certificates, warranties and manuals into the project files so the handover pack is complete in one place.',
      whyKey: 'cases.handover_and_closeout.step.documents.why',
      whyDefault:
        'The client remembers the handover long after the build. A complete, organised document set is the last impression and the first thing they use.',
      moduleLabel: 'Files',
      moduleLabelKey: 'nav.documents',
      to: '/projects/:projectId/files',
    },
    {
      id: 'closeout',
      icon: 'ShieldCheck',
      titleKey: 'cases.handover_and_closeout.step.closeout.title',
      titleDefault: 'Issue the handover',
      whatKey: 'cases.handover_and_closeout.step.closeout.what',
      whatDefault:
        'Assemble the close-out package, confirm the gates are met and issue the signed handover to the client and the operator.',
      whyKey: 'cases.handover_and_closeout.step.closeout.why',
      whyDefault:
        'Close-out is what turns a finished building into a discharged obligation. Issuing it cleanly starts the defects period on a clear footing.',
      moduleLabel: 'Close-out',
      moduleLabelKey: 'nav.closeout',
      to: '/closeout',
    },
  ],
};

export default playbook;
