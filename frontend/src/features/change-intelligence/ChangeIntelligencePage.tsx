// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Change Intelligence - one read surface over the change-adjacent modules.
// Six co-pilots, each a tab: what to act on first (coordination), waiting on
// whom (cycle time), who owes the next reply (correspondence digest), what the
// approved changes have committed (impact), what we mean to recover from others
// (cost recovery) and a stateless drafting helper (clarifier). Every panel is a
// thin view over its endpoint; money arrives as a string and is handed to
// MoneyDisplay untouched.

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  BrainCircuit,
  ListChecks,
  Clock,
  Mail,
  TrendingUp,
  Wallet,
  Sparkles,
  AlertTriangle,
  ArrowRight,
  Users,
  Inbox,
  Scale,
  GitCompareArrows,
  Radar,
  ShieldAlert,
} from 'lucide-react';
import { Card, Badge, EmptyState, SkeletonTable, DismissibleInfo, TabBar, tabIds } from '@/shared/ui';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { apiGet, getErrorMessage } from '@/shared/lib/api';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import {
  getCoordinationPlan,
  getCycleTimeBoard,
  getCommsDigest,
  getImpactProjection,
  getRecoveryLedger,
  listBackCharges,
  clarifyChangeNote,
  getDisputeRiskBoard,
  getDecisionImpact,
  getChangeWatch,
  type Urgency,
  type Awaiting,
  type ClarifiedRequest,
  type ExposureBand,
  type WatchClass,
} from './api';

type BadgeVariant = 'neutral' | 'blue' | 'success' | 'warning' | 'error';

interface ProjectLite {
  id: string;
  name?: string;
}

type Tab =
  | 'coordination'
  | 'cycle'
  | 'comms'
  | 'impact'
  | 'recovery'
  | 'dispute'
  | 'decision'
  | 'watch'
  | 'clarifier';

const URGENCY_VARIANT: Record<Urgency, BadgeVariant> = {
  overdue: 'error',
  due_soon: 'warning',
  upcoming: 'blue',
  no_date: 'neutral',
};

const AWAITING_VARIANT: Record<Awaiting, BadgeVariant> = {
  us: 'warning',
  them: 'blue',
  none: 'neutral',
};

const EXPOSURE_VARIANT: Record<ExposureBand, BadgeVariant> = {
  high: 'error',
  elevated: 'warning',
  low: 'neutral',
};

const WATCH_VARIANT: Record<WatchClass, BadgeVariant> = {
  lost: 'error',
  stalled: 'warning',
  incomplete: 'blue',
  ok: 'success',
};

/**
 * Badge variant for a clarification-gap severity. The engine emits
 * 'required' / 'recommended' (not 'high' / 'medium'); map them to the
 * error / warning traffic-light, everything else neutral.
 */
function severityVariant(severity: string): BadgeVariant {
  if (severity === 'required') return 'error';
  if (severity === 'recommended') return 'warning';
  return 'neutral';
}

