// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Build a baseline and track progress".
//
// Plan the works, freeze a baseline, then feed real site progress back so the
// schedule shows where you are against where you said you would be. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'schedule-and-track',
  order: 35,
  category: 'planning',
  icon: 'CalendarClock',
  titleKey: 'cases.schedule_and_track.title',
  titleDefault: 'Build a baseline and track progress',
  descKey: 'cases.schedule_and_track.desc',
  descDefault:
    'Plan the programme, freeze a baseline to measure against, capture real progress from site and read the variance so slippage shows early.',
  estMinutes: 12,
  steps: [
    {
      id: 'plan',
      icon: 'CalendarClock',
      titleKey: 'cases.schedule_and_track.step.plan.title',
      titleDefault: 'Lay out the programme',
      whatKey: 'cases.schedule_and_track.step.plan.what',
      whatDefault:
        'Build the activities, durations and links so the critical path is clear. Group the work the way you will report it, by trade, zone or phase.',
      whyKey: 'cases.schedule_and_track.step.plan.why',
      whyDefault:
        'The programme is the promise you make about time. A clear critical path tells you which delays actually move the finish date and which do not.',
      moduleLabel: 'Schedule',
      moduleLabelKey: 'schedule.title',
      to: '/schedule',
    },
    {
      id: 'baseline',
      icon: 'Flag',
      titleKey: 'cases.schedule_and_track.step.baseline.title',
      titleDefault: 'Freeze the baseline',
      whatKey: 'cases.schedule_and_track.step.baseline.what',
      whatDefault:
        'Save the agreed plan as a baseline before work starts. Every later update is compared against this frozen copy.',
      whyKey: 'cases.schedule_and_track.step.baseline.why',
      whyDefault:
        'Without a baseline there is nothing to be late against. Freezing it is what turns a plan into a yardstick you can defend in a claim.',
      moduleLabel: 'Advanced scheduling',
      moduleLabelKey: 'onboarding.mod_schedule_advanced',
      to: '/schedule-advanced',
    },
    {
      id: 'actuals',
      icon: 'HardHat',
      titleKey: 'cases.schedule_and_track.step.actuals.title',
      titleDefault: 'Capture real progress',
      whatKey: 'cases.schedule_and_track.step.actuals.what',
      whatDefault:
        'Record actual start and finish and the hours worked from the field so the schedule reflects what really happened this period.',
      whyKey: 'cases.schedule_and_track.step.actuals.why',
      whyDefault:
        'A plan nobody updates is fiction by the second week. Feeding real site data back is what keeps the forecast honest.',
      moduleLabel: 'Field time',
      moduleLabelKey: 'nav.field_time',
      to: '/projects/:projectId/field-time',
    },
    {
      id: 'variance',
      icon: 'FileBarChart',
      titleKey: 'cases.schedule_and_track.step.variance.title',
      titleDefault: 'Read the variance',
      whatKey: 'cases.schedule_and_track.step.variance.what',
      whatDefault:
        'Compare the updated schedule against the baseline and read the slippage and float. The advanced view shows the critical path shifting as progress lands.',
      whyKey: 'cases.schedule_and_track.step.variance.why',
      whyDefault:
        'Variance seen early is a decision you can still make. The point of tracking is to act on a two-week slip, not to record a two-month one.',
      moduleLabel: 'Advanced scheduling',
      moduleLabelKey: 'onboarding.mod_schedule_advanced',
      to: '/schedule-advanced',
    },
  ],
};

export default playbook;
