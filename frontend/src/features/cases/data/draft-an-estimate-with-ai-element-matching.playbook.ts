// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Draft an estimate with AI element matching".
//
// Build a first-pass estimate fast: match imported elements to cost items, let
// the AI estimator propose priced lines the estimator confirms, accept them
// into the bill and validate the result before you trust the number.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'draft-an-estimate-with-ai-element-matching',
  order: 304,
  category: 'estimating',
  companyTypes: ['general-contractor', 'subcontractor', 'cost-consultant'],
  icon: 'Sparkles',
  titleKey: 'cases.draft_an_estimate_with_ai_element_matching.title',
  titleDefault: 'Draft an estimate with AI element matching',
  descKey: 'cases.draft_an_estimate_with_ai_element_matching.desc',
  descDefault:
    'Match imported elements to cost items, let AI price the scope, accept it into the bill and validate before you trust it.',
  estMinutes: 10,
  steps: [
    {
      id: 'match',
      icon: 'Combine',
      titleKey: 'cases.draft_an_estimate_with_ai_element_matching.step.match.title',
      titleDefault: 'Match elements to cost items',
      whatKey: 'cases.draft_an_estimate_with_ai_element_matching.step.match.what',
      whatDefault:
        'Import your elements and descriptions and let the matcher line each one up to a cost-database item, with a confidence score on every match.',
      whyKey: 'cases.draft_an_estimate_with_ai_element_matching.step.match.why',
      whyDefault:
        'Coding hundreds of lines by hand is slow and uneven. Scored matches show where to trust the machine and where to check by hand.',
      moduleLabel: 'Match Elements',
      to: '/match-elements',
    },
    {
      id: 'ai-price',
      icon: 'Sparkles',
      titleKey: 'cases.draft_an_estimate_with_ai_element_matching.step.ai-price.title',
      titleDefault: 'Let AI price the scope',
      whatKey: 'cases.draft_an_estimate_with_ai_element_matching.step.ai-price.what',
      whatDefault:
        'Run the AI estimator over the matched scope so it proposes priced lines, then confirm or overrule each suggestion.',
      whyKey: 'cases.draft_an_estimate_with_ai_element_matching.step.ai-price.why',
      whyDefault:
        'A first-pass priced draft in minutes saves hours, but a number only goes in the bid once a person has signed it off.',
      moduleLabel: 'AI Estimator',
      to: '/ai-estimator',
    },
    {
      id: 'accept-boq',
      icon: 'Table2',
      titleKey: 'cases.draft_an_estimate_with_ai_element_matching.step.accept-boq.title',
      titleDefault: 'Accept lines into the bill',
      whatKey: 'cases.draft_an_estimate_with_ai_element_matching.step.accept-boq.what',
      whatDefault:
        'Pull the confirmed lines into the bill of quantities and enter or adjust the quantities.',
      whyKey: 'cases.draft_an_estimate_with_ai_element_matching.step.accept-boq.why',
      whyDefault:
        'The bill is what you actually price and submit. Getting the quantities right here is where the money is won or lost.',
      moduleLabel: 'BOQ',
      to: '/boq',
    },
    {
      id: 'validate',
      icon: 'ShieldCheck',
      titleKey: 'cases.draft_an_estimate_with_ai_element_matching.step.validate.title',
      titleDefault: 'Validate before you trust it',
      whatKey: 'cases.draft_an_estimate_with_ai_element_matching.step.validate.what',
      whatDefault:
        'Run validation over the finished bill to flag zero prices, missing quantities, duplicates and rate outliers.',
      whyKey: 'cases.draft_an_estimate_with_ai_element_matching.step.validate.why',
      whyDefault:
        'An AI draft can leave a hole or a silly rate that reads fine at a glance. Catching it before submission stops an underpriced or embarrassing bid.',
      moduleLabel: 'Validation',
      to: '/validation',
    },
  ],
};

export default playbook;
