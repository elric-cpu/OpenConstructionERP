// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * MatchProgressCard — live timeline UI for an in-flight match run.
 *
 * Polls ``GET /api/v1/match_elements/sessions/{id}/progress`` every
 * 800ms while a match is running and renders a 5-stage vertical
 * timeline with check / spin / dim icons + the per-stage counter +
 * elapsed time + estimated remaining. Stops polling immediately on
 * ``status: 'done'`` or ``status: 'error'``; calls ``onDone`` so the
 * parent can swap to the results pane.
 *
 * Why polling, not SSE: the run-match endpoint is already synchronous
 * (the request thread holds open for the full match duration), so
 * SSE would either compete for the same connection or require a
 * second worker. A 5-byte JSON poll every 800ms is cheap; the typical
 * match finishes in 30-180s so the user sees 40-200 polls per run.
 *
 * Why ``MatchSession.metadata_["progress"]`` instead of a dedicated
 * progress table: the metadata column already exists, requires no
 * migration, and the data is read-once-discard — no analytics value
 * after the match finishes. A new column would be over-engineering.
 *
 * Graceful degradation: when the endpoint 404s (older backend), the
 * card falls back to an undefined-progress shimmer rather than
 * breaking the wizard.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Building2,
  Check,
  Database,
  Loader2,
  Save,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';
import clsx from 'clsx';
import { matchElementsApi, type MatchProgress, type MatchStage } from './api';

interface Props {
  sessionId: string;
  /** Called once when the polled status flips to ``done``. */
  onDone: () => void;
  /** Called once when status flips to ``error`` (with the message). */
  onError?: (message: string) => void;
}

interface StageDef {
  id: MatchStage;
  idx: number;
  label: string;
  blurb: string;
  Icon: typeof Sparkles;
}

