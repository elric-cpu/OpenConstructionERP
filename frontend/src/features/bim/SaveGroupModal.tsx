/**
 * SaveGroupModal — turn the user's current viewer filter into a saved
 * `BIMElementGroup`.  Tiny modal: name + description + dynamic/static toggle.
 *
 * The actual filter criteria + element subset are passed in by the parent
 * (BIMPage) — this component is just the form.  Submit calls
 * `createElementGroup`, the backend resolves the membership and returns
 * a `BIMElementGroup` row that the parent caches.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X, Save, Loader2, Bookmark } from 'lucide-react';
import {
  createElementGroup,
  resolveElementUUID,
  type BIMGroupFilterCriteria,
  type BIMElementGroup,
} from './api';
import type { BIMElementData } from '@/shared/ui/BIMViewer';
import { GROUP_COLORS } from './BIMGroupsPanel';
import { useToastStore } from '@/stores/useToastStore';

interface SaveGroupModalProps {
  projectId: string;
  modelId: string | null;
  /** Filter criteria captured from the current state of BIMFilterPanel. */
  filterCriteria: BIMGroupFilterCriteria;
  /** Selected/visible element rows — used as a static snapshot when the
   *  user chooses "static" mode, ignored in dynamic mode.  Full rows
   *  (not just ids) so client-side stub ids (`_unmatched_N`) can be
   *  resolved to real BIMElement UUIDs before the group is persisted —
   *  storing stub ids verbatim makes the group unresolvable on reload. */
  elements: BIMElementData[];
  /** Live count of elements that match the filter right now — shown in
   *  the modal so the user knows how many things they're saving. */
  visibleCount: number;
  onClose: () => void;
  onSaved?: (group: BIMElementGroup) => void;
}

