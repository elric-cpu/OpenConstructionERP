// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Wave 4 / T13 — ISO 19650 EIR (Employer Information Requirements) matrix.
//
// Bentley OpenBuildings / Trimble Tilos parity: rows are requirements,
// columns are deliverable types (Model / Drawing / Schedule / Report /
// COBie / PSET), cells are a (LOD, LOI, status) triplet colour-coded
// by status (accepted = green, submitted = amber, missing = red).
// Click a cell → modal to create / edit the deliverable for that
// (requirement, type) pair.
//
// Route: /requirements/matrix  (project chosen via the global
// ProjectContextStore active selector, with ``?project=`` deep-link
// fallback for external links).

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  ClipboardList,
  Filter as FilterIcon,
  Loader2,
  Plus,
  RefreshCw,
} from 'lucide-react';

import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { EmptyState } from '@/shared/ui/EmptyState';
import { WideModal, WideModalSection } from '@/shared/ui/WideModal';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { useToastStore } from '@/stores/useToastStore';
import {
  createDeliverable,
  deleteDeliverable,
  getMatrix,
  updateDeliverable,
  type CreateDeliverablePayload,
  type Deliverable,
  type DeliverableStatus,
  type MatrixCell,
  type MatrixResponse,
  type MatrixRow,
  type UpdateDeliverablePayload,
} from './api';

// ── Constants ──────────────────────────────────────────────────────────

const CANONICAL_TYPES = [
  'model',
  'drawing',
  'schedule',
  'report',
  'cobie',
  'pset',
] as const;

const LOD_OPTIONS = ['100', '200', '300', '350', '400', '500'] as const;
const LOI_OPTIONS = ['1', '2', '3', '4', '5'] as const;

const STATUS_LABEL: Record<DeliverableStatus, string> = {
  accepted: 'Accepted',
  submitted: 'Submitted',
  missing: 'Missing',
};

const TYPE_LABEL: Record<string, string> = {
  model: 'Model',
  drawing: 'Drawing',
  schedule: 'Schedule',
  report: 'Report',
  cobie: 'COBie',
  pset: 'PSET',
  other: 'Other',
};

// Tailwind colour classes per status — heatmap cell background +
// accent border + text. Keeps the matrix scannable at a glance.
const CELL_STYLE: Record<DeliverableStatus, string> = {
  accepted:
    'bg-green-50 border-green-300 text-green-900 hover:bg-green-100 dark:bg-green-900/30 dark:border-green-700 dark:text-green-100 dark:hover:bg-green-900/50',
  submitted:
    'bg-amber-50 border-amber-300 text-amber-900 hover:bg-amber-100 dark:bg-amber-900/30 dark:border-amber-700 dark:text-amber-100 dark:hover:bg-amber-900/50',
  missing:
    'bg-red-50 border-red-200 text-red-700 hover:bg-red-100 dark:bg-red-900/20 dark:border-red-800/60 dark:text-red-300 dark:hover:bg-red-900/40',
};

// ── Coverage chip ───────────────────────────────────────────────────────

interface CoverageChipProps {
  pct: number;
}

function CoverageChip({ pct }: CoverageChipProps) {
  const tone =
    pct >= 80
      ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200'
      : pct >= 50
        ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200'
        : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200';
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
        tone,
      )}
    >
      {pct.toFixed(0)}%
    </span>
  );
}

// ── Cell editor modal ───────────────────────────────────────────────────

interface CellEditorState {
  open: boolean;
  row: MatrixRow | null;
  deliverableType: string;
  cell: MatrixCell | null;
}

interface CellEditorProps {
  state: CellEditorState;
  onClose: () => void;
  onSaved: () => void;
}

