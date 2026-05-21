/**
 * Permissions Matrix — read-only governance view of the RBAC engine.
 *
 * Rows are roles (Viewer / Editor / Manager / Admin), columns are
 * permission keys grouped under each module. Cells render one of three
 * states:
 *
 *   • check  — role has the permission (role-level ≥ min_role).
 *   • cross  — role is below the permission's min_role.
 *   • lock   — admin-only by design (min_role is admin).
 *
 * Everything here is read-only on purpose. The brief explicitly defers
 * edit-mode, role inheritance UI and custom-role builder to a later
 * pass — getting visibility first is the priority because today the
 * mapping lives only in the backend `PermissionRegistry` and isn't
 * inspectable from the UI at all.
 *
 * Backend: `GET /api/v1/admin/permissions/matrix` (audit.view, Manager+).
 */

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import clsx from 'clsx';
import {
  Check,
  ChevronDown,
  ChevronRight,
  Lock,
  Search,
  ShieldCheck,
  X as XIcon,
} from 'lucide-react';
import { Card, EmptyState } from '@/shared/ui';
import { SkeletonTable } from '@/shared/ui/SkeletonLoader';
import { useToastStore } from '@/stores/useToastStore';
import {
  cellState,
  fetchPermissionsMatrix,
  type MatrixCellState,
  type MatrixRole,
  type PermissionsMatrix,
} from './api';

/** Lowercase-and-trim normaliser so the search filter is forgiving. */
function normalise(s: string): string {
  return s.trim().toLowerCase();
}

interface CellProps {
  state: MatrixCellState;
  role: MatrixRole;
  minRole: MatrixRole;
  permissionKey: string;
  tooltip: string;
}

function MatrixCell({ state, role, permissionKey, tooltip }: CellProps) {
  const className = clsx(
    'flex items-center justify-center w-9 h-9 mx-auto rounded-md transition-colors',
    state === 'allowed' && 'text-emerald-600 bg-emerald-50 hover:bg-emerald-100',
    state === 'denied' && 'text-rose-500 bg-rose-50 hover:bg-rose-100',
    state === 'admin-bypass' && 'text-amber-700 bg-amber-50 hover:bg-amber-100',
  );
  const icon =
    state === 'allowed' ? (
      <Check size={16} aria-hidden />
    ) : state === 'admin-bypass' ? (
      <Lock size={14} aria-hidden />
    ) : (
      <XIcon size={16} aria-hidden />
    );
  return (
    <div
      className={className}
      title={tooltip}
      data-testid={`cell-${role}-${permissionKey}`}
      data-state={state}
      aria-label={tooltip}
    >
      {icon}
    </div>
  );
}

interface ModuleRowsProps {
  module: PermissionsMatrix['modules'][number];
  roles: MatrixRole[];
  hierarchy: Record<string, number>;
  hoveredRole: MatrixRole | null;
  query: string;
  collapsed: boolean;
  onToggle: () => void;
  t: ReturnType<typeof useTranslation>['t'];
}

