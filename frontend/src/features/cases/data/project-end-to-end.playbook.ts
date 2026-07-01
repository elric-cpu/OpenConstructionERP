// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Set up a project and hand it over".
//
// A lifecycle playbook that mirrors the journey-map arcs at a higher level. It
// walks a user from first project setup all the way to final handover, crossing
// the modules in the order a job actually moves: create the project, price the
// work, schedule it, track it on site, then close it out. Every content string
// is a key plus an inline English default; these stay HERE and are never added
// to en.ts (only the framework chrome lives there). Module chips reuse existing
// translated nav/title keys so they localize for free.
//
// Routes used are all real (verified against app/App.tsx). Where no project-
// scoped variant exists (schedule, closeout) the plain route is used and the
// runner scopes it through the active-project context, exactly as the journey
// map does.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'project-end-to-end',
  order: 5,
  icon: 'Layers',
  titleKey: 'cases.project_end_to_end.title',
  titleDefault: 'Set up a project and hand it over',
  descKey: 'cases.project_end_to_end.desc',
  descDefault:
    'Take a project from first setup all the way to handover. Create it, price the work, plan the schedule, track progress on site, then close it out. Five steps across the whole lifecycle.',
  estMinutes: 20,
  steps: [
    {
      id: 'create',
      icon: 'Building2',
      titleKey: 'cases.project_end_to_end.step.create.title',
      titleDefault: 'Create the project',
      whatKey: 'cases.project_end_to_end.step.create.what',
      whatDefault:
        'Open the new project form and fill in the basics: name, client, location and currency. Save it to get a project that everything else hangs off.',
      whyKey: 'cases.project_end_to_end.step.create.why',
      whyDefault:
        'The project is the container that ties the estimate, the schedule and the site records together. Setting it up first gives every later step a home.',
      moduleLabel: 'Projects',
      moduleLabelKey: 'nav.projects',
      to: '/projects/new',
    },
    {
      id: 'estimate',
      icon: 'Calculator',
      titleKey: 'cases.project_end_to_end.step.estimate.title',
      titleDefault: 'Build the estimate',
      whatKey: 'cases.project_end_to_end.step.estimate.what',
      whatDefault:
        'Open the Bill of Quantities and add positions with quantities and unit rates, drawn from the cost database or your own assemblies. The total rolls up live as you work.',
      whyKey: 'cases.project_end_to_end.step.estimate.why',
      whyDefault:
        'The BOQ is the priced scope of work. It sets the budget that the schedule and the site tracking are measured against later on.',
      moduleLabel: 'BOQ',
      moduleLabelKey: 'boq.title',
      to: '/projects/:projectId/boq',
    },
    {
      id: 'schedule',
      icon: 'Layers',
      titleKey: 'cases.project_end_to_end.step.schedule.title',
      titleDefault: 'Plan the schedule',
      whatKey: 'cases.project_end_to_end.step.schedule.what',
      whatDefault:
        'Open the schedule and lay out the activities, their durations and the links between them. The critical path shows which tasks drive the finish date.',
      whyKey: 'cases.project_end_to_end.step.schedule.why',
      whyDefault:
        'A schedule turns the priced scope into a dated plan. It tells the site team what to build and when, and flags slippage early enough to act on.',
      moduleLabel: 'Schedule',
      moduleLabelKey: 'nav.schedule',
      to: '/schedule',
    },
    {
      id: 'track',
      icon: 'ClipboardCheck',
      titleKey: 'cases.project_end_to_end.step.track.title',
      titleDefault: 'Track work on site',
      whatKey: 'cases.project_end_to_end.step.track.what',
      whatDefault:
        'Use the daily diary to log what happened each day: progress, crews, equipment, deliveries and weather. Each entry adds to a dated record of the job.',
      whyKey: 'cases.project_end_to_end.step.track.why',
      whyDefault:
        'A daily site record shows real progress against the plan and the budget. It is also the evidence you reach for if a delay or a claim comes up.',
      moduleLabel: 'Daily Diary',
      moduleLabelKey: 'nav.daily_diary',
      to: '/projects/:projectId/daily-diary',
    },
    {
      id: 'handover',
      icon: 'Handshake',
      titleKey: 'cases.project_end_to_end.step.handover.title',
      titleDefault: 'Hand over the project',
      whatKey: 'cases.project_end_to_end.step.handover.what',
      whatDefault:
        'Open handover and closeout to work through the punch list, gather the closeout documents and sign the project off to the client.',
      whyKey: 'cases.project_end_to_end.step.handover.why',
      whyDefault:
        'A clean handover closes the loop: the client gets a finished, documented building, and you keep a complete record of how it was delivered.',
      moduleLabel: 'Handover',
      moduleLabelKey: 'closeout.title',
      to: '/closeout',
    },
  ],
};

export default playbook;
