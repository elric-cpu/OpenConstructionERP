import { useState, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  Building2,
  UserPlus,
  Target,
  Activity as ActivityIcon,
  Plus,
  Search,
  X,
  Loader2,
  CheckCircle2,
  XCircle,
  ArrowRight,
  Trophy,
  Frown,
  AlertTriangle,
} from 'lucide-react';
import {
  Button,
  Card,
  Badge,
  EmptyState,
  Breadcrumb,
  SkeletonTable,
} from '@/shared/ui';
import {
  WideModal,
  WideModalSection,
  WideModalField,
} from '@/shared/ui/WideModal';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';
import {
  listAccounts,
  listLeads,
  listOpportunities,
  listActivities,
  listPipelineStages,
  createAccount,
  createLead,
  createOpportunity,
  createActivity,
  qualifyLead,
  disqualifyLead,
  moveOpportunityStage,
  winOpportunity,
  loseOpportunity,
  type Account,
  type Lead,
  type Opportunity,
  type Activity,
  type PipelineStage,
  type LeadStatus,
  type LeadSource,
  type OpportunityStatus,
  type AccountStatus,
  type AccountSize,
  type ActivityKind,
} from './api';

type Tab = 'accounts' | 'leads' | 'opportunities' | 'activities';

const LEAD_STATUS_VARIANT: Record<
  LeadStatus,
  'neutral' | 'blue' | 'success' | 'warning' | 'error'
> = {
  new: 'neutral',
  qualifying: 'warning',
  qualified: 'success',
  disqualified: 'error',
  converted: 'blue',
};

const OPP_STATUS_VARIANT: Record<
  OpportunityStatus,
  'neutral' | 'blue' | 'success' | 'warning' | 'error'
> = {
  open: 'blue',
  won: 'success',
  lost: 'error',
  abandoned: 'neutral',
};

const ACCOUNT_STATUS_VARIANT: Record<
  AccountStatus,
  'neutral' | 'blue' | 'success' | 'warning' | 'error'
> = {
  active: 'success',
  dormant: 'warning',
  lost: 'error',
};

const LEAD_STATUSES: LeadStatus[] = [
  'new',
  'qualifying',
  'qualified',
  'disqualified',
  'converted',
];

const OPP_STATUSES: OpportunityStatus[] = ['open', 'won', 'lost', 'abandoned'];

const LEAD_SOURCES: LeadSource[] = [
  'web',
  'referral',
  'event',
  'cold_outreach',
  'inbound',
];

const ACTIVITY_KINDS: ActivityKind[] = ['call', 'meeting', 'email', 'task', 'note'];

const inputCls =
  'h-9 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

