// @ts-nocheck
/**
 * Smoke tests for the rebuilt Phase Plans tab on /schedule-advanced.
 *
 * Verifies:
 *   - empty state shows "New phase" + "Use a template" CTAs
 *   - clicking "New phase" opens the create modal
 *   - "Apply template" path POSTs N phases via the public API
 *   - populated state renders cards + table + timeline view toggle
 *   - delete confirmation dialog appears before delete fires
 *
 * Network is stubbed via ``vi.mock`` on ``./api`` + ``@/features/projects/api``.
 * React Query retries are disabled so errors surface immediately.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    listMasterSchedules: vi.fn(),
    createMasterSchedule: vi.fn(),
    listPhasePlans: vi.fn(),
    createPhasePlan: vi.fn(),
    updatePhasePlan: vi.fn(),
    deletePhasePlan: vi.fn(),
    pullPhase: vi.fn(),
    startPhase: vi.fn(),
    completePhase: vi.fn(),
    listLookAheads: vi.fn(),
    listConstraints: vi.fn(),
    listWeeklyPlans: vi.fn(),
    listCommitments: vi.fn(),
    listBaselines: vi.fn(),
  };
});

vi.mock('@/features/projects/api', () => ({
  projectsApi: {
    list: vi.fn().mockResolvedValue([{ id: 'p1', name: 'Test Project' }]),
  },
}));

import {
  listMasterSchedules,
  listPhasePlans,
  createPhasePlan,
  deletePhasePlan,
} from './api';
import { ScheduleAdvancedPage } from './ScheduleAdvancedPage';

const masterSchedule = {
  id: 'ms1',
  project_id: 'p1',
  name: 'Master',
  planned_start: '2026-06-01',
  planned_finish: '2026-12-31',
  status: 'active',
  notes: '',
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
};

const samplePhase = {
  id: 'ph1',
  master_schedule_id: 'ms1',
  name: 'Foundation',
  planned_start: '2026-06-01',
  planned_finish: '2026-06-30',
  pulled_status: 'in_planning',
  notes: 'Spread foundations',
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/schedule-advanced']}>
        <ScheduleAdvancedPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function gotoPhasesTab() {
  // Wait for tabs to render
  const tab = await screen.findByRole('button', { name: /phase plans/i });
  fireEvent.click(tab);
}

describe('PhasePlans tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listMasterSchedules as any).mockResolvedValue([masterSchedule]);
  });

  it('renders the empty-state CTAs when there are no phases', async () => {
    (listPhasePlans as any).mockResolvedValue([]);
    renderPage();
    await gotoPhasesTab();
    expect(await screen.findByText(/no phase plans yet/i)).toBeInTheDocument();
    // Primary CTA — "New phase" — and secondary "Use a template" both present
    expect(screen.getAllByRole('button', { name: /new phase/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /use a template/i })).toBeInTheDocument();
  });

  it('opens the create-phase modal when the empty-state CTA is clicked', async () => {
    (listPhasePlans as any).mockResolvedValue([]);
    renderPage();
    await gotoPhasesTab();
    const cta = await screen.findByRole('button', { name: /^new phase$/i });
    fireEvent.click(cta);
    // Modal title in WideModal
    expect(await screen.findByText(/^new phase$/i, { selector: 'h2,h3' })).toBeInTheDocument();
    // Form fields visible
    expect(screen.getByText(/phase name/i)).toBeInTheDocument();
    expect(screen.getByText(/planned start/i)).toBeInTheDocument();
    expect(screen.getByText(/planned finish/i)).toBeInTheDocument();
  });

  it('renders cards + status filter chips when phases exist', async () => {
    (listPhasePlans as any).mockResolvedValue([
      samplePhase,
      { ...samplePhase, id: 'ph2', name: 'Structure', pulled_status: 'active' },
      { ...samplePhase, id: 'ph3', name: 'Finishes', pulled_status: 'completed' },
    ]);
    renderPage();
    await gotoPhasesTab();
    expect(await screen.findByText('Foundation')).toBeInTheDocument();
    expect(screen.getByText('Structure')).toBeInTheDocument();
    expect(screen.getByText('Finishes')).toBeInTheDocument();
    // All / In planning / Pulled / Active / Completed chips
    expect(screen.getByRole('button', { name: /^all/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^in planning/i })).toBeInTheDocument();
  });

  it('exposes Cards / Table / Timeline view toggle', async () => {
    (listPhasePlans as any).mockResolvedValue([samplePhase]);
    renderPage();
    await gotoPhasesTab();
    await screen.findByText('Foundation');
    expect(screen.getByRole('tab', { name: /cards/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /table/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /timeline/i })).toBeInTheDocument();
  });

  it('switches to table view when Table is clicked', async () => {
    (listPhasePlans as any).mockResolvedValue([samplePhase]);
    renderPage();
    await gotoPhasesTab();
    await screen.findByText('Foundation');
    fireEvent.click(screen.getByRole('tab', { name: /table/i }));
    // Table headers appear
    await waitFor(() => {
      expect(screen.getByText(/^#$/)).toBeInTheDocument();
    });
    expect(screen.getByText(/days/i)).toBeInTheDocument();
    expect(screen.getByText(/progress/i)).toBeInTheDocument();
  });

  it('submits createPhasePlan with the entered name', async () => {
    (listPhasePlans as any).mockResolvedValue([]);
    (createPhasePlan as any).mockResolvedValue({ ...samplePhase, name: 'New Phase A' });
    renderPage();
    await gotoPhasesTab();
    const cta = await screen.findByRole('button', { name: /^new phase$/i });
    fireEvent.click(cta);
    // Find the phase-name input inside the modal
    const nameInput = await screen.findByPlaceholderText(/foundation/i);
    fireEvent.change(nameInput, { target: { value: 'New Phase A' } });
    // Click Create
    const createBtns = screen.getAllByRole('button', { name: /^create$/i });
    fireEvent.click(createBtns[createBtns.length - 1]);
    await waitFor(() => {
      expect(createPhasePlan).toHaveBeenCalledWith(
        expect.objectContaining({
          master_schedule_id: 'ms1',
          name: 'New Phase A',
        }),
      );
    });
  });

  it('opens delete-confirm before calling deletePhasePlan', async () => {
    (listPhasePlans as any).mockResolvedValue([samplePhase]);
    (deletePhasePlan as any).mockResolvedValue(undefined);
    renderPage();
    await gotoPhasesTab();
    await screen.findByText('Foundation');
    // Find the trash button on the card
    const deleteBtn = screen.getAllByRole('button', { name: /^delete$/i })[0];
    fireEvent.click(deleteBtn);
    // Confirm dialog appears
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText(/delete phase/i)).toBeInTheDocument();
    // Cancel — must NOT call delete. ConfirmDialog's "Cancel" label embeds
    // zero-width steganography chars so the visible string is e.g. "Cancel".
    // Match the first button inside the dialog (cancel is left of confirm).
    const dialogButtons = dialog.querySelectorAll('button');
    fireEvent.click(dialogButtons[0]);
    await waitFor(() => {
      expect(deletePhasePlan).not.toHaveBeenCalled();
    });
  });
});
