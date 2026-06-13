// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// ModuleGuideButton — small pill that opens the module's "How it works"
// guide. Designed to sit immediately next to the existing ModuleHelpButton
// (the Tour button) so the two read as a single cluster on a module header.
//
// The Tour button (ModuleHelpButton, HelpCircle icon) walks the UI; this
// button (GraduationCap icon) explains the module's concepts and how to
// enter data. Distinct icon, same size and pill geometry so they line up.
//
// Mobile collapse: on `sm` and below the label hides and only the icon
// shows, matching ModuleHelpButton; the button stays accessible via
// aria-label.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GraduationCap } from 'lucide-react';
import clsx from 'clsx';

import { ModuleGuide, type ModuleGuideContent } from './ModuleGuide';

export interface ModuleGuideButtonProps {
  /** The guide content to teach when the button is clicked. */
  content: ModuleGuideContent;
  /** Optional extra classes for layout-specific tweaks. */
  className?: string;
  /** Optional override for the button label. Defaults to "How it works". */
  label?: string;
  /** Optional handler for the guide's closing CTA (last card). When the
   *  content defines a `ctaKey`, the CTA button runs this then closes. */
  onCta?: () => void;
}

export function ModuleGuideButton({
  content,
  className,
  label,
  onCta,
}: ModuleGuideButtonProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const resolvedLabel = label ?? t('guide.button', { defaultValue: 'How it works' });
  const aria = t('guide.button_aria', {
    defaultValue: 'Learn how this module works',
  });

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        data-testid="module-guide-button"
        aria-label={aria}
        aria-haspopup="dialog"
        aria-expanded={open}
        title={aria}
        className={clsx(
          'inline-flex items-center gap-1.5 rounded-full',
          'border border-oe-blue/30 bg-oe-blue/5 hover:bg-oe-blue/10',
          'px-2.5 h-7 text-xs font-medium text-oe-blue',
          'transition-colors focus:outline-none focus:ring-2 focus:ring-oe-blue/40',
          className,
        )}
      >
        <GraduationCap size={13} strokeWidth={2} />
        <span className="hidden sm:inline">{resolvedLabel}</span>
      </button>

      <ModuleGuide
        open={open}
        onClose={() => setOpen(false)}
        content={content}
        onCta={onCta}
      />
    </>
  );
}
