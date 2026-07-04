// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Procure materials from the BOQ".
//
// Turns priced bill positions into purchase orders: pull the quantities you
// need, raise a requisition, order from a supplier and receive against it.
// Content strings are key plus inline English default, kept only here.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'procure-from-boq',
  order: 25,
  category: 'tendering',
  icon: 'PackageCheck',
  titleKey: 'cases.procure_from_boq.title',
  titleDefault: 'Procure materials from the BOQ',
  descKey: 'cases.procure_from_boq.desc',
  descDefault:
    'Take the quantities you already priced and buy them: raise a requisition from the bill, order from a supplier and receive the goods on site.',
  estMinutes: 10,
  steps: [
    {
      id: 'boq',
      icon: 'Table2',
      titleKey: 'cases.procure_from_boq.step.boq.title',
      titleDefault: 'Pick the positions to buy',
      whatKey: 'cases.procure_from_boq.step.boq.what',
      whatDefault:
        'Open the bill and select the positions whose materials you need to order. Their quantities become the requisition, so you buy what you priced, not a fresh guess.',
      whyKey: 'cases.procure_from_boq.step.boq.why',
      whyDefault:
        'Buying straight from the estimate keeps the order tied to the budget. Any difference between ordered and estimated shows up at once, not at the final account.',
      moduleLabel: 'BOQ',
      moduleLabelKey: 'boq.title',
      to: '/projects/:projectId/boq',
    },
    {
      id: 'requisition',
      icon: 'ClipboardList',
      titleKey: 'cases.procure_from_boq.step.requisition.title',
      titleDefault: 'Raise the requisition',
      whatKey: 'cases.procure_from_boq.step.requisition.what',
      whatDefault:
        'In Procurement, create a requisition from those positions and send it for approval. It records what is needed, how much and by when.',
      whyKey: 'cases.procure_from_boq.step.requisition.why',
      whyDefault:
        'A requisition is the controlled request that sits between a need and a spend. It gives the buyer and the approver one clear document to act on.',
      moduleLabel: 'Procurement',
      moduleLabelKey: 'procurement.title',
      to: '/projects/:projectId/procurement',
    },
    {
      id: 'order',
      icon: 'Send',
      titleKey: 'cases.procure_from_boq.step.order.title',
      titleDefault: 'Order from a supplier',
      whatKey: 'cases.procure_from_boq.step.order.what',
      whatDefault:
        'Turn the approved requisition into a purchase order, pick the supplier and their catalogue price, and issue it. The order carries the lines, prices and delivery date.',
      whyKey: 'cases.procure_from_boq.step.order.why',
      whyDefault:
        'A purchase order is your commitment on paper. Issuing it from the requisition keeps quantities and prices consistent from estimate to spend.',
      moduleLabel: 'Procurement',
      moduleLabelKey: 'procurement.title',
      to: '/projects/:projectId/procurement',
    },
    {
      id: 'receive',
      icon: 'PackageCheck',
      titleKey: 'cases.procure_from_boq.step.receive.title',
      titleDefault: 'Receive against the order',
      whatKey: 'cases.procure_from_boq.step.receive.what',
      whatDefault:
        'When the delivery arrives, record what actually came in against the order. Short or over deliveries are flagged so the invoice can be checked against them.',
      whyKey: 'cases.procure_from_boq.step.receive.why',
      whyDefault:
        'Receiving closes the loop between ordered, delivered and invoiced. It is how you pay only for what you got and catch a wrong delivery before it is paid.',
      moduleLabel: 'Procurement',
      moduleLabelKey: 'procurement.title',
      to: '/projects/:projectId/procurement',
    },
  ],
};

export default playbook;
