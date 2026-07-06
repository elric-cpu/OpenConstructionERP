// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Prepare an interim payment application".
//
// Build the monthly application for payment: measure the work done to date,
// value it against the contract sum plus agreed variations, apply retention,
// and issue the application with its backup so it is certified in full.
// Content strings are key plus inline English default and live only here.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'prepare-an-interim-payment-application',
  order: 267,
  category: 'commercial',
  companyTypes: ['general-contractor', 'subcontractor', 'cost-consultant'],
  roles: ['commercial-manager', 'quantity-surveyor'],
  icon: 'ReceiptText',
  titleKey: 'cases.prepare_an_interim_payment_application.title',
  titleDefault: 'Prepare an interim payment application',
  descKey: 'cases.prepare_an_interim_payment_application.desc',
  descDefault:
    'Build the monthly interim application: measure the work done to date, value it against the contract sum plus agreed variations, apply retention, and issue the application with its backup so it certifies in full.',
  estMinutes: 10,
  steps: [
    {
      id: 'measure',
      icon: 'Ruler',
      titleKey: 'cases.prepare_an_interim_payment_application.step.measure.title',
      titleDefault: 'Measure the work done to date',
      whatKey: 'cases.prepare_an_interim_payment_application.step.measure.what',
      whatDefault:
        'Walk the works and set the percentage complete on each BOQ line to the application cut-off date, so the application is built on what is genuinely in place rather than a rounded guess.',
      whyKey: 'cases.prepare_an_interim_payment_application.step.measure.why',
      whyDefault:
        'An application measured line by line stands up when the assessor checks it. Over-claiming to smooth the month only gets clawed back later, and under-claiming is cash you lend the client for free.',
      moduleLabel: 'BOQ',
      moduleLabelKey: 'boq.title',
      to: '/projects/:projectId/boq',
    },
    {
      id: 'value',
      icon: 'TrendingUp',
      titleKey: 'cases.prepare_an_interim_payment_application.step.value.title',
      titleDefault: 'Value it against the contract sum',
      whatKey: 'cases.prepare_an_interim_payment_application.step.value.what',
      whatDefault:
        'Value the measured work against the contract sum, add the agreed variations and any materials on site, to reach the gross value earned to this date.',
      whyKey: 'cases.prepare_an_interim_payment_application.step.value.why',
      whyDefault:
        'Agreed variations belong in the application the month they are agreed, not months later. Rolling them in as they land is what keeps cash coming in level with the work and the changes you have carried.',
      moduleLabel: 'Value',
      moduleLabelKey: 'nav.value',
      to: '/projects/:projectId/value',
    },
    {
      id: 'retention',
      icon: 'Calculator',
      titleKey: 'cases.prepare_an_interim_payment_application.step.retention.title',
      titleDefault: 'Apply retention and previous payments',
      whatKey: 'cases.prepare_an_interim_payment_application.step.retention.what',
      whatDefault:
        'Take the gross value, hold back retention at the contract rate, deduct what has already been certified on earlier applications, and the balance is the net sum this application claims.',
      whyKey: 'cases.prepare_an_interim_payment_application.step.retention.why',
      whyDefault:
        'Getting retention and prior payments right is the difference between an application that certifies clean and one that bounces back for correction and misses the payment cycle.',
      moduleLabel: 'Finance',
      moduleLabelKey: 'nav.finance',
      to: '/projects/:projectId/finance',
    },
    {
      id: 'issue',
      icon: 'ReceiptText',
      titleKey: 'cases.prepare_an_interim_payment_application.step.issue.title',
      titleDefault: 'Issue the application with backup',
      whatKey: 'cases.prepare_an_interim_payment_application.step.issue.what',
      whatDefault:
        'Produce the application with the measured breakdown, the variation account and the retention calculation attached, and submit it before the cycle closes so it lands inside the payment terms.',
      whyKey: 'cases.prepare_an_interim_payment_application.step.issue.why',
      whyDefault:
        'An application submitted late or without backup is the one that gets cut under time pressure. Full evidence, on time, is what gets it certified in full instead of chased down.',
      moduleLabel: 'Reports',
      moduleLabelKey: 'nav.reports',
      to: '/reports',
    },
    {
      id: 'reconcile',
      icon: 'Scale',
      titleKey: 'cases.prepare_an_interim_payment_application.step.reconcile.title',
      titleDefault: 'Reconcile certified against applied',
      whatKey: 'cases.prepare_an_interim_payment_application.step.reconcile.what',
      whatDefault:
        'When the certificate comes back, set what was certified against what was applied for, and chase any line cut back while the measure and the backup behind it are still fresh.',
      whyKey: 'cases.prepare_an_interim_payment_application.step.reconcile.why',
      whyDefault:
        'A quiet under-certification left unchallenged carries forward every month. Reconciling each cycle is what keeps small cuts from compounding into a real shortfall by the final account.',
      moduleLabel: 'Reconciliation',
      moduleLabelKey: 'nav.reconciliation',
      to: '/projects/:projectId/reconciliation',
    },
  ],
};

export default playbook;
