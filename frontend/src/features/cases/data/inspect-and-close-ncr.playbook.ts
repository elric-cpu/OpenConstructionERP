// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Inspect work and close a non-conformance".
//
// The quality loop: inspect against criteria, raise an NCR when work fails,
// track the fix and re-inspect to close it out. Content strings are key plus
// inline English default and live only here.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'inspect-and-close-ncr',
  order: 55,
  category: 'quality',
  icon: 'BadgeCheck',
  titleKey: 'cases.inspect_and_close_ncr.title',
  titleDefault: 'Inspect work and close a non-conformance',
  descKey: 'cases.inspect_and_close_ncr.desc',
  descDefault:
    'Inspect against the criteria, raise a non-conformance when work fails, follow the correction and re-inspect to close it out.',
  estMinutes: 10,
  steps: [
    {
      id: 'inspect',
      icon: 'ClipboardCheck',
      titleKey: 'cases.inspect_and_close_ncr.step.inspect.title',
      titleDefault: 'Inspect the work',
      whatKey: 'cases.inspect_and_close_ncr.step.inspect.what',
      whatDefault:
        'Run the inspection against its checklist and record a pass or fail for each point, with a photo where it helps. A hold or witness point stops work until it is signed off.',
      whyKey: 'cases.inspect_and_close_ncr.step.inspect.why',
      whyDefault:
        'Inspecting against written criteria takes the argument out of quality. The record shows what was checked, by whom and against what standard.',
      moduleLabel: 'Inspections',
      moduleLabelKey: 'inspections.title',
      to: '/projects/:projectId/inspections',
    },
    {
      id: 'ncr',
      icon: 'AlertTriangle',
      titleKey: 'cases.inspect_and_close_ncr.step.ncr.title',
      titleDefault: 'Raise a non-conformance',
      whatKey: 'cases.inspect_and_close_ncr.step.ncr.what',
      whatDefault:
        'When work fails, raise an NCR from the inspection. Describe the defect, link the evidence and assign who must correct it and by when.',
      whyKey: 'cases.inspect_and_close_ncr.step.ncr.why',
      whyDefault:
        'An NCR turns a problem into a tracked action with an owner and a date. Defects that are only mentioned get built over; defects that are logged get fixed.',
      moduleLabel: 'NCR',
      moduleLabelKey: 'ncr.title',
      to: '/projects/:projectId/ncr',
    },
    {
      id: 'close',
      icon: 'BadgeCheck',
      titleKey: 'cases.inspect_and_close_ncr.step.close.title',
      titleDefault: 'Re-inspect and close',
      whatKey: 'cases.inspect_and_close_ncr.step.close.what',
      whatDefault:
        'Once the correction is done, re-inspect the work and, if it passes, close the NCR with the closing evidence attached.',
      whyKey: 'cases.inspect_and_close_ncr.step.close.why',
      whyDefault:
        'A non-conformance is only closed when the fix is proven, not when it is promised. The closing record is what the handover pack relies on.',
      moduleLabel: 'Inspections',
      moduleLabelKey: 'inspections.title',
      to: '/projects/:projectId/inspections',
    },
  ],
};

export default playbook;
