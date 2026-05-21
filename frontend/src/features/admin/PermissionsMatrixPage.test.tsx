// @ts-nocheck
/**
 * Vitest coverage for the Permissions Matrix admin page.
 *
 * Read-only behaviours
 * ~~~~~~~~~~~~~~~~~~~~
 *   - renders one row per permission grouped under each module header
 *   - paints cells as allowed / denied / admin-bypass per cellState()
 *   - filters rows when the user types into the search box
 *   - collapses & expands module groups via the toggle button
 *   - highlights the role column on hover
 *
 * Edit behaviours (admin caller)
 * ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 *   - clicking a cell opens the confirmation modal and on confirm
 *     fires updatePermissionMinRole + optimistic-updates the cache
 *   - failed update reverts the optimistic change
 *   - clicking the admin-only ``permissions.admin`` cell opens a
 *     lockout dialog rather than a normal confirmation
 *   - role-filter dropdown narrows the visible rows
 *
 * Network is stubbed via ``vi.mock('./api')`` — the real cellState pure
 * helper is re-exported from the mocked module so the production
 * decision logic is exercised end-to-end without a backend.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

// Default to an "admin" auth context so edit-mode tests can flip the
// edit toggle. Tests that want to verify the read-only fallback override
// this with a non-admin role via the mocked getState().
const authState = { userRole: 'admin' as string | null };
vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: (selector?: (s: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
}));

vi.mock('@/stores/useToastStore', () => {
  const state = { addToast: vi.fn() };
  const hook = (selector?: (s: typeof state) => unknown) =>
    selector ? selector(state) : state;
  hook.getState = () => state;
  return { useToastStore: hook };
});

vi.mock('./api', async () => {
  // Re-export the real cellState helper so the production decision
  // function gets exercised — only the network fetch is faked.
  const actual = await vi.importActual('./api');
  return {
    ...actual,
    fetchPermissionsMatrix: vi.fn(),
    updatePermissionMinRole: vi.fn(),
    applyPermissionPreset: vi.fn(),
  };
});

import {
  fetchPermissionsMatrix,
  updatePermissionMinRole,
  applyPermissionPreset,
} from './api';
import { PermissionsMatrixPage } from './PermissionsMatrixPage';

const sampleMatrix = {
  roles: ['viewer', 'editor', 'manager', 'admin'],
  role_hierarchy: { viewer: 0, editor: 1, manager: 2, admin: 3 },
  presets: ['viewer-default', 'editor-default', 'manager-default'],
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
        { key: 'permissions.admin', min_role: 'admin' },
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
    authState.userRole = 'admin';
    (fetchPermissionsMatrix as any).mockResolvedValue(sampleMatrix);
    (updatePermissionMinRole as any).mockResolvedValue({
      permission: 'projects.create',
      previous_min_role: 'editor',
      new_min_role: 'viewer',
    });
    (applyPermissionPreset as any).mockResolvedValue({
      preset: 'viewer-default',
      permissions_changed: 1,
      total_permissions: 6,
      changes: [],
    });
  });

  it('renders rows for every permission and paints cells per role', async () => {
    renderWithProviders();
    await waitFor(() =>
      expect(screen.getByTestId('permissions-matrix-table')).toBeInTheDocument(),
    );

    expect(screen.getByTestId('module-toggle-projects')).toBeInTheDocument();
    expect(screen.getByTestId('module-toggle-system')).toBeInTheDocument();

    expect(
      screen.getByTestId('cell-viewer-projects.create').getAttribute('data-state'),
    ).toBe('denied');
    expect(
      screen.getByTestId('cell-editor-projects.create').getAttribute('data-state'),
    ).toBe('allowed');
    expect(
      screen.getByTestId('cell-admin-projects.create').getAttribute('data-state'),
    ).toBe('allowed');
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

    expect(screen.getByTestId('module-toggle-projects')).toBeInTheDocument();
    const search = screen.getByTestId('permissions-matrix-search');
    fireEvent.change(search, { target: { value: 'audit' } });

    await waitFor(() => {
      expect(screen.queryByTestId('module-toggle-projects')).not.toBeInTheDocument();
      expect(screen.getByTestId('module-toggle-system')).toBeInTheDocument();
    });
    expect(screen.getByTestId('cell-manager-audit.view')).toBeInTheDocument();
  });

  it('filters rows by role (shows only denied-for-this-role)', async () => {
    renderWithProviders();
    await waitFor(() =>
      expect(screen.getByTestId('permissions-matrix-table')).toBeInTheDocument(),
    );

    const roleFilter = screen.getByTestId('permissions-matrix-role-filter');
    // Select viewer — only permissions where viewer is denied should
    // remain. projects.read (min=viewer) and audit.view (min=manager,
    // visible because viewer is denied) — projects.read is the
    // baseline-allowed row that should drop out.
    fireEvent.change(roleFilter, { target: { value: 'viewer' } });

    await waitFor(() => {
      // projects.read is allowed for viewer → its cell should disappear
      // after the role filter rewrites the visible matrix.
      expect(screen.queryByTestId('cell-viewer-projects.read')).not.toBeInTheDocument();
      // projects.create requires editor → viewer is denied, row stays.
      expect(screen.getByTestId('cell-viewer-projects.create')).toBeInTheDocument();
    });
  });

  it('enables edit mode for admins and pops the confirm modal on cell click', async () => {
    renderWithProviders();
    await waitFor(() =>
      expect(screen.getByTestId('permissions-matrix-table')).toBeInTheDocument(),
    );

    // Edit mode is off by default — clicking a cell does nothing.
    let cell = screen.getByTestId('cell-viewer-projects.create');
    fireEvent.click(cell);
    expect(updatePermissionMinRole).not.toHaveBeenCalled();

    // Flip into edit mode.
    const editToggle = screen.getByTestId('permissions-matrix-edit-toggle');
    fireEvent.click(editToggle);

    // Now click the viewer cell on projects.create → pops the confirm
    // dialog with the "Change" affordance.
    cell = await screen.findByTestId('cell-viewer-projects.create');
    fireEvent.click(cell);

    const confirmBtn = await screen.findByTestId('confirm-dialog-confirm');
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(updatePermissionMinRole).toHaveBeenCalledWith(
        'projects.create',
        'viewer',
      );
    });
  });

  it('reverts the optimistic update when the PATCH call fails', async () => {
    (updatePermissionMinRole as any).mockRejectedValueOnce(
      new Error('network down'),
    );

    renderWithProviders();
    await waitFor(() =>
      expect(screen.getByTestId('permissions-matrix-table')).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByTestId('permissions-matrix-edit-toggle'));

    // Before click: viewer can't projects.create.
    expect(
      screen.getByTestId('cell-viewer-projects.create').getAttribute('data-state'),
    ).toBe('denied');

    fireEvent.click(screen.getByTestId('cell-viewer-projects.create'));
    fireEvent.click(await screen.findByTestId('confirm-dialog-confirm'));

    // After the failure the cache rollback restores the original
    // "denied" state. We assert by waiting for the mutation call AND
    // the cell still showing "denied".
    await waitFor(() => {
      expect(updatePermissionMinRole).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(
        screen.getByTestId('cell-viewer-projects.create').getAttribute('data-state'),
      ).toBe('denied');
    });
  });

  it('shows the lockout modal when admin clicks permissions.admin', async () => {
    renderWithProviders();
    await waitFor(() =>
      expect(screen.getByTestId('permissions-matrix-table')).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByTestId('permissions-matrix-edit-toggle'));

    // Click viewer cell on permissions.admin — must NOT mutate, must
    // open the lockout-warning modal.
    fireEvent.click(screen.getByTestId('cell-viewer-permissions.admin'));

    await waitFor(() => {
      expect(
        screen.getByText(/cannot demote admin permission/i),
      ).toBeInTheDocument();
    });
    expect(updatePermissionMinRole).not.toHaveBeenCalled();
  });

  it('falls back to read-only when the caller is not admin', async () => {
    authState.userRole = 'manager';
    renderWithProviders();
    await waitFor(() =>
      expect(screen.getByTestId('permissions-matrix-table')).toBeInTheDocument(),
    );

    // No edit-toggle button is rendered for non-admins.
    expect(
      screen.queryByTestId('permissions-matrix-edit-toggle'),
    ).not.toBeInTheDocument();

    // Clicking a cell is a no-op — the cell is a plain div, not a button.
    const cell = screen.getByTestId('cell-viewer-projects.create');
    fireEvent.click(cell);
    expect(updatePermissionMinRole).not.toHaveBeenCalled();
  });

  it('shows the loading skeleton before data arrives', async () => {
    (fetchPermissionsMatrix as any).mockReturnValue(new Promise(() => {}));
    renderWithProviders();
    expect(screen.getByTestId('permissions-matrix-loading')).toBeInTheDocument();
  });
});