function ModuleRows({
  module,
  roles,
  hierarchy,
  hoveredRole,
  query,
  collapsed,
  onToggle,
  t,
}: ModuleRowsProps) {
  const filteredPerms = useMemo(() => {
    const q = normalise(query);
    if (!q) return module.permissions;
    return module.permissions.filter(
      (p) => normalise(p.key).includes(q) || normalise(module.name).includes(q),
    );
  }, [module, query]);

  if (filteredPerms.length === 0) return null;

  return (
    <>
      {/* Module header row — clickable to expand/collapse */}
      <tr className="bg-surface-secondary/60 sticky-col-group">
        <th
          scope="rowgroup"
          colSpan={roles.length + 1}
          className="px-3 py-2 text-left text-sm font-semibold text-text-primary"
        >
          <button
            type="button"
            onClick={onToggle}
            className="flex items-center gap-2 hover:text-accent-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary rounded"
            data-testid={`module-toggle-${module.name}`}
            aria-expanded={!collapsed}
          >
            {collapsed ? (
              <ChevronRight size={16} aria-hidden />
            ) : (
              <ChevronDown size={16} aria-hidden />
            )}
            <span className="font-mono">{module.name}</span>
            <span className="text-xs text-text-tertiary font-normal">
              {t('admin.permissions.module_count', {
                count: filteredPerms.length,
                defaultValue: '{{count}} permission_other',
              })}
            </span>
          </button>
        </th>
      </tr>

      {/* Permission rows */}
      {!collapsed &&
        filteredPerms.map((perm) => (
          <tr
            key={perm.key}
            className="border-b border-border-light last:border-0 hover:bg-surface-secondary/30"
          >
            <th
              scope="row"
              className={clsx(
                'sticky left-0 z-10 bg-surface-elevated px-3 py-2 text-left text-sm font-mono text-text-secondary',
                'border-r border-border-light',
              )}
            >
              <span className="block truncate max-w-[280px]" title={perm.key}>
                {perm.key}
              </span>
              <span className="block text-[10px] uppercase tracking-wider text-text-tertiary">
                {t('admin.permissions.min_role_label', {
                  defaultValue: 'min',
                })}
                : {perm.min_role}
              </span>
            </th>
            {roles.map((role) => {
              const state = cellState(role, perm.min_role, hierarchy);
              const tooltip =
                state === 'allowed'
                  ? t('admin.permissions.tooltip_allowed', {
                      defaultValue:
                        '{{role}} can {{key}} (min role: {{min}})',
                      role,
                      key: perm.key,
                      min: perm.min_role,
                    })
                  : state === 'admin-bypass'
                  ? t('admin.permissions.tooltip_admin_bypass', {
                      defaultValue:
                        'Admin-only by design — {{key}} requires admin',
                      key: perm.key,
                    })
                  : t('admin.permissions.tooltip_denied', {
                      defaultValue:
                        '{{role}} cannot {{key}} (min role: {{min}})',
                      role,
                      key: perm.key,
                      min: perm.min_role,
                    });
              return (
                <td
                  key={role}
                  className={clsx(
                    'px-2 py-2 text-center transition-colors',
                    hoveredRole === role && 'bg-accent-primary/10',
                  )}
                >
                  <MatrixCell
                    state={state}
                    role={role}
                    minRole={perm.min_role}
                    permissionKey={perm.key}
                    tooltip={tooltip}
                  />
                </td>
              );
            })}
          </tr>
        ))}
    </>
  );
}

