import { lazy } from 'react';
import { Building2 } from 'lucide-react';
import { isBensonEdition } from '@/editions/config';
import type { ModuleManifest } from '../_types';

const BensonOperationsPage = lazy(() =>
  import('@/features/benson/BensonOperationsPage').then((module) => ({
    default: module.BensonOperationsPage,
  })),
);

export const manifest: ModuleManifest = {
  id: 'benson-operations',
  name: 'modules.benson.name',
  description: 'modules.benson.description',
  version: '12.9.0',
  icon: Building2,
  category: 'tools',
  defaultEnabled: isBensonEdition,
  routes: [{ path: '/benson', title: 'Benson Operations', component: BensonOperationsPage }],
  navItems: [
    {
      labelKey: 'nav.benson_operations',
      to: '/benson',
      icon: Building2,
      group: 'tools',
    },
  ],
  searchEntries: [
    {
      label: 'Benson Operations',
      path: '/benson',
      keywords: ['benson', 'eastern oregon', 'operations', 'jurisdiction'],
    },
  ],
  translations: {
    en: {
      'modules.benson.name': 'Benson Operations',
      'modules.benson.description': 'Benson edition operating profile and integrated workflows',
      'nav.benson_operations': 'Benson Operations',
    },
  },
};
