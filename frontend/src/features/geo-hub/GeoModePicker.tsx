// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Segmented control switching between Global / Project / Development
 * scopes of the Geo Hub.
 *
 * Routing-aware — clicking a mode navigates via react-router and
 * preserves any contextual ids (active project / development). The
 * caller passes a per-page ``current`` so this component does not
 * have to know its mounting route.
 *
 * UX rule: a tab without context is NEVER inert. Clicking Project
 * with no active project navigates to ``/projects`` so the user can
 * pick one; Development with no active development navigates to
 * ``/property-dev``. Visually they are dimmed (``aria-disabled``)
 * with an explanatory tooltip + helper icon so the user understands
 * what's needed. ``aria-disabled`` (rather than the ``disabled`` HTML
 * attribute) keeps them keyboard-focusable per WAI-ARIA tabs pattern.
 *
 * Keeps the bespoke segmented-pill styling so it matches the rest of
 * the Geo Hub toolbar; uses {@link useTabKeyboardNav} for ArrowLeft /
 * Right / Home / End nav + roving tabIndex.
 */

import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Globe2, Building2, Boxes } from 'lucide-react';
import { useTabKeyboardNav } from '@/shared/hooks/useTabKeyboardNav';

export type GeoMode = 'global' | 'project' | 'development';

interface GeoModePickerProps {
  current: GeoMode;
  projectId?: string | null;
  developmentId?: string | null;
}

const ICONS = {
  global: Globe2,
  project: Building2,
  development: Boxes,
} as const;

const GEO_MODES: readonly GeoMode[] = ['global', 'project', 'development'];

export function GeoModePicker({
  current,
  projectId,
  developmentId,
}: GeoModePickerProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Each tab has a primary ``href`` (when context exists) and a
  // ``fallbackHref`` (where to send the user to *acquire* that context).
  // ``softDisabled`` means: visually dim + aria-disabled, but still
  // focusable and clickable — the click navigates to ``fallbackHref``.
  const items: Array<{
    key: GeoMode;
    label: string;
    description: string;
    href: string;
    softDisabled: boolean;
  }> = [
    {
      key: 'global',
      label: t('geo_hub.mode.global', { defaultValue: 'Global' }),
      description: t('geo_hub.mode.global_hint', {
        defaultValue: 'All projects on one earth-scale map.',
      }),
      href: '/geo',
      softDisabled: false,
    },
    {
      key: 'project',
      label: t('geo_hub.mode.project', { defaultValue: 'Project' }),
      description: projectId
        ? t('geo_hub.mode.project_hint', {
            defaultValue: 'Drop into a project — anchor, tilesets, viewpoints.',
          })
        : t('geo_hub.mode.project_hint_disabled', {
            defaultValue:
              'Open a project first to enable. Click to pick one from the Projects list.',
          }),
      href: projectId ? `/projects/${projectId}/geo` : '/projects',
      softDisabled: !projectId,
    },
    {
      key: 'development',
      label: t('geo_hub.mode.development', { defaultValue: 'Development' }),
      description: developmentId
        ? t('geo_hub.mode.development_hint', {
            defaultValue: 'Per-development map (PropDev only).',
          })
        : t('geo_hub.mode.development_hint_disabled', {
            defaultValue:
              'Open a development first to enable. Click to pick one from Property Developments.',
          }),
      href: developmentId
        ? `/property-dev/developments/${developmentId}/geo`
        : '/property-dev',
      softDisabled: !developmentId,
    },
  ];

  // Keyboard nav: skip nothing — every tab is reachable. We don't
  // pass disabledIds because soft-disabled tabs are still actionable
  // (they navigate to a picker), and the WAI-ARIA spec recommends
  // keeping aria-disabled tabs in the focus order so screen-reader
  // users can discover them.
  const onTabKeyDown = useTabKeyboardNav<GeoMode>({
    ids: GEO_MODES,
    activeId: current,
    onChange: (next) => {
      const item = items.find((it) => it.key === next);
      if (item) navigate(item.href);
    },
    orientation: 'horizontal',
  });

  return (
    <div
      className={[
        'inline-flex items-center gap-0.5 rounded-lg border border-border',
        'bg-surface-primary p-0.5 shadow-xs',
      ].join(' ')}
      role="tablist"
      aria-label={t('geo_hub.mode.tablist_label', { defaultValue: 'Map scope' })}
      onKeyDown={onTabKeyDown}
      data-testid="geo-tour-mode-picker"
    >
      {items.map((it) => {
        const active = it.key === current;
        const Icon = ICONS[it.key];
        return (
          <button
            key={it.key}
            type="button"
            role="tab"
            id={`geo-hub-mode-tab-${it.key}`}
            aria-selected={active}
            aria-controls={`geo-hub-mode-panel-${it.key}`}
            tabIndex={active ? 0 : -1}
            // Use aria-disabled (not the disabled attribute) so the
            // soft-disabled tabs stay keyboard-focusable and clickable.
            aria-disabled={it.softDisabled || undefined}
            title={it.description}
            onClick={() => {
              if (active) return;
              navigate(it.href);
            }}
            className={[
              'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium',
              'transition-colors duration-fast ease-oe',
              active
                ? 'bg-content-primary text-content-inverse shadow-sm'
                : it.softDisabled
                  ? 'text-content-quaternary hover:bg-surface-secondary hover:text-content-tertiary'
                  : 'text-content-secondary hover:bg-surface-secondary hover:text-content-primary',
            ].join(' ')}
            data-testid={`geo-mode-tab-${it.key}`}
          >
            <Icon size={13} strokeWidth={2} />
            {it.label}
            {it.softDisabled && (
              <span
                aria-hidden
                className="ml-0.5 inline-flex h-3.5 w-3.5 items-center justify-center rounded-full bg-amber-400/20 text-[9px] font-bold leading-none text-amber-700 ring-1 ring-amber-400/40 dark:text-amber-300"
                title={it.description}
              >
                ?
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export default GeoModePicker;
