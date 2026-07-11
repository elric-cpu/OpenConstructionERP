// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * DashboardLayoutManager — drag-to-reorder + show/hide control for the
 * dashboard widgets. One shared component, used in two places:
 *   • inline on the dashboard (the "Customize" panel), applying live
 *   • in Settings → Dashboard
 *
 * State lives in `useDashboardLayoutStore` (localStorage-persisted), so a
 * change here is reflected on the dashboard immediately and survives reloads.
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  closestCenter,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, Eye, EyeOff, RotateCcw, Check } from 'lucide-react';
import { Button } from '@/shared/ui';
import {
  useDashboardLayoutStore,
  reconcileOrder,
} from '@/stores/useDashboardLayoutStore';
import {
  DASHBOARD_WIDGET_IDS,
  DASHBOARD_WIDGET_BY_ID,
} from './widgetRegistry';

interface RowProps {
  id: string;
  hidden: boolean;
  onToggle: (id: string) => void;
}

function WidgetRow({ id, hidden, onToggle }: RowProps) {
  const { t } = useTranslation();
  const meta = DASHBOARD_WIDGET_BY_ID[id];
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });

  if (!meta) return null;
  const Icon = meta.icon;

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.55 : undefined,
      }}
      className={`group flex items-center gap-3 rounded-lg border bg-surface-primary px-3 py-2.5 transition-colors ${
        isDragging
          ? 'border-oe-blue/50 shadow-md'
          : 'border-border-light hover:border-border-medium'
      } ${hidden ? 'opacity-60' : ''}`}
      data-testid={`dash-widget-row-${id}`}
    >
      {/* Drag handle */}
      <button
        type="button"
        aria-label={t('dashboard.layout.drag', { defaultValue: 'Drag to reorder' })}
        className="shrink-0 cursor-grab touch-none rounded-md p-1 text-content-quaternary hover:bg-surface-secondary hover:text-content-secondary active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <GripVertical size={16} strokeWidth={2} />
      </button>

      {/* Icon */}
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
          hidden
            ? 'bg-surface-secondary text-content-quaternary'
            : 'bg-oe-blue/10 text-oe-blue'
        }`}
      >
        <Icon size={16} strokeWidth={2} />
      </span>

      {/* Label + description */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-content-primary">
          {t(meta.labelKey, { defaultValue: meta.labelDefault })}
        </p>
        <p className="truncate text-xs text-content-tertiary">
          {t(meta.descKey, { defaultValue: meta.descDefault })}
        </p>
      </div>

      {/* Show / hide toggle */}
      <button
        type="button"
        onClick={() => onToggle(id)}
        aria-pressed={!hidden}
        aria-label={
          hidden
            ? t('dashboard.layout.show', { defaultValue: 'Show widget' })
            : t('dashboard.layout.hide', { defaultValue: 'Hide widget' })
        }
        title={
          hidden
            ? t('dashboard.layout.show', { defaultValue: 'Show widget' })
            : t('dashboard.layout.hide', { defaultValue: 'Hide widget' })
        }
        className={`shrink-0 rounded-md p-1.5 transition-colors ${
          hidden
            ? 'text-content-quaternary hover:bg-surface-secondary hover:text-content-secondary'
            : 'text-oe-blue hover:bg-oe-blue/10'
        }`}
      >
        {hidden ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}

interface ManagerProps {
  /** Render a "Done" button that calls this (used by the inline panel). */
  onClose?: () => void;
  className?: string;
}

export function DashboardLayoutManager({ onClose, className }: ManagerProps) {
  const { t } = useTranslation();
  const order = useDashboardLayoutStore((s) => s.order);
  const hidden = useDashboardLayoutStore((s) => s.hidden);
  const setOrder = useDashboardLayoutStore((s) => s.setOrder);
  const toggleHidden = useDashboardLayoutStore((s) => s.toggleHidden);
  const reset = useDashboardLayoutStore((s) => s.reset);

  const resolved = useMemo(
    () => reconcileOrder(order, DASHBOARD_WIDGET_IDS),
    [order],
  );

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const hiddenCount = resolved.filter((id) => hidden.includes(id)).length;
  const isCustomised = order.length > 0 || hidden.length > 0;

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = resolved.indexOf(String(active.id));
    const to = resolved.indexOf(String(over.id));
    if (from === -1 || to === -1) return;
    setOrder(arrayMove(resolved, from, to));
  }

  return (
    <div className={className}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-xs text-content-tertiary">
          {t('dashboard.layout.help', {
            defaultValue:
              'Drag to reorder. Toggle the eye to show or hide a section. Changes apply instantly and are saved to this browser.',
          })}
        </p>
        {onClose && (
          <Button
            variant="primary"
            size="sm"
            icon={<Check size={14} />}
            onClick={onClose}
          >
            {t('common.done', { defaultValue: 'Done' })}
          </Button>
        )}
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext items={resolved} strategy={verticalListSortingStrategy}>
          <div className="flex flex-col gap-2">
            {resolved.map((id) => (
              <WidgetRow
                key={id}
                id={id}
                hidden={hidden.includes(id)}
                onToggle={toggleHidden}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-border-light pt-3">
        <span className="text-xs text-content-tertiary">
          {hiddenCount > 0
            ? t('dashboard.layout.hidden_count', {
                defaultValue: '{{count}} hidden',
                count: hiddenCount,
              })
            : t('dashboard.layout.all_visible', {
                defaultValue: 'All sections visible',
              })}
        </span>
        <Button
          variant="ghost"
          size="sm"
          icon={<RotateCcw size={14} />}
          disabled={!isCustomised}
          onClick={reset}
        >
          {t('dashboard.layout.reset', { defaultValue: 'Reset to default' })}
        </Button>
      </div>
    </div>
  );
}

export default DashboardLayoutManager;