function formatElapsed(ms: number): string {
  if (ms < 0) return '0s';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem.toString().padStart(2, '0')}s`;
}

/** Estimate seconds remaining from the per-group cadence so far.
 *  Returns null until we have at least 2 groups done and 2s of
 *  history — anything earlier would be wildly inaccurate. */
function estimateRemaining(
  startedMs: number,
  nowMs: number,
  done: number,
  total: number,
): number | null {
  if (total <= 0 || done < 2) return null;
  const elapsed = nowMs - startedMs;
  if (elapsed < 2000) return null;
  const perGroupMs = elapsed / done;
  const remainingMs = perGroupMs * (total - done);
  return Math.round(remainingMs / 1000);
}

export function MatchProgressCard({ sessionId, onDone, onError }: Props) {
  const { t } = useTranslation();
  const firedDoneRef = useRef(false);
  const firedErrorRef = useRef(false);
  // Sticks at the last frame's value so the bar doesn't jitter back
  // to zero on the brief idle → init transition (server takes one
  // tick to write the first progress snapshot).
  const [lastNonIdle, setLastNonIdle] = useState<MatchProgress | null>(null);

  const progressQ = useQuery({
    queryKey: ['match-progress', sessionId],
    queryFn: () => matchElementsApi.getProgress(sessionId),
    // Poll while the match is running; the queryFn body itself
    // detects the terminal states and short-circuits further polls.
    refetchInterval: (q) => {
      const data = q.state.data as MatchProgress | undefined;
      if (!data) return 800;
      if (data.status === 'done' || data.status === 'error') return false;
      return 800;
    },
    refetchIntervalInBackground: true,
    // Don't hammer the endpoint on retries — one fast retry is
    // enough to absorb a transient 502 mid-deploy.
    retry: 1,
    // The data is per-session and short-lived; never serve a stale
    // poll result from cache when the user re-opens the page.
    staleTime: 0,
  });

  // 404 = older backend that predates the progress column. The card
  // gracefully degrades to a generic "match running…" shimmer rather
  // than blowing up the wizard.
  const isUnsupported = useMemo(() => {
    const err = progressQ.error as Error | null;
    return err?.message?.startsWith('404 ') ?? false;
  }, [progressQ.error]);

  const progress: MatchProgress | undefined = progressQ.data;

  // Keep a sticky copy of the most-recent non-idle frame so brief
  // idle-blink between rest and init transitions doesn't reset the
  // visible bar to zero. Without this the user sees the timeline
  // pop back to "Loading…" the instant we cross the done boundary.
  useEffect(() => {
    if (progress && progress.status !== 'idle') {
      setLastNonIdle(progress);
    }
  }, [progress]);

  // Fire the parent callback exactly once on terminal status.
  useEffect(() => {
    if (!progress) return;
    if (progress.status === 'done' && !firedDoneRef.current) {
      firedDoneRef.current = true;
      // Tiny delay so the user sees the "all checks green" frame
      // for ~600ms before the results pane swaps in. Plays into the
      // "satisfying finish" feeling Artem asked for ("красивый").
      const handle = window.setTimeout(onDone, 600);
      return () => window.clearTimeout(handle);
    }
    if (progress.status === 'error' && !firedErrorRef.current) {
      firedErrorRef.current = true;
      onError?.(progress.error || 'Match failed');
    }
    return undefined;
  }, [progress, onDone, onError]);

  const startedAt = useMemo(() => {
    const iso = progress?.started_at ?? lastNonIdle?.started_at ?? null;
    return iso ? new Date(iso).getTime() : null;
  }, [progress, lastNonIdle]);

  // Tick clock so the elapsed counter updates every second even
  // when the underlying poll only fires every 800ms.
  const [now, setNow] = useState<number>(Date.now());
  useEffect(() => {
    if (progress?.status === 'done' || progress?.status === 'error') return;
    const handle = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(handle);
  }, [progress?.status]);

  const stages: StageDef[] = useMemo(
    () => [
      {
        id: 'init',
        idx: 1,
        label: t('match_progress.stage_init', 'Preparing session'),
        blurb: t(
          'match_progress.stage_init_blurb',
          'Loading project context, region, and catalogue binding',
        ),
        Icon: Sparkles,
      },
      {
        id: 'elements',
        idx: 2,
        label: t('match_progress.stage_elements', 'Loading source elements'),
        blurb: t(
          'match_progress.stage_elements_blurb',
          'Reading BIM elements / Excel rows / pasted text',
        ),
        Icon: Building2,
      },
      {
        id: 'ranking',
        idx: 3,
        label: t('match_progress.stage_ranking', 'Ranking candidates'),
        blurb: t(
          'match_progress.stage_ranking_blurb',
          'Vector search + sparse fusion + region/unit boost + rerank',
        ),
        Icon: Database,
      },
      {
        id: 'save',
        idx: 4,
        label: t('match_progress.stage_save', 'Persisting results'),
        blurb: t(
          'match_progress.stage_save_blurb',
          'Saving suggestions and auto-confirming high-confidence picks',
        ),
        Icon: Save,
      },
      {
        id: 'done',
        idx: 5,
        label: t('match_progress.stage_done', 'Done'),
        blurb: t(
          'match_progress.stage_done_blurb',
          'Results are ready — opening the review panel',
        ),
        Icon: Check,
      },
    ],
    [t],
  );

  const view: MatchProgress = progress ??
    lastNonIdle ?? {
      stage: 'init',
      stage_idx: 1,
      total_stages: 5,
      groups_done: 0,
      groups_total: 0,
      status: 'running',
      started_at: null,
      updated_at: null,
      error: null,
    };

  const elapsedMs = startedAt ? Math.max(0, now - startedAt) : 0;
  const remainingSec =
    startedAt && view.stage === 'ranking'
      ? estimateRemaining(startedAt, now, view.groups_done, view.groups_total)
      : null;

  const overallPct = (() => {
    // Stage weights: init 5%, elements 10%, ranking 75%, save 5%, done 5%.
    // The ranking band uses groups_done/groups_total to fill smoothly.
    if (view.status === 'done') return 100;
    if (view.stage === 'init') return 3;
    if (view.stage === 'elements') return 10;
    if (view.stage === 'save') return 95;
    if (view.stage === 'ranking') {
      const inner =
        view.groups_total > 0 ? view.groups_done / view.groups_total : 0;
      return 15 + Math.round(inner * 75);
    }
    return 0;
  })();

  const isError = view.status === 'error';
  const isDone = view.status === 'done';

  if (isUnsupported) {
    // Graceful fallback for older backends that don't expose
    // /progress yet — show a plain shimmer so the wizard isn't broken
    // mid-deploy. Disappears as soon as the parent flips to results.
    return (
      <div className="rounded-2xl border border-border bg-surface-primary shadow-sm p-6 max-w-3xl mx-auto mt-4">
        <div className="flex items-center gap-3 text-content-secondary">
          <Loader2 className="w-5 h-5 animate-spin text-indigo-600" />
          <span className="text-sm">
            {t(
              'match_progress.legacy_running',
              'Matching is running on the server. This may take 30s–3min depending on the model size.',
            )}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={clsx(
        'rounded-2xl border bg-surface-primary shadow-sm p-5 sm:p-7 max-w-3xl mx-auto mt-4 transition-opacity duration-500',
        isError ? 'border-rose-200 dark:border-rose-800/60' : 'border-border',
        isDone && 'opacity-90',
      )}
      data-testid="match-progress-card"
      data-stage={view.stage}
      data-status={view.status}
    >
      {/* Header — title + elapsed + ETA */}
      <header className="flex items-start justify-between gap-3 mb-5">
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold tracking-tight text-content-primary inline-flex items-center gap-2">
            {isError ? (
              <>
                <TriangleAlert className="w-5 h-5 text-rose-600" />
                {t('match_progress.title_error', 'Match failed')}
              </>
            ) : isDone ? (
              <>
                <span className="w-6 h-6 rounded-full bg-emerald-500 text-white inline-flex items-center justify-center shadow-sm shadow-emerald-500/40">
                  <Check className="w-4 h-4" strokeWidth={3} />
                </span>
                {t('match_progress.title_done', 'Match complete')}
              </>
            ) : (
              <>
                <Loader2 className="w-5 h-5 animate-spin text-indigo-600" />
                {t('match_progress.title_running', 'Matching in progress')}
              </>
            )}
          </h3>
          <p className="text-xs text-content-tertiary mt-1.5">
            {isError
              ? view.error ?? t('match_progress.subtitle_error', 'See the toast for details.')
              : isDone
              ? t(
                  'match_progress.subtitle_done',
                  'All stages green — handing over to the review panel.',
                )
              : t(
                  'match_progress.subtitle_running',
                  'Polling the server every 800ms. Safe to leave open in a tab.',
                )}
          </p>
        </div>
        <div className="shrink-0 text-right tabular-nums">
          <div className="text-[11px] uppercase tracking-[0.14em] text-content-tertiary font-semibold">
            {t('match_progress.elapsed', 'Elapsed')}
          </div>
          <div className="text-sm font-semibold text-content-primary">
            {formatElapsed(elapsedMs)}
          </div>
          {remainingSec !== null && remainingSec > 0 && (
            <div className="text-[11px] text-content-tertiary mt-0.5">
              {t('match_progress.eta', '~{{s}}s remaining', { s: remainingSec })}
            </div>
          )}
        </div>
      </header>

      {/* Overall bar */}
      <div
        className={clsx(
          'h-1.5 rounded-full mb-5 overflow-hidden',
          isError ? 'bg-rose-100 dark:bg-rose-950/40' : 'bg-surface-secondary',
        )}
      >
        <div
          className={clsx(
            'h-full rounded-full transition-all duration-500 ease-out',
            isError
              ? 'bg-rose-500'
              : isDone
              ? 'bg-emerald-500'
              : 'bg-gradient-to-r from-indigo-500 to-indigo-700',
          )}
          style={{ width: `${overallPct}%` }}
          aria-valuenow={overallPct}
          aria-valuemin={0}
          aria-valuemax={100}
          role="progressbar"
          aria-label={t('match_progress.overall_aria', 'Overall match progress')}
        />
      </div>

      {/* Vertical timeline */}
      <ol className="space-y-3.5">
        {stages.map((s) => {
          const isCurrent = view.stage === s.id && !isError;
          const isPast =
            !isError && view.stage_idx > s.idx;
          const isFinalStageGreen = isDone && s.id === 'done';
          const stageBadge = (() => {
            if (isError && view.stage_idx >= s.idx) {
              return (
                <span className="w-7 h-7 rounded-full bg-rose-100 dark:bg-rose-950/40 text-rose-600 dark:text-rose-300 inline-flex items-center justify-center ring-2 ring-rose-200 dark:ring-rose-800/40">
                  <TriangleAlert className="w-4 h-4" />
                </span>
              );
            }
            if (isPast || isFinalStageGreen) {
              return (
                <span className="w-7 h-7 rounded-full bg-emerald-500 text-white inline-flex items-center justify-center shadow-sm shadow-emerald-500/40">
                  <Check className="w-4 h-4" strokeWidth={3} />
                </span>
              );
            }
            if (isCurrent) {
              return (
                <span className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-indigo-700 text-white inline-flex items-center justify-center shadow-md shadow-indigo-500/40 ring-2 ring-indigo-200 dark:ring-indigo-900/40">
                  <Loader2 className="w-4 h-4 animate-spin" strokeWidth={2.5} />
                </span>
              );
            }
            return (
              <span className="w-7 h-7 rounded-full bg-surface-secondary text-content-tertiary inline-flex items-center justify-center border-2 border-border">
                <s.Icon className="w-3.5 h-3.5" strokeWidth={1.75} />
              </span>
            );
          })();
          const showCounter =
            s.id === 'ranking' && (isCurrent || isPast) && view.groups_total > 0;
          return (
            <li
              key={s.id}
              className={clsx(
                'flex items-start gap-3 transition-opacity duration-300',
                !isCurrent && !isPast && !isFinalStageGreen && 'opacity-50',
              )}
              data-stage-row={s.id}
              data-active={isCurrent}
              data-done={isPast || isFinalStageGreen}
            >
              {stageBadge}
              <div className="min-w-0 flex-1 pt-0.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={clsx(
                      'text-sm transition-colors',
                      isCurrent
                        ? 'font-semibold text-content-primary'
                        : isPast || isFinalStageGreen
                        ? 'font-medium text-content-secondary'
                        : 'text-content-tertiary',
                    )}
                  >
                    {s.label}
                  </span>
                  {showCounter && (
                    <span
                      className={clsx(
                        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold tabular-nums',
                        isCurrent
                          ? 'bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 border border-indigo-200/60 dark:border-indigo-800/40'
                          : 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200/60 dark:border-emerald-800/40',
                      )}
                    >
                      {view.groups_done} / {view.groups_total}
                    </span>
                  )}
                </div>
                <p className="text-xs text-content-tertiary mt-0.5 leading-snug">
                  {s.blurb}
                </p>
                {/* Per-stage thin bar — only on the active ranking stage,
                    where group-by-group progress is meaningful. */}
                {showCounter && isCurrent && view.groups_total > 0 && (
                  <div className="mt-2 h-1 rounded-full bg-surface-secondary overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-indigo-500 to-indigo-700 transition-all duration-500"
                      style={{
                        width: `${Math.round(
                          (view.groups_done / view.groups_total) * 100,
                        )}%`,
                      }}
                    />
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
