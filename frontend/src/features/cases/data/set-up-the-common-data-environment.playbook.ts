// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Set up the common data environment".
//
// Stand up the common data environment, load the information containers with
// the right status, and aim model coordination at the shared area.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'set-up-the-common-data-environment',
  order: 316,
  category: 'bim',
  companyTypes: ['general-contractor', 'bim-consultant', 'designer'],
  icon: 'Database',
  titleKey: 'cases.set_up_the_common_data_environment.title',
  titleDefault: 'Set up the common data environment',
  descKey: 'cases.set_up_the_common_data_environment.desc',
  descDefault: 'Stand up the common data environment, load the information containers with the right status, and aim coordination at the shared area.',
  estMinutes: 7,
  steps: [
    {
      id: 'define-states',
      icon: 'FolderOpen',
      titleKey: 'cases.set_up_the_common_data_environment.step.define-states.title',
      titleDefault: 'Define the status states',
      whatKey: 'cases.set_up_the_common_data_environment.step.define-states.what',
      whatDefault: 'In the CDE, define the status states, work in progress, shared, published and archived, and lay out the folder structure.',
      whyKey: 'cases.set_up_the_common_data_environment.step.define-states.why',
      whyDefault: 'If everyone reads and writes to their own copies, someone builds from a superseded drawing. The states tell you what is safe to use and what is still a draft.',
      moduleLabel: 'CDE',
      to: '/projects/:projectId/cde',
    },
    {
      id: 'load-containers',
      icon: 'Boxes',
      titleKey: 'cases.set_up_the_common_data_environment.step.load-containers.title',
      titleDefault: 'Load the containers',
      whatKey: 'cases.set_up_the_common_data_environment.step.load-containers.what',
      whatDefault: 'In Project Files, load the information containers, models, drawings and documents, and set each one to its status.',
      whyKey: 'cases.set_up_the_common_data_environment.step.load-containers.why',
      whyDefault: 'A container with no status is a trap, nobody knows if it is checked or just parked. Correct status is what lets the next person trust the file.',
      moduleLabel: 'Project Files',
      to: '/projects/:projectId/files',
    },
    {
      id: 'federate',
      icon: 'Combine',
      titleKey: 'cases.set_up_the_common_data_environment.step.federate.title',
      titleDefault: 'Federate the models',
      whatKey: 'cases.set_up_the_common_data_environment.step.federate.what',
      whatDefault: 'In Coordination, point the model federations at the shared area so everyone coordinates against the same set.',
      whyKey: 'cases.set_up_the_common_data_environment.step.federate.why',
      whyDefault: 'Clash checking against private working models finds clashes that are already fixed and misses the ones that are not. The shared area is the single source everyone federates from.',
      moduleLabel: 'Coordination',
      to: '/coordination',
    },
  ],
};

export default playbook;