/** Best-effort title-case of an engine token like "due_soon" or "change_order". */
function humanize(token: string): string {
  return (token || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

function dateOnly(value: string | null | undefined): string {
  if (!value) return '-';
  return String(value).slice(0, 10);
}

// --- Small shared layout helpers -------------------------------------------

function StatTile({ label, value, tone }: { label: string; value: React.ReactNode; tone?: BadgeVariant }) {
  const toneClass =
    tone === 'error'
      ? 'text-semantic-error'
      : tone === 'warning'
        ? 'text-semantic-warning'
        : tone === 'success'
          ? 'text-semantic-success'
          : 'text-content-primary';
  return (
    <Card className="p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-content-tertiary">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${toneClass}`}>{value}</div>
    </Card>
  );
}

function PanelState({
  loading,
  error,
  empty,
  emptyIcon,
  emptyTitle,
  emptyDescription,
  children,
}: {
  loading: boolean;
  error: unknown;
  empty: boolean;
  emptyIcon: React.ReactNode;
  emptyTitle: string;
  emptyDescription: string;
  children: React.ReactNode;
}) {
  if (loading) return <SkeletonTable />;
  if (error) {
    return (
      <Card className="p-4">
        <div className="flex items-center gap-2 text-sm text-semantic-error">
          <AlertTriangle className="h-4 w-4" />
          <span>{getErrorMessage(error)}</span>
        </div>
      </Card>
    );
  }
  if (empty) return <EmptyState icon={emptyIcon} title={emptyTitle} description={emptyDescription} />;
  return <>{children}</>;
}

// --- Tab: coordination ("what to act on first") ----------------------------

function CoordinationTab({ projectId }: { projectId: string }) {
  const q = useQuery({
    queryKey: ['change-intelligence', 'coordination', projectId],
    queryFn: () => getCoordinationPlan(projectId),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });
  const plan = q.data;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatTile label="Open items" value={plan?.total ?? 0} />
        <StatTile label="Overdue" value={plan?.overdue_count ?? 0} tone="error" />
        <StatTile label="Due soon" value={plan?.due_soon_count ?? 0} tone="warning" />
      </div>
      <PanelState
        loading={q.isLoading}
        error={q.isError ? q.error : null}
        empty={!plan || plan.steps.length === 0}
        emptyIcon={<ListChecks className="h-6 w-6" />}
        emptyTitle="Nothing waiting"
        emptyDescription="No open change items need an action right now."
      >
        <div className="space-y-2">
          {plan?.steps.map((s) => (
            <Card key={s.ref_id} className="p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={URGENCY_VARIANT[s.urgency]}>{humanize(s.urgency)}</Badge>
                <span className="text-xs text-content-tertiary">{humanize(s.kind)}</span>
                <span className="font-medium text-content-primary">{s.title || '(untitled)'}</span>
                <span className="ml-auto inline-flex items-center gap-1 text-sm font-medium text-oe-blue">
                  {humanize(s.recommended_action)}
                  <ArrowRight className="h-3.5 w-3.5" />
                </span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-content-secondary">
                <span>Ball in court: <span className="font-medium">{s.ball_in_court}</span></span>
                {s.days_to_due != null && (
                  <span>
                    {s.days_to_due < 0
                      ? `${Math.abs(s.days_to_due)}d overdue`
                      : `${s.days_to_due}d to due`}
                  </span>
                )}
                <span className="text-content-tertiary">{s.reason}</span>
              </div>
            </Card>
          ))}
        </div>
      </PanelState>
    </div>
  );
}

// --- Tab: cycle time ("waiting on whom") -----------------------------------

function CycleTimeTab({ projectId }: { projectId: string }) {
  const q = useQuery({
    queryKey: ['change-intelligence', 'cycle-time', projectId],
    queryFn: () => getCycleTimeBoard(projectId),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });
  const board = q.data;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatTile label="Open" value={board?.total_open ?? 0} />
        <StatTile label="Overdue" value={board?.total_overdue ?? 0} tone="error" />
        <StatTile label="Unassigned" value={board?.unassigned_open ?? 0} tone="warning" />
      </div>
      <PanelState
        loading={q.isLoading}
        error={q.isError ? q.error : null}
        empty={!board || board.parties.length === 0}
        emptyIcon={<Users className="h-6 w-6" />}
        emptyTitle="No open changes"
        emptyDescription="There are no open change records to age right now."
      >
        <Card className="overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="bg-surface-secondary text-left text-xs uppercase tracking-wide text-content-tertiary">
              <tr>
                <th className="px-3 py-2">Party (ball in court)</th>
                <th className="px-3 py-2 text-right">Open</th>
                <th className="px-3 py-2 text-right">Overdue</th>
                <th className="px-3 py-2 text-right">Avg age (d)</th>
                <th className="px-3 py-2 text-right">Oldest (d)</th>
              </tr>
            </thead>
            <tbody>
              {board?.parties.map((p) => (
                <tr key={p.party} className="border-t border-border-light">
                  <td className="px-3 py-2 font-medium text-content-primary">{p.party}</td>
                  <td className="px-3 py-2 text-right">{p.open_count}</td>
                  <td className="px-3 py-2 text-right text-semantic-error">{p.overdue_count || ''}</td>
                  <td className="px-3 py-2 text-right">{p.avg_age_days.toFixed(1)}</td>
                  <td className="px-3 py-2 text-right">{p.oldest_age_days.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </PanelState>
    </div>
  );
}

// --- Tab: correspondence digest --------------------------------------------

function CommsTab({ projectId }: { projectId: string }) {
  const q = useQuery({
    queryKey: ['change-intelligence', 'comms-digest', projectId],
    queryFn: () => getCommsDigest(projectId),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });
  const digest = q.data;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatTile label="Threads" value={digest?.thread_count ?? 0} />
        <StatTile label="Open" value={digest?.open_count ?? 0} />
        <StatTile label="Awaiting us" value={digest?.awaiting_us_count ?? 0} tone="warning" />
      </div>
      <PanelState
        loading={q.isLoading}
        error={q.isError ? q.error : null}
        empty={!digest || digest.threads.length === 0}
        emptyIcon={<Mail className="h-6 w-6" />}
        emptyTitle="No correspondence"
        emptyDescription="No letters or emails have been recorded for this project yet."
      >
        <div className="space-y-2">
          {digest?.threads.map((th) => (
            <Card key={th.thread_key || th.subject} className="p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={AWAITING_VARIANT[th.awaiting]}>
                  {th.awaiting === 'none' ? 'Closed' : `Awaiting ${th.awaiting}`}
                </Badge>
                <span className="font-medium text-content-primary">{th.subject || '(no subject)'}</span>
                <span className="ml-auto text-xs text-content-tertiary">{th.message_count} msg</span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-4 text-sm text-content-secondary">
                <span>Last: {dateOnly(th.last_at)}</span>
                <span>{humanize(th.last_direction)} from {th.last_sender || 'unknown'}</span>
                {th.participants.length > 0 && (
                  <span className="text-content-tertiary">{th.participants.length} participant(s)</span>
                )}
              </div>
            </Card>
          ))}
        </div>
      </PanelState>
    </div>
  );
}

// --- Tab: impact (committed cost and schedule) -----------------------------

function ImpactTab({ projectId }: { projectId: string }) {
  const q = useQuery({
    queryKey: ['change-intelligence', 'impact', projectId],
    queryFn: () => getImpactProjection(projectId),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });
  const imp = q.data;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatTile label="Approved changes" value={imp?.approved_count ?? 0} />
        <StatTile
          label="Committed cost"
          value={<MoneyDisplay amount={imp?.primary_currency_cost ?? '0'} currency={imp?.primary_currency} showCode colorize />}
        />
        <StatTile label="Schedule delta (d)" value={imp?.total_schedule_delta_days ?? 0} />
      </div>
      <PanelState
        loading={q.isLoading}
        error={q.isError ? q.error : null}
        empty={!imp || imp.by_kind.length === 0}
        emptyIcon={<TrendingUp className="h-6 w-6" />}
        emptyTitle="No committed impact"
        emptyDescription="No approved change orders or agreed variation orders carry cost or schedule yet."
      >
        <Card className="overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="bg-surface-secondary text-left text-xs uppercase tracking-wide text-content-tertiary">
              <tr>
                <th className="px-3 py-2">By kind</th>
                <th className="px-3 py-2 text-right">Count</th>
                <th className="px-3 py-2 text-right">Cost</th>
                <th className="px-3 py-2 text-right">Days</th>
              </tr>
            </thead>
            <tbody>
              {imp?.by_kind.map((k) => (
                <tr key={k.kind} className="border-t border-border-light">
                  <td className="px-3 py-2 font-medium text-content-primary">{humanize(k.kind)}</td>
                  <td className="px-3 py-2 text-right">{k.count}</td>
                  <td className="px-3 py-2 text-right">
                    <MoneyDisplay amount={k.total_cost} currency={imp?.primary_currency} showCode colorize />
                  </td>
                  <td className="px-3 py-2 text-right">{k.total_days}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        {imp && imp.by_currency.length > 1 && (
          <p className="text-xs text-content-tertiary">
            Costs span {imp.by_currency.length} currencies; the headline uses {imp.primary_currency || 'the primary currency'}.
          </p>
        )}
      </PanelState>
    </div>
  );
}

// --- Tab: cost recovery -----------------------------------------------------

function RecoveryTab({ projectId }: { projectId: string }) {
  const ledgerQ = useQuery({
    queryKey: ['change-intelligence', 'recovery-ledger', projectId],
    queryFn: () => getRecoveryLedger(projectId),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });
  const chargesQ = useQuery({
    queryKey: ['change-intelligence', 'back-charges', projectId],
    queryFn: () => listBackCharges(projectId),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });
  const ledger = ledgerQ.data;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatTile label="Back-charges" value={ledger?.item_count ?? 0} />
        <StatTile label="Open" value={ledger?.open_count ?? 0} tone="warning" />
        <StatTile
          label="Outstanding"
          value={<MoneyDisplay amount={ledger?.primary_outstanding ?? '0'} currency={ledger?.primary_currency} showCode />}
        />
      </div>
      <PanelState
        loading={ledgerQ.isLoading || chargesQ.isLoading}
        error={ledgerQ.isError ? ledgerQ.error : chargesQ.isError ? chargesQ.error : null}
        empty={!ledger || ledger.item_count === 0}
        emptyIcon={<Wallet className="h-6 w-6" />}
        emptyTitle="No back-charges"
        emptyDescription="Record a back-charge to start tracking what the project means to recover."
      >
        <Card className="overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="bg-surface-secondary text-left text-xs uppercase tracking-wide text-content-tertiary">
              <tr>
                <th className="px-3 py-2">Responsible party</th>
                <th className="px-3 py-2 text-right">Open</th>
                <th className="px-3 py-2 text-right">Chargeable</th>
                <th className="px-3 py-2 text-right">Recovered</th>
                <th className="px-3 py-2 text-right">Outstanding</th>
              </tr>
            </thead>
            <tbody>
              {ledger?.by_party.map((p) => (
                <tr key={`${p.party}-${p.currency}`} className="border-t border-border-light">
                  <td className="px-3 py-2 font-medium text-content-primary">{p.party}</td>
                  <td className="px-3 py-2 text-right">{p.open_count}</td>
                  <td className="px-3 py-2 text-right">
                    <MoneyDisplay amount={p.chargeable_total} currency={p.currency} showCode />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <MoneyDisplay amount={p.recovered_total} currency={p.currency} showCode />
                  </td>
                  <td className="px-3 py-2 text-right font-medium">
                    <MoneyDisplay amount={p.outstanding_total} currency={p.currency} showCode />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </PanelState>
    </div>
  );
}

// --- Tab: dispute risk (the dispute radar) ---------------------------------

function DisputeRiskTab({ projectId }: { projectId: string }) {
  const q = useQuery({
    queryKey: ['change-intelligence', 'dispute-risk', projectId],
    queryFn: () => getDisputeRiskBoard(projectId),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });
  const board = q.data;
  const bands = board?.summary.band_counts ?? {};
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Open changes" value={board?.summary.item_count ?? 0} />
        <StatTile label="High" value={bands.high ?? 0} tone="error" />
        <StatTile label="Elevated" value={bands.elevated ?? 0} tone="warning" />
        <StatTile label="Low" value={bands.low ?? 0} />
      </div>
      <PanelState
        loading={q.isLoading}
        error={q.isError ? q.error : null}
        empty={!board || board.items.length === 0}
        emptyIcon={<Radar className="h-6 w-6" />}
        emptyTitle="No open changes"
        emptyDescription="There are no open changes to assess for dispute exposure right now."
      >
        <div className="space-y-2">
          {board?.items.map((it) => (
            <Card key={it.change_id} className="p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={EXPOSURE_VARIANT[it.band]}>{humanize(it.band)}</Badge>
                <span className="text-sm font-semibold text-content-primary">{it.exposure_score}</span>
                <span className="text-xs text-content-tertiary">{humanize(it.kind)}</span>
                <span className="font-medium text-content-primary">
                  {it.change_ref ? `${it.change_ref}: ` : ''}
                  {it.title || '(untitled)'}
                </span>
                <span className="ml-auto inline-flex items-center gap-1 text-xs text-content-tertiary">
                  <ShieldAlert className="h-3.5 w-3.5" />
                  {humanize(it.dominant_driver)}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-content-secondary">
                {it.currency ? (
                  <span>
                    At risk: <MoneyDisplay amount={it.money_basis} currency={it.currency} showCode />
                  </span>
                ) : null}
                <span className="text-content-tertiary">{it.recommended_cure}</span>
              </div>
            </Card>
          ))}
        </div>
      </PanelState>
    </div>
  );
}

// --- Tab: decision impact ("what does approving this add?") ----------------

function DecisionImpactTab({ projectId }: { projectId: string }) {
  const [candidateId, setCandidateId] = useState('');
  const [submitted, setSubmitted] = useState('');
  const q = useQuery({
    queryKey: ['change-intelligence', 'decision-impact', projectId, submitted],
    queryFn: () => getDecisionImpact(projectId, submitted),
    enabled: !!projectId && !!submitted,
    retry: false,
    staleTime: 30_000,
  });
  const impact = q.data;
  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-4">
        <label className="block text-sm font-medium text-content-secondary" htmlFor="ci-candidate">
          Candidate change id
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <input
            id="ci-candidate"
            value={candidateId}
            onChange={(e) => setCandidateId(e.target.value)}
            placeholder="Paste the id of the change order, variation or MoC under decision"
            className="min-w-0 flex-1 rounded-md border border-border-light bg-surface-primary p-2 text-sm focus:border-oe-blue focus:outline-none focus:ring-2 focus:ring-oe-blue/30"
          />
          <button
            type="button"
            disabled={!candidateId.trim()}
            onClick={() => setSubmitted(candidateId.trim())}
            className="inline-flex items-center gap-1.5 rounded-md bg-oe-blue px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            <GitCompareArrows className="h-4 w-4" />
            Preview impact
          </button>
        </div>
        <p className="text-xs text-content-tertiary">
          Previews what approving this change adds on top of everything already committed, per currency. Nothing is changed.
        </p>
      </Card>
      {submitted ? (
        <PanelState
          loading={q.isLoading}
          error={q.isError ? q.error : null}
          empty={!impact || impact.totals_by_currency.length === 0}
          emptyIcon={<GitCompareArrows className="h-6 w-6" />}
          emptyTitle="No impact to show"
          emptyDescription="This candidate carries no cost or schedule against the committed baseline."
        >
          <Card className="overflow-hidden p-0">
            <table className="w-full text-sm">
              <thead className="bg-surface-secondary text-left text-xs uppercase tracking-wide text-content-tertiary">
                <tr>
                  <th className="px-3 py-2">By kind</th>
                  <th className="px-3 py-2 text-right">Committed</th>
                  <th className="px-3 py-2 text-right">This change</th>
                  <th className="px-3 py-2 text-right">Resulting</th>
                  <th className="px-3 py-2 text-right">Days</th>
                </tr>
              </thead>
              <tbody>
                {impact?.rows.map((r) => (
                  <tr key={`${r.kind}-${r.currency}`} className="border-t border-border-light">
                    <td className="px-3 py-2 font-medium text-content-primary">
                      {humanize(r.kind)} <span className="text-content-tertiary">{r.currency}</span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <MoneyDisplay amount={r.current_committed_cost} currency={r.currency} showCode />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <MoneyDisplay amount={r.candidate_cost_delta} currency={r.currency} showCode colorize />
                    </td>
                    <td className="px-3 py-2 text-right font-medium">
                      <MoneyDisplay amount={r.resulting_cost} currency={r.currency} showCode />
                    </td>
                    <td className="px-3 py-2 text-right">
                      {r.current_committed_days} &rarr; {r.resulting_days}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          {impact && impact.totals_by_currency.length > 1 && (
            <p className="text-xs text-content-tertiary">
              This decision spans {impact.totals_by_currency.length} currencies; totals are kept separate and never blended.
            </p>
          )}
        </PanelState>
      ) : (
        <EmptyState
          icon={<GitCompareArrows className="h-6 w-6" />}
          title="Preview a decision"
          description="Enter the id of a change under decision to see what approving it adds to the committed position."
        />
      )}
    </div>
  );
}

// --- Tab: watch ("which open changes are quietly going wrong") -------------

function WatchTab({ projectId }: { projectId: string }) {
  const q = useQuery({
    queryKey: ['change-intelligence', 'change-watch', projectId],
    queryFn: () => getChangeWatch(projectId),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });
  const watch = q.data;
  const counts = watch?.counts ?? {};
  // Only the flagged items are worth listing; an "ok" change is not drifting.
  const flagged = (watch?.items ?? []).filter((r) => r.classification !== 'ok');
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Lost" value={counts.lost ?? 0} tone="error" />
        <StatTile label="Stalled" value={counts.stalled ?? 0} tone="warning" />
        <StatTile label="Incomplete" value={counts.incomplete ?? 0} />
        <StatTile label="On track" value={counts.ok ?? 0} tone="success" />
      </div>
      <PanelState
        loading={q.isLoading}
        error={q.isError ? q.error : null}
        empty={flagged.length === 0}
        emptyIcon={<ShieldAlert className="h-6 w-6" />}
        emptyTitle="Nothing drifting"
        emptyDescription="No open change is stalled, lost or incomplete right now."
      >
        <div className="space-y-2">
          {flagged.map((r) => (
            <Card key={r.change_id} className="p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={WATCH_VARIANT[r.classification]}>{humanize(r.classification)}</Badge>
                <span className="text-xs text-content-tertiary">{humanize(r.kind)}</span>
                <span className="ml-auto flex flex-wrap items-center gap-x-3 text-sm text-content-secondary">
                  <span>{`${r.idle_days.toFixed(0)}d idle`}</span>
                  {r.overdue_days > 0 && (
                    <span className="text-semantic-error">{`${r.overdue_days.toFixed(0)}d overdue`}</span>
                  )}
                </span>
              </div>
              {r.reasons.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {r.reasons.map((reason) => (
                    <span key={reason} className="text-xs text-content-tertiary">
                      {humanize(reason)}
                    </span>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      </PanelState>
    </div>
  );
}

// --- Tab: clarifier co-pilot -----------------------------------------------

const CONTRACT_STANDARDS = ['', 'FIDIC', 'NEC4', 'JCT'];

function ClarifierTab() {
  const [note, setNote] = useState('');
  const [standard, setStandard] = useState('');
  const m = useMutation<ClarifiedRequest, unknown, void>({
    mutationFn: () => clarifyChangeNote(note, standard),
  });
  const result = m.data;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="space-y-3 p-4">
        <label className="block text-sm font-medium text-content-secondary" htmlFor="ci-note">
          Rough change note
        </label>
        <textarea
          id="ci-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={7}
          placeholder="Paste a quick description of the change as you would jot it down..."
          className="w-full rounded-md border border-border-light bg-surface-primary p-2 text-sm focus:border-oe-blue focus:outline-none focus:ring-2 focus:ring-oe-blue/30"
        />
        <div className="flex items-center gap-3">
          <select
            value={standard}
            onChange={(e) => setStandard(e.target.value)}
            className="rounded-md border border-border-light bg-surface-primary px-2 py-1.5 text-sm"
            aria-label="Contract standard"
          >
            {CONTRACT_STANDARDS.map((s) => (
              <option key={s || 'none'} value={s}>
                {s || 'No standard'}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!note.trim() || m.isPending}
            onClick={() => m.mutate()}
            className="inline-flex items-center gap-1.5 rounded-md bg-oe-blue px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            <Sparkles className="h-4 w-4" />
            {m.isPending ? 'Analyzing...' : 'Analyze'}
          </button>
        </div>
        {m.isError && (
          <div className="flex items-center gap-2 text-sm text-semantic-error">
            <AlertTriangle className="h-4 w-4" />
            <span>{getErrorMessage(m.error)}</span>
          </div>
        )}
      </Card>

      <Card className="p-4">
        {!result ? (
          <EmptyState
            icon={<Sparkles className="h-6 w-6" />}
            title="Structured draft"
            description="Analyze a note to see a suggested title, classification, gaps to fill and likely contract clauses."
          />
        ) : (
          <div className="space-y-3">
            <div>
              <div className="text-lg font-semibold text-content-primary">{result.title || '(untitled)'}</div>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <Badge variant="blue">{humanize(result.detected_classification)}</Badge>
                <Badge variant={result.completeness >= 0.7 ? 'success' : result.completeness >= 0.4 ? 'warning' : 'error'}>
                  {Math.round(result.completeness * 100)}% complete
                </Badge>
                {result.suggested_route && (
                  <span className="text-xs text-content-tertiary">Route: {humanize(result.suggested_route)}</span>
                )}
              </div>
            </div>
            {result.normalized_summary && (
              <p className="text-sm text-content-secondary">{result.normalized_summary}</p>
            )}
            {result.missing.length > 0 && (
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-content-tertiary">Still missing</div>
                <ul className="mt-1 space-y-1 text-sm">
                  {result.missing.map((g) => (
                    <li key={g.field} className="flex items-start gap-2">
                      <Badge variant={severityVariant(g.severity)}>{g.severity}</Badge>
                      <span className="text-content-secondary">{g.question}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {result.clause_suggestions.length > 0 && (
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-content-tertiary">Likely clauses</div>
                <ul className="mt-1 space-y-1 text-sm">
                  {result.clause_suggestions.map((c) => (
                    <li key={`${c.standard}-${c.clause_ref}`} className="text-content-secondary">
                      <span className="font-medium">{c.standard} {c.clause_ref}</span> - {c.rationale}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

// --- Page -------------------------------------------------------------------

export function ChangeIntelligencePage() {
  const { t } = useTranslation();
  const { projectId: routeProjectId } = useParams();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<ProjectLite[]>('/v1/projects/'),
    staleTime: 5 * 60_000,
  });
  const projectId = routeProjectId || activeProjectId || projects[0]?.id || '';

  const [tab, setTab] = useState<Tab>('coordination');
  const ids = tabIds('change-intel');

  return (
    <div className="space-y-5 animate-fade-in">
      <header className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-oe-blue/10 text-oe-blue">
          <BrainCircuit className="h-5 w-5" />
        </span>
        <div>
          <h1 className="text-xl font-semibold text-content-primary">
            {t('change_intelligence.title', { defaultValue: 'Change Intelligence' })}
          </h1>
          <p className="text-sm text-content-tertiary">
            {t('change_intelligence.subtitle', {
              defaultValue: 'What to act on first, who owes the next action, and what the changes have committed.',
            })}
          </p>
        </div>
      </header>

      <DismissibleInfo
        storageKey="change-intelligence"
        title={t('change_intelligence.intro_title', { defaultValue: 'One read of your change landscape' })}
      >
        {t('change_intelligence.intro_body', {
          defaultValue:
            'These co-pilots read your change orders, variations, management-of-change entries and correspondence in one place. Rank what needs action, see who the ball sits with and how long it has waited, total the committed cost and schedule of approved changes, track what you mean to recover, and turn a rough note into a structured request.',
        })}
      </DismissibleInfo>

      {!projectId ? (
        <EmptyState
          icon={<Inbox className="h-6 w-6" />}
          title={t('change_intelligence.no_project', { defaultValue: 'No project selected' })}
          description={t('change_intelligence.no_project_desc', {
            defaultValue: 'Select a project to see its change intelligence.',
          })}
        />
      ) : (
        <>
          <TabBar
            idPrefix="change-intel"
            ariaLabel={t('change_intelligence.title', { defaultValue: 'Change Intelligence' })}
            activeId={tab}
            onChange={(next) => setTab(next as Tab)}
            tabs={[
              { id: 'coordination', label: 'Act first', icon: <ListChecks className="h-4 w-4" /> },
              { id: 'cycle', label: 'Waiting on whom', icon: <Clock className="h-4 w-4" /> },
              { id: 'comms', label: 'Correspondence', icon: <Mail className="h-4 w-4" /> },
              { id: 'impact', label: 'Impact', icon: <TrendingUp className="h-4 w-4" /> },
              { id: 'recovery', label: 'Cost recovery', icon: <Wallet className="h-4 w-4" /> },
              { id: 'dispute', label: 'Dispute risk', icon: <Radar className="h-4 w-4" /> },
              { id: 'decision', label: 'Decision impact', icon: <Scale className="h-4 w-4" /> },
              { id: 'watch', label: 'Watch', icon: <ShieldAlert className="h-4 w-4" /> },
              { id: 'clarifier', label: 'Clarifier', icon: <Sparkles className="h-4 w-4" /> },
            ]}
          />
          <div role="tabpanel" id={ids.panelId(tab)} aria-labelledby={ids.tabId(tab)}>
            {tab === 'coordination' && <CoordinationTab projectId={projectId} />}
            {tab === 'cycle' && <CycleTimeTab projectId={projectId} />}
            {tab === 'comms' && <CommsTab projectId={projectId} />}
            {tab === 'impact' && <ImpactTab projectId={projectId} />}
            {tab === 'recovery' && <RecoveryTab projectId={projectId} />}
            {tab === 'dispute' && <DisputeRiskTab projectId={projectId} />}
            {tab === 'decision' && <DecisionImpactTab projectId={projectId} />}
            {tab === 'watch' && <WatchTab projectId={projectId} />}
            {tab === 'clarifier' && <ClarifierTab />}
          </div>
        </>
      )}
    </div>
  );
}

export default ChangeIntelligencePage;
