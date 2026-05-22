import { useState, useMemo, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  Package as PackageIcon,
  Mail,
  Inbox,
  HelpCircle,
  Plus,
  Search,
  X,
  Send,
  XCircle,
  Loader2,
  Calculator,
  Award,
  ArrowRight,
} from 'lucide-react';
import {
  Button,
  Card,
  Badge,
  EmptyState,
  Breadcrumb,
  SkeletonTable,
  WideModal,
  WideModalSection,
  WideModalField,
} from '@/shared/ui';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { PipelineBanner } from './PipelineBanner';
import { apiGet, getErrorMessage } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import {
  listPackages,
  getPackage,
  createPackage,
  publishPackage,
  closePackage,
  awardPackage,
  packageDashboard,
  createBidder,
  createInvitation,
  createQA,
  answerQA,
  createComparison,
  computeLeveling,
  levelingTable,
  type BidPackage,
  type BidPackageStatus,
  type BidInvitationStatus,
  type Bidder,
  type BidInvitation,
  type BidSubmission,
  type BidSubmissionLine,
  type BidQA,
  type BidPackageLineItem,
} from './api';

type Tab = 'packages' | 'invitations' | 'submissions' | 'qa';

const PACKAGE_STATUS_VARIANT: Record<
  BidPackageStatus,
  'neutral' | 'blue' | 'success' | 'warning' | 'error'
> = {
  draft: 'neutral',
  published: 'blue',
  open: 'warning',
  closed: 'neutral',
  cancelled: 'error',
  awarded: 'success',
};

const INVITATION_STATUS_VARIANT: Record<
  BidInvitationStatus,
  'neutral' | 'blue' | 'success' | 'warning' | 'error'
> = {
  pending: 'neutral',
  sent: 'blue',
  opened: 'warning',
  submitted: 'success',
  declined: 'error',
  expired: 'neutral',
};

const inputCls =
  'h-9 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

const labelCls = 'block text-xs font-medium text-content-secondary mb-1';

interface ProjectStub {
  id: string;
  name: string;
  currency?: string;
}

function listProjectsLite(): Promise<ProjectStub[]> {
  return apiGet<ProjectStub[]>('/v1/projects/?limit=200').catch(() => [] as ProjectStub[]);
}

function listInvitationsForPackage(packageId: string): Promise<BidInvitation[]> {
  return apiGet<BidInvitation[]>(
    `/v1/bid-management/invitations/?package_id=${packageId}&limit=200`,
  ).catch(() => [] as BidInvitation[]);
}

function listBiddersForPackage(packageId: string): Promise<Bidder[]> {
  return apiGet<Bidder[]>(
    `/v1/bid-management/bidders/?package_id=${packageId}&limit=200`,
  ).catch(() => [] as Bidder[]);
}

function listSubmissionsForPackage(packageId: string): Promise<BidSubmission[]> {
  return apiGet<BidSubmission[]>(
    `/v1/bid-management/submissions/?package_id=${packageId}&limit=200`,
  ).catch(() => [] as BidSubmission[]);
}

function listLineItemsForPackage(packageId: string): Promise<BidPackageLineItem[]> {
  return apiGet<BidPackageLineItem[]>(
    `/v1/bid-management/bid-package-line-items/?package_id=${packageId}&limit=500`,
  ).catch(() => [] as BidPackageLineItem[]);
}

function listSubmissionLines(submissionId: string): Promise<BidSubmissionLine[]> {
  return apiGet<BidSubmissionLine[]>(
    `/v1/bid-management/submission-lines/?submission_id=${submissionId}&limit=500`,
  ).catch(() => [] as BidSubmissionLine[]);
}

function listQAForPackage(packageId: string): Promise<BidQA[]> {
  return apiGet<BidQA[]>(
    `/v1/bid-management/q-and-a/?package_id=${packageId}&limit=200`,
  ).catch(() => [] as BidQA[]);
}

