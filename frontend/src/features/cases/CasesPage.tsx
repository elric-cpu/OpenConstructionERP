// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// CasesPage - the "Cases" hub.
//
// At /cases it lists every discovered case as a card (title, description, step
// count, time and any progress). At /cases/:playbookId it hands off to the
// PlaybookRunner stepper. One component serves both so the route stays a single
// lazy chunk.

import { useMemo, type ComponentType } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import clsx from 'clsx';
import {
  GraduationCap,
  ArrowRight,
  Clock,
  ListChecks,
  FileSpreadsheet,
  Ruler,
  ShieldCheck,
  Handshake,
  Layers,
  Sparkles,
  type LucideProps,
} from 'lucide-react';
import { Badge, EmptyState } from '@/shared/ui';
import { PLAYBOOKS, getPlaybook } from './playbooks';
import { PlaybookRunner } from './PlaybookRunner';
import { useCasesStore } from './useCasesStore';
import { completedCount } from './progress';
import type { Playbook } from './types';

const ICON_MAP: Record<string, ComponentType<LucideProps>> = {
  FileSpreadsheet,
  Ruler,
  ShieldCheck,
  Handshake,
  Layers,
  Sparkles,
  GraduationCap,
};

function iconFor(name: string | undefined): ComponentType<LucideProps> {
  if (name && name in ICON_MAP) return ICON_MAP[name]!;
  return Sparkles;
}

export function CasesPage() {
  const { playbookId } = useParams<{ playbookId?: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Detail mode: a specific case is open in the runner.
  if (playbookId) {
    const playbook = getPlaybook(playbookId);
    if (!playbook) {
      return (
        <div className="mx-auto max-w-3xl py-8">
          <EmptyState
            icon={<GraduationCap size={28} />}
            title={t('cases.not_found_title', { defaultValue: 'Case not found' })}
            description={t('cases.not_found_body', {
              defaultValue: 'This case does not exist or was removed. Browse the full list instead.',
            })}
            action={{
              label: t('cases.back_to_list', { defaultValue: 'All cases' }),
              onClick: () => navigate('/cases'),
            }}
          />
        </div>
      );
    }
    return <PlaybookRunner playbook={playbook} />;
  }

  // List mode.
  return <CasesList />;
}

function CasesList() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const runs = useCasesStore((s) => s.runs);

  // Best progress for a card = the furthest a user got on this case across any
  // run (unscoped or scoped to a sample project).
  const bestDoneFor = useMemo(() => {
    return (pb: Playbook): number => {
      let best = 0;
      for (const [k, prog] of Object.entries(runs)) {
        if (k === pb.id || k.startsWith(`${pb.id}::`)) {
          best = Math.max(best, completedCount(prog, pb));
        }
      }
      return best;
    };
  }, [runs]);

  return (
    <div className="mx-auto max-w-5xl space-y-6 animate-fade-in">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-oe-blue/10 text-oe-blue ring-1 ring-inset ring-oe-blue/20">
          <GraduationCap size={20} strokeWidth={1.9} />
        </span>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-content-primary">
            {t('cases.page_title', { defaultValue: 'Cases' })}
          </h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-content-secondary">
            {t('cases.page_subtitle', {
              defaultValue:
                'Guided, end-to-end playbooks that walk you through several modules in order. Pick a case, optionally choose a sample project to learn on, and follow each step.',
            })}
          </p>
        </div>
      </div>

      {/* ── Cards ───────────────────────────────────────────────────────── */}
      {PLAYBOOKS.length === 0 ? (
        <EmptyState
          icon={<GraduationCap size={28} />}
          title={t('cases.empty_title', { defaultValue: 'No cases yet' })}
          description={t('cases.empty_body', {
            defaultValue: 'Guided playbooks will appear here as they are added.',
          })}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PLAYBOOKS.map((pb) => {
            const Icon = iconFor(pb.icon);
            const total = pb.steps.length;
            const done = bestDoneFor(pb);
            const pct = total > 0 ? Math.round((done / total) * 100) : 0;
            const started = done > 0;
            const complete = total > 0 && done === total;
            return (
              <button
                key={pb.id}
                type="button"
                onClick={() => navigate(`/cases/${pb.id}`)}
                className={clsx(
                  'group flex h-full flex-col rounded-2xl border border-border-light bg-surface-primary p-5 text-left',
                  'shadow-xs transition-all hover:-translate-y-0.5 hover:border-oe-blue/40 hover:shadow-md',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40',
                )}
              >
                <div className="mb-3 flex items-center justify-between gap-2">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-oe-blue/15 to-oe-blue/5 text-oe-blue ring-1 ring-inset ring-oe-blue/15">
                    <Icon size={19} strokeWidth={1.9} />
                  </span>
                  {complete ? (
                    <Badge variant="success" size="sm">
                      {t('cases.card.done_badge', { defaultValue: 'Done' })}
                    </Badge>
                  ) : started ? (
                    <Badge variant="blue" size="sm">
                      {t('cases.card.in_progress', { defaultValue: 'In progress' })}
                    </Badge>
                  ) : null}
                </div>

                <h2 className="text-sm font-semibold leading-snug text-content-primary">
                  {t(pb.titleKey, { defaultValue: pb.titleDefault })}
                </h2>
                <p className="mt-1.5 flex-1 text-xs leading-relaxed text-content-secondary">
                  {t(pb.descKey, { defaultValue: pb.descDefault })}
                </p>

                {/* Progress bar (only once started) */}
                {started && (
                  <div className="mt-3">
                    <div
                      className="h-1.5 w-full overflow-hidden rounded-full bg-surface-secondary"
                      role="progressbar"
                      aria-valuemin={0}
                      aria-valuemax={total}
                      aria-valuenow={done}
                      aria-valuetext={t('cases.steps_progress', {
                        defaultValue: '{{done}} of {{total}} steps',
                        done,
                        total,
                      })}
                      aria-label={t('cases.progress_label', { defaultValue: 'Case progress' })}
                    >
                      <div
                        className="h-full rounded-full bg-oe-blue transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <p
                      aria-hidden="true"
                      className="mt-1 text-2xs text-content-tertiary tabular-nums"
                    >
                      {t('cases.steps_progress', {
                        defaultValue: '{{done}} of {{total}} steps',
                        done,
                        total,
                      })}
                    </p>
                  </div>
                )}

                {/* Footer meta + CTA */}
                <div className="mt-4 flex items-center justify-between gap-2 border-t border-border-light pt-3">
                  <div className="flex items-center gap-3 text-2xs text-content-tertiary">
                    <span className="inline-flex items-center gap-1">
                      <ListChecks size={12} aria-hidden="true" />
                      {t('cases.card.steps', { defaultValue: '{{count}} steps', count: total })}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <Clock size={12} aria-hidden="true" />
                      {t('cases.card.minutes', {
                        defaultValue: 'about {{count}} min',
                        count: pb.estMinutes,
                      })}
                    </span>
                  </div>
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-oe-blue">
                    {started
                      ? t('cases.card.continue', { defaultValue: 'Continue' })
                      : t('cases.card.open', { defaultValue: 'Open' })}
                    <ArrowRight
                      size={13}
                      className="transition-transform group-hover:translate-x-0.5"
                      aria-hidden="true"
                    />
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
