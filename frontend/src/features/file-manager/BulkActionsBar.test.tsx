// @ts-nocheck
/**
 * Unit tests for the bulk-delete dispatcher in ``BulkActionsBar``.
 *
 * Covers:
 *   1. ``groupByKind`` partitions rows by ``file.kind``.
 *   2. ``dispatchBulkDelete`` routes each kind to its module's delete
 *      endpoint (documents → batch, others → per-id loop).
 *   3. Partial failure (some kinds 200, others 404/403) flows through to
 *      a "warning" summary toast — full success → "success", full
 *      failure → "error".
 *
 * The dispatcher's only external dependencies are ``bulkDeleteDocuments``
 * and ``deleteByKind`` from ``./api``. We mock those directly — testing
 * the live ``fetch`` pipeline is covered by the integration tests for
 * each module's delete endpoint.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

/* ── API layer mock — what the dispatcher actually calls ───────────── */

vi.mock('./api', () => {
  return {
    bulkDeleteDocuments: vi.fn(async (ids: string[]) => ({
      requested: ids.length,
      deleted: ids.length,
    })),
    deleteByKind: vi.fn(async (_kind: string, _id: string) => undefined),
    deletePathForKind: (kind: string, id: string) => `/v1/${kind}/${id}`,
  };
});

import * as api from './api';
const bulkDeleteDocumentsMock = api.bulkDeleteDocuments as unknown as ReturnType<typeof vi.fn>;
const deleteByKindMock = api.deleteByKind as unknown as ReturnType<typeof vi.fn>;

import {
  BulkActionsBar,
  dispatchBulkDelete,
  groupByKind,
} from './components/BulkActionsBar';
import type { FileKind, FileRow } from './types';

/* ── Toast spy ─────────────────────────────────────────────────────── */

vi.mock('@/stores/useToastStore', () => {
  const addToast = vi.fn();
  return {
    useToastStore: Object.assign(
      (selector: (s: { addToast: typeof addToast }) => unknown) => selector({ addToast }),
      { getState: () => ({ addToast }) },
    ),
    __addToast: addToast,
  };
});

import * as toastMod from '@/stores/useToastStore';
const addToastSpy = (toastMod as unknown as { __addToast: ReturnType<typeof vi.fn> }).__addToast;

/* ── i18n stub ─────────────────────────────────────────────────────── */

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const fallback = (opts?.defaultValue as string) ?? key;
      // tiny {{var}} substitution so we can assert on toast text
      return fallback.replace(/\{\{(\w+)\}\}/g, (_, name) =>
        opts && opts[name] !== undefined ? String(opts[name]) : `{{${name}}}`,
      );
    },
  }),
}));

/* ── Fixtures ──────────────────────────────────────────────────────── */

function row(id: string, kind: FileKind): FileRow {
  return {
    id,
    kind,
    name: `${kind}-${id}.bin`,
    project_id: 'proj-001',
    size_bytes: 1024,
    mime_type: null,
    extension: null,
    modified_at: null,
    physical_path: '/tmp/x',
    relative_path: 'x',
    storage_backend: 'local',
    download_url: null,
    preview_url: null,
    thumbnail_url: null,
    discipline: null,
    category: null,
    extra: {},
  };
}

/* ── Call recorders driven by the mocked api module ────────────────── */

let docBatchCalls: { ids: string[] }[] = [];
let photoDeleteIds: string[] = [];
let bimDeleteIds: string[] = [];
let reportDeleteIds: string[] = [];
let photoFailIds = new Set<string>();