export function BidManagementPage() {
  const { t } = useTranslation();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const setActiveProject = useProjectContextStore((s) => s.setActiveProject);

  const projectsQ = useQuery({
    queryKey: ['bid-management', 'projects'],
    queryFn: listProjectsLite,
    staleTime: 60_000,
  });

  const projects = projectsQ.data ?? [];
  const projectId = activeProjectId || projects[0]?.id || '';
  const currentProject = useMemo(
    () => projects.find((p) => p.id === projectId),
    [projects, projectId],
  );

  const [tab, setTab] = useState<Tab>('packages');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [selectedPackageId, setSelectedPackageId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const packagesQ = useQuery({
    queryKey: ['bid-management', 'packages', projectId, statusFilter],
    queryFn: () =>
      listPackages({ project_id: projectId, status: statusFilter || undefined, limit: 200 }),
    enabled: !!projectId,
  });

  const filteredPackages = useMemo(() => {
    const items = packagesQ.data ?? [];
    if (!search.trim()) return items;
    const s = search.toLowerCase();
    return items.filter(
      (p) =>
        p.code.toLowerCase().includes(s) ||
        (p.title || '').toLowerCase().includes(s) ||
        (p.scope_description || '').toLowerCase().includes(s),
    );
  }, [packagesQ.data, search]);

  const isLoading = packagesQ.isLoading || projectsQ.isLoading;

  if (!projectId) {
    return (
      <div className="space-y-5">
        <Breadcrumb
          items={[{ label: t('bid_management.title', { defaultValue: 'Bid Management' }) }]}
        />
        <EmptyState
          icon={<PackageIcon size={22} />}
          title={t('bid_management.no_project', {
            defaultValue: 'Select a project to manage bid packages',
          })}
          description={t('bid_management.no_project_desc', {
            defaultValue:
              'Bid Management is project-scoped — create or open a project, then return here.',
          })}
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <Breadcrumb
        items={[{ label: t('bid_management.title', { defaultValue: 'Bid Management' }) }]}
      />

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">
            {t('bid_management.title', { defaultValue: 'Bid Management' })}
          </h1>
          <p className="mt-1 text-sm text-content-secondary">
            {t('bid_management.subtitle', {
              defaultValue:
                'Run end-to-end tendering: packages, invitations, submissions, Q&A, and bid leveling.',
            })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {projects.length > 1 && (
            <select
              value={projectId}
              onChange={(e) => {
                const p = projects.find((x) => x.id === e.target.value);
                if (p) setActiveProject(p.id, p.name);
              }}
              className={clsx(inputCls, 'max-w-[260px]')}
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
          <Button variant="primary" icon={<Plus size={14} />} onClick={() => setCreateOpen(true)}>
            {t('bid_management.new_package', { defaultValue: 'New Package' })}
          </Button>
        </div>
      </div>

      <PipelineBanner
        intro={t('bid_management.pipeline_intro', {
          defaultValue:
            'Take won work to market: bundle scope into a package, invite prequalified subcontractors, collect priced submissions, level them side by side, and award. The award becomes a contract.',
        })}
        steps={[
          { label: t('bid_management.step_crm', { defaultValue: 'CRM' }), to: '/crm' },
          {
            label: t('bid_management.step_subs', {
              defaultValue: 'Subcontractors',
            }),
            to: '/subcontractors',
          },
          {
            label: t('bid_management.step_bid', { defaultValue: 'Bid Management' }),
            current: true,
          },
          {
            label: t('bid_management.step_contract', { defaultValue: 'Contracts' }),
            to: '/contracts',
          },
        ]}
      />

      <div className="border-b border-border-light">
        <nav className="flex gap-1 -mb-px" role="tablist">
          {(
            [
              {
                id: 'packages',
                label: t('bid_management.tab_packages', { defaultValue: 'Packages' }),
                icon: PackageIcon,
              },
              {
                id: 'invitations',
                label: t('bid_management.tab_invitations', { defaultValue: 'Invitations' }),
                icon: Mail,
              },
              {
                id: 'submissions',
                label: t('bid_management.tab_submissions', { defaultValue: 'Submissions' }),
                icon: Inbox,
              },
              {
                id: 'qa',
                label: t('bid_management.tab_qa', { defaultValue: 'Q & A' }),
                icon: HelpCircle,
              },
            ] as { id: Tab; label: string; icon: React.ElementType }[]
          ).map((tabItem) => {
            const Icon = tabItem.icon;
            return (
              <button
                key={tabItem.id}
                type="button"
                role="tab"
                aria-selected={tab === tabItem.id}
                onClick={() => {
                  setTab(tabItem.id);
                  setStatusFilter('');
                  setSearch('');
                }}
                className={clsx(
                  'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
                  tab === tabItem.id
                    ? 'border-oe-blue text-oe-blue'
                    : 'border-transparent text-content-secondary hover:text-content-primary',
                )}
              >
                <Icon size={14} />
                {tabItem.label}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-content-tertiary"
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('common.search', { defaultValue: 'Search…' })}
            className={clsx(inputCls, 'pl-8')}
          />
        </div>
        {tab === 'packages' && (
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className={clsx(inputCls, 'max-w-[200px]')}
          >
            <option value="">{t('common.all_statuses', { defaultValue: 'All statuses' })}</option>
            {['draft', 'published', 'open', 'closed', 'cancelled', 'awarded'].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        )}
      </div>

      <Card padding="none">
        {isLoading ? (
          <div className="p-4">
            <SkeletonTable rows={8} columns={5} />
          </div>
        ) : packagesQ.isError ? (
          <EmptyState
            icon={<XCircle size={22} />}
            title={t('bid_management.load_failed', {
              defaultValue: 'Could not load bid packages',
            })}
            description={getErrorMessage(packagesQ.error)}
            action={{
              label: t('common.retry', { defaultValue: 'Retry' }),
              onClick: () => packagesQ.refetch(),
            }}
          />
        ) : tab === 'packages' ? (
          <PackageTable
            rows={filteredPackages}
            onSelect={(id) => setSelectedPackageId(id)}
            currency={currentProject?.currency || 'EUR'}
            emptyAction={() => setCreateOpen(true)}
          />
        ) : tab === 'invitations' ? (
          <InvitationsView packages={filteredPackages} />
        ) : tab === 'submissions' ? (
          <SubmissionsLevelingView
            packages={filteredPackages}
            currency={currentProject?.currency || 'EUR'}
          />
        ) : (
          <QAView packages={filteredPackages} />
        )}
      </Card>

      {selectedPackageId && (
        <PackageDrawer
          packageId={selectedPackageId}
          onClose={() => setSelectedPackageId(null)}
          currency={currentProject?.currency || 'EUR'}
        />
      )}

      {createOpen && (
        <CreatePackageModal
          projectId={projectId}
          currency={currentProject?.currency || 'EUR'}
          onClose={() => setCreateOpen(false)}
        />
      )}
    </div>
  );
}

/* ─── Package table ─── */

function PackageTable({
  rows,
  onSelect,
  currency,
  emptyAction,
}: {
  rows: BidPackage[];
  onSelect: (id: string) => void;
  currency: string;
  emptyAction: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<PackageIcon size={22} />}
        title={t('bid_management.empty_packages', { defaultValue: 'No bid packages yet' })}
        description={t('bid_management.empty_packages_desc', {
          defaultValue: 'Bundle scope, invite bidders and award the best offer.',
        })}
        action={{
          label: t('bid_management.new_package', { defaultValue: 'New Package' }),
          onClick: emptyAction,
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
              {t('bid_management.code', { defaultValue: 'Code' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('bid_management.title_col', { defaultValue: 'Title' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('bid_management.deadline', { defaultValue: 'Deadline' })}
            </th>
            <th className="px-4 py-2.5 text-left">
              {t('bid_management.status', { defaultValue: 'Status' })}
            </th>
            <th className="px-4 py-2.5 text-right">
              {t('bid_management.budget', { defaultValue: 'Budget' })}
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
              <td className="px-4 py-2 font-mono text-xs text-content-secondary">{r.code}</td>
              <td className="px-4 py-2 font-medium truncate max-w-[420px]">{r.title || '—'}</td>
              <td className="px-4 py-2 text-xs text-content-secondary">
                {r.submission_deadline ? <DateDisplay value={r.submission_deadline} /> : '—'}
              </td>
              <td className="px-4 py-2">
                <Badge variant={PACKAGE_STATUS_VARIANT[r.status]} dot>
                  {r.status}
                </Badge>
              </td>
              <td className="px-4 py-2 text-right">
                <MoneyDisplay
                  amount={Number(r.total_budget_estimate) || 0}
                  currency={r.currency || currency}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ─── Invitations view ─── */

function InvitationsView({ packages }: { packages: BidPackage[] }) {
  const { t } = useTranslation();
  const [openPkg, setOpenPkg] = useState<string | null>(null);

  if (packages.length === 0) {
    return (
      <EmptyState
        icon={<Mail size={22} />}
        title={t('bid_management.empty_invitations', { defaultValue: 'No invitations to show' })}
        description={t('bid_management.empty_invitations_desc', {
          defaultValue: 'Create a bid package first, then invite bidders.',
        })}
      />
    );
  }

  return (
    <div className="divide-y divide-border-light">
      {packages.map((pkg) => (
        <PackageInvitationsRow
          key={pkg.id}
          pkg={pkg}
          open={openPkg === pkg.id}
          onToggle={() => setOpenPkg(openPkg === pkg.id ? null : pkg.id)}
        />
      ))}
    </div>
  );
}

function PackageInvitationsRow({
  pkg,
  open,
  onToggle,
}: {
  pkg: BidPackage;
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const dashQ = useQuery({
    queryKey: ['bid-management', 'dashboard', pkg.id],
    queryFn: () => packageDashboard(pkg.id),
  });
  const invQ = useQuery({
    queryKey: ['bid-management', 'invitations', pkg.id],
    queryFn: () => listInvitationsForPackage(pkg.id),
    enabled: open,
  });
  const stats = dashQ.data;
  const sent = stats?.invitations_count ?? 0;
  const responded = stats?.submissions_count ?? 0;

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-secondary text-left"
        aria-expanded={open}
      >
        <div className="min-w-0">
          <p className="font-mono text-xs text-content-secondary">{pkg.code}</p>
          <p className="text-sm font-medium truncate">{pkg.title || '—'}</p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <Badge variant="blue">
            {t('bid_management.sent', { defaultValue: 'Sent' })}: {sent}
          </Badge>
          <Badge variant="success">
            {t('bid_management.responded', { defaultValue: 'Responded' })}: {responded}
          </Badge>
        </div>
      </button>
      {open && (
        <div className="px-4 pb-4">
          {invQ.isLoading ? (
            <SkeletonTable rows={3} columns={4} />
          ) : (invQ.data ?? []).length === 0 ? (
            <p className="text-xs text-content-secondary py-2">
              {t('bid_management.no_invitations', {
                defaultValue: 'No invitations sent for this package yet.',
              })}
            </p>
          ) : (
            <table className="w-full text-xs border border-border-light rounded">
              <thead className="bg-surface-secondary text-content-tertiary uppercase tracking-wide">
                <tr>
                  <th className="px-3 py-2 text-left">
                    {t('bid_management.invitee', { defaultValue: 'Invitee' })}
                  </th>
                  <th className="px-3 py-2 text-left">
                    {t('bid_management.email', { defaultValue: 'Email' })}
                  </th>
                  <th className="px-3 py-2 text-left">
                    {t('bid_management.sent_at', { defaultValue: 'Sent' })}
                  </th>
                  <th className="px-3 py-2 text-left">
                    {t('bid_management.status', { defaultValue: 'Status' })}
                  </th>
                </tr>
              </thead>
              <tbody>
                {(invQ.data ?? []).map((inv) => (
                  <tr key={inv.id} className="border-t border-border-light">
                    <td className="px-3 py-1.5">{inv.invitee_company_name || '—'}</td>
                    <td className="px-3 py-1.5 text-content-secondary">{inv.invitee_email}</td>
                    <td className="px-3 py-1.5 text-content-secondary">
                      {inv.sent_at ? <DateDisplay value={inv.sent_at} /> : '—'}
                    </td>
                    <td className="px-3 py-1.5">
                      <Badge variant={INVITATION_STATUS_VARIANT[inv.status]} dot>
                        {inv.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── Submissions + Bid leveling ─── */

function SubmissionsLevelingView({
  packages,
  currency,
}: {
  packages: BidPackage[];
  currency: string;
}) {
  const { t } = useTranslation();
  // Controlled selection that *defaults* to the first package even when
  // `packages` arrives after first render — a bare useState(packages[0]?.id)
  // would freeze at '' and the dropdown would look broken.
  const [activePkg, setActivePkg] = useState<string>('');
  const pkg =
    packages.find((p) => p.id === activePkg) || packages[0] || undefined;

  if (!pkg) {
    return (
      <EmptyState
        icon={<Inbox size={22} />}
        title={t('bid_management.empty_submissions', { defaultValue: 'No submissions yet' })}
        description={t('bid_management.empty_submissions_desc', {
          defaultValue: 'Submissions show up here once bidders have replied.',
        })}
      />
    );
  }

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <label className={clsx(labelCls, 'mb-0 mr-1')}>
          {t('bid_management.package', { defaultValue: 'Package' })}
        </label>
        <select
          value={pkg.id}
          onChange={(e) => setActivePkg(e.target.value)}
          className={clsx(inputCls, 'max-w-[420px]')}
        >
          {packages.map((p) => (
            <option key={p.id} value={p.id}>
              {p.code} — {p.title || '—'}
            </option>
          ))}
        </select>
      </div>
      {(pkg.status === 'awarded' || pkg.status === 'cancelled') && (
        <div
          className={clsx(
            'rounded-lg border px-3 py-2 text-xs',
            pkg.status === 'awarded'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-200'
              : 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200',
          )}
        >
          {pkg.status === 'awarded'
            ? t('bid_management.already_awarded', {
                defaultValue:
                  'This package has been awarded. Leveling is read-only — open Contracts to manage the awarded scope.',
              })
            : t('bid_management.pkg_cancelled', {
                defaultValue: 'This package was cancelled — no further awards possible.',
              })}
        </div>
      )}
      <LevelingTable
        packageId={pkg.id}
        currency={pkg.currency || currency}
        awardable={pkg.status !== 'awarded' && pkg.status !== 'cancelled'}
      />
    </div>
  );
}

function LevelingTable({
  packageId,
  currency,
  awardable,
}: {
  packageId: string;
  currency: string;
  awardable: boolean;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const submissionsQ = useQuery({
    queryKey: ['bid-management', 'submissions', packageId],
    queryFn: () => listSubmissionsForPackage(packageId),
  });
  const linesQ = useQuery({
    queryKey: ['bid-management', 'lines', packageId],
    queryFn: () => listLineItemsForPackage(packageId),
  });
  const biddersQ = useQuery({
    queryKey: ['bid-management', 'bidders', packageId],
    queryFn: () => listBiddersForPackage(packageId),
  });

  const submissions = submissionsQ.data ?? [];
  const lineItems = linesQ.data ?? [];
  const bidders = biddersQ.data ?? [];

  const subLinesQs = useQuery({
    queryKey: ['bid-management', 'submission-lines', packageId, submissions.map((s) => s.id).join(',')],
    queryFn: async () => {
      const buckets = await Promise.all(submissions.map((s) => listSubmissionLines(s.id)));
      const map: Record<string, BidSubmissionLine[]> = {};
      submissions.forEach((s, i) => {
        map[s.id] = buckets[i] ?? [];
      });
      return map;
    },
    enabled: submissions.length > 0,
  });

  const awardMut = useMutation({
    mutationFn: async (sub: BidSubmission) => {
      return awardPackage(packageId, {
        package_id: packageId,
        awarded_bidder_id: sub.bidder_id,
        awarded_amount: Number(sub.total_amount) || 0,
        currency: sub.currency || currency,
        decision_summary: '',
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bid-management'] });
      addToast({
        type: 'success',
        title: t('bid_management.awarded', { defaultValue: 'Package awarded' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  if (submissionsQ.isLoading || linesQ.isLoading || biddersQ.isLoading) {
    return <SkeletonTable rows={6} columns={4} />;
  }
  if (submissions.length === 0) {
    return (
      <EmptyState
        icon={<Inbox size={22} />}
        title={t('bid_management.no_submissions_for_pkg', {
          defaultValue: 'No submissions for this package',
        })}
        description={t('bid_management.no_submissions_desc', {
          defaultValue: 'Once bidders submit their priced offers, leveling appears here.',
        })}
      />
    );
  }

  const bidderName = (id: string) => bidders.find((b) => b.id === id)?.company_name || id.slice(0, 8);

  const totalsBySub = new Map<string, number>(
    submissions.map((s) => [s.id, Number(s.total_amount) || 0]),
  );
  const totals = Array.from(totalsBySub.values());
  const min = Math.min(...totals);
  const max = Math.max(...totals);

  const linePriceMap = (subId: string, lineItemId: string): number => {
    const arr = subLinesQs.data?.[subId];
    if (!arr) return 0;
    const row = arr.find((l) => l.line_item_id === lineItemId);
    return row ? Number(row.total_price) || 0 : 0;
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead className="bg-surface-secondary text-content-tertiary text-xs uppercase tracking-wide">
          <tr>
            <th className="px-3 py-2 text-left sticky left-0 z-10 bg-surface-secondary">
              {t('bid_management.scope_line', { defaultValue: 'Scope line' })}
            </th>
            {submissions.map((sub) => (
              <th key={sub.id} className="px-3 py-2 text-right whitespace-nowrap">
                {bidderName(sub.bidder_id)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lineItems.map((li) => {
            const prices = submissions.map((sub) => linePriceMap(sub.id, li.id));
            const nonZero = prices.filter((p) => p > 0);
            const lo = nonZero.length ? Math.min(...nonZero) : 0;
            const hi = nonZero.length ? Math.max(...nonZero) : 0;
            return (
              <tr key={li.id} className="border-t border-border-light">
                <td className="px-3 py-1.5 sticky left-0 z-10 bg-surface-primary">
                  <div className="font-mono text-xs text-content-tertiary">{li.code || '—'}</div>
                  <div className="text-xs truncate max-w-[260px]">{li.description || '—'}</div>
                </td>
                {submissions.map((sub, i) => {
                  const p = prices[i] ?? 0;
                  const cls =
                    p > 0 && p === lo
                      ? 'text-green-700 font-semibold'
                      : p > 0 && p === hi && lo !== hi
                        ? 'text-red-700'
                        : 'text-content-primary';
                  return (
                    <td key={sub.id} className={clsx('px-3 py-1.5 text-right tabular-nums', cls)}>
                      {p > 0 ? (
                        <MoneyDisplay amount={p} currency={sub.currency || currency} />
                      ) : (
                        <span className="text-content-tertiary">—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
          <tr className="border-t-2 border-border bg-surface-secondary font-semibold">
            <td className="px-3 py-2 sticky left-0 bg-surface-secondary">
              {t('bid_management.total', { defaultValue: 'Total' })}
            </td>
            {submissions.map((sub) => {
              const v = Number(sub.total_amount) || 0;
              const cls =
                v > 0 && v === min
                  ? 'text-green-700'
                  : v > 0 && v === max && min !== max
                    ? 'text-red-700'
                    : '';
              return (
                <td key={sub.id} className={clsx('px-3 py-2 text-right tabular-nums', cls)}>
                  <MoneyDisplay amount={v} currency={sub.currency || currency} />
                </td>
              );
            })}
          </tr>
          <tr className="border-t border-border-light">
            <td className="px-3 py-2 sticky left-0 bg-surface-primary text-xs text-content-secondary">
              {t('bid_management.action', { defaultValue: 'Action' })}
            </td>
            {submissions.map((sub) => (
              <td key={sub.id} className="px-3 py-2 text-right">
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Award size={12} />}
                  loading={awardMut.isPending}
                  disabled={!awardable}
                  title={
                    awardable
                      ? t('bid_management.award', { defaultValue: 'Award' })
                      : t('bid_management.award_disabled', {
                          defaultValue:
                            'Package already awarded or cancelled',
                        })
                  }
                  onClick={() => awardMut.mutate(sub)}
                >
                  {t('bid_management.award', { defaultValue: 'Award' })}
                </Button>
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/* ─── Q & A view ─── */

function QAView({ packages }: { packages: BidPackage[] }) {
  const { t } = useTranslation();
  const [activePkg, setActivePkg] = useState<string>('');

  if (packages.length === 0) {
    return (
      <EmptyState
        icon={<HelpCircle size={22} />}
        title={t('bid_management.empty_qa', { defaultValue: 'No Q&A to show' })}
        description={t('bid_management.empty_qa_desc', {
          defaultValue: 'Bidder questions and clarifications will appear here.',
        })}
      />
    );
  }

  const pkg = packages.find((p) => p.id === activePkg) ?? packages[0];
  if (!pkg) return null;

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <label className={clsx(labelCls, 'mb-0 mr-1')}>
          {t('bid_management.package', { defaultValue: 'Package' })}
        </label>
        <select
          value={pkg.id}
          onChange={(e) => setActivePkg(e.target.value)}
          className={clsx(inputCls, 'max-w-[420px]')}
        >
          {packages.map((p) => (
            <option key={p.id} value={p.id}>
              {p.code} — {p.title || '—'}
            </option>
          ))}
        </select>
      </div>
      <QAList packageId={pkg.id} />
    </div>
  );
}

function QAList({ packageId }: { packageId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const qaQ = useQuery({
    queryKey: ['bid-management', 'qa', packageId],
    queryFn: () => listQAForPackage(packageId),
  });

  const [question, setQuestion] = useState('');
  const [askerEmail, setAskerEmail] = useState('');
  const askMut = useMutation({
    mutationFn: () =>
      createQA({
        package_id: packageId,
        question: question.trim(),
        asked_by_email: askerEmail.trim(),
        is_public: true,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bid-management', 'qa', packageId] });
      setQuestion('');
      addToast({
        type: 'success',
        title: t('bid_management.question_posted', { defaultValue: 'Question posted' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  if (qaQ.isLoading) return <SkeletonTable rows={4} columns={2} />;

  const rows = qaQ.data ?? [];

  return (
    <div className="space-y-3">
      <Card padding="sm">
        <p className="text-xs font-semibold text-content-secondary uppercase tracking-wide mb-2">
          {t('bid_management.post_question', { defaultValue: 'Post a question' })}
        </p>
        <div className="space-y-2">
          <input
            value={askerEmail}
            onChange={(e) => setAskerEmail(e.target.value)}
            placeholder={t('bid_management.your_email', { defaultValue: 'Your email' })}
            className={inputCls}
          />
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t('bid_management.question_placeholder', {
              defaultValue: 'Type your question…',
            })}
            rows={2}
            className={clsx(inputCls, 'h-auto py-2')}
          />
          <Button
            variant="primary"
            icon={<Send size={14} />}
            disabled={!question.trim()}
            loading={askMut.isPending}
            onClick={() => askMut.mutate()}
          >
            {t('bid_management.post', { defaultValue: 'Post' })}
          </Button>
        </div>
      </Card>

      {rows.length === 0 ? (
        <EmptyState
          icon={<HelpCircle size={22} />}
          title={t('bid_management.no_questions', { defaultValue: 'No questions yet' })}
          description={t('bid_management.no_questions_desc', {
            defaultValue: 'Be the first to ask — replies are shared with all bidders by default.',
          })}
        />
      ) : (
        <div className="space-y-2">
          {rows.map((qa) => (
            <QAItem key={qa.id} qa={qa} packageId={packageId} />
          ))}
        </div>
      )}
    </div>
  );
}

function QAItem({ qa, packageId }: { qa: BidQA; packageId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [answer, setAnswer] = useState('');
  const answerMut = useMutation({
    mutationFn: () => answerQA(qa.id, { answer: answer.trim(), is_public: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bid-management', 'qa', packageId] });
      setAnswer('');
      addToast({
        type: 'success',
        title: t('bid_management.answer_posted', { defaultValue: 'Answer posted' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  return (
    <Card padding="sm">
      <div className="flex items-start gap-2">
        <Badge variant={qa.is_public ? 'success' : 'neutral'}>
          {qa.is_public
            ? t('bid_management.public', { defaultValue: 'public' })
            : t('bid_management.private', { defaultValue: 'private' })}
        </Badge>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium whitespace-pre-wrap">{qa.question}</p>
          <p className="mt-0.5 text-xs text-content-tertiary">
            {qa.asked_by_email || '—'}
            {qa.asked_at && (
              <>
                {' · '}
                <DateDisplay value={qa.asked_at} />
              </>
            )}
          </p>
          {qa.answer ? (
            <div className="mt-2 rounded bg-surface-secondary p-2">
              <p className="text-xs uppercase tracking-wide text-content-tertiary">
                {t('bid_management.answer', { defaultValue: 'Answer' })}
              </p>
              <p className="text-sm whitespace-pre-wrap">{qa.answer}</p>
            </div>
          ) : (
            <div className="mt-2 flex gap-2">
              <input
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder={t('bid_management.answer_placeholder', {
                  defaultValue: 'Write an answer…',
                })}
                className={inputCls}
              />
              <Button
                variant="secondary"
                size="sm"
                disabled={!answer.trim()}
                loading={answerMut.isPending}
                onClick={() => answerMut.mutate()}
              >
                {t('bid_management.reply', { defaultValue: 'Reply' })}
              </Button>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

/* ─── Package Drawer ─── */

function PackageDrawer({
  packageId,
  onClose,
  currency,
}: {
  packageId: string;
  onClose: () => void;
  currency: string;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const pkgQ = useQuery({
    queryKey: ['bid-management', 'package', packageId],
    queryFn: () => getPackage(packageId),
  });
  const linesQ = useQuery({
    queryKey: ['bid-management', 'lines', packageId],
    queryFn: () => listLineItemsForPackage(packageId),
  });
  const invQ = useQuery({
    queryKey: ['bid-management', 'invitations', packageId],
    queryFn: () => listInvitationsForPackage(packageId),
  });
  const subsQ = useQuery({
    queryKey: ['bid-management', 'submissions', packageId],
    queryFn: () => listSubmissionsForPackage(packageId),
  });

  const publishMut = useMutation({
    mutationFn: () => publishPackage(packageId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bid-management'] });
      addToast({
        type: 'success',
        title: t('bid_management.published', { defaultValue: 'Package published' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const closeMut = useMutation({
    mutationFn: () => closePackage(packageId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bid-management'] });
      addToast({
        type: 'success',
        title: t('bid_management.closed_pkg', { defaultValue: 'Package closed' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const compareMut = useMutation({
    mutationFn: async () => {
      const c = await createComparison({ package_id: packageId });
      await computeLeveling(c.id);
      return levelingTable(c.id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bid-management'] });
      addToast({
        type: 'success',
        title: t('bid_management.leveling_done', { defaultValue: 'Leveling computed' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const pkg = pkgQ.data;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="bid-package-drawer-title"
        className="relative h-full w-full max-w-2xl overflow-y-auto bg-surface-elevated shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border-light bg-surface-elevated px-5 py-3">
          <h2 id="bid-package-drawer-title" className="text-base font-semibold">
            {pkg ? pkg.code : '…'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 hover:bg-surface-secondary"
            aria-label={t('common.close', { defaultValue: 'Close' })}
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 p-5">
          {pkgQ.isError ? (
            <EmptyState
              icon={<XCircle size={22} />}
              title={t('bid_management.package_load_failed', {
                defaultValue: 'Could not load this package',
              })}
              description={getErrorMessage(pkgQ.error)}
              action={{
                label: t('common.retry', { defaultValue: 'Retry' }),
                onClick: () => pkgQ.refetch(),
              }}
            />
          ) : pkgQ.isLoading || !pkg ? (
            <SkeletonTable rows={4} columns={2} />
          ) : (
            <>
              <div>
                <p className="text-lg font-semibold">{pkg.title || '—'}</p>
                <p className="mt-1 text-sm text-content-secondary whitespace-pre-wrap">
                  {pkg.scope_description || '—'}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Field
                  label={t('bid_management.status')}
                  value={
                    <Badge variant={PACKAGE_STATUS_VARIANT[pkg.status]} dot>
                      {pkg.status}
                    </Badge>
                  }
                />
                <Field
                  label={t('bid_management.confidentiality', { defaultValue: 'Confidentiality' })}
                  value={pkg.confidentiality_level}
                />
                <Field
                  label={t('bid_management.deadline')}
                  value={pkg.submission_deadline ? <DateDisplay value={pkg.submission_deadline} /> : '—'}
                />
                <Field
                  label={t('bid_management.decision_due', { defaultValue: 'Decision due' })}
                  value={pkg.decision_due_by ? <DateDisplay value={pkg.decision_due_by} /> : '—'}
                />
                <Field
                  label={t('bid_management.budget')}
                  value={
                    <MoneyDisplay
                      amount={Number(pkg.total_budget_estimate) || 0}
                      currency={pkg.currency || currency}
                    />
                  }
                />
                <Field
                  label={t('bid_management.published_at', { defaultValue: 'Published' })}
                  value={pkg.published_at ? <DateDisplay value={pkg.published_at} /> : '—'}
                />
              </div>

              <div className="flex flex-wrap gap-2 pt-2 border-t border-border-light">
                {pkg.status === 'draft' && (
                  <Button
                    variant="primary"
                    icon={<Send size={14} />}
                    onClick={() => publishMut.mutate()}
                    loading={publishMut.isPending}
                  >
                    {t('bid_management.publish', { defaultValue: 'Publish' })}
                  </Button>
                )}
                {(pkg.status === 'open' || pkg.status === 'published') && (
                  <Button
                    variant="secondary"
                    icon={<XCircle size={14} />}
                    onClick={() => closeMut.mutate()}
                    loading={closeMut.isPending}
                  >
                    {t('bid_management.close_pkg', { defaultValue: 'Close Bidding' })}
                  </Button>
                )}
                <Button
                  variant="secondary"
                  icon={<Calculator size={14} />}
                  onClick={() => compareMut.mutate()}
                  loading={compareMut.isPending}
                >
                  {t('bid_management.run_leveling', { defaultValue: 'Compute Leveling' })}
                </Button>
                {pkg.status === 'awarded' && (
                  <Link to="/contracts">
                    <Button variant="primary" icon={<ArrowRight size={14} />}>
                      {t('bid_management.create_contract', {
                        defaultValue: 'Formalise as Contract',
                      })}
                    </Button>
                  </Link>
                )}
              </div>

              <Card padding="sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-2">
                  {t('bid_management.scope_lines', { defaultValue: 'Scope lines' })}
                </p>
                {linesQ.isLoading ? (
                  <SkeletonTable rows={3} columns={3} />
                ) : (linesQ.data ?? []).length === 0 ? (
                  <p className="text-xs text-content-tertiary">
                    {t('bid_management.no_lines', { defaultValue: 'No scope lines yet.' })}
                  </p>
                ) : (
                  <table className="w-full text-xs">
                    <thead className="text-content-tertiary uppercase">
                      <tr>
                        <th className="text-left py-1">
                          {t('bid_management.code', { defaultValue: 'Code' })}
                        </th>
                        <th className="text-left py-1">
                          {t('bid_management.description', { defaultValue: 'Description' })}
                        </th>
                        <th className="text-right py-1">
                          {t('bid_management.qty', { defaultValue: 'Qty' })}
                        </th>
                        <th className="text-left py-1">
                          {t('bid_management.unit', { defaultValue: 'Unit' })}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {(linesQ.data ?? []).map((li) => (
                        <tr key={li.id} className="border-t border-border-light">
                          <td className="py-1 font-mono">{li.code || '—'}</td>
                          <td className="py-1 truncate max-w-[300px]">{li.description || '—'}</td>
                          <td className="py-1 text-right tabular-nums">{Number(li.quantity)}</td>
                          <td className="py-1 text-content-secondary">{li.unit || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>

              <Card padding="sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-2">
                  {t('bid_management.invitations_list', { defaultValue: 'Invitations' })}
                </p>
                {invQ.isLoading ? (
                  <SkeletonTable rows={3} columns={3} />
                ) : (invQ.data ?? []).length === 0 ? (
                  <p className="text-xs text-content-tertiary">
                    {t('bid_management.no_invitations', {
                      defaultValue: 'No invitations sent for this package yet.',
                    })}
                  </p>
                ) : (
                  <ul className="space-y-1 text-xs">
                    {(invQ.data ?? []).map((inv) => (
                      <li
                        key={inv.id}
                        className="flex items-center justify-between border-b border-border-light pb-1 last:border-b-0"
                      >
                        <span className="truncate">
                          <span className="font-medium">{inv.invitee_company_name || '—'}</span>
                          <span className="ml-2 text-content-tertiary">{inv.invitee_email}</span>
                        </span>
                        <Badge variant={INVITATION_STATUS_VARIANT[inv.status]} dot>
                          {inv.status}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              <InlineInviteForm packageId={packageId} />

              {subsQ.data && subsQ.data.length > 0 && (
                <Card padding="sm">
                  <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-2">
                    {t('bid_management.submissions_summary', {
                      defaultValue: 'Submissions summary',
                    })}
                  </p>
                  <ul className="space-y-1 text-xs">
                    {subsQ.data.map((sub) => (
                      <li key={sub.id} className="flex items-center justify-between">
                        <span className="font-mono text-content-tertiary">
                          {sub.id.slice(0, 8)}
                        </span>
                        <span>
                          <MoneyDisplay
                            amount={Number(sub.total_amount) || 0}
                            currency={sub.currency || currency}
                          />
                        </span>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function InlineInviteForm({ packageId }: { packageId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const inviteMut = useMutation({
    mutationFn: async () => {
      const bidder = await createBidder({
        package_id: packageId,
        company_name: company.trim() || email.trim(),
        contact_email: email.trim(),
      });
      return createInvitation({
        package_id: packageId,
        bidder_ref_id: bidder.id,
        invitee_email: email.trim(),
        invitee_company_name: company.trim(),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bid-management'] });
      setEmail('');
      setCompany('');
      addToast({
        type: 'success',
        title: t('bid_management.invite_sent', { defaultValue: 'Invitation sent' }),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  return (
    <Card padding="sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-content-secondary mb-2">
        {t('bid_management.invite_bidder', { defaultValue: 'Invite a bidder' })}
      </p>
      <div className="space-y-2">
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder={t('bid_management.company', { defaultValue: 'Company' })}
          className={inputCls}
        />
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t('bid_management.email', { defaultValue: 'Email' })}
          className={inputCls}
        />
        <Button
          variant="primary"
          icon={<Send size={14} />}
          disabled={!email.trim()}
          loading={inviteMut.isPending}
          onClick={() => inviteMut.mutate()}
        >
          {t('bid_management.invite', { defaultValue: 'Invite' })}
        </Button>
      </div>
    </Card>
  );
}

function Field({ label, value }: { label: React.ReactNode; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-content-tertiary">{label}</p>
      <p className="mt-0.5 text-sm text-content-primary">{value}</p>
    </div>
  );
}

/* ─── Create package modal ─── */

function CreatePackageModal({
  projectId,
  currency,
  onClose,
}: {
  projectId: string;
  currency: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [form, setForm] = useState({
    code: '',
    title: '',
    scope_description: '',
    submission_deadline: '',
    currency,
    total_budget_estimate: '0',
  });
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!form.code.trim()) {
      addToast({
        type: 'error',
        title: t('bid_management.code_required', { defaultValue: 'Code is required' }),
      });
      return;
    }
    setBusy(true);
    try {
      await createPackage({
        project_id: projectId,
        code: form.code.trim(),
        title: form.title.trim(),
        scope_description: form.scope_description.trim(),
        submission_deadline: form.submission_deadline || null,
        currency: form.currency.trim() || currency,
        total_budget_estimate: Number(form.total_budget_estimate) || 0,
      });
      qc.invalidateQueries({ queryKey: ['bid-management'] });
      addToast({
        type: 'success',
        title: t('bid_management.package_created', { defaultValue: 'Package created' }),
      });
      onClose();
    } catch (err) {
      addToast({ type: 'error', title: getErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <WideModal
      open
      onClose={onClose}
      title={t('bid_management.new_package', { defaultValue: 'New bid package' })}
      subtitle={t('bid_management.new_package_subtitle', {
        defaultValue:
          'A bid package groups the scope you are putting out to tender. After you create it, add bidders and send invitations from the package detail view.',
      })}
      size="lg"
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
      <WideModalSection columns={2}>
        <WideModalField
          label={t('bid_management.code', { defaultValue: 'Code' })}
          required
          hint={t('bid_management.code_hint', {
            defaultValue: 'Short identifier used in emails — e.g. BP-001.',
          })}
        >
          <input
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
            className={inputCls}
            placeholder="BP-001"
            autoFocus
          />
        </WideModalField>
        <WideModalField
          label={t('bid_management.title_col', { defaultValue: 'Title' })}
        >
          <input
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className={inputCls}
            placeholder={t('bid_management.title_placeholder', {
              defaultValue: 'Façade cladding works',
            })}
          />
        </WideModalField>
        <WideModalField
          label={t('bid_management.scope', { defaultValue: 'Scope description' })}
          hint={t('bid_management.scope_hint', {
            defaultValue: 'High-level summary sent to all invited bidders.',
          })}
          span={2}
        >
          <textarea
            value={form.scope_description}
            onChange={(e) => setForm({ ...form, scope_description: e.target.value })}
            rows={4}
            className={clsx(inputCls, 'h-auto py-2 resize-y')}
          />
        </WideModalField>
        <WideModalField
          label={t('bid_management.deadline', { defaultValue: 'Submission deadline' })}
        >
          <input
            type="date"
            value={form.submission_deadline}
            onChange={(e) => setForm({ ...form, submission_deadline: e.target.value })}
            className={inputCls}
          />
        </WideModalField>
        <WideModalField
          label={t('common.currency', { defaultValue: 'Currency' })}
          hint={t('bid_management.currency_hint', { defaultValue: 'ISO-4217 3-letter code.' })}
        >
          <input
            value={form.currency}
            onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
            className={inputCls}
            maxLength={3}
          />
        </WideModalField>
        <WideModalField
          label={t('bid_management.budget', { defaultValue: 'Budget estimate' })}
          hint={t('bid_management.budget_hint', {
            defaultValue: 'Internal anchor — not shared with bidders.',
          })}
          span={2}
        >
          <input
            type="number"
            min="0"
            step="0.01"
            value={form.total_budget_estimate}
            onChange={(e) => setForm({ ...form, total_budget_estimate: e.target.value })}
            className={inputCls}
          />
        </WideModalField>
      </WideModalSection>
    </WideModal>
  );
}
