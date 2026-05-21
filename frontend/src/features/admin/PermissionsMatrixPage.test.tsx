// @ts-nocheck
/**
 * Vitest coverage for the Permissions Matrix admin page.
 *
 * Verifies that with a fixture payload from
 * ``GET /v1/admin/permissions/matrix`` the page:
 *   - renders one row per permission grouped under each module header
 *   - paints cells as allowed / denied / admin-bypass per the
 *     cellState() decision function
 *   - filters rows when the user types into the search box
 *   - collapses & expands module groups via the toggle button
 *   - highlights the role column on hover (added class on <th> + cell)
 *
 * Network is stubbed via ``vi.mock('./api')`` — the real cellState pure
 * helper is re-exported from the mocked module so the production
 * decision logic is exercised end-to-end without a backend.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('./api', async () => {
  // Re-export the real cellState helper so the production decision
  // function gets exercised — only the network fetch is faked.
  const actual = await vi.importActual('./api');
  return {
    ...actual,
    fetchPermissionsMatrix: vi.fn(),
  };
});

import { fetchPermissionsMatrix } from './api';
import { PermissionsMatrixPage } from './PermissionsMatrixPage';

const sampleMatrix = {
  roles: ['viewer', 'editor', 'manager', 'admin'],
  role_hierarchy: { viewer: 0, editor: 1, manager: 2, admin: 3 },
  modules: [
    {
      name: 'projects',
      permissions: [
        { key: 'projects.create', min_role: 'editor' },
        { key: 'projects.delete', min_role: 'manager' },
        { key: 'projects.read', min_role: 'viewer' },
      ],
    },
    {
      name: 'system',
      permissions: [
        { key: 'system.settings.write', min_role: 'admin' },
        { key: 'audit.view', min_role: 'manager' },
      ],
    },
  ],
};

function renderWithProviders() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/permissions']}>
        <PermissionsMatrixPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PermissionsMatrixPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (fetchPermissionsMatrix as any).mockResolvedValue(sampleMatrix);
  });

  it('renders rows for every permission and paints cells per role', async () => {
    renderWithProviders();
    await waitFor(() =>
      expect(screen.getByTestId('permissions-matrix-table')).toBeInTheDocument(),
    );

    // Module headers are clickable toggle buttons.
    expect(screen.getByTestId('module-toggle-projects')).toBeInTheDocument();
    expect(screen.getByTestId('module-toggle-system')).toBeInTheDocument();

    // Cell states for a few representative (role, permission) pairs.
    // projects.create requires editor — viewer is denied, editor allowed,
    // manager allowed, admin allowed.
    expect(
      screen.getByTestId('cell-viewer-projects.create').getAttribute('data-state'),
    ).toBe('denied');
    expect(
      screen.getByTestId('cell-editor-projects.create').getAttribute('data-state'),
    ).toBe('allowed');
    expect(
      screen.getByTestId('cell-admin-projects.create').getAttribute('data-state'),
    ).toBe('allowed');

    // system.settings.write requires admin — admin renders as the
    // admin-bypass lock state (admin AND min_role is admin).
    expect(
      screen.getByTestId('cell-admin-system.settings.write').getAttribute('data-state'),
    ).toBe('admin-bypass');
    expect(
      screen.getByTestId('cell-viewer-system.settings.write').getAttribute('data-state'),
    ).toBe('denied');
  });

  it('filters rows based on the search input', async () => {
    renderWithProviders();
    await waitFor(() =>
      expect(screen.getByTestId('permissions-matrix-table')).toBeInTheDocument(),
    );

    // Pre-filter: both modules visible.
    expect(screen.getByTestId('module-toggle-projects')).toBeInTheDocument();
    expect(screen.getByTestId('module-toggle-system')).toBeInTheDocument();

    const search = screen.getByTestId('permissions-matrix-search');
    fireEvent.change(search, { target: { value: 'audit' } });

    // After typing "audit", only the system module (which has audit.view)
    // should remain. The projects module no longer matches and is
    // hidden by ModuleRows returning null.
    await waitFor(() => {
      expect(screen.queryByTestId('module-toggle-projects')).not.toBeInTheDocument();
      expect(screen.getByTestId('module-toggle-system')).toBeInTheDocument();
    });

    // The matching permission row still renders.
    expect(screen.getByTestId('cell-manager-audit.view')).toBeInTheDocument();
  });

  it('collapses and re-expands a module group', async () => {
    renderWithProviders();
    await waitFor(() =>
      expect(screen.getByTestId('permissions-matrix-table')).toBeInTheDocument(),
    );

    // Initially expanded: projects.create cell rendered.
    expect(screen.getByTestId('cell-viewer-projects.create')).toBeInTheDocument();

    // Collapse the projects group.
    const toggle = screen.getByTestId('module-toggle-projects');
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(
        screen.queryByTestId('cell-viewer-projects.create'),
      ).not.toBeInTheDocument();
    });

    // The toggle button itself remains visible so the user can reopen.
    expect(screen.getByTestId('module-toggle-projects')).toBeInTheDocument();

    // Re-expand.
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(
        screen.getByTestId('cell-viewer-projects.create'),
      ).toBeInTheDocument();
    });
  });

  it('highlights a role column when the header is hovered', async () => {
    renderWithProviders();
    await waitFor(() =>
      expect(screen.getByTestId('permissions-matrix-table')).toBeInTheDocument(),
    );

    const managerHeader = screen.getByTestId('role-header-manager');
    // Before hover: the active hover class is absent.
    expect(managerHeader.className).not.toMatch(/bg-accent-primary/);

    fireEvent.mouseEnter(managerHeader);
    await waitFor(() => {
      expect(managerHeader.className).toMatch(/bg-accent-primary/);
    });

    fireEvent.mouseLeave(managerHeader);
    await waitFor(() => {
      expect(managerHeader.className).not.toMatch(/bg-accent-primary/);
    });
  });

  it('shows the loading skeleton before data arrives', async () => {
    // Re-mock with a never-resolving promise to keep the page in loading.
    (fetchPermissionsMatrix as any).mockReturnValue(new Promise(() => {}));
    renderWithProviders();
    expect(screen.getByTestId('permissions-matrix-loading')).toBeInTheDocument();
  });
});
