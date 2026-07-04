// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run the site day".
//
// The daily site loop: log the diary, book the labour and plant hours, capture
// photos and raise a safety observation, so a day on site becomes a record you
// can stand behind. Content strings are key plus inline English default.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'run-the-site-day',
  order: 50,
  category: 'site',
  icon: 'HardHat',
  titleKey: 'cases.run_the_site_day.title',
  titleDefault: 'Run the site day',
  descKey: 'cases.run_the_site_day.desc',
  descDefault:
    'The daily site loop: write the diary, book labour and plant hours, capture photos and log a safety observation, so the day is on the record.',
  estMinutes: 9,
  steps: [
    {
      id: 'diary',
      icon: 'NotebookPen',
      titleKey: 'cases.run_the_site_day.step.diary.title',
      titleDefault: 'Write the site diary',
      whatKey: 'cases.run_the_site_day.step.diary.what',
      whatDefault:
        'Log the weather, who was on site, what was done and anything that held work up. This is the contemporaneous record of the day.',
      whyKey: 'cases.run_the_site_day.step.diary.why',
      whyDefault:
        'The diary written on the day carries weight a memo written months later never will. It is the first thing anyone reaches for in a dispute.',
      moduleLabel: 'Site diary',
      moduleLabelKey: 'onboarding.mod_daily_diary',
      to: '/projects/:projectId/daily-diary',
    },
    {
      id: 'hours',
      icon: 'Clock',
      titleKey: 'cases.run_the_site_day.step.hours.title',
      titleDefault: 'Book labour and plant hours',
      whatKey: 'cases.run_the_site_day.step.hours.what',
      whatDefault:
        'Record the hours worked by each gang and the plant on site against the project, with a cost code so they land in the right place.',
      whyKey: 'cases.run_the_site_day.step.hours.why',
      whyDefault:
        'Hours captured daily are hours you can bill, cost and check. Left to the end of the month they become an estimate, and estimates leak money.',
      moduleLabel: 'Field time',
      moduleLabelKey: 'nav.field_time',
      to: '/projects/:projectId/field-time',
    },
    {
      id: 'photos',
      icon: 'Camera',
      titleKey: 'cases.run_the_site_day.step.photos.title',
      titleDefault: 'Capture site photos',
      whatKey: 'cases.run_the_site_day.step.photos.what',
      whatDefault:
        'Upload the photos from the day from the project files. They are tagged as site pictures and appear in the gallery, the strip and the diary.',
      whyKey: 'cases.run_the_site_day.step.photos.why',
      whyDefault:
        'A dated photo settles arguments no words can. It is proof of progress, of condition and of what was covered before it was covered up.',
      moduleLabel: 'Files',
      moduleLabelKey: 'nav.documents',
      to: '/projects/:projectId/files',
    },
    {
      id: 'safety',
      icon: 'ShieldCheck',
      titleKey: 'cases.run_the_site_day.step.safety.title',
      titleDefault: 'Log a safety observation',
      whatKey: 'cases.run_the_site_day.step.safety.what',
      whatDefault:
        'Record any hazard, near miss or positive observation from the day and assign who closes it out. Toolbox talks go here too.',
      whyKey: 'cases.run_the_site_day.step.safety.why',
      whyDefault:
        'Safety recorded is safety managed. A near miss logged today is the incident you did not have next week.',
      moduleLabel: 'Safety',
      moduleLabelKey: 'safety.title',
      to: '/projects/:projectId/safety',
    },
  ],
};

export default playbook;