export default function SaveGroupModal({
  projectId,
  modelId,
  filterCriteria,
  elements,
  visibleCount,
  onClose,
  onSaved,
}: SaveGroupModalProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  // Dynamic mode means "re-resolve from filter criteria every time".  If the
  // criteria are empty (e.g. the user only Ctrl+selected elements without
  // filtering), dynamic would resolve to *every* element in the project —
  // never what's wanted.  Default to static and disable dynamic in that case.
  const criteriaEmpty =
    !filterCriteria || Object.keys(filterCriteria).length === 0;
  const [isDynamic, setIsDynamic] = useState(false);
  const dynamicAllowed = !criteriaEmpty;
  const effectiveDynamic = isDynamic && dynamicAllowed;
  const [color, setColor] = useState('#2979ff');

  const createMut = useMutation({
    mutationFn: async () => {
      // Static mode persists explicit element ids.  Resolve every
      // selected row to a real BIMElement UUID first — the viewer's
      // selection can carry client-side stub ids (`_unmatched_N`) or raw
      // Revit numeric ids for meshes the backend never materialised, and
      // storing those verbatim makes the group's members unresolvable on
      // reload (the long-standing "group save broken" bug). Dynamic mode
      // relies on filter criteria, so no id resolution is needed there.
      let resolvedIds: string[] | undefined;
      if (!effectiveDynamic) {
        resolvedIds = [];
        for (const el of elements) {
          if (!modelId) {
            // No active model — fall back to whatever id we have. Static
            // groups without a model are rare (cross-model selections).
            resolvedIds.push(el.id);
            continue;
          }
          resolvedIds.push(await resolveElementUUID(modelId, el));
        }
      }
      return createElementGroup(projectId, {
        name: name.trim(),
        description: description.trim() || undefined,
        model_id: modelId,
        is_dynamic: effectiveDynamic,
        filter_criteria: filterCriteria,
        element_ids: resolvedIds,
        color,
      });
    },
    onSuccess: (group) => {
      addToast({
        type: 'success',
        title: t('bim.group_saved_title', { defaultValue: 'Group saved' }),
        message: t('bim.group_saved_msg', {
          defaultValue: '"{{name}}" — {{count}} elements',
          name: group.name,
          count: group.element_count,
        }),
      });
      qc.invalidateQueries({
        predicate: (q) => {
          const k = q.queryKey;
          return Array.isArray(k) && k[0] === 'bim-element-groups' && k[1] === projectId;
        },
      });
      onSaved?.(group);
      onClose();
    },
    onError: (err: Error) => {
      addToast({
        type: 'error',
        title: t('common.error', { defaultValue: 'Error' }),
        message: err.message || String(err),
      });
    },
  });

  const canSave = name.trim().length > 0 && !createMut.isPending;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-lg p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="bg-surface-primary rounded-xl shadow-2xl w-full max-w-md flex flex-col border border-border-light"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-border-light shrink-0">
          <div className="flex items-center gap-2">
            <Bookmark size={16} className="text-oe-blue" />
            <h2 className="text-sm font-semibold text-content-primary">
              {t('bim.save_group_title', { defaultValue: 'Save current filter as group' })}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded text-content-tertiary hover:text-content-primary hover:bg-surface-secondary"
            aria-label={t('common.close', { defaultValue: 'Close' })}
          >
            <X size={16} />
          </button>
        </div>

        {/* Form */}
        <div className="p-5 space-y-3">
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-content-tertiary mb-1">
              {t('bim.group_name', { defaultValue: 'Group name' })}
              <span className="text-rose-500 ml-0.5">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              placeholder={t('bim.group_name_placeholder', {
                defaultValue: 'e.g. Walls on Level 1',
              })}
              className="w-full px-2 py-1.5 text-sm rounded border border-border-light bg-surface-primary focus:outline-none focus:ring-1 focus:ring-oe-blue"
            />
          </div>

          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-content-tertiary mb-1">
              {t('bim.group_description', { defaultValue: 'Description (optional)' })}
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full px-2 py-1.5 text-sm rounded border border-border-light bg-surface-primary focus:outline-none focus:ring-1 focus:ring-oe-blue resize-none"
            />
          </div>

          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-content-tertiary mb-1.5">
              {t('bim.group_color', { defaultValue: 'Color' })}
            </label>
            <div className="flex items-center gap-1.5">
              {GROUP_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={`h-6 w-6 rounded-full border-2 transition-transform hover:scale-110 ${
                    color === c
                      ? 'border-content-primary scale-105'
                      : 'border-transparent'
                  }`}
                  style={{ background: c }}
                  title={c}
                />
              ))}
            </div>
          </div>

          {/* Dynamic vs static toggle */}
          <div className="rounded-md border border-border-light p-3 space-y-2">
            <label
              className={`flex items-start gap-2 ${
                dynamicAllowed ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'
              }`}
              title={
                dynamicAllowed
                  ? undefined
                  : t('bim.group_dynamic_disabled_title', {
                      defaultValue:
                        'Dynamic mode needs at least one filter (storey, type, or search). Apply a filter to enable it.',
                    })
              }
            >
              <input
                type="radio"
                checked={effectiveDynamic}
                onChange={() => setIsDynamic(true)}
                disabled={!dynamicAllowed}
                className="mt-0.5"
              />
              <div className="text-xs">
                <div className="font-semibold text-content-primary">
                  {t('bim.group_dynamic', { defaultValue: 'Dynamic' })}
                </div>
                <div className="text-content-tertiary text-[11px]">
                  {dynamicAllowed
                    ? t('bim.group_dynamic_desc', {
                        defaultValue:
                          'Re-compute members from the filter every time. Auto-updates when the model is re-imported.',
                      })
                    : t('bim.group_dynamic_desc_disabled', {
                        defaultValue:
                          'Disabled — no filter is active. Apply a storey, type or search filter to enable dynamic mode.',
                      })}
                </div>
              </div>
            </label>
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="radio"
                checked={!effectiveDynamic}
                onChange={() => setIsDynamic(false)}
                className="mt-0.5"
              />
              <div className="text-xs">
                <div className="font-semibold text-content-primary">
                  {t('bim.group_static', { defaultValue: 'Static' })}
                </div>
                <div className="text-content-tertiary text-[11px]">
                  {t('bim.group_static_desc', {
                    defaultValue:
                      'Snapshot the current {{count}} elements. Membership stays frozen even if the model changes.',
                    count: elements.length,
                  })}
                </div>
              </div>
            </label>
          </div>

          {/* Counts pill — show what will actually be saved */}
          <div className="flex items-center gap-2 text-[11px] text-content-tertiary">
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-oe-blue/10 text-oe-blue font-medium">
              {(effectiveDynamic ? visibleCount : elements.length).toLocaleString()}{' '}
              {t('bim.elements', { defaultValue: 'elements' })}
            </span>
            {modelId && (
              <span>{t('bim.in_current_model', { defaultValue: 'in this model' })}</span>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border-light shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-content-tertiary hover:text-content-primary px-2"
          >
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </button>
          <button
            type="button"
            onClick={() => createMut.mutate()}
            disabled={!canSave}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-oe-blue text-white hover:bg-oe-blue-dark disabled:opacity-50"
          >
            {createMut.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Save size={12} />
            )}
            {t('bim.save_group', { defaultValue: 'Save group' })}
          </button>
        </div>
      </div>
    </div>
  );
}
