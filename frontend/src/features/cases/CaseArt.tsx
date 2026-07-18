// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { type ComponentType } from 'react';
import clsx from 'clsx';
import type { LucideProps } from 'lucide-react';
import { CASE_SCENES, CaseScene } from './caseScenes';
import { accentFor } from './categories';
import type { CaseCategory } from './types';

interface CaseArtProps {
  /** Playbook id; selects the bespoke vector scene from {@link CASE_SCENES}. */
  id: string;
  /** Case discipline; picks the accent ramp the scene is painted in, so a tile
   *  reads in its card's colour. Falls back to the neutral blue ramp. */
  category?: CaseCategory;
  /** Discipline icon shown if a case has no scene yet. */
  fallbackIcon: ComponentType<LucideProps>;
  /** Colour class for the fallback icon (discipline tint text). */
  fallbackClass?: string;
  alt?: string;
}

/**
 * The illustration for a case tile. Every case is drawn as a bespoke vector
 * scene (see {@link CASE_SCENES}) in the shared blueprint line-art language, so
 * the art stays crisp at any size, weighs almost nothing and reads the same in
 * light and dark theme on its always-light tile. A case with no scene yet falls
 * back to its discipline icon rather than a broken picture.
 */
export function CaseArt({ id, category, fallbackIcon: Icon, fallbackClass, alt = '' }: CaseArtProps) {
  if (CASE_SCENES[id]) {
    return <CaseScene id={id} title={alt} accent={accentFor(category)} />;
  }

  return (
    <div className="flex h-full w-full items-center justify-center">
      <Icon size={40} strokeWidth={1.4} className={clsx('opacity-80', fallbackClass)} />
    </div>
  );
}
