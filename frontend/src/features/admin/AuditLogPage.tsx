/**
 * Audit Log Page — read-only timeline of every audit-bearing change in
 * the system.  Gated on the backend by `audit.view` (Manager+) and
 * exposed in the sidebar's Admin group when the JWT role is admin or
 * manager (the SidebarItem-gated check mirrors backend perms).
 *
 * Surface:
 *   • Server-side pagination (default limit=50, controls top + bottom).
 *   • Filters: user picker (autocomplete from /v1/users/), module/entity
 *     dropdown, free-text action, ISO date range, severity-band chips
 *     (heuristic — backend does not yet emit a severity column, see
 *     "Deferred" at bottom of the report).
 *   • Per-row drawer with side-by-side before/after JSON diff (hand-rolled
 *     to avoid adding a `react-diff-view` dependency).
 *   • CSV export of the current page (client-side render).
 *   • Touch-friendly: rows ≥56px, large tap targets, full-width on
 *     mobile.  Pure read-only — no mutation buttons.
 */

import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import clsx from 'clsx';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  Eye,
  Filter,
  History as HistoryIcon,
  Search,
  ShieldAlert,
  ShieldCheck,
  User as UserIcon,
  X,
} from 'lucide-react';
import { Badge, Card, EmptyState } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import { triggerDownload } from '@/shared/lib/api';
import { fetchUsers, type User } from '@/features/users/api';
import {
  listAuditEntries,
  type AuditEntry,
  type AuditFilters,
  WELL_KNOWN_ENTITY_TYPES,
  WELL_KNOWN_ACTIONS,
} from './api';

const DEFAULT_LIMIT = 50;

/** Map common audit actions to a severity bucket for the chip filter. */
type Severity = 'info' | 'warning' | 'critical';
const SEVERITY_BY_ACTION: Record<string, Severity> = {
  create: 'info',
  update: 'info',
  login: 'info',
  logout: 'info',
  export: 'info',
  import: 'info',
  enable: 'info',
  approve: 'info',
  status_changed: 'info',
  reject: 'warning',
  disable: 'warning',
  archive: 'warning',
  delete: 'critical',
  restore: 'warning',
};

function severityOf(action: string): Severity {
  const key = action.toLowerCase();
  return SEVERITY_BY_ACTION[key] ?? 'info';
}

function severityBadgeVariant(sev: Severity): 'neutral' | 'blue' | 'warning' | 'error' {
  if (sev === 'critical') return 'error';
  if (sev === 'warning') return 'warning';
  return 'blue';
}

