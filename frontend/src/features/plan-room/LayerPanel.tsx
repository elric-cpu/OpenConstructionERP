// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Layer legend + visibility toggles.
 *
 * One row per overlay source: a colour swatch, the layer name, its count on
 * this page and a checkbox that shows / hides that layer on the sheet. This is
 * the control a site engineer reads first - "what is on this drawing, and let
 * me turn the noise off".
 */

import { useTranslation } from 'react-i18next';
import { Eye, EyeOff, Layers } from 'lucide-react';
import clsx from 'clsx';
import { LAYERS, type LayerKey } from './layers';

interface Props {
  visibility: Record<LayerKey, boolean>;
  counts: Record<LayerKey, number>;
  onToggle: (key: LayerKey) => void;
}

export function LayerPanel({ visibility, counts, onToggle }: Props) {
  const { t } = useTranslation();

  return (
    <div className="rounded-xl border border-border-light bg-surface-primary p-3">
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-content-tertiary">
        <Layers size={13} />
        {t('plan_room.layers', { defaultValue: 'Layers' })}
      </h4>
      <ul className="space-y-0.5">
        {LAYERS.map((layer) => {
          const on = visibility[layer.key];
          const count = counts[layer.key] ?? 0;
          return (
            <li key={layer.key}>
              <button
                type="button"
                onClick={() => onToggle(layer.key)}
                aria-pressed={on}
                className={clsx(
                  'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm',
                  'hover:bg-surface-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40',
                  !on && 'opacity-50',
                )}
              >
                <span
                  className="h-3 w-3 shrink-0 rounded-sm border border-black/10"
                  style={{ backgroundColor: layer.color }}
                  aria-hidden
                />
                <span className="min-w-0 flex-1 truncate text-content-secondary">
                  {t(layer.labelKey, { defaultValue: layer.defaultLabel })}
                </span>
                <span className="shrink-0 text-2xs tabular-nums text-content-quaternary">
                  {count}
                </span>
                {on ? (
                  <Eye size={14} className="shrink-0 text-content-tertiary" />
                ) : (
                  <EyeOff size={14} className="shrink-0 text-content-quaternary" />
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
