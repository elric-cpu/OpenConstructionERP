/**
 * Coordination Hub Dashboard — top-level "Model Coordination" landing page.
 *
 * Unifies federations + clashes + smart views + rule packs + BCF activity
 * into one project-scoped view. Built as a thin composition over three
 * sub-components (KPI cards, trade matrix, timeline) so each can be
 * tested in isolation.
 *
 * Visual language: glass cards on a soft gradient backdrop with
 * per-block colour accents (rose / amber / emerald / sky) so the four
 * health signals are readable at a glance, not just a wall of numbers.
 *
 * Empty state: when no project is in the global project-context store
 * we render an EmptyState with a CTA back to the projects list rather
 * than showing zeros against an undefined id.
 */

import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  RefreshCw,
  Radar,
  Layers,
  SlidersHorizontal,
  Eye,
  Sparkles,
  Activity,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { DateDisplay } from '@/shared/ui/DateDisplay';
import { RecoveryCard } from '@/shared/ui';
import { RequiresProject } from '@/shared/auth/RequiresProject';
import { useActiveProjectProfile } from '@/features/projects/useProjectProfile';
import {
  fetchCoordinationDashboard,
  fetchCoordinationTimeline,
  fetchTradeMatrix,
} from './api';
import { CoordinationKPICards } from './CoordinationKPICards';
import { CoordinationTimeline } from './CoordinationTimeline';
import { CoordinationTradeMatrix } from './CoordinationTradeMatrix';
import type { CoordinationDashboard } from './types';

/** Tiny presentational wrapper — gives any section the same glass
 *  treatment as the KPI row above. Two faint accent strokes (top
 *  gradient border + radial corner glow) keep panels visually
 *  consistent without re-implementing them per-component. */
function GlassPanel({
  testId,
  title,
  subtitle,
  icon,
  action,
  children,
}: {
  testId?: string;
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section
      data-testid={testId}
      className="relative overflow-hidden rounded-2xl border border-white/40 bg-white/60 backdrop-blur-xl shadow-lg shadow-slate-900/[0.04] dark:border-white/5 dark:bg-slate-900/40 dark:shadow-slate-950/30"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -top-20 -right-20 h-48 w-48 rounded-full bg-gradient-radial from-sky-500/15 to-transparent blur-3xl"
      />
      <div className="relative flex items-start justify-between gap-3 border-b border-white/40 px-5 py-4 dark:border-white/5">
        <div className="flex items-start gap-3">
          {icon ? (
            <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-content-secondary dark:bg-slate-800">
              {icon}
            </div>
          ) : null}
          <div>
            <h2 className="text-sm font-semibold text-content-primary">
              {title}
            </h2>
            {subtitle ? (
              <p className="text-xs text-content-tertiary">{subtitle}</p>
            ) : null}
          </div>
        </div>
        {action}
      </div>
      <div className="relative p-5">{children}</div>
    </section>
  );
}

/** Project-health banner shown directly above KPI cards. Reads the
 *  dashboard payload and decides traffic-light tone:
 *    • green   — no open clashes, no failing rules
 *    • amber   — some open clashes or failing rules but under threshold
 *    • rose    — open clashes ≥ 50 OR failing rules ≥ 5 (matches the
 *                default thresholds shipped by coordination_hub) */
function HealthBanner({ data }: { data: CoordinationDashboard | undefined }) {
  const { t } = useTranslation();
  if (!data) return null;
  const open = data.clashes.open_count;
  const failing = data.rule_packs.last_check_fail_count;
  const isWarn = open >= 1 || failing >= 1;
  const isError = open >= 50 || failing >= 5;

  const tone = isError ? 'rose' : isWarn ? 'amber' : 'emerald';
  const palette = {
    emerald: {
      ring: 'ring-emerald-400/20',
      bg: 'from-emerald-50 to-teal-50/40 dark:from-emerald-500/10 dark:to-teal-500/5',
      icon: 'text-emerald-600 dark:text-emerald-400',
      Icon: CheckCircle2,
      title: t('coordination.health_ok_title', { defaultValue: 'All clear' }),
      msg: t('coordination.health_ok_msg', {
        defaultValue: 'No open clashes, all rule packs passing.',
      }),
    },
    amber: {
      ring: 'ring-amber-400/20',
      bg: 'from-amber-50 to-orange-50/40 dark:from-amber-500/10 dark:to-orange-500/5',
      icon: 'text-amber-600 dark:text-amber-400',
      Icon: Activity,
      title: t('coordination.health_attention_title', {
        defaultValue: 'Coordination in progress',
      }),
      msg: t('coordination.health_attention_msg', {
        defaultValue:
          '{{open}} open clash(es), {{fail}} failing rule(s). Within threshold — keep iterating.',
        open,
        fail: failing,
      }),
    },
    rose: {
      ring: 'ring-rose-400/30',
      bg: 'from-rose-50 to-orange-50/50 dark:from-rose-500/10 dark:to-orange-500/5',
      icon: 'text-rose-600 dark:text-rose-400',
      Icon: AlertTriangle,
      title: t('coordination.health_alert_title', {
        defaultValue: 'Attention required',
      }),
      msg: t('coordination.health_alert_msg', {
        defaultValue:
          '{{open}} open clash(es), {{fail}} failing rule(s). Above standard threshold — schedule a coordination meeting.',
        open,
        fail: failing,
      }),
    },
  }[tone];

  const Icon = palette.Icon;

  return (
    <div
      data-testid="coordination-health-banner"
      className={`relative overflow-hidden rounded-2xl border border-white/40 bg-gradient-to-br ${palette.bg} ring-1 ${palette.ring} px-5 py-4 backdrop-blur-xl dark:border-white/5`}
    >
      <div className="flex items-center gap-3">
        <div
          className={`flex h-10 w-10 items-center justify-center rounded-xl bg-white/70 backdrop-blur dark:bg-slate-900/60 ${palette.icon}`}
        >
          <Icon size={20} />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-content-primary">
            {palette.title}
          </h3>
          <p className="text-xs text-content-secondary">{palette.msg}</p>
        </div>
      </div>
    </div>
  );
}