function resetApiMocks() {
  bulkDeleteDocumentsMock.mockReset();
  deleteByKindMock.mockReset();

  bulkDeleteDocumentsMock.mockImplementation(async (ids: string[]) => {
    docBatchCalls.push({ ids });
    return { requested: ids.length, deleted: ids.length };
  });

  deleteByKindMock.mockImplementation(async (kind: string, id: string) => {
    if (kind === 'photo') {
      if (photoFailIds.has(id)) {
        throw new Error('Not found');
      }
      photoDeleteIds.push(id);
      return;
    }
    if (kind === 'bim_model') {
      bimDeleteIds.push(id);
      return;
    }
    if (kind === 'report') {
      reportDeleteIds.push(id);
      return;
    }
  });
}

resetApiMocks();

afterEach(() => {
  docBatchCalls = [];
  photoDeleteIds = [];
  bimDeleteIds = [];
  reportDeleteIds = [];
  photoFailIds = new Set();
  addToastSpy.mockClear();
  resetApiMocks();
  cleanup();
});

/* ── groupByKind ───────────────────────────────────────────────────── */

describe('groupByKind', () => {
  it('partitions rows by their kind', () => {
    const groups = groupByKind([
      row('a', 'document'),
      row('b', 'photo'),
      row('c', 'document'),
      row('d', 'bim_model'),
    ]);
    expect(groups.get('document')?.map((r) => r.id)).toEqual(['a', 'c']);
    expect(groups.get('photo')?.map((r) => r.id)).toEqual(['b']);
    expect(groups.get('bim_model')?.map((r) => r.id)).toEqual(['d']);
  });
});

/* ── dispatchBulkDelete ────────────────────────────────────────────── */

describe('dispatchBulkDelete', () => {
  it('routes documents via batch and other kinds via per-id DELETE', async () => {
    const rows = [row('d1', 'document'), row('d2', 'document'), row('p1', 'photo')];
    const summary = await dispatchBulkDelete(rows);

    expect(docBatchCalls).toHaveLength(1);
    expect(docBatchCalls[0]!.ids).toEqual(['d1', 'd2']);
    expect(photoDeleteIds).toEqual(['p1']);
    expect(summary.total).toBe(3);
    expect(summary.deleted).toBe(3);
    expect(summary.failed).toBe(0);
  });

  it('records per-id failures from a partial 404 without aborting siblings', async () => {
    photoFailIds = new Set(['p2']);
    const rows = [row('p1', 'photo'), row('p2', 'photo'), row('m1', 'bim_model')];
    const summary = await dispatchBulkDelete(rows);

    expect(photoDeleteIds).toEqual(['p1']); // p2 rejected
    expect(bimDeleteIds).toEqual(['m1']);
    expect(summary.total).toBe(3);
    expect(summary.deleted).toBe(2);
    expect(summary.failed).toBe(1);
    const photoResult = summary.perKind.find((r) => r.kind === 'photo');
    expect(photoResult?.failed).toHaveLength(1);
    expect(photoResult?.failed[0]!.id).toBe('p2');
  });
});

/* ── BulkActionsBar component-level partial-failure toast ──────────── */

function renderBar(rows: FileRow[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <BulkActionsBar selectedRows={rows} projectId="proj-001" onClear={() => {}} />
    </QueryClientProvider>,
  );
}

describe('BulkActionsBar — partial failure summary toast', () => {
  it('emits a warning toast with succeeded/failed counts when one kind 404s', async () => {
    photoFailIds = new Set(['p2']);
    renderBar([row('p1', 'photo'), row('p2', 'photo'), row('r1', 'report')]);

    // Two-step confirm: open the inline confirm, then click Delete.
    fireEvent.click(screen.getAllByRole('button', { name: /^Delete$/ })[0]!);
    fireEvent.click(screen.getByRole('button', { name: /^Delete$/ }));

    await waitFor(() => {
      expect(addToastSpy).toHaveBeenCalled();
    });

    const lastCall = addToastSpy.mock.calls.at(-1)![0];
    expect(lastCall.type).toBe('warning');
    expect(lastCall.title).toMatch(/2 of 3 deleted/);
    expect(lastCall.message).toMatch(/1 file\(s\) could not be deleted/);
  });
});
