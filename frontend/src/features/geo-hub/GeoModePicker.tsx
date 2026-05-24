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

  const items: Array<{
    key: GeoMode;
    label: string;
    description: string;
    href: string | null;
  }> = [
    {
      key: 'global',
      label: t('geo_hub.mode.global', { defaultValue: 'Global' }),
      description: t('geo_hub.mode.global_hint', {
        defaultValue: 'All projects on one earth-scale map.',
      }),
      href: '/geo',
    },
    {
      key: 'project',
      label: t('geo_hub.mode.project', { defaultValue: 'Project' }),
      description: t('geo_hub.mode.project_hint', {
        defaultValue: 'Drop into a project — anchor, tilesets, viewpoints.',
      }),
      href: projectId ? `/projects/${projectId}/geo` : null,
    },
    {
      key: 'development',
      label: t('geo_hub.mode.development', { defaultValue: 'Development' }),
      description: t('geo_hub.mode.development_hint', {
        defaultValue: 'Per-development map (PropDev only).',
      }),
      href: developmentId ? `/property-dev/developments/${developmentId}/geo` : null,
    },
  ];

  const disabledIds = items.filter((it) => !it.href).map((it) => it.key);

  const onTabKeyDown = useTabKeyboardNav<GeoMode>({
    ids: GEO_MODES,
    activeId: current,
    onChange: (next) => {
      const item = items.find((it) => it.key === next);
      if (item?.href) navigate(item.href);
    },
    orientation: 'horizontal',
    disabledIds,
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
        const disabled = !it.href || active;
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
            disabled={!it.href}
            title={it.description}
            onClick={() => {
              if (it.href && !active) navigate(it.href);
            }}
            className={[
              'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium',
              'transition-colors duration-fast ease-oe',
              active
                ? 'bg-content-primary text-content-inverse shadow-sm'
                : disabled
                  ? 'cursor-not-allowed text-content-quaternary'
                  : 'text-content-secondary hover:bg-surface-secondary hover:text-content-primary',
            ].join(' ')}
          >
            <Icon size={13} strokeWidth={2} />
            {it.label}
          </button>
        );
      })}
    </div>
  );
}

export default GeoModePicker;
