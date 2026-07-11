// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { useState, type ComponentType } from 'react';
import clsx from 'clsx';
import type { LucideProps } from 'lucide-react';
import { CASE_SCENES, CaseScene } from './caseScenes';

interface CaseArtProps {
  /** Playbook id; maps to /cases-art/line/<id>.webp. */
  id: string;
  /** Discipline icon shown if the illustration is missing. */
  fallbackIcon: ComponentType<LucideProps>;
  /** Colour class for the fallback icon (discipline tint text). */
  fallbackClass?: string;
  alt?: string;
}

/**
 * The line-art illustration for a case, sitting on its own always-light tile so
 * the slate linework reads the same in light and dark theme. Falls back to the
 * discipline icon when a picture has not been generated for a case yet.
 */
export function CaseArt({ id, fallbackIcon: Icon, fallbackClass, alt = '' }: CaseArtProps) {
  const [broken, setBroken] = useState(false);
  const [lastId, setLastId] = useState(id);
  // Reset the fallback during render when the tile is reused for another case,
  // so a stale illustration or icon never flashes before an effect can run.
  if (id !== lastId) {
    setLastId(id);
    setBroken(false);
  }

  // The generated line-art picture is the canonical, consistent style for the
  // case hub, so it WINS. Only when a picture has not been generated for this
  // case (the image 404s / errors) do we fall back to a bespoke vector scene,
  // and finally to the discipline icon - so the hub never shows a lone icon
  // when a drawn scene exists, yet cases that DO have a picture read uniformly.
  // (Inside a case, the step-by-step action visualisations stay vector - that
  // is a different surface; this only governs the case tile / header art.)
  if (!broken) {
    return (
      <img
        src={`/cases-art/line/${id}.webp`}
        alt={alt}
        loading="lazy"
        decoding="async"
        width={512}
        height={512}
        draggable={false}
        onError={() => setBroken(true)}
        className="h-full w-full object-contain p-2.5"
      />
    );
  }

  if (CASE_SCENES[id]) {
    return <CaseScene id={id} title={alt} />;
  }

  return (
    <div className="flex h-full w-full items-center justify-center">
      <Icon size={40} strokeWidth={1.4} className={clsx('opacity-80', fallbackClass)} />
    </div>
  );
}