export function PermissionsMatrixPage() {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const [query, setQuery] = useState('');
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [hoveredRole, setHoveredRole] = useState<MatrixRole | null>(null);

  const {
    data,
    isLoading,
    error,
    isError,
  } = useQuery<PermissionsMatrix>({
    queryKey: ['admin', 'permissions-matrix'],
    queryFn: fetchPermissionsMatrix,
    retry: false,
    staleTime: 60_000,
  });

  // Surface fetch errors as a toast (single fire per error message — the
  // user can still see the in-page error panel if they dismiss the toast).
  useEffect(() => {
    if (!isError) return;
    const message =
      error instanceof Error
        ? error.message
        : t('admin.permissions.error_unknown', { defaultValue: 'Failed to load permissions matrix' });
    addToast(
      {
        type: 'error',
        title: t('admin.permissions.error_title', { defaultValue: 'Permissions matrix' }),
        message,
      },
      { duration: 6000 },
    );
  }, [isError, error, addToast, t]);

  // Visible modules + permission counts after applying the search query.
  const visibleStats = useMemo(() => {
    if (!data) return { modules: 0, permissions: 0 };
    const q = normalise(query);
    let modules = 0;
    let permissions = 0;
    for (const m of data.modules) {
      const matches = q
        ? m.permissions.filter(
            (p) => normalise(p.key).includes(q) || normalise(m.name).includes(q),
          ).length
        : m.permissions.length;
      if (matches > 0) {
        modules += 1;
        permissions += matches;
      }
    }
    return { modules, permissions };
  }, [data, query]);

  if (isLoading) {
    return (
      <div className="p-4" data-testid="permissions-matrix-loading">
        <SkeletonTable rows={8} columns={5} />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-4">
        <EmptyState
          icon={<ShieldCheck className="text-rose-500" size={48} aria-hidden />}
          title={t('admin.permissions.error_title', {
            defaultValue: 'Could not load permissions matrix',
          })}
          description={
            error instanceof Error
              ? error.message
              : t('admin.permissions.error_unknown', {
                  defaultValue: 'Unknown error',
                })
          }
        />
      </div>
    );
  }

  if (!data || data.modules.length === 0) {
    return (
      <div className="p-4">
        <EmptyState
          icon={<ShieldCheck size={48} aria-hidden />}
          title={t('admin.permissions.empty_title', {
            defaultValue: 'No permissions registered',
          })}
          description={t('admin.permissions.empty_description', {
            defaultValue:
              'No modules have registered permissions yet. They appear here as soon as a module loads.',
          })}
        />
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4" data-testid="permissions-matrix-page">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold text-text-primary">
          {t('admin.permissions.title', { defaultValue: 'Permissions Matrix' })}
        </h1>
        <p className="text-sm text-text-secondary max-w-3xl">
          {t('admin.permissions.subtitle', {
            defaultValue:
              'Read-only view of every permission registered by every module, and which roles can use it. Admin always passes — locked cells indicate admin-only by design.',
          })}
        </p>
        <div className="flex items-center gap-4 flex-wrap">
          <div className="relative flex-1 min-w-[240px] max-w-md">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none"
              aria-hidden
            />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('admin.permissions.search_placeholder', {
                defaultValue: 'Filter by module or permission key',
              })}
              aria-label={t('admin.permissions.search_label', {
                defaultValue: 'Search permissions',
              })}
              data-testid="permissions-matrix-search"
              className="w-full pl-9 pr-3 py-2 text-sm border border-border-light rounded-md bg-surface-elevated focus:outline-none focus:ring-2 focus:ring-accent-primary"
            />
          </div>
          <div className="text-xs text-text-tertiary">
            {t('admin.permissions.summary', {
              defaultValue: '{{modules}} modules · {{permissions}} permissions',
              modules: visibleStats.modules,
              permissions: visibleStats.permissions,
            })}
          </div>
        </div>
      </header>

      <Card className="overflow-x-auto p-0">
        <table
          className="w-full text-sm border-collapse"
          data-testid="permissions-matrix-table"
        >
          <thead>
            <tr className="bg-surface-secondary border-b border-border-light">
              <th
                scope="col"
                className="sticky left-0 z-20 bg-surface-secondary px-3 py-2 text-left text-xs uppercase tracking-wider text-text-tertiary border-r border-border-light min-w-[260px]"
              >
                {t('admin.permissions.col_permission', {
                  defaultValue: 'Permission',
                })}
              </th>
              {data.roles.map((role) => (
                <th
                  key={role}
                  scope="col"
                  className={clsx(
                    'px-3 py-2 text-center text-xs uppercase tracking-wider transition-colors cursor-default',
                    hoveredRole === role
                      ? 'bg-accent-primary/10 text-accent-primary'
                      : 'text-text-tertiary',
                  )}
                  onMouseEnter={() => setHoveredRole(role)}
                  onMouseLeave={() => setHoveredRole(null)}
                  onFocus={() => setHoveredRole(role)}
                  onBlur={() => setHoveredRole(null)}
                  data-testid={`role-header-${role}`}
                  tabIndex={0}
                >
                  {t(`admin.permissions.role_${role}`, {
                    defaultValue: role,
                  })}
                  <div className="text-[10px] font-normal normal-case text-text-tertiary">
                    {role}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.modules.map((module) => (
              <ModuleRows
                key={module.name}
                module={module}
                roles={data.roles}
                hierarchy={data.role_hierarchy}
                hoveredRole={hoveredRole}
                query={query}
                collapsed={!!collapsed[module.name]}
                onToggle={() =>
                  setCollapsed((prev) => ({
                    ...prev,
                    [module.name]: !prev[module.name],
                  }))
                }
                t={t}
              />
            ))}
          </tbody>
        </table>
      </Card>

      <footer className="text-xs text-text-tertiary flex items-center gap-4 flex-wrap">
        <span className="inline-flex items-center gap-1">
          <Check size={14} className="text-emerald-600" aria-hidden />
          {t('admin.permissions.legend_allowed', { defaultValue: 'allowed' })}
        </span>
        <span className="inline-flex items-center gap-1">
          <XIcon size={14} className="text-rose-500" aria-hidden />
          {t('admin.permissions.legend_denied', { defaultValue: 'denied' })}
        </span>
        <span className="inline-flex items-center gap-1">
          <Lock size={12} className="text-amber-700" aria-hidden />
          {t('admin.permissions.legend_admin_bypass', {
            defaultValue: 'admin-only by design',
          })}
        </span>
      </footer>
    </div>
  );
}

export default PermissionsMatrixPage;
