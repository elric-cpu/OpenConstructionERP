// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// No-match action modal: Custom position · Send to RFQ · Mark TBD.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X, FileEdit, Send, Clock, Loader2 } from 'lucide-react';
import { matchElementsApi } from './api';

interface Props {
  sessionId: string;
  groupKey: string;
  onClose: () => void;
  onDone: () => void;
}

type Action = 'custom' | 'rfq' | 'tbd';

export function NoMatchModal({ sessionId, groupKey, onClose, onDone }: Props) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [action, setAction] = useState<Action>('tbd');
  const [desc, setDesc] = useState('');
  const [unit, setUnit] = useState('m3');
  const [rate, setRate] = useState('');

  const mut = useMutation({
    mutationFn: () =>
      matchElementsApi.noMatch(sessionId, {
        group_key: groupKey,
        action,
        ...(action === 'custom'
          ? {
              custom_description: desc || undefined,
              custom_unit: unit || undefined,
              custom_rate: rate ? Number(rate) : undefined,
            }
          : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['match-groups', sessionId] });
      qc.invalidateQueries({ queryKey: ['match-detail', sessionId] });
      onDone();
    },
  });

  const opts: Array<{ value: Action; icon: typeof FileEdit; title: string; sub: string }> = [
    {
      value: 'custom',
      icon: FileEdit,
      title: t('match_elements.no_match.custom.title', 'Create custom position'),
      sub: t('match_elements.no_match.custom.sub', 'Add a project-only position with description, unit and rate.'),
    },
    {
      value: 'rfq',
      icon: Send,
      title: t('match_elements.no_match.rfq.title', 'Send to RFQ'),
      sub: t('match_elements.no_match.rfq.sub', 'Mark for tendering — request quotes from subcontractors.'),
    },
    {
      value: 'tbd',
      icon: Clock,
      title: t('match_elements.no_match.tbd.title', 'Mark TBD'),
      sub: t('match_elements.no_match.tbd.sub', 'Park the group; revisit later. Excluded from BOQ totals until resolved.'),
    },
  ];

  return (
    <div
      className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-slate-900 rounded-lg shadow-2xl w-full max-w-lg border border-slate-200 dark:border-slate-700"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <h3 className="text-base font-semibold">{t('match_elements.no_match.heading', 'No match — choose action')}</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800">
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="p-4 space-y-2">
          {opts.map((o) => (
            <label
              key={o.value}
              className={`block p-3 rounded border cursor-pointer transition ${
                action === o.value
                  ? 'border-indigo-400 bg-indigo-50 dark:bg-indigo-900/20'
                  : 'border-slate-200 dark:border-slate-700 hover:border-slate-300'
              }`}
            >
              <div className="flex items-start gap-2">
                <input
                  type="radio"
                  name="no-match-action"
                  value={o.value}
                  checked={action === o.value}
                  onChange={() => setAction(o.value)}
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <o.icon className="w-4 h-4" />
                    {o.title}
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">{o.sub}</div>
                </div>
              </div>
            </label>
          ))}

          {action === 'custom' && (
            <div className="border border-slate-200 dark:border-slate-700 rounded p-3 mt-3 space-y-2">
              <input
                type="text"
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                placeholder={t('match_elements.no_match.placeholder.description', 'Position description')}
                className="w-full px-2 py-1.5 text-sm rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
              />
              <div className="flex gap-2">
                <input
                  type="text"
                  value={unit}
                  onChange={(e) => setUnit(e.target.value)}
                  placeholder={t('match_elements.no_match.placeholder.unit', 'Unit')}
                  className="w-24 px-2 py-1.5 text-sm rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                />
                <input
                  type="number"
                  value={rate}
                  onChange={(e) => setRate(e.target.value)}
                  placeholder={t('match_elements.no_match.placeholder.rate', 'Unit rate')}
                  step="0.01"
                  className="flex-1 px-2 py-1.5 text-sm rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                />
              </div>
            </div>
          )}
        </div>

        <footer className="px-4 py-3 border-t border-slate-200 dark:border-slate-700 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm rounded border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            {t('match_elements.no_match.cancel', 'Cancel')}
          </button>
          <button
            onClick={() => mut.mutate()}
            disabled={mut.isPending}
            className="px-3 py-1.5 text-sm rounded bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            {mut.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            {t('match_elements.no_match.apply', 'Apply')}
          </button>
        </footer>
      </div>
    </div>
  );
}
