// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Track an opportunity from enquiry to tender".
//
// Follow a lead end to end: capture the client contacts, run the opportunity
// through the CRM pipeline, convert the win into a live project and carry it
// into the tender you will price and submit.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'track-an-opportunity-from-enquiry-to-tender',
  order: 308,
  category: 'commercial',
  companyTypes: ['general-contractor', 'subcontractor', 'cost-consultant'],
  icon: 'TrendingUp',
  titleKey: 'cases.track_an_opportunity_from_enquiry_to_tender.title',
  titleDefault: 'Track an opportunity from enquiry to tender',
  descKey: 'cases.track_an_opportunity_from_enquiry_to_tender.desc',
  descDefault:
    'Capture the client contacts, run the opportunity through the pipeline, convert the win into a project and carry it into tender.',
  estMinutes: 7,
  steps: [
    {
      id: 'contact',
      icon: 'Users',
      titleKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.contact.title',
      titleDefault: 'Record the client and contacts',
      whatKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.contact.what',
      whatDefault:
        'Add the client and the key people behind the enquiry, with their roles and how to reach them.',
      whyKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.contact.why',
      whyDefault:
        'Enquiries arrive by phone and email and get lost. One clean contact record is who you chase and who signs.',
      moduleLabel: 'Contacts',
      to: '/contacts',
    },
    {
      id: 'opportunity',
      icon: 'TrendingUp',
      titleKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.opportunity.title',
      titleDefault: 'Open and track the opportunity',
      whatKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.opportunity.what',
      whatDefault:
        'Open the opportunity, set its value, stage and win probability, and log every call and meeting against it.',
      whyKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.opportunity.why',
      whyDefault:
        'A pipeline you cannot see is one you cannot forecast. Stage and probability tell you what to chase and what to staff for.',
      moduleLabel: 'CRM',
      to: '/crm',
    },
    {
      id: 'new-project',
      icon: 'Building2',
      titleKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.new-project.title',
      titleDefault: 'Convert the win to a project',
      whatKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.new-project.what',
      whatDefault:
        'When the enquiry is won, spin it up as a live project and carry the client and scope across.',
      whyKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.new-project.why',
      whyDefault:
        'Re-keying a won job into a fresh system loses detail and wastes a day. Converting keeps the history and starts delivery clean.',
      moduleLabel: 'New project',
      to: '/projects/new',
    },
    {
      id: 'tender',
      icon: 'Gavel',
      titleKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.tender.title',
      titleDefault: 'Carry it into the tender',
      whatKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.tender.what',
      whatDefault: 'Move the won opportunity into tendering to build, price and submit the bid.',
      whyKey: 'cases.track_an_opportunity_from_enquiry_to_tender.step.tender.why',
      whyDefault:
        'The commercial thread should run unbroken from first enquiry to submitted price. A gap is where scope and margin leak out.',
      moduleLabel: 'Tendering',
      to: '/tendering',
    },
  ],
};

export default playbook;