/** Format an ISO timestamp into a locale-friendly "MMM d, HH:mm:ss" string. */
function formatTimestamp(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

/** Lookup helper for the user picker — populates the user_id → email map. */
function buildUserMap(users: User[] | undefined): Map<string, User> {
  const m = new Map<string, User>();
  for (const u of users ?? []) m.set(u.id, u);
  return m;
}

/** Pull "before"/"after" payload shapes from the details column.
 *  Audit emitters do not all agree on a single shape, so we try a few
 *  well-known keys before falling back to "raw details".  All branches
 *  return a tuple so the caller can render a single side-by-side panel. */
function extractDiff(details: Record<string, unknown> | null): {
  before: unknown;
  after: unknown;
  raw: Record<string, unknown> | null;
} {
  if (!details) return { before: null, after: null, raw: null };
  const d = details as Record<string, unknown>;
  if ('before' in d || 'after' in d) {
    return { before: d.before ?? null, after: d.after ?? null, raw: d };
  }
  if ('old' in d || 'new' in d) {
    return { before: d.old ?? null, after: d.new ?? null, raw: d };
  }
  return { before: null, after: null, raw: d };
}

function toCsvCell(value: unknown): string {
  if (value == null) return '';
  const s = typeof value === 'string' ? value : JSON.stringify(value);
  const needsQuote = /[",\n\r]/.test(s);
  const escaped = s.replace(/"/g, '""');
  return needsQuote ? `"${escaped}"` : escaped;
}

function entriesToCsv(entries: AuditEntry[], userMap: Map<string, User>): string {
  const header = [
    'created_at',
    'action',
    'entity_type',
    'entity_id',
    'user_id',
    'user_email',
    'ip_address',
    'details',
  ];
  const rows = entries.map((e) => {
    const u = e.user_id ? userMap.get(e.user_id) : null;
    return [
      toCsvCell(e.created_at),
      toCsvCell(e.action),
      toCsvCell(e.entity_type),
      toCsvCell(e.entity_id),
      toCsvCell(e.user_id),
      toCsvCell(u?.email ?? ''),
      toCsvCell(e.ip_address),
      toCsvCell(e.details ?? {}),
    ].join(',');
  });
  return [header.join(','), ...rows].join('\r\n');
}

/* ── filter bar ─────────────────────────────────────────────────────── */

interface FilterBarProps {
  draft: AuditFilters;
  severity: Severity | 'all';
  users: User[] | undefined;
  onSeverity: (s: Severity | 'all') => void;
  onChange: (next: AuditFilters) => void;
  onReset: () => void;
}

function FilterBar({ draft, severity, users, onSeverity, onChange, onReset }: FilterBarProps) {
  const { t } = useTranslation();
  const [userQuery, setUserQuery] = useState('');
  const [userOpen, setUserOpen] = useState(false);

  const filteredUsers = useMemo(() => {
    const q = userQuery.trim().toLowerCase();
    const list = users ?? [];
    if (!q) return list.slice(0, 12);
    return list
      .filter(
        (u) =>
          u.email.toLowerCase().includes(q) ||
          (u.full_name ?? '').toLowerCase().includes(q),
      )
      .slice(0, 12);
  }, [users, userQuery]);

  const selectedUser = useMemo(
    () => (draft.userId ? users?.find((u) => u.id === draft.userId) : undefined),
    [users, draft.userId],
  );

  const sevChips: Array<{ id: Severity | 'all'; label: string; icon: typeof ShieldCheck }> = [
    { id: 'all', label: t('audit.severity_all', { defaultValue: 'All' }), icon: Filter },
    { id: 'info', label: t('audit.severity_info', { defaultValue: 'Info' }), icon: ShieldCheck },
    { id: 'warning', label: t('audit.severity_warning', { defaultValue: 'Warning' }), icon: ShieldAlert },
    { id: 'critical', label: t('audit.severity_critical', { defaultValue: 'Critical' }), icon: AlertCircle },
  ];

  return (
    <Card className="mb-4">
      <div className="p-4 grid gap-3 md:grid-cols-2 lg:grid-cols-5">
        {/* User picker */}
        <div className="relative">
          <label className="block text-xs font-medium text-content-secondary mb-1">
            {t('audit.filter_user', { defaultValue: 'User' })}
          </label>
          <div className="relative">
            <UserIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 text-content-tertiary" size={14} />
            <input
              type="text"
              role="combobox"
              aria-expanded={userOpen}
              aria-label={t('audit.filter_user', { defaultValue: 'User' })}
              value={selectedUser ? selectedUser.email : userQuery}
              placeholder={t('audit.filter_user_placeholder', { defaultValue: 'Search by email or name…' })}
              onFocus={() => setUserOpen(true)}
              onBlur={() => window.setTimeout(() => setUserOpen(false), 150)}
              onChange={(e) => {
                setUserQuery(e.target.value);
                if (draft.userId) onChange({ ...draft, userId: null });
              }}
              className="h-9 w-full rounded-lg border border-border bg-surface-primary pl-8 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue"
            />
            {(draft.userId || userQuery) && (
              <button
                type="button"
                onClick={() => {
                  setUserQuery('');
                  onChange({ ...draft, userId: null });
                }}
                aria-label={t('common.clear', { defaultValue: 'Clear' })}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-content-tertiary hover:text-content-primary"
              >
                <X size={14} />
              </button>
            )}
          </div>
          {userOpen && filteredUsers.length > 0 && (
            <ul
              role="listbox"
              className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-border bg-surface-primary shadow-lg"
            >
              {filteredUsers.map((u) => (
                <li key={u.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={draft.userId === u.id}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      setUserQuery('');
                      setUserOpen(false);
                      onChange({ ...draft, userId: u.id });
                    }}
                    className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-secondary"
                  >
                    <div className="font-medium">{u.full_name || u.email}</div>
                    <div className="text-xs text-content-tertiary">{u.email}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Module / entity-type */}
        <div>
          <label className="block text-xs font-medium text-content-secondary mb-1">
            {t('audit.filter_module', { defaultValue: 'Module / entity' })}
          </label>
          <select
            value={draft.entityType ?? ''}
            onChange={(e) => onChange({ ...draft, entityType: e.target.value || null })}
            className="h-9 w-full rounded-lg border border-border bg-surface-primary px-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue"
            aria-label={t('audit.filter_module', { defaultValue: 'Module / entity' })}
          >
            <option value="">{t('audit.filter_module_all', { defaultValue: 'All entities' })}</option>
            {WELL_KNOWN_ENTITY_TYPES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>

        {/* Action — free text with datalist hint */}
        <div>
          <label className="block text-xs font-medium text-content-secondary mb-1">
            {t('audit.filter_action', { defaultValue: 'Action' })}
          </label>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-content-tertiary" size={14} />
            <input
              type="text"
              list="audit-action-suggestions"
              value={draft.action ?? ''}
              onChange={(e) => onChange({ ...draft, action: e.target.value || null })}
              placeholder={t('audit.filter_action_placeholder', { defaultValue: 'create, update, delete…' })}
              className="h-9 w-full rounded-lg border border-border bg-surface-primary pl-8 pr-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue"
              aria-label={t('audit.filter_action', { defaultValue: 'Action' })}
            />
            <datalist id="audit-action-suggestions">
              {WELL_KNOWN_ACTIONS.map((a) => (
                <option key={a} value={a} />
              ))}
            </datalist>
          </div>
        </div>

        {/* Date range — from / to as two native date inputs */}
        <div>
          <label className="block text-xs font-medium text-content-secondary mb-1">
            {t('audit.filter_from', { defaultValue: 'From' })}
          </label>
          <input
            type="date"
            value={draft.dateFrom ? draft.dateFrom.slice(0, 10) : ''}
            onChange={(e) =>
              onChange({ ...draft, dateFrom: e.target.value ? `${e.target.value}T00:00:00Z` : null })
            }
            className="h-9 w-full rounded-lg border border-border bg-surface-primary px-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue"
            aria-label={t('audit.filter_from', { defaultValue: 'From' })}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-content-secondary mb-1">
            {t('audit.filter_to', { defaultValue: 'To' })}
          </label>
          <input
            type="date"
            value={draft.dateTo ? draft.dateTo.slice(0, 10) : ''}
            onChange={(e) =>
              onChange({ ...draft, dateTo: e.target.value ? `${e.target.value}T23:59:59Z` : null })
            }
            className="h-9 w-full rounded-lg border border-border bg-surface-primary px-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue"
            aria-label={t('audit.filter_to', { defaultValue: 'To' })}
          />
        </div>
      </div>

      {/* Severity chips + reset */}
      <div className="flex flex-wrap items-center gap-2 px-4 pb-4">
        <span className="text-xs font-medium text-content-secondary mr-1">
          {t('audit.severity', { defaultValue: 'Severity' })}:
        </span>
        {sevChips.map((c) => {
          const active = severity === c.id;
          const Icon = c.icon;
          return (
            <button
              key={c.id}
              type="button"
              aria-pressed={active}
              onClick={() => onSeverity(c.id)}
              className={clsx(
                'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                active
                  ? 'bg-oe-blue text-content-inverse border-oe-blue'
                  : 'border-border text-content-secondary hover:bg-surface-secondary',
              )}
            >
              <Icon size={12} />
              {c.label}
            </button>
          );
        })}
        <div className="grow" />
        <button
          type="button"
          onClick={onReset}
          className="text-xs text-content-secondary hover:text-content-primary underline-offset-2 hover:underline"
        >
          {t('audit.reset_filters', { defaultValue: 'Reset filters' })}
        </button>
      </div>
    </Card>
  );
}

/* ── row + drawer ───────────────────────────────────────────────────── */

function TimelineRow({
  entry,
  user,
  onOpen,
}: {
  entry: AuditEntry;
  user: User | undefined;
  onOpen: () => void;
}) {
  const sev = severityOf(entry.action);
  return (
    <button
      type="button"
      onClick={onOpen}
      data-testid="audit-row"
      className={clsx(
        'group flex w-full items-center gap-3 border-b border-border-light bg-surface-primary px-4 py-3 text-left',
        'min-h-[56px] hover:bg-surface-secondary focus:bg-surface-secondary focus:outline-none focus:ring-2 focus:ring-inset focus:ring-oe-blue/30',
      )}
      aria-label={`${entry.action} ${entry.entity_type}`}
    >
      <Badge variant={severityBadgeVariant(sev)} className="shrink-0">
        {sev}
      </Badge>
      <div className="grow min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="font-mono text-xs text-content-tertiary">
            <Clock className="inline mr-1" size={11} />
            {formatTimestamp(entry.created_at)}
          </span>
          <span className="font-medium text-sm">{entry.action}</span>
          <span className="text-sm text-content-secondary">·</span>
          <span className="text-sm text-content-primary">{entry.entity_type}</span>
          {entry.entity_id && (
            <span className="font-mono text-xs text-content-tertiary truncate">
              #{entry.entity_id.slice(0, 8)}
            </span>
          )}
        </div>
        <div className="text-xs text-content-tertiary truncate">
          {user ? `${user.full_name || user.email}` : entry.user_id ? `user:${entry.user_id.slice(0, 8)}` : 'system'}
          {entry.ip_address ? ` · ${entry.ip_address}` : ''}
        </div>
      </div>
      <Eye size={14} className="shrink-0 text-content-tertiary opacity-0 group-hover:opacity-100 transition-opacity" />
    </button>
  );
}

function JsonBlock({ data }: { data: unknown }) {
  let pretty: string;
  try {
    pretty = JSON.stringify(data ?? null, null, 2);
  } catch {
    pretty = String(data);
  }
  return (
    <pre className="m-0 overflow-auto rounded-md bg-surface-secondary p-3 text-xs leading-relaxed text-content-primary whitespace-pre-wrap break-words">
      {pretty}
    </pre>
  );
}

function DetailDrawer({
  entry,
  user,
  onClose,
}: {
  entry: AuditEntry;
  user: User | undefined;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const diff = extractDiff(entry.details);
  const hasDiff = diff.before !== null || diff.after !== null;
  return (
    <div
      className="fixed inset-0 z-40 flex"
      role="dialog"
      aria-modal="true"
      aria-label={t('audit.drawer_title', { defaultValue: 'Audit entry detail' })}
    >
      <div
        className="absolute inset-0 bg-black/30"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        data-testid="audit-drawer"
        className="relative ml-auto h-full w-full max-w-xl overflow-y-auto bg-surface-primary shadow-xl"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-surface-primary px-4 py-3">
          <div className="min-w-0">
            <div className="text-xs text-content-tertiary">
              {formatTimestamp(entry.created_at)}
            </div>
            <div className="truncate font-medium">
              {entry.action} · {entry.entity_type}
              {entry.entity_id ? ` · ${entry.entity_id}` : ''}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close', { defaultValue: 'Close' })}
            className="flex h-8 w-8 items-center justify-center rounded-md text-content-tertiary hover:bg-surface-secondary hover:text-content-primary"
          >
            <X size={16} />
          </button>
        </div>
        <div className="space-y-4 p-4">
          <section>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-content-tertiary">
              {t('audit.actor', { defaultValue: 'Actor' })}
            </div>
            <div className="text-sm">
              {user ? (
                <>
                  <div>{user.full_name || user.email}</div>
                  <div className="text-xs text-content-tertiary">{user.email}</div>
                </>
              ) : entry.user_id ? (
                <span className="font-mono text-xs">{entry.user_id}</span>
              ) : (
                <span className="text-content-tertiary">{t('audit.system', { defaultValue: 'System / background' })}</span>
              )}
              {entry.ip_address && (
                <div className="text-xs text-content-tertiary font-mono">{entry.ip_address}</div>
              )}
            </div>
          </section>

          {hasDiff ? (
            <section>
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-content-tertiary">
                {t('audit.diff', { defaultValue: 'Before / after' })}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <div className="mb-1 text-xs text-content-secondary">
                    {t('audit.before', { defaultValue: 'Before' })}
                  </div>
                  <JsonBlock data={diff.before} />
                </div>
                <div>
                  <div className="mb-1 text-xs text-content-secondary">
                    {t('audit.after', { defaultValue: 'After' })}
                  </div>
                  <JsonBlock data={diff.after} />
                </div>
              </div>
            </section>
          ) : null}

          <section>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-content-tertiary">
              {t('audit.raw_payload', { defaultValue: 'Raw payload' })}
            </div>
            <JsonBlock data={diff.raw} />
          </section>
        </div>
      </aside>
    </div>
  );
}

/* ── page ───────────────────────────────────────────────────────────── */

export function AuditLogPage() {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);

  const [filters, setFilters] = useState<AuditFilters>({ limit: DEFAULT_LIMIT, offset: 0 });
  const [draft, setDraft] = useState<AuditFilters>({ limit: DEFAULT_LIMIT, offset: 0 });
  const [severity, setSeverity] = useState<Severity | 'all'>('all');
  const [activeId, setActiveId] = useState<string | null>(null);

  const usersQuery = useQuery({
    queryKey: ['audit-log', 'users'],
    queryFn: () => fetchUsers({ limit: 200 }),
    staleTime: 60_000,
  });

  const entriesQuery = useQuery({
    queryKey: ['audit-log', 'entries', filters],
    queryFn: () => listAuditEntries(filters),
  });

  const userMap = useMemo(() => buildUserMap(usersQuery.data), [usersQuery.data]);

  const filteredEntries = useMemo(() => {
    const list = entriesQuery.data ?? [];
    if (severity === 'all') return list;
    return list.filter((e) => severityOf(e.action) === severity);
  }, [entriesQuery.data, severity]);

  const applyFilters = useCallback(() => {
    // Reset pagination whenever the filter set changes — otherwise an
    // offset that pointed into the old result set bleeds into the new one
    // and shows an empty page on the first apply.
    setFilters({ ...draft, offset: 0 });
  }, [draft]);

  const resetFilters = useCallback(() => {
    const reset: AuditFilters = { limit: DEFAULT_LIMIT, offset: 0 };
    setDraft(reset);
    setFilters(reset);
    setSeverity('all');
  }, []);

  const offset = filters.offset ?? 0;
  const limit = filters.limit ?? DEFAULT_LIMIT;
  const pageStart = offset + 1;
  const pageEnd = offset + (entriesQuery.data?.length ?? 0);
  const canPrev = offset > 0;
  const canNext = (entriesQuery.data?.length ?? 0) >= limit;

  const handlePrev = useCallback(() => {
    setFilters((f) => ({ ...f, offset: Math.max(0, (f.offset ?? 0) - (f.limit ?? DEFAULT_LIMIT)) }));
  }, []);

  const handleNext = useCallback(() => {
    setFilters((f) => ({ ...f, offset: (f.offset ?? 0) + (f.limit ?? DEFAULT_LIMIT) }));
  }, []);

  const handleExportCsv = useCallback(() => {
    const list = entriesQuery.data ?? [];
    if (list.length === 0) {
      addToast({
        type: 'info',
        title: t('audit.export_empty', { defaultValue: 'Nothing to export' }),
      });
      return;
    }
    const csv = entriesToCsv(list, userMap);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    triggerDownload(blob, `audit-log-${stamp}.csv`);
  }, [entriesQuery.data, userMap, addToast, t]);

  const activeEntry = useMemo(() => {
    if (!activeId) return null;
    return entriesQuery.data?.find((e) => e.id === activeId) ?? null;
  }, [activeId, entriesQuery.data]);

  /* ── render ─────────────────────────────────────────────────────── */

  const pagerLabel = (entriesQuery.data?.length ?? 0) > 0
    ? t('audit.page_of', {
        defaultValue: 'Showing {{start}}–{{end}}',
        start: pageStart,
        end: pageEnd,
      })
    : t('audit.page_empty', { defaultValue: 'No entries on this page' });

  const PageControls = (
    <div className="flex items-center justify-between gap-2 px-1">
      <span className="text-xs text-content-tertiary">{pagerLabel}</span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={handlePrev}
          disabled={!canPrev}
          aria-label={t('common.prev', { defaultValue: 'Previous page' })}
          className="flex h-8 w-8 items-center justify-center rounded-md border border-border bg-surface-primary text-content-secondary hover:bg-surface-secondary disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <ChevronLeft size={14} />
        </button>
        <button
          type="button"
          onClick={handleNext}
          disabled={!canNext}
          aria-label={t('common.next', { defaultValue: 'Next page' })}
          className="flex h-8 w-8 items-center justify-center rounded-md border border-border bg-surface-primary text-content-secondary hover:bg-surface-secondary disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );

  return (
    <div className="mx-auto max-w-6xl p-4 md:p-6 space-y-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <HistoryIcon size={18} className="text-oe-blue" />
            {t('admin.audit_log_title', { defaultValue: 'Audit Log' })}
          </h1>
          <p className="text-sm text-content-secondary">
            {t('admin.audit_log_subtitle', {
              defaultValue:
                'Read-only timeline of every recorded change. Filter by user, module, action or date — open a row for the full payload.',
            })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={applyFilters}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-primary px-3 py-1.5 text-sm font-medium hover:bg-surface-secondary"
          >
            <Filter size={14} />
            {t('audit.apply_filters', { defaultValue: 'Apply' })}
          </button>
          <button
            type="button"
            onClick={handleExportCsv}
            data-testid="audit-export-csv"
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-primary px-3 py-1.5 text-sm font-medium hover:bg-surface-secondary"
          >
            <Download size={14} />
            {t('audit.export_csv', { defaultValue: 'Export CSV' })}
          </button>
        </div>
      </header>

      <FilterBar
        draft={draft}
        severity={severity}
        users={usersQuery.data}
        onSeverity={setSeverity}
        onChange={setDraft}
        onReset={resetFilters}
      />

      {PageControls}

      <Card>
        {entriesQuery.isLoading ? (
          <div className="divide-y divide-border-light" aria-busy="true">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3 min-h-[56px]">
                <div className="h-5 w-14 rounded-full bg-surface-secondary animate-pulse" />
                <div className="flex-1 space-y-1">
                  <div className="h-3 w-2/3 rounded bg-surface-secondary animate-pulse" />
                  <div className="h-2.5 w-1/3 rounded bg-surface-secondary animate-pulse" />
                </div>
              </div>
            ))}
          </div>
        ) : entriesQuery.isError ? (
          <div className="p-6">
            <EmptyState
              icon={<AlertCircle size={20} />}
              title={t('audit.error_title', { defaultValue: 'Could not load audit log' })}
              description={
                entriesQuery.error instanceof Error
                  ? entriesQuery.error.message
                  : t('audit.error_generic', { defaultValue: 'Please try again or refine the filters.' })
              }
              action={{
                label: t('common.retry', { defaultValue: 'Retry' }),
                onClick: () => void entriesQuery.refetch(),
              }}
            />
          </div>
        ) : filteredEntries.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<HistoryIcon size={20} />}
              title={t('audit.empty_title', { defaultValue: 'No audit entries match these filters' })}
              description={t('audit.empty_desc', {
                defaultValue: 'Adjust the filters above or extend the date range.',
              })}
            />
          </div>
        ) : (
          <div role="list" className="divide-y divide-border-light">
            {filteredEntries.map((entry) => (
              <div role="listitem" key={entry.id}>
                <TimelineRow
                  entry={entry}
                  user={entry.user_id ? userMap.get(entry.user_id) : undefined}
                  onOpen={() => setActiveId(entry.id)}
                />
              </div>
            ))}
          </div>
        )}
      </Card>

      {PageControls}

      {activeEntry && (
        <DetailDrawer
          entry={activeEntry}
          user={activeEntry.user_id ? userMap.get(activeEntry.user_id) : undefined}
          onClose={() => setActiveId(null)}
        />
      )}
    </div>
  );
}

export default AuditLogPage;