function toNum(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = typeof v === 'string' ? Number(v) : v;
  return Number.isFinite(n) ? n : 0;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/* ─── Page ─── */

export function CRMPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('accounts');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<string | null>(
    null,
  );

  const accountsQ = useQuery({
    queryKey: ['crm', 'accounts'],
    queryFn: () => listAccounts({ limit: 200 }),
    enabled: tab === 'accounts' || tab === 'leads' || tab === 'opportunities',
  });
  const leadsQ = useQuery({
    queryKey: ['crm', 'leads'],
    queryFn: () => listLeads({ limit: 200 }),
    enabled: tab === 'leads',
  });
  const oppsQ = useQuery({
    queryKey: ['crm', 'opportunities'],
    queryFn: () => listOpportunities({ limit: 200 }),
    enabled: tab === 'opportunities',
  });
  const activitiesQ = useQuery({
    queryKey: ['crm', 'activities'],
    queryFn: () => listActivities({ limit: 200 }),
    enabled: tab === 'activities',
  });
  const stagesQ = useQuery({
    queryKey: ['crm', 'pipeline-stages'],
    queryFn: () => listPipelineStages(),
  });

  const stagesById = useMemo<Record<string, PipelineStage>>(() => {
    const map: Record<string, PipelineStage> = {};
    (stagesQ.data ?? []).forEach((s) => {
      map[s.id] = s;
    });
    return map;
  }, [stagesQ.data]);

  const accountsById = useMemo<Record<string, Account>>(() => {
    const map: Record<string, Account> = {};
    (accountsQ.data ?? []).forEach((a) => {
      map[a.id] = a;
    });
    return map;
  }, [accountsQ.data]);

  const filteredAccounts = useMemo(() => {
    const s = search.toLowerCase();
    return (accountsQ.data ?? []).filter((a) => {
      if (statusFilter && a.status !== statusFilter) return false;
      if (!s) return true;
      return (
        a.name.toLowerCase().includes(s) ||
        (a.industry || '').toLowerCase().includes(s) ||
        (a.country || '').toLowerCase().includes(s)
      );
    });
  }, [accountsQ.data, search, statusFilter]);

  const filteredLeads = useMemo(() => {
    const s = search.toLowerCase();
    return (leadsQ.data ?? []).filter((l) => {
      if (statusFilter && l.status !== statusFilter) return false;
      if (!s) return true;
      return (
        l.contact_name.toLowerCase().includes(s) ||
        (l.contact_email || '').toLowerCase().includes(s)
      );
    });
  }, [leadsQ.data, search, statusFilter]);

  const filteredOpps = useMemo(() => {
    const s = search.toLowerCase();
    return (oppsQ.data ?? []).filter((o) => {
      if (statusFilter && o.status !== statusFilter) return false;
      if (!s) return true;
      return (
        o.title.toLowerCase().includes(s) ||
        (accountsById[o.account_id]?.name || '').toLowerCase().includes(s)
      );
    });
  }, [oppsQ.data, accountsById, search, statusFilter]);

  const filteredActivities = useMemo(() => {
    const s = search.toLowerCase();
    return (activitiesQ.data ?? []).filter((a) => {
      if (statusFilter && a.kind !== statusFilter) return false;
      if (!s) return true;
      return (
        a.subject.toLowerCase().includes(s) ||
        (a.body || '').toLowerCase().includes(s)
      );
    });
  }, [activitiesQ.data, search, statusFilter]);

  const isLoading =
    (tab === 'accounts' && accountsQ.isLoading) ||
    (tab === 'leads' && (accountsQ.isLoading || leadsQ.isLoading)) ||
    (tab === 'opportunities' &&
      (accountsQ.isLoading || oppsQ.isLoading || stagesQ.isLoading)) ||
    (tab === 'activities' && activitiesQ.isLoading);

  // Surface real query failures (5xx / network) instead of silently
  // showing an empty table. safeGetList already absorbs 404/501 (module
  // not installed) into [], so anything reaching isError is genuine.
  const activeError =
    tab === 'accounts'
      ? accountsQ.error
      : tab === 'leads'
        ? (accountsQ.error ?? leadsQ.error)
        : tab === 'opportunities'
          ? (accountsQ.error ?? oppsQ.error ?? stagesQ.error)
          : activitiesQ.error;
  const isError = !isLoading && Boolean(activeError);

  return (
    <div className="space-y-5">
      <Breadcrumb
        items={[{ label: t('crm.title', { defaultValue: 'CRM' }) }]}
      />

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">
            {t('crm.title', { defaultValue: 'CRM' })}
          </h1>
          <p className="mt-1 text-sm text-content-secondary">
            {t('crm.subtitle', {
              defaultValue:
                'Accounts, leads, opportunities and activities — the construction sales pipeline.',
            })}
          </p>
        </div>
        <Button
          variant="primary"
          icon={<Plus size={14} />}
          onClick={() => setCreateOpen(true)}
        >
          {tab === 'accounts' && t('crm.new_account', { defaultValue: 'New Account' })}
          {tab === 'leads' && t('crm.new_lead', { defaultValue: 'New Lead' })}
          {tab === 'opportunities' &&
            t('crm.new_opportunity', { defaultValue: 'New Opportunity' })}
          {tab === 'activities' &&
            t('crm.new_activity', { defaultValue: 'New Activity' })}
        </Button>
      </div>

      {/* Tabs */}
      <div className="border-b border-border-light">
        <nav className="flex gap-1 -mb-px">
          {(
            [
              {
                id: 'accounts',
                label: t('crm.tab_accounts', { defaultValue: 'Accounts' }),
                icon: Building2,
              },
              {
                id: 'leads',
                label: t('crm.tab_leads', { defaultValue: 'Leads' }),
                icon: UserPlus,
              },
              {
                id: 'opportunities',
                label: t('crm.tab_opportunities', { defaultValue: 'Opportunities' }),
                icon: Target,
              },
              {
                id: 'activities',
                label: t('crm.tab_activities', { defaultValue: 'Activities' }),
                icon: ActivityIcon,
              },
            ] as { id: Tab; label: string; icon: React.ElementType }[]
          ).map((it) => {
            const Icon = it.icon;
            return (
              <button
                key={it.id}
                type="button"
                onClick={() => {
                  setTab(it.id);
                  setSearch('');
                  setStatusFilter('');
                }}
                className={clsx(
                  'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
                  tab === it.id
                    ? 'border-oe-blue text-oe-blue'
                    : 'border-transparent text-content-secondary hover:text-content-primary',
                )}
              >
                <Icon size={14} />
                {it.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-content-tertiary"
          />
          <input
            type="text"
            placeholder={t('common.search', { defaultValue: 'Search…' })}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={clsx(inputCls, 'pl-8')}
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className={clsx(inputCls, 'max-w-[200px]')}
        >
          <option value="">
            {tab === 'activities'
              ? t('crm.all_kinds', { defaultValue: 'All kinds' })
              : t('common.all_statuses', { defaultValue: 'All statuses' })}
          </option>
          {tab === 'accounts' &&
            (['active', 'dormant', 'lost'] as AccountStatus[]).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          {tab === 'leads' &&
            LEAD_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          {tab === 'opportunities' &&
            OPP_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          {tab === 'activities' &&
            ACTIVITY_KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
        </select>
      </div>

      {/* Body */}
      <Card padding="none">
        {isLoading ? (
          <div className="p-4">
            <SkeletonTable rows={8} columns={5} />
          </div>
        ) : isError ? (
          <EmptyState
            icon={<AlertTriangle size={22} />}
            title={t('crm.load_failed', {
              defaultValue: 'Could not load CRM data',
            })}
            description={getErrorMessage(activeError)}
          />
        ) : tab === 'accounts' ? (
          <AccountsTable rows={filteredAccounts} onCreate={() => setCreateOpen(true)} />
        ) : tab === 'leads' ? (
          <LeadsTable
            rows={filteredLeads}
            accountsById={accountsById}
            onSelect={setSelectedLeadId}
            onCreate={() => setCreateOpen(true)}
          />
        ) : tab === 'opportunities' ? (
          <OpportunitiesTable
            rows={filteredOpps}
            accountsById={accountsById}
            stagesById={stagesById}
            onSelect={setSelectedOpportunityId}
            onCreate={() => setCreateOpen(true)}
          />
        ) : (
          <ActivitiesTable rows={filteredActivities} onCreate={() => setCreateOpen(true)} />
        )}
      </Card>

      {/* Drawers */}
      {selectedLeadId && (
        <LeadDetailDrawer
          leadId={selectedLeadId}
          leads={leadsQ.data ?? []}
          accountsById={accountsById}
          onClose={() => setSelectedLeadId(null)}
        />
      )}
      {selectedOpportunityId && (
        <OpportunityDetailDrawer
          opportunityId={selectedOpportunityId}
          opportunities={oppsQ.data ?? []}
          stages={stagesQ.data ?? []}
          accountsById={accountsById}
          onClose={() => setSelectedOpportunityId(null)}
        />
      )}

      {/* Create modal */}
      {createOpen && (
        <CreateModal
          kind={tab}
          accounts={accountsQ.data ?? []}
          stages={stagesQ.data ?? []}
          onClose={() => setCreateOpen(false)}
        />
      )}
    </div>
  );
}

/* ─── Tables ─── */

function AccountsTable({
  rows,
  onCreate,
}: {
  rows: Account[];
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<Building2 size={22} />}
        title={t('crm.empty_accounts', { defaultValue: 'No accounts yet' })}
        description={t('crm.empty_accounts_desc', {
          defaultValue: 'Create accounts to track companies you do business with.',
        })}
        action={{
          label: t('crm.new_account', { defaultValue: 'New Account' }),
          onClick: onCreate,
        }}
      />
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-4 py-2.5 text-left">
              {t('crm.account_name', { defaultValue: 'Name' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.industry', { defaultValue: 'Industry' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.country', { defaultValue: 'Country' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.size', { defaultValue: 'Size' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.status', { defaultValue: 'Status' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-border-light hover:bg-surface-secondary">
              <td className="px-4 py-2 font-medium">{r.name}</td>
              <td className="px-4 py-2 text-content-secondary">
                {r.industry || '—'}
              </td>
              <td className="px-4 py-2 text-content-secondary">
                {r.country || '—'}
              </td>
              <td className="px-4 py-2 text-xs text-content-secondary capitalize">
                {r.size_category}
              </td>
              <td className="px-4 py-2">
                <Badge variant={ACCOUNT_STATUS_VARIANT[r.status]} dot>
                  {r.status}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LeadsTable({
  rows,
  accountsById,
  onSelect,
  onCreate,
}: {
  rows: Lead[];
  accountsById: Record<string, Account>;
  onSelect: (id: string) => void;
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<UserPlus size={22} />}
        title={t('crm.empty_leads', { defaultValue: 'No leads yet' })}
        description={t('crm.empty_leads_desc', {
          defaultValue:
            'Leads are inbound enquiries — qualify them, then convert to opportunities.',
        })}
        action={{
          label: t('crm.new_lead', { defaultValue: 'New Lead' }),
          onClick: onCreate,
        }}
      />
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-4 py-2.5 text-left">
              {t('crm.contact', { defaultValue: 'Contact' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.account', { defaultValue: 'Account' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.source', { defaultValue: 'Source' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.status', { defaultValue: 'Status' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.created', { defaultValue: 'Created' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              onClick={() => onSelect(r.id)}
              className="border-t border-border-light hover:bg-surface-secondary cursor-pointer"
            >
              <td className="px-4 py-2">
                <div className="font-medium">{r.contact_name}</div>
                <div className="text-xs text-content-tertiary">
                  {r.contact_email || r.contact_phone || ''}
                </div>
              </td>
              <td className="px-4 py-2 text-content-secondary">
                {r.account_id ? accountsById[r.account_id]?.name || '—' : '—'}
              </td>
              <td className="px-4 py-2 text-xs text-content-secondary capitalize">
                {r.source.replace(/_/g, ' ')}
              </td>
              <td className="px-4 py-2">
                <Badge variant={LEAD_STATUS_VARIANT[r.status]} dot>
                  {r.status}
                </Badge>
              </td>
              <td className="px-4 py-2 text-xs text-content-secondary">
                <DateDisplay value={r.created_at} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OpportunitiesTable({
  rows,
  accountsById,
  stagesById,
  onSelect,
  onCreate,
}: {
  rows: Opportunity[];
  accountsById: Record<string, Account>;
  stagesById: Record<string, PipelineStage>;
  onSelect: (id: string) => void;
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<Target size={22} />}
        title={t('crm.empty_opportunities', { defaultValue: 'No opportunities yet' })}
        description={t('crm.empty_opportunities_desc', {
          defaultValue:
            'Track deals through the pipeline: prospecting → qualified → proposal → negotiation → won.',
        })}
        action={{
          label: t('crm.new_opportunity', { defaultValue: 'New Opportunity' }),
          onClick: onCreate,
        }}
      />
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-4 py-2.5 text-left">
              {t('crm.title_col', { defaultValue: 'Title' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.account', { defaultValue: 'Account' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.stage', { defaultValue: 'Stage' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.status', { defaultValue: 'Status' })}
            </th>
            <th className="px-4 py-2.5 text-right">
              {t('crm.value', { defaultValue: 'Value' })}
            </th>
            <th className="px-4 py-2.5 text-right">
              {t('crm.weighted', { defaultValue: 'Weighted' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const stage = stagesById[r.stage_id];
            return (
              <tr
                key={r.id}
                onClick={() => onSelect(r.id)}
                className="border-t border-border-light hover:bg-surface-secondary cursor-pointer"
              >
                <td className="px-4 py-2 font-medium text-content-primary truncate max-w-[260px]">
                  {r.title}
                </td>
                <td className="px-4 py-2 text-content-secondary">
                  {accountsById[r.account_id]?.name || '—'}
                </td>
                <td className="px-4 py-2">
                  <StageChip stage={stage} probability={r.probability_percent} />
                </td>
                <td className="px-4 py-2">
                  <Badge variant={OPP_STATUS_VARIANT[r.status]} dot>
                    {r.status}
                  </Badge>
                </td>
                <td className="px-4 py-2 text-right">
                  <MoneyDisplay
                    amount={toNum(r.estimated_value)}
                    currency={r.currency || undefined}
                  />
                </td>
                <td className="px-4 py-2 text-right text-content-secondary">
                  <MoneyDisplay
                    amount={toNum(r.weighted_value)}
                    currency={r.currency || undefined}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StageChip({
  stage,
  probability,
}: {
  stage: PipelineStage | undefined;
  probability: number;
}) {
  if (!stage) {
    return (
      <span className="text-xs text-content-tertiary">
        {probability}%
      </span>
    );
  }
  const bg = stage.is_won
    ? 'bg-emerald-50 dark:bg-emerald-950/40 ring-emerald-200 dark:ring-emerald-800 text-emerald-700 dark:text-emerald-300'
    : stage.is_lost
      ? 'bg-rose-50 dark:bg-rose-950/40 ring-rose-200 dark:ring-rose-800 text-rose-700 dark:text-rose-300'
      : 'bg-blue-50 dark:bg-blue-950/40 ring-blue-200 dark:ring-blue-800 text-blue-700 dark:text-blue-300';
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        bg,
      )}
    >
      {stage.name}
      <span className="ml-1.5 opacity-70">· {probability}%</span>
    </span>
  );
}

function ActivitiesTable({
  rows,
  onCreate,
}: {
  rows: Activity[];
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<ActivityIcon size={22} />}
        title={t('crm.empty_activities', { defaultValue: 'No activities yet' })}
        description={t('crm.empty_activities_desc', {
          defaultValue:
            'Log calls, meetings, emails and tasks tied to accounts, leads or opportunities.',
        })}
        action={{
          label: t('crm.new_activity', { defaultValue: 'New Activity' }),
          onClick: onCreate,
        }}
      />
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-4 py-2.5 text-left">
              {t('crm.kind', { defaultValue: 'Kind' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.subject', { defaultValue: 'Subject' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.due', { defaultValue: 'Due' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('crm.outcome', { defaultValue: 'Outcome' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-border-light hover:bg-surface-secondary">
              <td className="px-4 py-2 text-xs text-content-secondary capitalize">
                {r.kind}
              </td>
              <td className="px-4 py-2 font-medium truncate max-w-[360px]">
                {r.subject || '—'}
              </td>
              <td className="px-4 py-2 text-xs text-content-secondary">
                {r.due_at ? <DateDisplay value={r.due_at} /> : '—'}
              </td>
              <td className="px-4 py-2 text-xs text-content-secondary">
                {r.outcome || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ─── Lead detail drawer ─── */

function LeadDetailDrawer({
  leadId,
  leads,
  accountsById,
  onClose,
}: {
  leadId: string;
  leads: Lead[];
  accountsById: Record<string, Account>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const lead = leads.find((l) => l.id === leadId);
  const [notes, setNotes] = useState(lead?.qualification_notes ?? '');

  useEffect(() => {
    setNotes(lead?.qualification_notes ?? '');
  }, [lead?.id, lead?.qualification_notes]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const qualifyMut = useMutation({
    mutationFn: () => qualifyLead(leadId, { qualification_notes: notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['crm', 'leads'] });
      addToast({
        type: 'success',
        title: t('crm.lead_qualified', { defaultValue: 'Lead qualified' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const disqualifyMut = useMutation({
    mutationFn: () => disqualifyLead(leadId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['crm', 'leads'] });
      addToast({
        type: 'success',
        title: t('crm.lead_disqualified', { defaultValue: 'Lead disqualified' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  if (!lead) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('crm.lead_detail', {
          defaultValue: 'Lead detail: {{name}}',
          name: lead.contact_name,
        })}
        className="relative h-full w-full max-w-lg overflow-y-auto bg-surface-elevated shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-light bg-surface-elevated px-5 py-3">
          <div>
            <h2 className="text-base font-semibold">{lead.contact_name}</h2>
            <Badge variant={LEAD_STATUS_VARIANT[lead.status]} dot>
              {lead.status}
            </Badge>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close', { defaultValue: 'Close' })}
            className="rounded p-1 hover:bg-surface-secondary"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 p-5">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field
              label={t('crm.email', { defaultValue: 'Email' })}
              value={lead.contact_email || '—'}
            />
            <Field
              label={t('crm.phone', { defaultValue: 'Phone' })}
              value={lead.contact_phone || '—'}
            />
            <Field
              label={t('crm.source', { defaultValue: 'Source' })}
              value={<span className="capitalize">{lead.source.replace(/_/g, ' ')}</span>}
            />
            <Field
              label={t('crm.account', { defaultValue: 'Account' })}
              value={
                lead.account_id
                  ? accountsById[lead.account_id]?.name || lead.account_id
                  : '—'
              }
            />
            {lead.qualified_at && (
              <Field
                label={t('crm.qualified_at', { defaultValue: 'Qualified at' })}
                value={<DateDisplay value={lead.qualified_at} />}
              />
            )}
            {lead.converted_at && (
              <Field
                label={t('crm.converted_at', { defaultValue: 'Converted at' })}
                value={<DateDisplay value={lead.converted_at} />}
              />
            )}
          </div>

          {(lead.status === 'new' || lead.status === 'qualifying') && (
            <Card padding="sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-2">
                {t('crm.qualify_lead', { defaultValue: 'Qualify lead' })}
              </p>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={4}
                placeholder={t('crm.qualification_notes', {
                  defaultValue:
                    'Notes — budget, authority, need, timeline, fit, …',
                })}
                className={clsx(inputCls, 'h-auto py-2')}
              />
              <div className="flex gap-2 mt-2">
                <Button
                  variant="primary"
                  icon={<CheckCircle2 size={14} />}
                  onClick={() => qualifyMut.mutate()}
                  loading={qualifyMut.isPending}
                >
                  {t('crm.qualify', { defaultValue: 'Qualify' })}
                </Button>
                <Button
                  variant="ghost"
                  icon={<XCircle size={14} />}
                  onClick={() => disqualifyMut.mutate()}
                  loading={disqualifyMut.isPending}
                >
                  {t('crm.disqualify', { defaultValue: 'Disqualify' })}
                </Button>
              </div>
            </Card>
          )}

          {lead.qualification_notes && lead.status !== 'new' && lead.status !== 'qualifying' && (
            <Card padding="sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-1">
                {t('crm.notes', { defaultValue: 'Notes' })}
              </p>
              <p className="text-sm whitespace-pre-wrap">
                {lead.qualification_notes}
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Opportunity detail drawer ─── */

function OpportunityDetailDrawer({
  opportunityId,
  opportunities,
  stages,
  accountsById,
  onClose,
}: {
  opportunityId: string;
  opportunities: Opportunity[];
  stages: PipelineStage[];
  accountsById: Record<string, Account>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const opp = opportunities.find((o) => o.id === opportunityId);

  const activitiesQ = useQuery({
    queryKey: ['crm', 'activities', 'opp', opportunityId],
    queryFn: () => listActivities({ opportunity_id: opportunityId, limit: 50 }),
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const [loseReason, setLoseReason] = useState('');

  const moveMut = useMutation({
    mutationFn: (toStageId: string) =>
      moveOpportunityStage(opportunityId, { to_stage_id: toStageId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['crm', 'opportunities'] });
      addToast({
        type: 'success',
        title: t('crm.stage_moved', { defaultValue: 'Stage updated' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const winMut = useMutation({
    mutationFn: () => winOpportunity(opportunityId, { won_at: todayIso() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['crm', 'opportunities'] });
      addToast({
        type: 'success',
        title: t('crm.opportunity_won', { defaultValue: 'Opportunity won' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const loseMut = useMutation({
    mutationFn: () =>
      loseOpportunity(opportunityId, {
        lost_reason_code: loseReason.trim(),
        lost_at: todayIso(),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['crm', 'opportunities'] });
      addToast({
        type: 'success',
        title: t('crm.opportunity_lost', { defaultValue: 'Opportunity lost' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  if (!opp) return null;

  const sortedStages = [...stages].sort((a, b) => a.display_order - b.display_order);
  const currentIdx = sortedStages.findIndex((s) => s.id === opp.stage_id);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('crm.opportunity_detail', {
          defaultValue: 'Opportunity detail: {{title}}',
          title: opp.title,
        })}
        className="relative h-full w-full max-w-2xl overflow-y-auto bg-surface-elevated shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-light bg-surface-elevated px-5 py-3">
          <div>
            <h2 className="text-base font-semibold">{opp.title}</h2>
            <div className="mt-1 flex items-center gap-2">
              <Badge variant={OPP_STATUS_VARIANT[opp.status]} dot>
                {opp.status}
              </Badge>
              <span className="text-xs text-content-tertiary">
                {accountsById[opp.account_id]?.name || ''}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close', { defaultValue: 'Close' })}
            className="rounded p-1 hover:bg-surface-secondary"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 p-5">
          {/* Headline KPIs */}
          <div className="grid grid-cols-3 gap-3">
            <KPI
              label={t('crm.value', { defaultValue: 'Value' })}
              value={
                <MoneyDisplay
                  amount={toNum(opp.estimated_value)}
                  currency={opp.currency || undefined}
                />
              }
            />
            <KPI
              label={t('crm.weighted', { defaultValue: 'Weighted' })}
              value={
                <MoneyDisplay
                  amount={toNum(opp.weighted_value)}
                  currency={opp.currency || undefined}
                />
              }
            />
            <KPI
              label={t('crm.probability', { defaultValue: 'Probability' })}
              value={`${opp.probability_percent}%`}
            />
          </div>

          {/* Pipeline visual */}
          <Card padding="sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-2">
              {t('crm.pipeline', { defaultValue: 'Pipeline' })}
            </p>
            <div className="flex items-center gap-1 flex-wrap">
              {sortedStages.map((s, idx) => {
                const isCurrent = s.id === opp.stage_id;
                const isPast = currentIdx >= 0 && idx < currentIdx;
                const bg = isCurrent
                  ? s.is_won
                    ? 'bg-emerald-500 text-white ring-emerald-500'
                    : s.is_lost
                      ? 'bg-rose-500 text-white ring-rose-500'
                      : 'bg-oe-blue text-white ring-oe-blue'
                  : isPast
                    ? 'bg-surface-secondary text-content-secondary ring-border-light'
                    : 'bg-transparent text-content-tertiary ring-border-light';
                return (
                  <div key={s.id} className="flex items-center gap-1">
                    <button
                      type="button"
                      disabled={
                        opp.status !== 'open' ||
                        isCurrent ||
                        moveMut.isPending
                      }
                      onClick={() => moveMut.mutate(s.id)}
                      className={clsx(
                        'inline-flex items-center rounded-md px-2.5 py-1 text-xs font-medium ring-1 ring-inset transition-colors',
                        bg,
                        opp.status === 'open' && !isCurrent
                          ? 'hover:opacity-80 cursor-pointer'
                          : 'cursor-default',
                      )}
                    >
                      {s.name}
                    </button>
                    {idx < sortedStages.length - 1 && (
                      <ArrowRight
                        size={12}
                        className="text-content-tertiary shrink-0"
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Workflow buttons */}
          {opp.status === 'open' && (
            <Card padding="sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-2">
                {t('crm.close_deal', { defaultValue: 'Close the deal' })}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  icon={<Trophy size={14} />}
                  onClick={() => winMut.mutate()}
                  loading={winMut.isPending}
                >
                  {t('crm.win', { defaultValue: 'Win' })}
                </Button>
                <div className="flex gap-1 flex-1 max-w-md">
                  <input
                    value={loseReason}
                    onChange={(e) => setLoseReason(e.target.value)}
                    aria-label={t('crm.lose_reason', {
                      defaultValue: 'Loss reason code',
                    })}
                    placeholder={t('crm.lose_reason', {
                      defaultValue: 'Loss reason code',
                    })}
                    className={inputCls}
                  />
                  <Button
                    variant="ghost"
                    icon={<Frown size={14} />}
                    onClick={() => loseMut.mutate()}
                    loading={loseMut.isPending}
                    disabled={!loseReason.trim()}
                  >
                    {t('crm.lose', { defaultValue: 'Lose' })}
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {/* Description / notes */}
          {(opp.description || opp.notes) && (
            <Card padding="sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-1">
                {t('crm.description', { defaultValue: 'Description' })}
              </p>
              <p className="text-sm whitespace-pre-wrap">
                {opp.description || opp.notes}
              </p>
            </Card>
          )}

          {/* Activity feed */}
          <Card padding="sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-2">
              {t('crm.activities', { defaultValue: 'Activities' })}
              <span className="ml-2 text-content-tertiary normal-case">
                ({(activitiesQ.data ?? []).length})
              </span>
            </p>
            {activitiesQ.isLoading ? (
              <SkeletonTable rows={3} columns={3} />
            ) : (activitiesQ.data ?? []).length === 0 ? (
              <p className="text-sm text-content-tertiary py-1">
                {t('crm.no_activities', { defaultValue: 'No activities logged yet.' })}
              </p>
            ) : (
              <ul className="space-y-2">
                {(activitiesQ.data ?? []).map((a) => (
                  <li
                    key={a.id}
                    className="flex gap-3 border-b border-border-light pb-2 last:border-0"
                  >
                    <span className="text-[10px] uppercase font-semibold text-content-tertiary mt-0.5 w-16 shrink-0">
                      {a.kind}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm font-medium">{a.subject || '—'}</p>
                      {a.body && (
                        <p className="text-xs text-content-secondary whitespace-pre-wrap mt-0.5">
                          {a.body}
                        </p>
                      )}
                      <p className="text-[10px] text-content-tertiary mt-0.5">
                        <DateDisplay value={a.created_at} />
                        {a.outcome && ` · ${a.outcome}`}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Competitors */}
          {opp.competitor_names.length > 0 && (
            <Card padding="sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-1">
                {t('crm.competitors', { defaultValue: 'Competitors' })}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {opp.competitor_names.map((c) => (
                  <span
                    key={c}
                    className="inline-flex items-center rounded-md bg-surface-secondary px-2 py-0.5 text-xs text-content-secondary"
                  >
                    {c}
                  </span>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function KPI({ label, value }: { label: React.ReactNode; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border-light bg-surface-secondary px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-content-tertiary">
        {label}
      </p>
      <p className="mt-0.5 text-sm font-semibold text-content-primary">
        {value}
      </p>
    </div>
  );
}

function Field({ label, value }: { label: React.ReactNode; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-content-tertiary">
        {label}
      </p>
      <p className="mt-0.5 text-sm text-content-primary">{value}</p>
    </div>
  );
}

/* ─── Create modal ─── */

function CreateModal({
  kind,
  accounts,
  stages,
  onClose,
}: {
  kind: Tab;
  accounts: Account[];
  stages: PipelineStage[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [busy, setBusy] = useState(false);

  const [accountForm, setAccountForm] = useState({
    name: '',
    industry: '',
    country: '',
    size_category: 'sme' as AccountSize,
    status: 'active' as AccountStatus,
  });

  const [leadForm, setLeadForm] = useState({
    contact_name: '',
    contact_email: '',
    contact_phone: '',
    account_id: '',
    source: 'inbound' as LeadSource,
  });

  const [oppForm, setOppForm] = useState({
    account_id: accounts[0]?.id || '',
    title: '',
    estimated_value: '0',
    currency: 'EUR',
    probability_percent: '20',
    stage_id: stages[0]?.id || '',
    expected_close_date: '',
  });

  const [actForm, setActForm] = useState({
    kind: 'note' as ActivityKind,
    subject: '',
    body: '',
    due_at: '',
  });

  const submit = async () => {
    setBusy(true);
    try {
      if (kind === 'accounts') {
        if (!accountForm.name.trim()) throw new Error('Name required');
        await createAccount({
          name: accountForm.name.trim(),
          industry: accountForm.industry || undefined,
          country: accountForm.country || undefined,
          size_category: accountForm.size_category,
          status: accountForm.status,
        });
        addToast({
          type: 'success',
          title: t('crm.account_created', { defaultValue: 'Account created' }),
        });
        qc.invalidateQueries({ queryKey: ['crm', 'accounts'] });
      } else if (kind === 'leads') {
        if (!leadForm.contact_name.trim()) throw new Error('Contact name required');
        await createLead({
          contact_name: leadForm.contact_name.trim(),
          contact_email: leadForm.contact_email || undefined,
          contact_phone: leadForm.contact_phone || undefined,
          account_id: leadForm.account_id || null,
          source: leadForm.source,
        });
        addToast({
          type: 'success',
          title: t('crm.lead_created', { defaultValue: 'Lead created' }),
        });
        qc.invalidateQueries({ queryKey: ['crm', 'leads'] });
      } else if (kind === 'opportunities') {
        if (!oppForm.account_id) throw new Error('Account required');
        if (!oppForm.stage_id) throw new Error('Stage required');
        if (!oppForm.title.trim()) throw new Error('Title required');
        await createOpportunity({
          account_id: oppForm.account_id,
          title: oppForm.title.trim(),
          estimated_value: Number(oppForm.estimated_value) || 0,
          currency: oppForm.currency || 'EUR',
          probability_percent: Number(oppForm.probability_percent) || 0,
          stage_id: oppForm.stage_id,
          expected_close_date: oppForm.expected_close_date || null,
        });
        addToast({
          type: 'success',
          title: t('crm.opportunity_created', {
            defaultValue: 'Opportunity created',
          }),
        });
        qc.invalidateQueries({ queryKey: ['crm', 'opportunities'] });
      } else if (kind === 'activities') {
        await createActivity({
          kind: actForm.kind,
          subject: actForm.subject || undefined,
          body: actForm.body || undefined,
          due_at: actForm.due_at || null,
        });
        addToast({
          type: 'success',
          title: t('crm.activity_created', { defaultValue: 'Activity created' }),
        });
        qc.invalidateQueries({ queryKey: ['crm', 'activities'] });
      }
      onClose();
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  const title =
    kind === 'accounts'
      ? t('crm.new_account', { defaultValue: 'New Account' })
      : kind === 'leads'
        ? t('crm.new_lead', { defaultValue: 'New Lead' })
        : kind === 'opportunities'
          ? t('crm.new_opportunity', { defaultValue: 'New Opportunity' })
          : t('crm.new_activity', { defaultValue: 'New Activity' });

  // Opportunities have the widest form (7 fields) so we use xl; accounts
  // and leads fit comfortably in lg.
  const size = kind === 'opportunities' ? 'xl' : 'lg';

  return (
    <WideModal
      open
      onClose={onClose}
      title={title}
      size={size}
      busy={busy}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            loading={busy}
            icon={busy ? <Loader2 size={14} /> : <Plus size={14} />}
          >
            {t('common.create', { defaultValue: 'Create' })}
          </Button>
        </>
      }
    >
      {kind === 'accounts' && (
        <WideModalSection columns={2}>
          <WideModalField
            label={t('crm.account_name', { defaultValue: 'Name' })}
            required
            span={2}
          >
            <input
              value={accountForm.name}
              onChange={(e) =>
                setAccountForm({ ...accountForm, name: e.target.value })
              }
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('crm.industry', { defaultValue: 'Industry' })}
          >
            <input
              value={accountForm.industry}
              onChange={(e) =>
                setAccountForm({ ...accountForm, industry: e.target.value })
              }
              className={inputCls}
            />
          </WideModalField>
          <WideModalField label={t('crm.country', { defaultValue: 'Country' })}>
            <input
              value={accountForm.country}
              onChange={(e) =>
                setAccountForm({ ...accountForm, country: e.target.value })
              }
              className={inputCls}
            />
          </WideModalField>
          <WideModalField label={t('crm.size', { defaultValue: 'Size' })}>
            <select
              value={accountForm.size_category}
              onChange={(e) =>
                setAccountForm({
                  ...accountForm,
                  size_category: e.target.value as AccountSize,
                })
              }
              className={inputCls}
            >
              <option value="sme">SME</option>
              <option value="mid">Mid-market</option>
              <option value="enterprise">Enterprise</option>
            </select>
          </WideModalField>
          <WideModalField label={t('crm.status', { defaultValue: 'Status' })}>
            <select
              value={accountForm.status}
              onChange={(e) =>
                setAccountForm({
                  ...accountForm,
                  status: e.target.value as AccountStatus,
                })
              }
              className={inputCls}
            >
              <option value="active">active</option>
              <option value="dormant">dormant</option>
              <option value="lost">lost</option>
            </select>
          </WideModalField>
        </WideModalSection>
      )}

      {kind === 'leads' && (
        <WideModalSection columns={2}>
          <WideModalField
            label={t('crm.contact_name', { defaultValue: 'Contact name' })}
            required
            span={2}
          >
            <input
              value={leadForm.contact_name}
              onChange={(e) =>
                setLeadForm({ ...leadForm, contact_name: e.target.value })
              }
              className={inputCls}
            />
          </WideModalField>
          <WideModalField label={t('crm.email', { defaultValue: 'Email' })}>
            <input
              type="email"
              value={leadForm.contact_email}
              onChange={(e) =>
                setLeadForm({ ...leadForm, contact_email: e.target.value })
              }
              className={inputCls}
            />
          </WideModalField>
          <WideModalField label={t('crm.phone', { defaultValue: 'Phone' })}>
            <input
              value={leadForm.contact_phone}
              onChange={(e) =>
                setLeadForm({ ...leadForm, contact_phone: e.target.value })
              }
              className={inputCls}
            />
          </WideModalField>
          <WideModalField label={t('crm.account', { defaultValue: 'Account' })}>
            <select
              value={leadForm.account_id}
              onChange={(e) =>
                setLeadForm({ ...leadForm, account_id: e.target.value })
              }
              className={inputCls}
            >
              <option value="">—</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </WideModalField>
          <WideModalField label={t('crm.source', { defaultValue: 'Source' })}>
            <select
              value={leadForm.source}
              onChange={(e) =>
                setLeadForm({ ...leadForm, source: e.target.value as LeadSource })
              }
              className={inputCls}
            >
              {LEAD_SOURCES.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </WideModalField>
        </WideModalSection>
      )}

      {kind === 'opportunities' && (
        <>
          <WideModalSection
            title={t('crm.section_basic', { defaultValue: 'Basic info' })}
            columns={2}
          >
            <WideModalField
              label={t('crm.title_col', { defaultValue: 'Title' })}
              required
              span={2}
            >
              <input
                value={oppForm.title}
                onChange={(e) =>
                  setOppForm({ ...oppForm, title: e.target.value })
                }
                className={inputCls}
              />
            </WideModalField>
            <WideModalField
              label={t('crm.account', { defaultValue: 'Account' })}
              required
              span={2}
            >
              <select
                value={oppForm.account_id}
                onChange={(e) =>
                  setOppForm({ ...oppForm, account_id: e.target.value })
                }
                className={inputCls}
              >
                <option value="">—</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </WideModalField>
          </WideModalSection>

          <WideModalSection
            title={t('crm.section_value', { defaultValue: 'Value & pipeline' })}
            columns={2}
          >
            <WideModalField label={t('crm.value', { defaultValue: 'Value' })}>
              <input
                type="number"
                value={oppForm.estimated_value}
                onChange={(e) =>
                  setOppForm({ ...oppForm, estimated_value: e.target.value })
                }
                className={inputCls}
              />
            </WideModalField>
            <WideModalField
              label={t('crm.currency', { defaultValue: 'Currency' })}
            >
              <input
                value={oppForm.currency}
                onChange={(e) =>
                  setOppForm({ ...oppForm, currency: e.target.value })
                }
                className={inputCls}
                maxLength={8}
              />
            </WideModalField>
            <WideModalField label={t('crm.stage', { defaultValue: 'Stage' })}>
              <select
                value={oppForm.stage_id}
                onChange={(e) =>
                  setOppForm({ ...oppForm, stage_id: e.target.value })
                }
                className={inputCls}
              >
                <option value="">—</option>
                {stages.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </WideModalField>
            <WideModalField
              label={t('crm.probability', { defaultValue: 'Probability %' })}
            >
              <input
                type="number"
                min={0}
                max={100}
                value={oppForm.probability_percent}
                onChange={(e) =>
                  setOppForm({
                    ...oppForm,
                    probability_percent: e.target.value,
                  })
                }
                className={inputCls}
              />
            </WideModalField>
            <WideModalField
              label={t('crm.expected_close', { defaultValue: 'Expected close' })}
              span={2}
            >
              <input
                type="date"
                value={oppForm.expected_close_date}
                onChange={(e) =>
                  setOppForm({ ...oppForm, expected_close_date: e.target.value })
                }
                className={inputCls}
              />
            </WideModalField>
          </WideModalSection>
        </>
      )}

      {kind === 'activities' && (
        <WideModalSection columns={2}>
          <WideModalField label={t('crm.kind', { defaultValue: 'Kind' })}>
            <select
              value={actForm.kind}
              onChange={(e) =>
                setActForm({ ...actForm, kind: e.target.value as ActivityKind })
              }
              className={inputCls}
            >
              {ACTIVITY_KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </WideModalField>
          <WideModalField label={t('crm.due', { defaultValue: 'Due' })}>
            <input
              type="date"
              value={actForm.due_at}
              onChange={(e) =>
                setActForm({ ...actForm, due_at: e.target.value })
              }
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('crm.subject', { defaultValue: 'Subject' })}
            span={2}
          >
            <input
              value={actForm.subject}
              onChange={(e) =>
                setActForm({ ...actForm, subject: e.target.value })
              }
              className={inputCls}
            />
          </WideModalField>
          <WideModalField
            label={t('crm.body', { defaultValue: 'Body' })}
            span={2}
          >
            <textarea
              value={actForm.body}
              onChange={(e) =>
                setActForm({ ...actForm, body: e.target.value })
              }
              rows={4}
              className={clsx(inputCls, 'h-auto py-2')}
            />
          </WideModalField>
        </WideModalSection>
      )}
    </WideModal>
  );
}
