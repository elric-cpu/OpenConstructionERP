import { useState, useCallback, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Info, X, ArrowRight } from 'lucide-react';

/**
 * Contextual intro / help banner for the Quality & Safety section.
 *
 * Every page in this section uses it to explain — *in the UI itself* —
 * what the page is for, what to do next, and how it connects to the rest
 * of the platform (BOQ / BIM / canonical model, the quality workflow,
 * cost & change-order traceability). Dismissal is remembered per page via
 * localStorage so power users are not nagged.
 */

export interface SectionLink {
  label: string;
  onClick: () => void;
}

export function SectionIntro({
  storageKey,
  title,
  children,
  links,
}: {
  /** Stable key — dismissal is remembered under `oce.intro.<storageKey>`. */
  storageKey: string;
  title: string;
  children: ReactNode;
  /** Optional cross-module shortcuts rendered as inline pills. */
  links?: SectionLink[];
}) {
  const { t } = useTranslation();
  const lsKey = `oce.intro.${storageKey}`;

  const [dismissed, setDismissed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(lsKey) === '1';
    } catch {
      return false;
    }
  });

  const dismiss = useCallback(() => {
    setDismissed(true);
    try {
      localStorage.setItem(lsKey, '1');
    } catch {
      /* private mode / quota — non-fatal, banner just reappears next load */
    }
  }, [lsKey]);

  if (dismissed) return null;

  return (
    <div className="mb-5 rounded-xl border border-oe-blue/20 bg-oe-blue-subtle/60 px-4 py-3.5 animate-fade-in">
      <div className="flex items-start gap-3">
        <Info size={16} className="mt-0.5 shrink-0 text-oe-blue" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-content-primary">{title}</p>
          <p className="mt-1 text-sm leading-relaxed text-content-secondary">{children}</p>
          {links && links.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {links.map((l) => (
                <button
                  key={l.label}
                  type="button"
                  onClick={l.onClick}
                  className="inline-flex items-center gap-1 rounded-full border border-oe-blue/30 bg-surface-primary px-2.5 py-1 text-xs font-medium text-oe-blue transition-colors hover:bg-oe-blue hover:text-content-inverse"
                >
                  {l.label}
                  <ArrowRight size={11} />
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label={t('common.dismiss', { defaultValue: 'Dismiss' })}
          title={t('common.dismiss', { defaultValue: 'Dismiss' })}
          className="shrink-0 rounded-md p-1 text-content-tertiary transition-colors hover:bg-surface-secondary hover:text-content-primary"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