/** Single quick-action tile inside the QuickActions row. */
function QuickActionTile({
  to,
  icon,
  label,
  description,
  navigate,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  description: string;
  navigate: ReturnType<typeof useNavigate>;
}) {
  return (
    <button
      type="button"
      onClick={() => navigate(to)}
      className="group relative flex items-start gap-3 overflow-hidden rounded-xl border border-white/40 bg-white/40 px-3.5 py-3 text-left backdrop-blur-xl transition-all hover:-translate-y-0.5 hover:border-oe-blue/40 hover:bg-white/70 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 dark:border-white/5 dark:bg-slate-900/40 dark:hover:bg-slate-800/60"
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-oe-blue/10 text-oe-blue transition-colors group-hover:bg-oe-blue group-hover:text-white">
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-sm font-semibold text-content-primary">{label}</div>
        <div className="truncate text-xs text-content-tertiary">{description}</div>
      </div>
    </button>
  );
}

export function CoordinationHubPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { projectId } = useActiveProjectProfile();

  const dashboardQuery = useQuery({
    queryKey: ['coordination-dashboard', projectId],
    queryFn: () => fetchCoordinationDashboard(projectId as string),
    enabled: !!projectId,
    staleTime: 30_000,
    retry: false,
  });

  const matrixQuery = useQuery({
    queryKey: ['coordination-trade-matrix', projectId],
    queryFn: () => fetchTradeMatrix(projectId as string),
    enabled: !!projectId,
    staleTime: 30_000,
    retry: false,
  });

  const timelineQuery = useQuery({
    queryKey: ['coordination-timeline', projectId, 30],
    queryFn: () => fetchCoordinationTimeline(projectId as string, 30),
    enabled: !!projectId,
    staleTime: 30_000,
    retry: false,
  });

  if (!projectId) {
    return (
      <div data-testid="coordination-no-project" className="px-4 py-8">
        <RequiresProject
          emptyHint={t('coordination.no_project_desc', {
            defaultValue: 'Pick a project to see its coordination dashboard.',
          })}
        >{null}</RequiresProject>
      </div>
    );
  }

  const handleRefresh = () => {
    dashboardQuery.refetch();
    matrixQuery.refetch();
    timelineQuery.refetch();
  };

  const hasError =
    dashboardQuery.isError && matrixQuery.isError && timelineQuery.isError;

  return (
    <div
      data-testid="coordination-hub-page"
      className="relative min-h-full overflow-hidden"
    >
      {/* Page-level gradient backdrop. Layered so the glass cards
          above pick up a tint without us needing per-card gradients. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-br from-sky-50 via-white to-emerald-50/40 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 -left-40 -z-10 h-96 w-96 rounded-full bg-gradient-radial from-sky-400/15 to-transparent blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-40 -right-40 -z-10 h-96 w-96 rounded-full bg-gradient-radial from-emerald-400/15 to-transparent blur-3xl"
      />

      <div className="space-y-5 px-4 py-5 lg:px-6 lg:py-6">
        {/* Hero header — glass pill with title, subtitle, refresh */}
        <header className="relative overflow-hidden rounded-2xl border border-white/40 bg-white/60 px-5 py-4 backdrop-blur-xl shadow-lg shadow-slate-900/[0.04] dark:border-white/5 dark:bg-slate-900/40">
          <div
            aria-hidden
            className="pointer-events-none absolute -top-16 right-1/4 h-40 w-40 rounded-full bg-gradient-radial from-sky-400/20 to-transparent blur-3xl"
          />
          <div className="relative flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-blue-600 text-white shadow-md shadow-sky-500/25">
                <LayoutDashboard size={22} />
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight text-content-primary">
                  {t('coordination.title', { defaultValue: 'Model Coordination' })}
                </h1>
                <p className="mt-0.5 text-sm text-content-secondary">
                  {t('coordination.subtitle', {
                    defaultValue:
                      'Federations, clashes, rule packs and BCF activity in one view.',
                  })}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {dashboardQuery.data ? (
                <span
                  data-testid="coordination-as-of"
                  className="text-xs text-content-tertiary"
                >
                  {t('coordination.as_of', { defaultValue: 'As of' })}{' '}
                  <DateDisplay
                    value={dashboardQuery.data.as_of}
                    format="datetime"
                  />
                </span>
              ) : null}
              <button
                data-testid="coordination-refresh"
                type="button"
                onClick={handleRefresh}
                className="inline-flex items-center gap-1.5 rounded-lg border border-white/40 bg-white/50 px-3 py-1.5 text-xs font-medium text-content-secondary backdrop-blur transition hover:border-oe-blue/40 hover:bg-white/80 hover:text-content-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 dark:border-white/5 dark:bg-slate-800/50 dark:hover:bg-slate-700/50"
              >
                <RefreshCw size={13} />
                {t('coordination.refresh', { defaultValue: 'Refresh' })}
              </button>
            </div>
          </div>
        </header>

        {hasError ? (
          <div data-testid="coordination-error">
            <RecoveryCard
              error={dashboardQuery.error ?? matrixQuery.error ?? timelineQuery.error}
              onRetry={handleRefresh}
            />
          </div>
        ) : (
          <>
            <HealthBanner data={dashboardQuery.data} />

            <CoordinationKPICards
              data={dashboardQuery.data}
              isLoading={dashboardQuery.isLoading}
            />

            {/* Quick actions — get-to-the-work shortcuts. Mirrors the
                "Skip the sales call" home-page CTA pattern but scoped
                to coordination workflows. */}
            <GlassPanel
              testId="coordination-quick-actions"
              icon={<Sparkles size={16} />}
              title={t('coordination.quick_actions_title', {
                defaultValue: 'Quick actions',
              })}
              subtitle={t('coordination.quick_actions_subtitle', {
                defaultValue: 'Jump straight to the next coordination task',
              })}
            >
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <QuickActionTile
                  navigate={navigate}
                  to="/clash"
                  icon={<Radar size={16} />}
                  label={t('coordination.qa_clash_label', {
                    defaultValue: 'Review clashes',
                  })}
                  description={t('coordination.qa_clash_desc', {
                    defaultValue: 'Triage, suppress, assign to disciplines',
                  })}
                />
                <QuickActionTile
                  navigate={navigate}
                  to="/bim/federations"
                  icon={<Layers size={16} />}
                  label={t('coordination.qa_federations_label', {
                    defaultValue: 'Federations',
                  })}
                  description={t('coordination.qa_federations_desc', {
                    defaultValue: 'Stitch BIM models, view by discipline',
                  })}
                />
                <QuickActionTile
                  navigate={navigate}
                  to="/bim/rules"
                  icon={<SlidersHorizontal size={16} />}
                  label={t('coordination.qa_rules_label', {
                    defaultValue: 'Rule packs',
                  })}
                  description={t('coordination.qa_rules_desc', {
                    defaultValue: 'LOD300 / LOD400 / COBie compliance',
                  })}
                />
                <QuickActionTile
                  navigate={navigate}
                  to="/bim"
                  icon={<Eye size={16} />}
                  label={t('coordination.qa_smart_views_label', {
                    defaultValue: 'Smart views',
                  })}
                  description={t('coordination.qa_smart_views_desc', {
                    defaultValue: 'Filter, color and isolate in 3D',
                  })}
                />
              </div>
            </GlassPanel>

            {/* Trade matrix — clash distribution across discipline pairs */}
            <GlassPanel
              testId="coordination-trade-matrix-panel"
              icon={<Radar size={16} />}
              title={t('coordination.trade_matrix_title', {
                defaultValue: 'Clashes by discipline pair',
              })}
              subtitle={t('coordination.trade_matrix_subtitle', {
                defaultValue:
                  'Click a cell to drill into the filtered clash list',
              })}
            >
              <CoordinationTradeMatrix
                data={matrixQuery.data}
                isLoading={matrixQuery.isLoading}
                projectId={projectId}
              />
            </GlassPanel>

            {/* Recent activity timeline */}
            <GlassPanel
              testId="coordination-timeline-panel"
              icon={<Activity size={16} />}
              title={t('coordination.timeline_title', {
                defaultValue: 'Recent activity (30 days)',
              })}
              subtitle={t('coordination.timeline_subtitle', {
                defaultValue:
                  'Clash runs, federations, rule pack checks and BCF topics',
              })}
            >
              <CoordinationTimeline
                data={timelineQuery.data}
                isLoading={timelineQuery.isLoading}
              />
            </GlassPanel>
          </>
        )}
      </div>
    </div>
  );
}