function CellEditor({ state, onClose, onSaved }: CellEditorProps) {
  const toast = useToastStore((s) => s.addToast);
  const isEditing = state.cell?.deliverable_id != null;

  const [lod, setLod] = useState<string>(state.cell?.lod ?? '');
  const [loi, setLoi] = useState<string>(state.cell?.loi ?? '');
  const [submittedAt, setSubmittedAt] = useState<string>(
    state.cell?.submitted_at ? state.cell.submitted_at.slice(0, 16) : '',
  );
  const [acceptedAt, setAcceptedAt] = useState<string>(
    state.cell?.accepted_at ? state.cell.accepted_at.slice(0, 16) : '',
  );

  // Reset local state whenever the modal opens with a different cell —
  // otherwise reopening on a new (row, col) keeps stale values.
  useEffect(() => {
    setLod(state.cell?.lod ?? '');
    setLoi(state.cell?.loi ?? '');
    setSubmittedAt(
      state.cell?.submitted_at ? state.cell.submitted_at.slice(0, 16) : '',
    );
    setAcceptedAt(
      state.cell?.accepted_at ? state.cell.accepted_at.slice(0, 16) : '',
    );
  }, [state.open, state.row?.requirement_id, state.deliverableType]);

  const buildPayload = (): CreateDeliverablePayload | UpdateDeliverablePayload => {
    const toIso = (s: string): string | null =>
      s ? new Date(s).toISOString() : null;
    return {
      deliverable_type: state.deliverableType,
      lod: lod || null,
      loi: loi || null,
      submitted_at: toIso(submittedAt),
      accepted_at: toIso(acceptedAt),
    };
  };

  const save = useMutation({
    mutationFn: async () => {
      if (!state.row) return;
      if (isEditing && state.cell?.deliverable_id) {
        await updateDeliverable(
          state.row.requirement_id,
          state.cell.deliverable_id,
          buildPayload() as UpdateDeliverablePayload,
        );
      } else {
        await createDeliverable(
          state.row.requirement_id,
          buildPayload() as CreateDeliverablePayload,
        );
      }
    },
    onSuccess: () => {
      toast({
        type: 'success',
        title: isEditing ? 'Deliverable updated' : 'Deliverable added',
      });
      onSaved();
      onClose();
    },
    onError: (err) => {
      toast({
        type: 'error',
        title: 'Save failed',
        message: (err as Error).message,
      });
    },
  });

  const remove = useMutation({
    mutationFn: async () => {
      if (!state.row || !state.cell?.deliverable_id) return;
      await deleteDeliverable(
        state.row.requirement_id,
        state.cell.deliverable_id,
      );
    },
    onSuccess: () => {
      toast({ type: 'success', title: 'Deliverable removed' });
      onSaved();
      onClose();
    },
    onError: (err) => {
      toast({
        type: 'error',
        title: 'Delete failed',
        message: (err as Error).message,
      });
    },
  });

  if (!state.open || !state.row) return null;

  const typeLabel = TYPE_LABEL[state.deliverableType] ?? state.deliverableType;
  const title = `${typeLabel} — ${state.row.entity}.${state.row.attribute}`;

  return (
    <WideModal
      open={state.open}
      onClose={onClose}
      title={title}
      subtitle={
        isEditing
          ? 'Edit the LOD / LOI and submission timestamps for this EIR deliverable.'
          : 'Attach a new ISO 19650 deliverable to this requirement.'
      }
      size="md"
      busy={save.isPending || remove.isPending}
      footer={
        <>
          {isEditing && (
            <Button
              variant="danger"
              size="md"
              onClick={() => remove.mutate()}
              loading={remove.isPending}
            >
              Remove
            </Button>
          )}
          <Button variant="ghost" size="md" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={() => save.mutate()}
            loading={save.isPending}
          >
            {isEditing ? 'Save' : 'Create'}
          </Button>
        </>
      }
    >
      <WideModalSection title="Level of detail / information" columns={2}>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-content-secondary">LOD (BIMForum)</span>
          <select
            value={lod}
            onChange={(e) => setLod(e.target.value)}
            className="h-9 rounded-md border border-border bg-surface-primary px-2 text-sm"
          >
            <option value="">—</option>
            {LOD_OPTIONS.map((v) => (
              <option key={v} value={v}>
                LOD {v}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-content-secondary">LOI (ISO 19650)</span>
          <select
            value={loi}
            onChange={(e) => setLoi(e.target.value)}
            className="h-9 rounded-md border border-border bg-surface-primary px-2 text-sm"
          >
            <option value="">—</option>
            {LOI_OPTIONS.map((v) => (
              <option key={v} value={v}>
                LOI {v}
              </option>
            ))}
          </select>
        </label>
      </WideModalSection>

      <WideModalSection title="Submission lifecycle" columns={2}>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-content-secondary">Submitted at</span>
          <input
            type="datetime-local"
            value={submittedAt}
            onChange={(e) => setSubmittedAt(e.target.value)}
            className="h-9 rounded-md border border-border bg-surface-primary px-2 text-sm"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-content-secondary">Accepted at</span>
          <input
            type="datetime-local"
            value={acceptedAt}
            onChange={(e) => setAcceptedAt(e.target.value)}
            className="h-9 rounded-md border border-border bg-surface-primary px-2 text-sm"
          />
        </label>
      </WideModalSection>
    </WideModal>
  );
}

// ── Main page ──────────────────────────────────────────────────────────

export function RequirementsMatrixPage() {
  const [params, setParams] = useSearchParams();
  const ctxProjectId = useProjectContextStore((s) => s.activeProjectId);
  const ctxProjectName = useProjectContextStore((s) => s.activeProjectName);
  const projectId = ctxProjectId ?? params.get('project') ?? '';

  const [typeFilter, setTypeFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<DeliverableStatus | ''>('');
  const [editor, setEditor] = useState<CellEditorState>({
    open: false,
    row: null,
    deliverableType: '',
    cell: null,
  });

  // Keep `?project=` in the URL in sync with the active project so the
  // back button + deep-links stay coherent.
  useEffect(() => {
    if (projectId && params.get('project') !== projectId) {
      const next = new URLSearchParams(params);
      next.set('project', projectId);
      setParams(next, { replace: true });
    }
  }, [projectId, params, setParams]);

  const qc = useQueryClient();
  const matrixQuery = useQuery<MatrixResponse>({
    queryKey: ['requirements-matrix', projectId, typeFilter],
    enabled: !!projectId,
    queryFn: () => getMatrix(projectId, typeFilter || undefined),
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['requirements-matrix', projectId] });
  };

  // Apply the status filter client-side: hide rows whose every visible
  // cell falls outside the selected status. (Server already trimmed
  // columns when typeFilter is set.)
  const visibleRows: MatrixRow[] = useMemo(() => {
    if (!matrixQuery.data) return [];
    const cols =
      typeFilter ? [typeFilter] : matrixQuery.data.deliverable_types;
    if (!statusFilter) return matrixQuery.data.rows;
    return matrixQuery.data.rows.filter((row) =>
      cols.some((col) => row.cells[col]?.status === statusFilter),
    );
  }, [matrixQuery.data, typeFilter, statusFilter]);

  const cols =
    matrixQuery.data?.deliverable_types?.length
      ? matrixQuery.data.deliverable_types
      : (CANONICAL_TYPES as readonly string[]);

  // ── Render ────────────────────────────────────────────────────────

  if (!projectId) {
    return (
      <div className="p-6">
        <EmptyState
          icon={<ClipboardList size={32} />}
          title="Select a project"
          description="Pick an active project from the global selector to view its ISO 19650 EIR matrix."
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6">
      {/* Header */}
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-content-primary">
            EIR Matrix
          </h1>
          <p className="text-sm text-content-secondary">
            ISO 19650 Employer Information Requirements coverage for
            {ctxProjectName ? ` ${ctxProjectName}` : ' the selected project'}.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {matrixQuery.data && (
            <div className="flex items-center gap-2 rounded-lg border border-border-light bg-surface-elevated px-3 py-1.5 text-sm">
              <span className="text-content-secondary">Project coverage</span>
              <CoverageChip pct={matrixQuery.data.coverage_pct} />
            </div>
          )}
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} />}
            onClick={refresh}
            disabled={matrixQuery.isFetching}
          >
            Refresh
          </Button>
        </div>
      </header>

      {/* Filters */}
      <Card padding="sm">
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex items-center gap-2 text-sm text-content-secondary">
            <FilterIcon size={14} /> Filters
          </div>
          <label className="flex items-center gap-1.5 text-sm">
            <span className="text-content-secondary">Deliverable</span>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="h-8 rounded-md border border-border bg-surface-primary px-2 text-sm"
            >
              <option value="">All</option>
              {cols.map((t) => (
                <option key={t} value={t}>
                  {TYPE_LABEL[t] ?? t}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-sm">
            <span className="text-content-secondary">Status</span>
            <select
              value={statusFilter}
              onChange={(e) =>
                setStatusFilter(e.target.value as DeliverableStatus | '')
              }
              className="h-8 rounded-md border border-border bg-surface-primary px-2 text-sm"
            >
              <option value="">All</option>
              <option value="accepted">Accepted</option>
              <option value="submitted">Submitted</option>
              <option value="missing">Missing</option>
            </select>
          </label>
          {(typeFilter || statusFilter) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setTypeFilter('');
                setStatusFilter('');
              }}
            >
              Clear
            </Button>
          )}
        </div>
      </Card>

      {/* Matrix */}
      <Card padding="none" className="overflow-hidden">
        {matrixQuery.isLoading ? (
          <div className="flex items-center justify-center p-12 text-content-secondary">
            <Loader2 className="mr-2 animate-spin" size={18} /> Loading matrix…
          </div>
        ) : matrixQuery.isError ? (
          <div className="p-6 text-sm text-red-600">
            Failed to load the EIR matrix:{' '}
            {(matrixQuery.error as Error).message}
          </div>
        ) : visibleRows.length === 0 ? (
          <EmptyState
            icon={<ClipboardList size={28} />}
            title="No requirements"
            description="This project has no requirements yet, or none match the current filters. Use the Requirements module to add some, then return here to attach deliverables."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse">
              <thead className="bg-surface-secondary/60 text-xs uppercase tracking-wider text-content-secondary">
                <tr>
                  <th className="sticky left-0 z-10 bg-surface-secondary/60 px-3 py-2 text-left font-medium">
                    Requirement
                  </th>
                  <th className="px-3 py-2 text-left font-medium">Coverage</th>
                  {cols.map((col) => (
                    <th
                      key={col}
                      className="px-3 py-2 text-left font-medium"
                    >
                      {TYPE_LABEL[col] ?? col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr
                    key={row.requirement_id}
                    className="border-t border-border-light/60"
                  >
                    <td className="sticky left-0 z-10 bg-surface-elevated px-3 py-2 align-top">
                      <div className="font-medium text-content-primary">
                        {row.entity}
                      </div>
                      <div className="text-xs text-content-secondary">
                        {row.attribute}
                        {row.priority && (
                          <span className="ml-1 rounded bg-surface-secondary px-1 py-0.5 text-[10px] uppercase">
                            {row.priority}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 align-middle">
                      <CoverageChip pct={row.coverage_pct} />
                    </td>
                    {cols.map((col) => {
                      const cell = row.cells[col];
                      const status: DeliverableStatus =
                        (cell?.status as DeliverableStatus) ?? 'missing';
                      return (
                        <td key={col} className="px-2 py-2 align-middle">
                          <button
                            type="button"
                            onClick={() =>
                              setEditor({
                                open: true,
                                row,
                                deliverableType: col,
                                cell: cell ?? null,
                              })
                            }
                            className={clsx(
                              'group flex w-full min-w-[120px] flex-col items-start gap-0.5 rounded-lg border px-2.5 py-1.5 text-left text-xs transition',
                              CELL_STYLE[status],
                            )}
                            aria-label={`${TYPE_LABEL[col] ?? col} ${STATUS_LABEL[status]}`}
                          >
                            <span className="font-semibold uppercase tracking-wide">
                              {STATUS_LABEL[status]}
                            </span>
                            <span className="text-[11px] opacity-80">
                              {cell?.lod ? `LOD ${cell.lod}` : 'LOD —'}
                              {' · '}
                              {cell?.loi ? `LOI ${cell.loi}` : 'LOI —'}
                            </span>
                            {!cell?.deliverable_id && (
                              <span className="inline-flex items-center gap-0.5 text-[11px] opacity-70 group-hover:opacity-100">
                                <Plus size={10} /> Add
                              </span>
                            )}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <CellEditor
        state={editor}
        onClose={() =>
          setEditor({
            open: false,
            row: null,
            deliverableType: '',
            cell: null,
          })
        }
        onSaved={refresh}
      />
    </div>
  );
}

// Keep the default export so the lazy loader in App.tsx can map it
// either way (named or default).
export default RequirementsMatrixPage;

// Used by lazy-loader checks — keeps the reference live as a sanity touch
// of every exported binding so dead-code analysers don't drop the named
// helpers (they are imported by the modal sub-component).
export type { Deliverable };
