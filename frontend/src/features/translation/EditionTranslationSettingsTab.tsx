import { isBensonEdition } from '@/editions/config';
import {
  TranslationSettingsTab as UpstreamTranslationSettingsTab,
  type TranslationSettingsTabProps,
} from './TranslationSettingsTab';

export function EditionTranslationSettingsTab(props: TranslationSettingsTabProps) {
  if (isBensonEdition) return null;
  return <UpstreamTranslationSettingsTab {...props} />;
}
