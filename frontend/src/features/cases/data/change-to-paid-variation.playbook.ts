// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Turn a change into a paid variation".
//
// The commercial loop for scope change: raise the change, price it as a
// contract variation and bill it in a progress claim so the extra work is
// recovered. Content strings are key plus inline English default.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'change-to-paid-variation',
  order: 60,
  category: 'commercial',
  icon: 'FileSignature',
  titleKey: 'cases.change_to_paid_variation.title',
  titleDefault: 'Turn a change into a paid variation',
  descKey: 'cases.change_to_paid_variation.desc',
  descDefault:
    'Catch a scope change, price it as a contract variation and bill it in a progress claim, so extra work is recovered instead of absorbed.',
  estMinutes: 11,
  steps: [
    {
      id: 'change',
      icon: 'GitCompareArrows',
      titleKey: 'cases.change_to_paid_variation.step.change.title',
      titleDefault: 'Raise the change',
      whatKey: 'cases.change_to_paid_variation.step.change.what',
      whatDefault:
        'Record the change: what moved, who instructed it and the drawing or instruction behind it. Capture the time and cost impact while it is fresh.',
      whyKey: 'cases.change_to_paid_variation.step.change.why',
      whyDefault:
        'A change logged at the moment it happens is a change you can prove. The ones absorbed quietly are the ones that erode the margin.',
      moduleLabel: 'Change orders',
      moduleLabelKey: 'nav.change_orders',
      to: '/change-orders',
    },
    {
      id: 'variation',
      icon: 'FileSignature',
      titleKey: 'cases.change_to_paid_variation.step.variation.title',
      titleDefault: 'Price it as a variation',
      whatKey: 'cases.change_to_paid_variation.step.variation.what',
      whatDefault:
        'Turn the change into a contract variation, price the added or omitted work against your rates and route it for the client instruction.',
      whyKey: 'cases.change_to_paid_variation.step.variation.why',
      whyDefault:
        'A variation is the contractual home of a change. Pricing it against agreed rates is what makes it defensible when it is challenged.',
      moduleLabel: 'Contracts',
      moduleLabelKey: 'onboarding.mod_contracts',
      to: '/projects/:projectId/contracts',
    },
    {
      id: 'claim',
      icon: 'ReceiptText',
      titleKey: 'cases.change_to_paid_variation.step.claim.title',
      titleDefault: 'Bill it in a progress claim',
      whatKey: 'cases.change_to_paid_variation.step.claim.what',
      whatDefault:
        'Include the agreed variation in the next progress claim against the contract, so it is invoiced alongside the measured work.',
      whyKey: 'cases.change_to_paid_variation.step.claim.why',
      whyDefault:
        'Priced and instructed is only paid once it is claimed. Rolling the variation into the claim is the step that actually recovers the money.',
      moduleLabel: 'Contracts',
      moduleLabelKey: 'onboarding.mod_contracts',
      to: '/projects/:projectId/contracts',
    },
  ],
};

export default playbook;
