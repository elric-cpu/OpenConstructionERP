import { useState, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  ShieldAlert,
  ClipboardList,
  HardHat,
  FileCheck,
  Award,
  Wrench,
  Users,
  X,
  Plus,
  Search,
  ShieldCheck,
  Clock,
  CheckCircle2,
} from 'lucide-react';
import {
  Button,
  Card,
  Badge,
  EmptyState,
  Breadcrumb,
  SkeletonTable,
} from '@/shared/ui';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { normalizeListResponse } from '@/shared/lib/apiHelpers';
import { getErrorMessage } from '@/shared/lib/api';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { useToastStore } from '@/stores/useToastStore';
import {
  fetchInvestigations,
  fetchJSAs,
  fetchPermits,
  fetchToolboxTalks,
  fetchPPEIssues,
  fetchAudits,
  fetchCAPAs,
  createInvestigation,
  createJSA,
  createPermit,
  createToolboxTalk,
  createPPEIssue,
  createAudit,
  createCAPA,
  daysUntil,
  type IncidentInvestigation,
  type JobSafetyAnalysis,
  type PermitToWork,
  type ToolboxTalk,
  type PPEIssue,
  type SafetyAudit,
  type CorrectiveAction,
  type IncidentSeverity,
  type PermitStatus,
  type CAPAStatus,
  type FiveWhys,
} from './api';

type HSETab = 'incidents' | 'jsa' | 'permits' | 'toolbox' | 'ppe' | 'audits' | 'capa';

type BadgeVariant = 'neutral' | 'blue' | 'success' | 'warning' | 'error';

const SEVERITY_COLORS: Record<IncidentSeverity, BadgeVariant> = {
  minor: 'neutral',
  moderate: 'warning',
  major: 'error',
  severe: 'error',
  critical: 'error',
};

const PERMIT_STATUS_COLORS: Record<PermitStatus, BadgeVariant> = {
  draft: 'neutral',
  pending: 'warning',
  active: 'success',
  expired: 'error',
  closed: 'neutral',
  cancelled: 'neutral',
};

const CAPA_STATUS_COLORS: Record<CAPAStatus, BadgeVariant> = {
  open: 'warning',
  in_progress: 'blue',
  completed: 'success',
  verified: 'success',
  closed: 'neutral',
  overdue: 'error',
};

const inputCls =
  'h-10 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';
const textareaCls =
  'w-full rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue resize-none';

/* ── Main Page ─────────────────────────────────────────────────────────── */

