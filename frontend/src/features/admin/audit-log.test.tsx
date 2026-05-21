// @ts-nocheck
/**
 * Tests for the Audit Log admin page:
 *   - URL construction for the `listAuditEntries` filter set
 *   - RTL render with mocked API: row visible, drawer opens on click
 *
 * Network calls are stubbed via `vi.mock('./api', …)` so the test runs
 * fully offline. React Query retries are disabled so errors surface
 * synchronously (matches the BIM AssetsPage test convention).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { buildAuditListUrl, type AuditEntry } from './api';

/* ── api stub ──────────────────────────────────────────────────────── */

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>();
  return {
    ...actual,
    listAuditEntries: vi.fn(),
    getAuditDetail: vi.fn(),
  };
});

vi.mock('@/features/users/api', () => ({
  fetchUsers: vi.fn(),
}));

import { listAuditEntries } from './api';
import { fetchUsers } from '@/features/users/api';
import { AuditLogPage } from './AuditLogPage';

const sampleEntry: AuditEntry = {
  id: 'audit-1',
  action: 'update',
  entity_type: 'boq',
  entity_id: '11111111-2222-3333-4444-555555555555',
  user_id: 'user-1',
  ip_address: '10.0.0.5',
  details: { before: { quantity: 10 }, after: { quantity: 12 } },
  created_at: '2026-05-15T09:30:00Z',
};

const sampleUsers = [
  {
    id: 'user-1',
    email: 'estimator@example.com',
    full_name: 'Maya Estimator',
    role: 'manager' as const,
    locale: 'en',
    is_active: true,
    last_login_at: null,
    timezone: 'UTC',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

function renderWithProviders() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/audit-log']}>
        <AuditLogPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

/* ── URL construction ──────────────────────────────────────────────── */

describe('buildAuditListUrl', () => {
  it('returns the bare path when no filters are supplied', () => {
    expect(buildAuditListUrl()).toBe('/v1/audit');
  });

  it('omits null and empty values', () => {
    const url = buildAuditListUrl({
      userId: null,
      entityType: '',
      action: null,
      limit: undefined,
    });
    expect(url).toBe('/v1/audit');
  });

  it('uses user_id_filter alias for the user filter', () => {
    const url = buildAuditListUrl({ userId: 'abc-123' });
    expect(url).toBe('/v1/audit?user_id_filter=abc-123');
  });

  it('serialises the full filter set with stable encoding', () => {
    const url = buildAuditListUrl({
      userId: 'u1',
      entityType: 'boq',
      action: 'update',
      dateFrom: '2026-05-01T00:00:00Z',
      dateTo: '2026-05-31T23:59:59Z',
      limit: 25,
      offset: 50,
    });
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('entity_type')).toBe('boq');
    expect(params.get('action')).toBe('update');
    expect(params.get('user_id_filter')).toBe('u1');
    expect(params.get('date_from')).toBe('2026-05-01T00:00:00Z');
    expect(params.get('date_to')).toBe('2026-05-31T23:59:59Z');
    expect(params.get('limit')).toBe('25');
    expect(params.get('offset')).toBe('50');
  });

  it('keeps offset=0 distinct from an absent offset', () => {
    const url = buildAuditListUrl({ offset: 0 });
    // offset=0 must round-trip — otherwise a fresh first page would
    // become "no offset", and refetches would drop the explicit reset.
    expect(url).toContain('offset=0');
  });
});

/* ── render + drawer ────────────────────────────────────────────────── */

describe('AuditLogPage', () => {
  it('renders a timeline row from the API and opens the drawer on click', async () => {
    (listAuditEntries as ReturnType<typeof vi.fn>).mockResolvedValue([sampleEntry]);
    (fetchUsers as ReturnType<typeof vi.fn>).mockResolvedValue(sampleUsers);

    renderWithProviders();

    // Row appears once the query resolves.
    const row = await screen.findByTestId('audit-row');
    expect(row).toBeInTheDocument();
    expect(row).toHaveTextContent('update');
    expect(row).toHaveTextContent('boq');
    // Actor name is resolved through the users map.
    expect(row).toHaveTextContent('Maya Estimator');

    // Drawer is closed by default.
    expect(screen.queryByTestId('audit-drawer')).not.toBeInTheDocument();

    fireEvent.click(row);

    // Drawer renders with the diff sections.
    await waitFor(() => {
      expect(screen.getByTestId('audit-drawer')).toBeInTheDocument();
    });
    const drawer = screen.getByTestId('audit-drawer');
    expect(drawer).toHaveTextContent('update');
    expect(drawer).toHaveTextContent('boq');
    // Both before/after blobs are serialised into the JSON panels.
    expect(drawer.textContent).toContain('"quantity": 10');
    expect(drawer.textContent).toContain('"quantity": 12');
  });
});
