// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run a subcontractor package".
//
// Award a trade package to a subcontractor, put it on a contract and pay it
// down through progress claims with retention held. Content strings are key
// plus inline English default and live only here.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'subcontractor-package',
  order: 65,
  category: 'commercial',
  icon: 'PackageCheck',
  titleKey: 'cases.subcontractor_package.title',
  titleDefault: 'Run a subcontractor package',
  descKey: 'cases.subcontractor_package.desc',
  descDefault:
    'Set a trade package up with a subcontractor, put it on a contract with retention, then pay it down through progress claims.',
  estMinutes: 11,
  steps: [
    {
      id: 'subbie',
      icon: 'Users',
      titleKey: 'cases.subcontractor_package.step.subbie.title',
      titleDefault: 'Set up the subcontractor',
      whatKey: 'cases.subcontractor_package.step.subbie.what',
      whatDefault:
        'Add the subcontractor and their scope, and record the checks you hold them to: insurance, qualifications and any prequalification.',
      whyKey: 'cases.subcontractor_package.step.subbie.why',
      whyDefault:
        'The package is only as sound as the firm delivering it. Recording the checks up front is what protects you if the work or the paperwork later falls short.',
      moduleLabel: 'Subcontractors',
      moduleLabelKey: 'onboarding.mod_subcontractors',
      to: '/projects/:projectId/subcontractors',
    },
    {
      id: 'contract',
      icon: 'FileSignature',
      titleKey: 'cases.subcontractor_package.step.contract.title',
      titleDefault: 'Put it on a contract',
      whatKey: 'cases.subcontractor_package.step.contract.what',
      whatDefault:
        'Create the subcontract with the agreed sum, the schedule of values to bill against and the retention percentage to hold.',
      whyKey: 'cases.subcontractor_package.step.contract.why',
      whyDefault:
        'A contract with a clear schedule of values is what every later claim is measured against. Retention held now is your cover for defects later.',
      moduleLabel: 'Contracts',
      moduleLabelKey: 'onboarding.mod_contracts',
      to: '/projects/:projectId/contracts',
    },
    {
      id: 'claim',
      icon: 'ReceiptText',
      titleKey: 'cases.subcontractor_package.step.claim.title',
      titleDefault: 'Pay down with progress claims',
      whatKey: 'cases.subcontractor_package.step.claim.what',
      whatDefault:
        'Each period, certify the work done against the schedule of values, apply retention and record the payment. The contract keeps the running balance.',
      whyKey: 'cases.subcontractor_package.step.claim.why',
      whyDefault:
        'Certifying against the schedule of values means you pay for progress, not for optimism. The running balance stops over-payment before it happens.',
      moduleLabel: 'Contracts',
      moduleLabelKey: 'onboarding.mod_contracts',
      to: '/projects/:projectId/contracts',
    },
  ],
};

export default playbook;