export function HSEAdvancedPage() {
  const { t } = useTranslation();
  const { projectId: routeProjectId } = useParams<{ projectId?: string }>();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const projectName = useProjectContextStore((s) => s.activeProjectName);
  const projectId = routeProjectId || activeProjectId || '';

  const [tab, setTab] = useState<HSETab>('incidents');

  const tabs: { key: HSETab; label: string; icon: React.ReactNode }[] = [
    {
      key: 'incidents',
      label: t('hse_advanced.tab_incidents', { defaultValue: 'Incidents' }),
      icon: <ShieldAlert size={15} />,
    },
    {
      key: 'jsa',
      label: t('hse_advanced.tab_jsa', { defaultValue: 'JSAs' }),
      icon: <ClipboardList size={15} />,
    },
    {
      key: 'permits',
      label: t('hse_advanced.tab_permits', { defaultValue: 'Permits' }),
      icon: <FileCheck size={15} />,
    },
    {
      key: 'toolbox',
      label: t('hse_advanced.tab_toolbox', { defaultValue: 'Toolbox' }),
      icon: <Users size={15} />,
    },
    {
      key: 'ppe',
      label: t('hse_advanced.tab_ppe', { defaultValue: 'PPE' }),
      icon: <HardHat size={15} />,
    },
    {
      key: 'audits',
      label: t('hse_advanced.tab_audits', { defaultValue: 'Audits' }),
      icon: <ShieldCheck size={15} />,
    },
    {
      key: 'capa',
      label: t('hse_advanced.tab_capa', { defaultValue: 'CAPA' }),
      icon: <Wrench size={15} />,
    },
  ];

  return (
    <div className="w-full animate-fade-in">
      <Breadcrumb
        items={[
          { label: t('nav.dashboard', { defaultValue: 'Dashboard' }), to: '/' },
          ...(projectName ? [{ label: projectName, to: `/projects/${projectId}` }] : []),
          { label: t('hse_advanced.title', { defaultValue: 'HSE Advanced' }) },
        ]}
        className="mb-4"
      />

      <div className="mb-6">
        <h1 className="text-2xl font-bold text-content-primary">
          {t('hse_advanced.title', { defaultValue: 'HSE Advanced' })}
        </h1>
        <p className="mt-1 text-sm text-content-secondary">
          {t('hse_advanced.subtitle', {
            defaultValue:
              'Investigate incidents, run JSAs, manage permits, deliver toolbox talks, issue PPE, audit the site and close CAPAs.',
          })}
        </p>
      </div>

      {!projectId && (
        <EmptyState
          icon={<Award size={28} strokeWidth={1.5} />}
          title={t('hse_advanced.no_project', { defaultValue: 'No project selected' })}
          description={t('hse_advanced.no_project_desc', {
            defaultValue:
              'Pick a project from the header to manage advanced HSE records: investigations, permits, audits and corrective actions.',
          })}
        />
      )}

      {projectId && (
        <>
          <div
            className="flex items-center gap-1 mb-6 border-b border-border-light overflow-x-auto"
            role="tablist"
          >
            {tabs.map((tb) => (
              <button
                key={tb.key}
                role="tab"
                aria-selected={tab === tb.key}
                onClick={() => setTab(tb.key)}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all whitespace-nowrap ${
                  tab === tb.key
                    ? 'border-oe-blue text-oe-blue'
                    : 'border-transparent text-content-tertiary hover:text-content-primary hover:bg-surface-secondary'
                }`}
              >
                {tb.icon}
                {tb.label}
              </button>
            ))}
          </div>

          {tab === 'incidents' && <IncidentsTab projectId={projectId} />}
          {tab === 'jsa' && <JSATab projectId={projectId} />}
          {tab === 'permits' && <PermitsTab projectId={projectId} />}
          {tab === 'toolbox' && <ToolboxTab projectId={projectId} />}
          {tab === 'ppe' && <PPETab projectId={projectId} />}
          {tab === 'audits' && <AuditsTab projectId={projectId} />}
          {tab === 'capa' && <CAPATab projectId={projectId} />}
        </>
      )}
    </div>
  );
}

/* ── Search Bar ──────────────────────────────────────────────────────── */

function SearchBar({
  value,
  onChange,
  placeholder,
  onCreate,
  createLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  onCreate: () => void;
  createLabel: string;
}) {
  return (
    <div className="p-4 border-b border-border-light flex items-center gap-3 flex-wrap">
      <div className="relative max-w-sm flex-1">
        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-content-tertiary">
          <Search size={16} />
        </div>
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
          className="h-10 w-full rounded-lg border border-border bg-surface-primary pl-10 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue"
        />
      </div>
      <Button variant="primary" size="sm" icon={<Plus size={14} />} onClick={onCreate}>
        {createLabel}
      </Button>
    </div>
  );
}

/* ── Filter Chips ────────────────────────────────────────────────────── */

function FilterChips<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string; count?: number }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
            value === opt.value
              ? 'border-oe-blue bg-oe-blue-subtle text-oe-blue'
              : 'border-border bg-surface-primary text-content-secondary hover:bg-surface-secondary'
          }`}
        >
          <span>{opt.label}</span>
          {opt.count !== undefined && (
            <span className="text-2xs text-content-tertiary">{opt.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

/* ── Modal Shell ─────────────────────────────────────────────────────── */

function ModalShell({
  title,
  onClose,
  children,
  footer,
  size = 'max-w-2xl',
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer: React.ReactNode;
  size?: string;
}) {
  const { t } = useTranslation();

  // Escape-to-close — standard accessible-dialog behaviour.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-lg animate-fade-in"
      onClick={onClose}
    >
      <div
        className={`w-full ${size} bg-surface-elevated rounded-xl shadow-xl border border-border animate-card-in mx-4 max-h-[90vh] overflow-y-auto`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-light">
          <h2 className="text-lg font-semibold text-content-primary">{title}</h2>
          <button
            onClick={onClose}
            aria-label={t('common.close', { defaultValue: 'Close' })}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-content-tertiary hover:bg-surface-secondary hover:text-content-primary transition-colors"
          >
            <X size={18} />
          </button>
        </div>
        <div className="px-6 py-4 space-y-4">{children}</div>
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border-light">
          {footer}
        </div>
      </div>
    </div>
  );
}

/* ── Incidents Tab ───────────────────────────────────────────────────── */

function IncidentsTab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState<IncidentInvestigation | null>(null);
  const [form, setForm] = useState({
    title: '',
    incident_date: new Date().toISOString().slice(0, 10),
    severity: 'minor' as IncidentSeverity,
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ['hse-investigations', projectId],
    queryFn: () => fetchInvestigations(projectId),
    select: (d) => normalizeListResponse<IncidentInvestigation>(d),
  });

  const createMut = useMutation({
    mutationFn: () => createInvestigation({ project_id: projectId, ...form }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hse-investigations', projectId] });
      setShowCreate(false);
      setForm({
        title: '',
        incident_date: new Date().toISOString().slice(0, 10),
        severity: 'minor',
      });
      addToast({
        type: 'success',
        title: t('hse_advanced.investigation_created', {
          defaultValue: 'Investigation opened',
        }),
      });
    },
    onError: (e) =>
      addToast({
        type: 'error',
        title: t('hse_advanced.investigation_failed', {
          defaultValue: 'Failed to open investigation',
        }),
        message: getErrorMessage(e),
      }),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!search) return data;
    const q = search.toLowerCase();
    return data.filter(
      (it) =>
        it.title.toLowerCase().includes(q) ||
        it.investigation_number.toLowerCase().includes(q),
    );
  }, [data, search]);

  if (isLoading) return <SkeletonTable rows={5} columns={6} />;

  if (isError) {
    return (
      <Card className="py-12">
        <EmptyState
          icon={<AlertTriangle size={28} strokeWidth={1.5} />}
          title={t('common.error', { defaultValue: 'Error' })}
          description={t('hse_advanced.load_error', {
            defaultValue: 'Failed to load HSE records. Please try again.',
          })}
        />
      </Card>
    );
  }

  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon={<ShieldAlert size={28} strokeWidth={1.5} />}
        title={t('hse_advanced.no_investigations', {
          defaultValue: 'No investigations yet',
        })}
        description={t('hse_advanced.no_investigations_desc', {
          defaultValue:
            'Open a formal investigation when an incident requires 5-Whys analysis, root-cause review, and corrective actions.',
        })}
        action={{
          label: t('hse_advanced.open_investigation', { defaultValue: 'Open Investigation' }),
          onClick: () => setShowCreate(true),
        }}
      />
    );
  }

  return (
    <>
      <Card padding="none">
        <SearchBar
          value={search}
          onChange={setSearch}
          placeholder={t('hse_advanced.search_investigations', {
            defaultValue: 'Search investigations...',
          })}
          onCreate={() => setShowCreate(true)}
          createLabel={t('hse_advanced.open_investigation', {
            defaultValue: 'Open Investigation',
          })}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-light bg-surface-secondary/50">
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.number', { defaultValue: '#' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.title', { defaultValue: 'Title' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.incident_date', { defaultValue: 'Incident date' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('hse_advanced.severity', { defaultValue: 'Severity' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('common.status', { defaultValue: 'Status' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('hse_advanced.linked_capa', { defaultValue: 'CAPA' })}
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-content-tertiary">
                    {t('hse_advanced.no_matches', { defaultValue: 'No matches' })}
                  </td>
                </tr>
              ) : (
                filtered.map((it) => (
                  <tr
                    key={it.id}
                    className="border-b border-border-light hover:bg-surface-secondary/30 cursor-pointer transition-colors"
                    onClick={() => setDetail(it)}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-content-primary">
                      {it.investigation_number}
                    </td>
                    <td className="px-4 py-3 text-content-primary">{it.title}</td>
                    <td className="px-4 py-3 text-content-secondary">
                      <DateDisplay value={it.incident_date} />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Badge variant={SEVERITY_COLORS[it.severity] ?? 'neutral'} size="sm">
                        {t(`hse_advanced.severity_${it.severity}`, { defaultValue: it.severity })}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Badge
                        variant={it.status === 'completed' ? 'success' : 'blue'}
                        size="sm"
                      >
                        {t(`hse_advanced.invest_status_${it.status}`, {
                          defaultValue: it.status.replace(/_/g, ' '),
                        })}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-center text-xs text-content-tertiary tabular-nums">
                      {it.linked_capa_ids?.length ?? 0}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {showCreate && (
        <ModalShell
          title={t('hse_advanced.open_investigation', { defaultValue: 'Open Investigation' })}
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setShowCreate(false)}>
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </Button>
              <Button
                variant="primary"
                disabled={!form.title.trim() || createMut.isPending}
                onClick={() => createMut.mutate()}
              >
                {t('common.create', { defaultValue: 'Create' })}
              </Button>
            </>
          }
        >
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('common.title', { defaultValue: 'Title' })}{' '}
              <span className="text-semantic-error">*</span>
            </label>
            <input
              className={inputCls}
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('hse_advanced.incident_date', { defaultValue: 'Incident date' })}
            </label>
            <input
              type="date"
              className={inputCls}
              value={form.incident_date}
              onChange={(e) => setForm((f) => ({ ...f, incident_date: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('hse_advanced.severity', { defaultValue: 'Severity' })}
            </label>
            <select
              className={inputCls}
              value={form.severity}
              onChange={(e) =>
                setForm((f) => ({ ...f, severity: e.target.value as IncidentSeverity }))
              }
            >
              <option value="minor">
                {t('hse_advanced.severity_minor', { defaultValue: 'Minor' })}
              </option>
              <option value="moderate">
                {t('hse_advanced.severity_moderate', { defaultValue: 'Moderate' })}
              </option>
              <option value="major">
                {t('hse_advanced.severity_major', { defaultValue: 'Major' })}
              </option>
              <option value="severe">
                {t('hse_advanced.severity_severe', { defaultValue: 'Severe' })}
              </option>
              <option value="critical">
                {t('hse_advanced.severity_critical', { defaultValue: 'Critical' })}
              </option>
            </select>
          </div>
        </ModalShell>
      )}

      {detail && <IncidentDetailDrawer item={detail} onClose={() => setDetail(null)} />}
    </>
  );
}

/* ── Incident Detail Drawer ──────────────────────────────────────────── */

function IncidentDetailDrawer({
  item,
  onClose,
}: {
  item: IncidentInvestigation;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const five: FiveWhys = item.five_whys ?? {};
  const whys: { key: keyof FiveWhys; label: string }[] = [
    { key: 'why1', label: 'Why 1' },
    { key: 'why2', label: 'Why 2' },
    { key: 'why3', label: 'Why 3' },
    { key: 'why4', label: 'Why 4' },
    { key: 'why5', label: 'Why 5' },
  ];

  return (
    <ModalShell
      title={`${item.investigation_number} — ${item.title}`}
      onClose={onClose}
      size="max-w-3xl"
      footer={
        <Button variant="ghost" onClick={onClose}>
          {t('common.close', { defaultValue: 'Close' })}
        </Button>
      }
    >
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-xs text-content-tertiary uppercase">
            {t('hse_advanced.severity', { defaultValue: 'Severity' })}
          </div>
          <Badge variant={SEVERITY_COLORS[item.severity] ?? 'neutral'} size="sm">
            {t(`hse_advanced.severity_${item.severity}`, { defaultValue: item.severity })}
          </Badge>
        </div>
        <div>
          <div className="text-xs text-content-tertiary uppercase">
            {t('common.status', { defaultValue: 'Status' })}
          </div>
          <Badge variant={item.status === 'completed' ? 'success' : 'blue'} size="sm">
            {item.status.replace(/_/g, ' ')}
          </Badge>
        </div>
      </div>

      <div>
        <div className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-2">
          {t('hse_advanced.section_5_whys', { defaultValue: '5-Whys analysis' })}
        </div>
        <div className="space-y-2">
          {whys.map((w) => (
            <div key={w.key} className="flex items-start gap-2">
              <span className="text-xs font-medium text-content-tertiary w-12 pt-2 shrink-0">
                {w.label}
              </span>
              <textarea
                rows={2}
                className={textareaCls}
                readOnly
                value={five[w.key] ?? ''}
                placeholder={t('hse_advanced.why_placeholder', {
                  defaultValue: 'No answer recorded',
                })}
              />
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-2">
          {t('hse_advanced.section_factors', { defaultValue: 'Contributing factors' })}
        </div>
        {item.contributing_factors && item.contributing_factors.length > 0 ? (
          <ul className="list-disc pl-5 text-sm text-content-secondary space-y-1">
            {item.contributing_factors.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-content-tertiary">
            {t('hse_advanced.no_factors', { defaultValue: 'No contributing factors recorded.' })}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-1">
            {t('hse_advanced.immediate_cause', { defaultValue: 'Immediate cause' })}
          </div>
          <p className="text-sm text-content-secondary">
            {item.immediate_cause || t('common.not_set', { defaultValue: 'Not set' })}
          </p>
        </div>
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-1">
            {t('hse_advanced.root_cause', { defaultValue: 'Root cause' })}
          </div>
          <p className="text-sm text-content-secondary">
            {item.root_cause || t('common.not_set', { defaultValue: 'Not set' })}
          </p>
        </div>
      </div>

      <div>
        <div className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-2">
          {t('hse_advanced.linked_capa_actions', { defaultValue: 'Linked CAPA actions' })}
        </div>
        {item.linked_capa_ids && item.linked_capa_ids.length > 0 ? (
          <ul className="space-y-1 text-sm text-content-secondary">
            {item.linked_capa_ids.map((id) => (
              <li key={id} className="font-mono text-xs">
                {id}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-content-tertiary">
            {t('hse_advanced.no_capa_linked', { defaultValue: 'No CAPA linked yet.' })}
          </p>
        )}
      </div>
    </ModalShell>
  );
}

/* ── JSA Tab ─────────────────────────────────────────────────────────── */

function JSATab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', task_description: '', location: '' });

  const { data, isLoading, isError } = useQuery({
    queryKey: ['hse-jsas', projectId],
    queryFn: () => fetchJSAs(projectId),
    select: (d) => normalizeListResponse<JobSafetyAnalysis>(d),
  });

  const createMut = useMutation({
    mutationFn: () => createJSA({ project_id: projectId, ...form }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hse-jsas', projectId] });
      setShowCreate(false);
      setForm({ title: '', task_description: '', location: '' });
      addToast({
        type: 'success',
        title: t('hse_advanced.jsa_created', { defaultValue: 'JSA created' }),
      });
    },
    onError: (e) =>
      addToast({
        type: 'error',
        title: t('hse_advanced.jsa_failed', { defaultValue: 'Failed to create JSA' }),
        message: getErrorMessage(e),
      }),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!search) return data;
    const q = search.toLowerCase();
    return data.filter(
      (it) => it.title.toLowerCase().includes(q) || it.jsa_number.toLowerCase().includes(q),
    );
  }, [data, search]);

  if (isLoading) return <SkeletonTable rows={5} columns={5} />;
  if (isError) {
    return (
      <Card className="py-12">
        <EmptyState
          icon={<AlertTriangle size={28} strokeWidth={1.5} />}
          title={t('common.error', { defaultValue: 'Error' })}
          description={t('hse_advanced.load_error', {
            defaultValue: 'Failed to load HSE records. Please try again.',
          })}
        />
      </Card>
    );
  }
  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon={<ClipboardList size={28} strokeWidth={1.5} />}
        title={t('hse_advanced.no_jsas', { defaultValue: 'No JSAs yet' })}
        description={t('hse_advanced.no_jsas_desc', {
          defaultValue:
            'A Job Safety Analysis breaks a task into steps, identifies hazards per step, and lists controls. Create one before high-risk work begins.',
        })}
        action={{
          label: t('hse_advanced.new_jsa', { defaultValue: 'New JSA' }),
          onClick: () => setShowCreate(true),
        }}
      />
    );
  }

  return (
    <>
      <Card padding="none">
        <SearchBar
          value={search}
          onChange={setSearch}
          placeholder={t('hse_advanced.search_jsas', { defaultValue: 'Search JSAs...' })}
          onCreate={() => setShowCreate(true)}
          createLabel={t('hse_advanced.new_jsa', { defaultValue: 'New JSA' })}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-light bg-surface-secondary/50">
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.number', { defaultValue: '#' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.title', { defaultValue: 'Title' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.location', { defaultValue: 'Location' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('hse_advanced.steps', { defaultValue: 'Steps' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.created', { defaultValue: 'Created' })}
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-content-tertiary">
                    {t('hse_advanced.no_matches', { defaultValue: 'No matches' })}
                  </td>
                </tr>
              ) : (
                filtered.map((it) => (
                  <tr key={it.id} className="border-b border-border-light hover:bg-surface-secondary/30">
                    <td className="px-4 py-3 font-mono text-xs">{it.jsa_number}</td>
                    <td className="px-4 py-3 text-content-primary">{it.title}</td>
                    <td className="px-4 py-3 text-content-secondary">{it.location ?? '—'}</td>
                    <td className="px-4 py-3 text-center tabular-nums">{it.steps?.length ?? 0}</td>
                    <td className="px-4 py-3 text-content-secondary">
                      <DateDisplay value={it.created_at} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {showCreate && (
        <ModalShell
          title={t('hse_advanced.new_jsa', { defaultValue: 'New JSA' })}
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setShowCreate(false)}>
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </Button>
              <Button
                variant="primary"
                disabled={!form.title.trim() || createMut.isPending}
                onClick={() => createMut.mutate()}
              >
                {t('common.create', { defaultValue: 'Create' })}
              </Button>
            </>
          }
        >
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('common.title', { defaultValue: 'Title' })}{' '}
              <span className="text-semantic-error">*</span>
            </label>
            <input
              className={inputCls}
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('hse_advanced.task_description', { defaultValue: 'Task description' })}
            </label>
            <textarea
              rows={3}
              className={textareaCls}
              value={form.task_description}
              onChange={(e) => setForm((f) => ({ ...f, task_description: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('hse_advanced.location', { defaultValue: 'Location' })}
            </label>
            <input
              className={inputCls}
              value={form.location}
              onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))}
            />
          </div>
        </ModalShell>
      )}
    </>
  );
}

/* ── Permits Tab ─────────────────────────────────────────────────────── */

function PermitsTab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState<PermitToWork | null>(null);
  const [filter, setFilter] = useState<'all' | 'active' | 'expired'>('active');
  const [form, setForm] = useState({
    title: '',
    permit_type: 'hot_work',
    scope: '',
    expires_at: '',
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ['hse-permits', projectId],
    queryFn: () => fetchPermits(projectId),
    select: (d) => normalizeListResponse<PermitToWork>(d),
  });

  const createMut = useMutation({
    mutationFn: () =>
      createPermit({
        project_id: projectId,
        title: form.title,
        permit_type: form.permit_type,
        scope: form.scope,
        expires_at: form.expires_at || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hse-permits', projectId] });
      setShowCreate(false);
      setForm({ title: '', permit_type: 'hot_work', scope: '', expires_at: '' });
      addToast({
        type: 'success',
        title: t('hse_advanced.permit_created', { defaultValue: 'Permit issued' }),
      });
    },
    onError: (e) =>
      addToast({
        type: 'error',
        title: t('hse_advanced.permit_failed', { defaultValue: 'Failed to create permit' }),
        message: getErrorMessage(e),
      }),
  });

  const counts = useMemo(() => {
    const c = { all: data?.length ?? 0, active: 0, expired: 0 };
    if (!data) return c;
    for (const p of data) {
      if (p.status === 'active') c.active++;
      else if (p.status === 'expired') c.expired++;
    }
    return c;
  }, [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    let rows = data;
    if (filter === 'active') rows = rows.filter((p) => p.status === 'active');
    else if (filter === 'expired') rows = rows.filter((p) => p.status === 'expired');
    if (!search) return rows;
    const q = search.toLowerCase();
    return rows.filter(
      (p) => p.title.toLowerCase().includes(q) || p.permit_number.toLowerCase().includes(q),
    );
  }, [data, search, filter]);

  if (isLoading) return <SkeletonTable rows={5} columns={6} />;
  if (isError) {
    return (
      <Card className="py-12">
        <EmptyState
          icon={<AlertTriangle size={28} strokeWidth={1.5} />}
          title={t('common.error', { defaultValue: 'Error' })}
          description={t('hse_advanced.load_error', {
            defaultValue: 'Failed to load HSE records. Please try again.',
          })}
        />
      </Card>
    );
  }
  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon={<FileCheck size={28} strokeWidth={1.5} />}
        title={t('hse_advanced.no_permits', { defaultValue: 'No permits yet' })}
        description={t('hse_advanced.no_permits_desc', {
          defaultValue:
            'Issue a Permit to Work to authorise hot work, confined-space entry, work-at-height and other high-risk tasks. Each permit tracks scope, hazards, controls and signatures.',
        })}
        action={{
          label: t('hse_advanced.new_permit', { defaultValue: 'Issue Permit' }),
          onClick: () => setShowCreate(true),
        }}
      />
    );
  }

  return (
    <>
      <div className="mb-4">
        <FilterChips<'all' | 'active' | 'expired'>
          value={filter}
          onChange={setFilter}
          options={[
            {
              value: 'active',
              label: t('hse_advanced.filter_active', { defaultValue: 'Active' }),
              count: counts.active,
            },
            {
              value: 'expired',
              label: t('hse_advanced.filter_expired', { defaultValue: 'Expired' }),
              count: counts.expired,
            },
            {
              value: 'all',
              label: t('hse_advanced.filter_all', { defaultValue: 'All' }),
              count: counts.all,
            },
          ]}
        />
      </div>

      <Card padding="none">
        <SearchBar
          value={search}
          onChange={setSearch}
          placeholder={t('hse_advanced.search_permits', { defaultValue: 'Search permits...' })}
          onCreate={() => setShowCreate(true)}
          createLabel={t('hse_advanced.new_permit', { defaultValue: 'Issue Permit' })}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-light bg-surface-secondary/50">
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.number', { defaultValue: '#' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.title', { defaultValue: 'Title' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.permit_type', { defaultValue: 'Type' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('common.status', { defaultValue: 'Status' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.expires', { defaultValue: 'Expires' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('hse_advanced.countdown', { defaultValue: 'Countdown' })}
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-content-tertiary">
                    {t('hse_advanced.no_matches', { defaultValue: 'No matches' })}
                  </td>
                </tr>
              ) : (
                filtered.map((p) => {
                  const days = daysUntil(p.expires_at);
                  return (
                    <tr
                      key={p.id}
                      className="border-b border-border-light hover:bg-surface-secondary/30 cursor-pointer"
                      onClick={() => setDetail(p)}
                    >
                      <td className="px-4 py-3 font-mono text-xs">{p.permit_number}</td>
                      <td className="px-4 py-3 text-content-primary">{p.title}</td>
                      <td className="px-4 py-3 text-content-secondary text-xs">
                        {p.permit_type.replace(/_/g, ' ')}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Badge variant={PERMIT_STATUS_COLORS[p.status] ?? 'neutral'} size="sm">
                          {t(`hse_advanced.permit_status_${p.status}`, {
                            defaultValue: p.status,
                          })}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-content-secondary">
                        {p.expires_at ? <DateDisplay value={p.expires_at} /> : '—'}
                      </td>
                      <td className="px-4 py-3 text-center tabular-nums">
                        {days === null ? (
                          <span className="text-content-tertiary">—</span>
                        ) : days < 0 ? (
                          <span className="text-semantic-error font-medium">
                            {t('hse_advanced.expired_days_ago', {
                              defaultValue: '{{n}}d ago',
                              n: Math.abs(days),
                            })}
                          </span>
                        ) : days <= 1 ? (
                          <span className="text-semantic-error font-medium">
                            {t('hse_advanced.expires_today', { defaultValue: 'today' })}
                          </span>
                        ) : (
                          <span
                            className={
                              days <= 3
                                ? 'text-amber-600 font-medium'
                                : 'text-content-secondary'
                            }
                          >
                            {t('hse_advanced.in_days', { defaultValue: 'in {{n}}d', n: days })}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {showCreate && (
        <ModalShell
          title={t('hse_advanced.new_permit', { defaultValue: 'Issue Permit' })}
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setShowCreate(false)}>
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </Button>
              <Button
                variant="primary"
                disabled={!form.title.trim() || createMut.isPending}
                onClick={() => createMut.mutate()}
              >
                {t('common.issue', { defaultValue: 'Issue' })}
              </Button>
            </>
          }
        >
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('common.title', { defaultValue: 'Title' })}{' '}
              <span className="text-semantic-error">*</span>
            </label>
            <input
              className={inputCls}
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('hse_advanced.permit_type', { defaultValue: 'Type' })}
            </label>
            <select
              className={inputCls}
              value={form.permit_type}
              onChange={(e) => setForm((f) => ({ ...f, permit_type: e.target.value }))}
            >
              <option value="hot_work">
                {t('hse_advanced.permit_type_hot_work', { defaultValue: 'Hot work' })}
              </option>
              <option value="confined_space">
                {t('hse_advanced.permit_type_confined_space', {
                  defaultValue: 'Confined space',
                })}
              </option>
              <option value="work_at_height">
                {t('hse_advanced.permit_type_work_at_height', {
                  defaultValue: 'Work at height',
                })}
              </option>
              <option value="excavation">
                {t('hse_advanced.permit_type_excavation', { defaultValue: 'Excavation' })}
              </option>
              <option value="electrical">
                {t('hse_advanced.permit_type_electrical', { defaultValue: 'Electrical' })}
              </option>
              <option value="lifting">
                {t('hse_advanced.permit_type_lifting', { defaultValue: 'Lifting / crane' })}
              </option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('hse_advanced.scope', { defaultValue: 'Scope of work' })}
            </label>
            <textarea
              rows={3}
              className={textareaCls}
              value={form.scope}
              onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('hse_advanced.expires_at', { defaultValue: 'Expires at' })}
            </label>
            <input
              type="datetime-local"
              className={inputCls}
              value={form.expires_at}
              onChange={(e) => setForm((f) => ({ ...f, expires_at: e.target.value }))}
            />
          </div>
        </ModalShell>
      )}

      {detail && <PermitDetailDrawer item={detail} onClose={() => setDetail(null)} />}
    </>
  );
}

/* ── Permit Detail Drawer ────────────────────────────────────────────── */

function PermitDetailDrawer({ item, onClose }: { item: PermitToWork; onClose: () => void }) {
  const { t } = useTranslation();
  const days = daysUntil(item.expires_at);

  return (
    <ModalShell
      title={`${item.permit_number} — ${item.title}`}
      onClose={onClose}
      size="max-w-2xl"
      footer={
        <Button variant="ghost" onClick={onClose}>
          {t('common.close', { defaultValue: 'Close' })}
        </Button>
      }
    >
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-xs text-content-tertiary uppercase">
            {t('hse_advanced.permit_type', { defaultValue: 'Type' })}
          </div>
          <div className="text-content-primary">{item.permit_type.replace(/_/g, ' ')}</div>
        </div>
        <div>
          <div className="text-xs text-content-tertiary uppercase">
            {t('common.status', { defaultValue: 'Status' })}
          </div>
          <Badge variant={PERMIT_STATUS_COLORS[item.status] ?? 'neutral'} size="sm">
            {item.status}
          </Badge>
        </div>
      </div>

      <div>
        <div className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-1">
          {t('hse_advanced.scope', { defaultValue: 'Scope of work' })}
        </div>
        <p className="text-sm text-content-secondary whitespace-pre-wrap">
          {item.scope || t('common.not_set', { defaultValue: 'Not set' })}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-1">
            {t('hse_advanced.hazards', { defaultValue: 'Hazards' })}
          </div>
          {item.hazards && item.hazards.length > 0 ? (
            <ul className="list-disc pl-5 text-sm text-content-secondary">
              {item.hazards.map((h, i) => (
                <li key={i}>{h}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-content-tertiary">
              {t('hse_advanced.no_hazards', { defaultValue: 'None listed' })}
            </p>
          )}
        </div>
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-1">
            {t('hse_advanced.controls', { defaultValue: 'Controls' })}
          </div>
          {item.controls && item.controls.length > 0 ? (
            <ul className="list-disc pl-5 text-sm text-content-secondary">
              {item.controls.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-content-tertiary">
              {t('hse_advanced.no_controls', { defaultValue: 'None listed' })}
            </p>
          )}
        </div>
      </div>

      <div>
        <div className="text-xs font-semibold uppercase tracking-wider text-content-tertiary mb-1">
          {t('hse_advanced.signatures', { defaultValue: 'Signatures' })}
        </div>
        {item.signatures && item.signatures.length > 0 ? (
          <ul className="text-sm text-content-secondary space-y-1">
            {item.signatures.map((s, i) => (
              <li key={i} className="flex items-center gap-2">
                <CheckCircle2 size={14} className="text-semantic-success" />
                <span className="font-medium">{s.role}:</span>
                <span>{s.name}</span>
                {s.signed_at && (
                  <span className="text-xs text-content-tertiary">
                    <DateDisplay value={s.signed_at} />
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-content-tertiary">
            {t('hse_advanced.no_signatures', { defaultValue: 'No signatures yet' })}
          </p>
        )}
      </div>

      <div className="rounded-lg bg-surface-secondary p-3">
        <div className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-1.5 text-content-secondary">
            <Clock size={14} />
            {t('hse_advanced.countdown', { defaultValue: 'Expiry countdown' })}
          </span>
          <span
            className={
              days !== null && days < 0
                ? 'text-semantic-error font-semibold'
                : days !== null && days <= 3
                  ? 'text-amber-600 font-semibold'
                  : 'text-content-primary font-medium'
            }
          >
            {days === null
              ? t('common.not_set', { defaultValue: 'Not set' })
              : days < 0
                ? t('hse_advanced.expired_days_ago', {
                    defaultValue: '{{n}}d ago',
                    n: Math.abs(days),
                  })
                : t('hse_advanced.in_days', { defaultValue: 'in {{n}}d', n: days })}
          </span>
        </div>
      </div>
    </ModalShell>
  );
}

/* ── Toolbox Tab ─────────────────────────────────────────────────────── */

function ToolboxTab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    title: '',
    talk_date: new Date().toISOString().slice(0, 10),
    presenter: '',
    summary: '',
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ['hse-toolbox', projectId],
    queryFn: () => fetchToolboxTalks(projectId),
    select: (d) => normalizeListResponse<ToolboxTalk>(d),
  });

  const createMut = useMutation({
    mutationFn: () => createToolboxTalk({ project_id: projectId, ...form }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hse-toolbox', projectId] });
      setShowCreate(false);
      setForm({
        title: '',
        talk_date: new Date().toISOString().slice(0, 10),
        presenter: '',
        summary: '',
      });
      addToast({
        type: 'success',
        title: t('hse_advanced.toolbox_created', { defaultValue: 'Toolbox talk logged' }),
      });
    },
    onError: (e) =>
      addToast({
        type: 'error',
        title: t('hse_advanced.toolbox_failed', { defaultValue: 'Failed to log talk' }),
        message: getErrorMessage(e),
      }),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!search) return data;
    const q = search.toLowerCase();
    return data.filter((it) => it.title.toLowerCase().includes(q));
  }, [data, search]);

  if (isLoading) return <SkeletonTable rows={5} columns={5} />;
  if (isError) {
    return (
      <Card className="py-12">
        <EmptyState
          icon={<AlertTriangle size={28} strokeWidth={1.5} />}
          title={t('common.error', { defaultValue: 'Error' })}
          description={t('hse_advanced.load_error', {
            defaultValue: 'Failed to load HSE records. Please try again.',
          })}
        />
      </Card>
    );
  }
  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon={<Users size={28} strokeWidth={1.5} />}
        title={t('hse_advanced.no_toolbox', { defaultValue: 'No toolbox talks yet' })}
        description={t('hse_advanced.no_toolbox_desc', {
          defaultValue:
            'Log daily toolbox talks with topic, presenter and attendance. Each talk is a record that workers were briefed before high-risk activities.',
        })}
        action={{
          label: t('hse_advanced.new_toolbox', { defaultValue: 'Log Talk' }),
          onClick: () => setShowCreate(true),
        }}
      />
    );
  }

  return (
    <>
      <Card padding="none">
        <SearchBar
          value={search}
          onChange={setSearch}
          placeholder={t('hse_advanced.search_toolbox', { defaultValue: 'Search talks...' })}
          onCreate={() => setShowCreate(true)}
          createLabel={t('hse_advanced.new_toolbox', { defaultValue: 'Log Talk' })}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-light bg-surface-secondary/50">
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.number', { defaultValue: '#' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.title', { defaultValue: 'Title' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.presenter', { defaultValue: 'Presenter' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.date', { defaultValue: 'Date' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('hse_advanced.attendance', { defaultValue: 'Attendance' })}
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-content-tertiary">
                    {t('hse_advanced.no_matches', { defaultValue: 'No matches' })}
                  </td>
                </tr>
              ) : (
                filtered.map((it) => (
                  <tr key={it.id} className="border-b border-border-light hover:bg-surface-secondary/30">
                    <td className="px-4 py-3 font-mono text-xs">{it.talk_number}</td>
                    <td className="px-4 py-3 text-content-primary">{it.title}</td>
                    <td className="px-4 py-3 text-content-secondary">{it.presenter ?? '—'}</td>
                    <td className="px-4 py-3 text-content-secondary">
                      <DateDisplay value={it.talk_date} />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Badge variant="blue" size="sm">
                        {it.attendance?.length ?? 0}
                      </Badge>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {showCreate && (
        <ModalShell
          title={t('hse_advanced.new_toolbox', { defaultValue: 'Log Toolbox Talk' })}
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setShowCreate(false)}>
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </Button>
              <Button
                variant="primary"
                disabled={!form.title.trim() || createMut.isPending}
                onClick={() => createMut.mutate()}
              >
                {t('common.save', { defaultValue: 'Save' })}
              </Button>
            </>
          }
        >
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('common.title', { defaultValue: 'Title' })}{' '}
              <span className="text-semantic-error">*</span>
            </label>
            <input
              className={inputCls}
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-content-primary mb-1.5">
                {t('hse_advanced.date', { defaultValue: 'Date' })}
              </label>
              <input
                type="date"
                className={inputCls}
                value={form.talk_date}
                onChange={(e) => setForm((f) => ({ ...f, talk_date: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-content-primary mb-1.5">
                {t('hse_advanced.presenter', { defaultValue: 'Presenter' })}
              </label>
              <input
                className={inputCls}
                value={form.presenter}
                onChange={(e) => setForm((f) => ({ ...f, presenter: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('hse_advanced.summary', { defaultValue: 'Summary' })}
            </label>
            <textarea
              rows={3}
              className={textareaCls}
              value={form.summary}
              onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))}
            />
          </div>
        </ModalShell>
      )}
    </>
  );
}

/* ── PPE Tab ─────────────────────────────────────────────────────────── */

function PPETab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState<PPEIssue | null>(null);
  const [filter, setFilter] = useState<'all' | 'issued' | 'expiring'>('all');
  const [form, setForm] = useState({
    item_type: 'hard_hat',
    item_description: '',
    issued_to_name: '',
    issued_at: new Date().toISOString().slice(0, 10),
    return_by: '',
    quantity: 1,
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ['hse-ppe', projectId],
    queryFn: () => fetchPPEIssues(projectId),
    select: (d) => normalizeListResponse<PPEIssue>(d),
  });

  const createMut = useMutation({
    mutationFn: () =>
      createPPEIssue({
        project_id: projectId,
        item_type: form.item_type,
        item_description: form.item_description || undefined,
        issued_to_name: form.issued_to_name,
        issued_at: form.issued_at,
        return_by: form.return_by || undefined,
        quantity: form.quantity,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hse-ppe', projectId] });
      setShowCreate(false);
      setForm({
        item_type: 'hard_hat',
        item_description: '',
        issued_to_name: '',
        issued_at: new Date().toISOString().slice(0, 10),
        return_by: '',
        quantity: 1,
      });
      addToast({
        type: 'success',
        title: t('hse_advanced.ppe_created', { defaultValue: 'PPE issued' }),
      });
    },
    onError: (e) =>
      addToast({
        type: 'error',
        title: t('hse_advanced.ppe_failed', { defaultValue: 'Failed to issue PPE' }),
        message: getErrorMessage(e),
      }),
  });

  const counts = useMemo(() => {
    const c = { all: data?.length ?? 0, issued: 0, expiring: 0 };
    if (!data) return c;
    for (const it of data) {
      if (!it.returned_at) c.issued++;
      const d = daysUntil(it.expires_at);
      if (d !== null && d >= 0 && d <= 30) c.expiring++;
    }
    return c;
  }, [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    let rows = data;
    if (filter === 'issued') rows = rows.filter((p) => !p.returned_at);
    else if (filter === 'expiring')
      rows = rows.filter((p) => {
        const d = daysUntil(p.expires_at);
        return d !== null && d >= 0 && d <= 30;
      });
    if (!search) return rows;
    const q = search.toLowerCase();
    return rows.filter(
      (p) =>
        p.issued_to_name.toLowerCase().includes(q) ||
        p.item_type.toLowerCase().includes(q) ||
        p.ppe_number.toLowerCase().includes(q),
    );
  }, [data, search, filter]);

  if (isLoading) return <SkeletonTable rows={5} columns={6} />;
  if (isError) {
    return (
      <Card className="py-12">
        <EmptyState
          icon={<AlertTriangle size={28} strokeWidth={1.5} />}
          title={t('common.error', { defaultValue: 'Error' })}
          description={t('hse_advanced.load_error', {
            defaultValue: 'Failed to load HSE records. Please try again.',
          })}
        />
      </Card>
    );
  }
  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon={<HardHat size={28} strokeWidth={1.5} />}
        title={t('hse_advanced.no_ppe', { defaultValue: 'No PPE issued yet' })}
        description={t('hse_advanced.no_ppe_desc', {
          defaultValue:
            'Log PPE issued to workers — hard hats, harnesses, respirators, hearing protection. Tracks expiry, return-by dates and inventory.',
        })}
        action={{
          label: t('hse_advanced.new_ppe', { defaultValue: 'Issue PPE' }),
          onClick: () => setShowCreate(true),
        }}
      />
    );
  }

  return (
    <>
      <div className="mb-4">
        <FilterChips<'all' | 'issued' | 'expiring'>
          value={filter}
          onChange={setFilter}
          options={[
            {
              value: 'all',
              label: t('hse_advanced.filter_all', { defaultValue: 'All' }),
              count: counts.all,
            },
            {
              value: 'issued',
              label: t('hse_advanced.filter_issued', { defaultValue: 'Issued' }),
              count: counts.issued,
            },
            {
              value: 'expiring',
              label: t('hse_advanced.filter_expiring', { defaultValue: 'Expiring 30d' }),
              count: counts.expiring,
            },
          ]}
        />
      </div>

      <Card padding="none">
        <SearchBar
          value={search}
          onChange={setSearch}
          placeholder={t('hse_advanced.search_ppe', { defaultValue: 'Search PPE...' })}
          onCreate={() => setShowCreate(true)}
          createLabel={t('hse_advanced.new_ppe', { defaultValue: 'Issue PPE' })}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-light bg-surface-secondary/50">
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.number', { defaultValue: '#' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.item', { defaultValue: 'Item' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.issued_to', { defaultValue: 'Issued to' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.issued_at', { defaultValue: 'Issued at' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('hse_advanced.qty', { defaultValue: 'Qty' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('hse_advanced.expiry', { defaultValue: 'Expiry' })}
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-content-tertiary">
                    {t('hse_advanced.no_matches', { defaultValue: 'No matches' })}
                  </td>
                </tr>
              ) : (
                filtered.map((p) => {
                  const d = daysUntil(p.expires_at);
                  const flag = d !== null && d >= 0 && d <= 30;
                  return (
                    <tr
                      key={p.id}
                      className="border-b border-border-light hover:bg-surface-secondary/30 cursor-pointer"
                      onClick={() => setDetail(p)}
                    >
                      <td className="px-4 py-3 font-mono text-xs">{p.ppe_number}</td>
                      <td className="px-4 py-3 text-content-primary">
                        {p.item_type.replace(/_/g, ' ')}
                      </td>
                      <td className="px-4 py-3 text-content-secondary">{p.issued_to_name}</td>
                      <td className="px-4 py-3 text-content-secondary">
                        <DateDisplay value={p.issued_at} />
                      </td>
                      <td className="px-4 py-3 text-center tabular-nums">{p.quantity}</td>
                      <td className="px-4 py-3 text-center">
                        {p.expires_at ? (
                          <span
                            className={
                              flag
                                ? 'text-amber-600 font-medium text-xs'
                                : 'text-content-secondary text-xs'
                            }
                          >
                            <DateDisplay value={p.expires_at} />
                            {flag && (
                              <AlertTriangle
                                size={12}
                                className="inline ml-1 text-amber-600"
                              />
                            )}
                          </span>
                        ) : (
                          <span className="text-content-tertiary">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {showCreate && (
        <ModalShell
          title={t('hse_advanced.new_ppe', { defaultValue: 'Issue PPE' })}
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setShowCreate(false)}>
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </Button>
              <Button
                variant="primary"
                disabled={!form.issued_to_name.trim() || createMut.isPending}
                onClick={() => createMut.mutate()}
              >
                {t('common.issue', { defaultValue: 'Issue' })}
              </Button>
            </>
          }
        >
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-content-primary mb-1.5">
                {t('hse_advanced.item_type', { defaultValue: 'Item type' })}
              </label>
              <select
                className={inputCls}
                value={form.item_type}
                onChange={(e) => setForm((f) => ({ ...f, item_type: e.target.value }))}
              >
                <option value="hard_hat">
                  {t('hse_advanced.ppe_hard_hat', { defaultValue: 'Hard hat' })}
                </option>
                <option value="safety_boots">
                  {t('hse_advanced.ppe_safety_boots', { defaultValue: 'Safety boots' })}
                </option>
                <option value="hi_vis">
                  {t('hse_advanced.ppe_hi_vis', { defaultValue: 'Hi-vis vest' })}
                </option>
                <option value="harness">
                  {t('hse_advanced.ppe_harness', { defaultValue: 'Fall harness' })}
                </option>
                <option value="respirator">
                  {t('hse_advanced.ppe_respirator', { defaultValue: 'Respirator' })}
                </option>
                <option value="hearing">
                  {t('hse_advanced.ppe_hearing', { defaultValue: 'Hearing protection' })}
                </option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-content-primary mb-1.5">
                {t('hse_advanced.qty', { defaultValue: 'Qty' })}
              </label>
              <input
                type="number"
                min={1}
                className={inputCls}
                value={form.quantity}
                onChange={(e) =>
                  setForm((f) => ({ ...f, quantity: Math.max(1, Number(e.target.value) || 1) }))
                }
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('hse_advanced.issued_to', { defaultValue: 'Issued to' })}{' '}
              <span className="text-semantic-error">*</span>
            </label>
            <input
              className={inputCls}
              value={form.issued_to_name}
              onChange={(e) => setForm((f) => ({ ...f, issued_to_name: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-content-primary mb-1.5">
                {t('hse_advanced.issued_at', { defaultValue: 'Issued at' })}
              </label>
              <input
                type="date"
                className={inputCls}
                value={form.issued_at}
                onChange={(e) => setForm((f) => ({ ...f, issued_at: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-content-primary mb-1.5">
                {t('hse_advanced.return_by', { defaultValue: 'Return by' })}
              </label>
              <input
                type="date"
                className={inputCls}
                value={form.return_by}
                onChange={(e) => setForm((f) => ({ ...f, return_by: e.target.value }))}
              />
            </div>
          </div>
        </ModalShell>
      )}

      {detail && <PPEDetailDrawer item={detail} onClose={() => setDetail(null)} />}
    </>
  );
}

/* ── PPE Detail Drawer ───────────────────────────────────────────────── */

function PPEDetailDrawer({ item, onClose }: { item: PPEIssue; onClose: () => void }) {
  const { t } = useTranslation();
  const expiryDays = daysUntil(item.expires_at);
  const returnDays = daysUntil(item.return_by);

  return (
    <ModalShell
      title={`${item.ppe_number} — ${item.item_type.replace(/_/g, ' ')}`}
      onClose={onClose}
      size="max-w-xl"
      footer={
        <Button variant="ghost" onClick={onClose}>
          {t('common.close', { defaultValue: 'Close' })}
        </Button>
      }
    >
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-xs text-content-tertiary uppercase">
            {t('hse_advanced.issued_to', { defaultValue: 'Issued to' })}
          </div>
          <div className="text-content-primary font-medium">{item.issued_to_name}</div>
        </div>
        <div>
          <div className="text-xs text-content-tertiary uppercase">
            {t('hse_advanced.qty', { defaultValue: 'Quantity' })}
          </div>
          <div className="text-content-primary tabular-nums">{item.quantity}</div>
        </div>
        <div>
          <div className="text-xs text-content-tertiary uppercase">
            {t('hse_advanced.issued_at', { defaultValue: 'Issued at' })}
          </div>
          <div className="text-content-secondary">
            <DateDisplay value={item.issued_at} />
          </div>
        </div>
        <div>
          <div className="text-xs text-content-tertiary uppercase">
            {t('hse_advanced.return_by', { defaultValue: 'Return by' })}
          </div>
          <div
            className={
              returnDays !== null && returnDays < 0
                ? 'text-semantic-error font-medium'
                : 'text-content-secondary'
            }
          >
            {item.return_by ? <DateDisplay value={item.return_by} /> : '—'}
            {returnDays !== null &&
              ` (${
                returnDays < 0
                  ? t('hse_advanced.expired_days_ago', {
                      defaultValue: '{{n}}d ago',
                      n: Math.abs(returnDays),
                    })
                  : t('hse_advanced.in_days', { defaultValue: 'in {{n}}d', n: returnDays })
              })`}
          </div>
        </div>
      </div>

      {item.expires_at && (
        <div className="rounded-lg bg-surface-secondary p-3 text-sm flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-content-secondary">
            <Clock size={14} />
            {t('hse_advanced.expiry', { defaultValue: 'Expiry' })}
          </span>
          <span
            className={
              expiryDays !== null && expiryDays < 0
                ? 'text-semantic-error font-semibold'
                : expiryDays !== null && expiryDays <= 30
                  ? 'text-amber-600 font-semibold'
                  : 'text-content-primary'
            }
          >
            <DateDisplay value={item.expires_at} />
            {expiryDays !== null &&
              ` — ${
                expiryDays < 0
                  ? t('hse_advanced.expired_days_ago', {
                      defaultValue: '{{n}}d ago',
                      n: Math.abs(expiryDays),
                    })
                  : t('hse_advanced.in_days', { defaultValue: 'in {{n}}d', n: expiryDays })
              }`}
          </span>
        </div>
      )}

      {item.notes && (
        <div>
          <div className="text-xs text-content-tertiary uppercase mb-1">
            {t('common.notes', { defaultValue: 'Notes' })}
          </div>
          <p className="text-sm text-content-secondary whitespace-pre-wrap">{item.notes}</p>
        </div>
      )}
    </ModalShell>
  );
}

/* ── Audits Tab ──────────────────────────────────────────────────────── */

function AuditsTab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    title: '',
    audit_date: new Date().toISOString().slice(0, 10),
    auditor: '',
    scope: '',
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ['hse-audits', projectId],
    queryFn: () => fetchAudits(projectId),
    select: (d) => normalizeListResponse<SafetyAudit>(d),
  });

  const createMut = useMutation({
    mutationFn: () => createAudit({ project_id: projectId, ...form }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hse-audits', projectId] });
      setShowCreate(false);
      setForm({
        title: '',
        audit_date: new Date().toISOString().slice(0, 10),
        auditor: '',
        scope: '',
      });
      addToast({
        type: 'success',
        title: t('hse_advanced.audit_created', { defaultValue: 'Audit scheduled' }),
      });
    },
    onError: (e) =>
      addToast({
        type: 'error',
        title: t('hse_advanced.audit_failed', { defaultValue: 'Failed to schedule audit' }),
        message: getErrorMessage(e),
      }),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!search) return data;
    const q = search.toLowerCase();
    return data.filter((it) => it.title.toLowerCase().includes(q));
  }, [data, search]);

  if (isLoading) return <SkeletonTable rows={5} columns={6} />;
  if (isError) {
    return (
      <Card className="py-12">
        <EmptyState
          icon={<AlertTriangle size={28} strokeWidth={1.5} />}
          title={t('common.error', { defaultValue: 'Error' })}
          description={t('hse_advanced.load_error', {
            defaultValue: 'Failed to load HSE records. Please try again.',
          })}
        />
      </Card>
    );
  }
  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon={<ShieldCheck size={28} strokeWidth={1.5} />}
        title={t('hse_advanced.no_audits', { defaultValue: 'No safety audits yet' })}
        description={t('hse_advanced.no_audits_desc', {
          defaultValue:
            'Plan recurring safety audits and walk-throughs. Findings can be converted into CAPA actions with assigned owners and due dates.',
        })}
        action={{
          label: t('hse_advanced.new_audit', { defaultValue: 'Schedule Audit' }),
          onClick: () => setShowCreate(true),
        }}
      />
    );
  }

  return (
    <>
      <Card padding="none">
        <SearchBar
          value={search}
          onChange={setSearch}
          placeholder={t('hse_advanced.search_audits', { defaultValue: 'Search audits...' })}
          onCreate={() => setShowCreate(true)}
          createLabel={t('hse_advanced.new_audit', { defaultValue: 'Schedule Audit' })}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-light bg-surface-secondary/50">
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.number', { defaultValue: '#' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.title', { defaultValue: 'Title' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.auditor', { defaultValue: 'Auditor' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.date', { defaultValue: 'Date' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('common.status', { defaultValue: 'Status' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('hse_advanced.findings', { defaultValue: 'Findings' })}
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-content-tertiary">
                    {t('hse_advanced.no_matches', { defaultValue: 'No matches' })}
                  </td>
                </tr>
              ) : (
                filtered.map((it) => (
                  <tr key={it.id} className="border-b border-border-light hover:bg-surface-secondary/30">
                    <td className="px-4 py-3 font-mono text-xs">{it.audit_number}</td>
                    <td className="px-4 py-3 text-content-primary">{it.title}</td>
                    <td className="px-4 py-3 text-content-secondary">{it.auditor ?? '—'}</td>
                    <td className="px-4 py-3 text-content-secondary">
                      <DateDisplay value={it.audit_date} />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Badge
                        variant={it.status === 'completed' ? 'success' : 'blue'}
                        size="sm"
                      >
                        {it.status.replace(/_/g, ' ')}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-center tabular-nums">
                      {it.findings_count ?? it.findings?.length ?? 0}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {showCreate && (
        <ModalShell
          title={t('hse_advanced.new_audit', { defaultValue: 'Schedule Audit' })}
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setShowCreate(false)}>
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </Button>
              <Button
                variant="primary"
                disabled={!form.title.trim() || createMut.isPending}
                onClick={() => createMut.mutate()}
              >
                {t('common.schedule', { defaultValue: 'Schedule' })}
              </Button>
            </>
          }
        >
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('common.title', { defaultValue: 'Title' })}{' '}
              <span className="text-semantic-error">*</span>
            </label>
            <input
              className={inputCls}
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-content-primary mb-1.5">
                {t('hse_advanced.date', { defaultValue: 'Date' })}
              </label>
              <input
                type="date"
                className={inputCls}
                value={form.audit_date}
                onChange={(e) => setForm((f) => ({ ...f, audit_date: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-content-primary mb-1.5">
                {t('hse_advanced.auditor', { defaultValue: 'Auditor' })}
              </label>
              <input
                className={inputCls}
                value={form.auditor}
                onChange={(e) => setForm((f) => ({ ...f, auditor: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('hse_advanced.scope', { defaultValue: 'Scope' })}
            </label>
            <textarea
              rows={3}
              className={textareaCls}
              value={form.scope}
              onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value }))}
            />
          </div>
        </ModalShell>
      )}
    </>
  );
}

/* ── CAPA Tab ────────────────────────────────────────────────────────── */

function CAPATab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [filter, setFilter] = useState<'all' | 'open' | 'closed'>('open');
  const [form, setForm] = useState({
    title: '',
    description: '',
    assigned_to: '',
    due_date: '',
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ['hse-capa', projectId],
    queryFn: () => fetchCAPAs(projectId),
    select: (d) => normalizeListResponse<CorrectiveAction>(d),
  });

  const createMut = useMutation({
    mutationFn: () =>
      createCAPA({
        project_id: projectId,
        title: form.title,
        description: form.description,
        assigned_to: form.assigned_to || undefined,
        due_date: form.due_date || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hse-capa', projectId] });
      setShowCreate(false);
      setForm({ title: '', description: '', assigned_to: '', due_date: '' });
      addToast({
        type: 'success',
        title: t('hse_advanced.capa_created', { defaultValue: 'CAPA created' }),
      });
    },
    onError: (e) =>
      addToast({
        type: 'error',
        title: t('hse_advanced.capa_failed', { defaultValue: 'Failed to create CAPA' }),
        message: getErrorMessage(e),
      }),
  });

  const counts = useMemo(() => {
    const c = { all: data?.length ?? 0, open: 0, closed: 0 };
    if (!data) return c;
    for (const it of data) {
      if (it.status === 'closed' || it.status === 'verified' || it.status === 'completed')
        c.closed++;
      else c.open++;
    }
    return c;
  }, [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    let rows = data;
    if (filter === 'open')
      rows = rows.filter(
        (it) => it.status !== 'closed' && it.status !== 'verified' && it.status !== 'completed',
      );
    else if (filter === 'closed')
      rows = rows.filter(
        (it) => it.status === 'closed' || it.status === 'verified' || it.status === 'completed',
      );
    if (!search) return rows;
    const q = search.toLowerCase();
    return rows.filter(
      (it) => it.title.toLowerCase().includes(q) || it.capa_number.toLowerCase().includes(q),
    );
  }, [data, search, filter]);

  if (isLoading) return <SkeletonTable rows={5} columns={6} />;
  if (isError) {
    return (
      <Card className="py-12">
        <EmptyState
          icon={<AlertTriangle size={28} strokeWidth={1.5} />}
          title={t('common.error', { defaultValue: 'Error' })}
          description={t('hse_advanced.load_error', {
            defaultValue: 'Failed to load HSE records. Please try again.',
          })}
        />
      </Card>
    );
  }
  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon={<Wrench size={28} strokeWidth={1.5} />}
        title={t('hse_advanced.no_capa', { defaultValue: 'No corrective actions yet' })}
        description={t('hse_advanced.no_capa_desc', {
          defaultValue:
            'Corrective and Preventive Actions track what was done to fix an issue and prevent recurrence. They link back to incidents, audits or NCRs.',
        })}
        action={{
          label: t('hse_advanced.new_capa', { defaultValue: 'New CAPA' }),
          onClick: () => setShowCreate(true),
        }}
      />
    );
  }

  return (
    <>
      <div className="mb-4">
        <FilterChips<'all' | 'open' | 'closed'>
          value={filter}
          onChange={setFilter}
          options={[
            {
              value: 'open',
              label: t('hse_advanced.filter_open', { defaultValue: 'Open' }),
              count: counts.open,
            },
            {
              value: 'closed',
              label: t('hse_advanced.filter_closed', { defaultValue: 'Closed' }),
              count: counts.closed,
            },
            {
              value: 'all',
              label: t('hse_advanced.filter_all', { defaultValue: 'All' }),
              count: counts.all,
            },
          ]}
        />
      </div>

      <Card padding="none">
        <SearchBar
          value={search}
          onChange={setSearch}
          placeholder={t('hse_advanced.search_capa', { defaultValue: 'Search CAPAs...' })}
          onCreate={() => setShowCreate(true)}
          createLabel={t('hse_advanced.new_capa', { defaultValue: 'New CAPA' })}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-light bg-surface-secondary/50">
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.number', { defaultValue: '#' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('common.title', { defaultValue: 'Title' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.assigned_to', { defaultValue: 'Assigned to' })}
                </th>
                <th className="px-4 py-3 text-left font-medium text-content-tertiary">
                  {t('hse_advanced.due', { defaultValue: 'Due' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('common.status', { defaultValue: 'Status' })}
                </th>
                <th className="px-4 py-3 text-center font-medium text-content-tertiary">
                  {t('hse_advanced.countdown', { defaultValue: 'Countdown' })}
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-content-tertiary">
                    {t('hse_advanced.no_matches', { defaultValue: 'No matches' })}
                  </td>
                </tr>
              ) : (
                filtered.map((it) => {
                  const days = daysUntil(it.due_date);
                  const isClosed =
                    it.status === 'closed' ||
                    it.status === 'verified' ||
                    it.status === 'completed';
                  return (
                    <tr
                      key={it.id}
                      className="border-b border-border-light hover:bg-surface-secondary/30"
                    >
                      <td className="px-4 py-3 font-mono text-xs">{it.capa_number}</td>
                      <td className="px-4 py-3 text-content-primary">{it.title}</td>
                      <td className="px-4 py-3 text-content-secondary">
                        {it.assigned_to ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-content-secondary">
                        {it.due_date ? <DateDisplay value={it.due_date} /> : '—'}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Badge variant={CAPA_STATUS_COLORS[it.status] ?? 'neutral'} size="sm">
                          {it.status.replace(/_/g, ' ')}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-center tabular-nums text-xs">
                        {isClosed || days === null ? (
                          <span className="text-content-tertiary">—</span>
                        ) : days < 0 ? (
                          <span className="text-semantic-error font-medium">
                            {t('hse_advanced.overdue_days', {
                              defaultValue: '{{n}}d overdue',
                              n: Math.abs(days),
                            })}
                          </span>
                        ) : (
                          <span
                            className={
                              days <= 3 ? 'text-amber-600 font-medium' : 'text-content-secondary'
                            }
                          >
                            {t('hse_advanced.in_days', { defaultValue: 'in {{n}}d', n: days })}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {showCreate && (
        <ModalShell
          title={t('hse_advanced.new_capa', { defaultValue: 'New CAPA' })}
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setShowCreate(false)}>
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </Button>
              <Button
                variant="primary"
                disabled={!form.title.trim() || !form.description.trim() || createMut.isPending}
                onClick={() => createMut.mutate()}
              >
                {t('common.create', { defaultValue: 'Create' })}
              </Button>
            </>
          }
        >
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('common.title', { defaultValue: 'Title' })}{' '}
              <span className="text-semantic-error">*</span>
            </label>
            <input
              className={inputCls}
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-content-primary mb-1.5">
              {t('common.description', { defaultValue: 'Description' })}{' '}
              <span className="text-semantic-error">*</span>
            </label>
            <textarea
              rows={3}
              className={textareaCls}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-content-primary mb-1.5">
                {t('hse_advanced.assigned_to', { defaultValue: 'Assigned to' })}
              </label>
              <input
                className={inputCls}
                value={form.assigned_to}
                onChange={(e) => setForm((f) => ({ ...f, assigned_to: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-content-primary mb-1.5">
                {t('hse_advanced.due_date', { defaultValue: 'Due date' })}
              </label>
              <input
                type="date"
                className={inputCls}
                value={form.due_date}
                onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))}
              />
            </div>
          </div>
        </ModalShell>
      )}
    </>
  );
}
