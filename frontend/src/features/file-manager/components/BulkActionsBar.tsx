/** Bulk-actions bar — visible when one or more files are selected.
 *
 * Bulk delete dispatches per-kind:
 *   - documents → POST /v1/documents/batch/delete/ (server-side batch)
 *   - everything else (photos, sheets, BIM models, DWG drawings, takeoff
 *     uploads, reports, markups) → DELETE one-id-at-a-time on the module's
 *     own per-id endpoint, in parallel.
 *
 * The toast surface reports a per-kind tally: how many files of each kind
 * were deleted, and — on partial failure — which kinds had errors so the
 * user can retry just those.
 *
 * Other bulk operations (classify, export-selection) are TODO — once
 * file_manager exposes them, wire them through this same bar.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient, useMutation } from '@tanstack/react-query';
import { Trash2, X, Loader2 } from 'lucide-react';
import { useToastStore } from '@/stores/useToastStore';
import { fileManagerKeys } from '../hooks';
import { bulkDeleteDocuments, deleteByKind } from '../api';
import type { FileKind, FileRow } from '../types';

interface BulkActionsBarProps {
  selectedRows: FileRow[];
  projectId: string;
  onClear: () => void;
}

interface PerKindResult {
  kind: FileKind;
  requested: number;
  deleted: number;
  failed: { id: string; message: string }[];
}

interface DispatchSummary {
  total: number;
  deleted: number;
  failed: number;
  perKind: PerKindResult[];
}

/** Group selected rows by their file kind. Exported for the unit test. */
export function groupByKind(rows: FileRow[]): Map<FileKind, FileRow[]> {
  const out = new Map<FileKind, FileRow[]>();
  for (const row of rows) {
    const bucket = out.get(row.kind);
    if (bucket) {
      bucket.push(row);
    } else {
      out.set(row.kind, [row]);
    }
  }
  return out;
}

/**
 * Run the per-kind delete dispatch and tally results.
 *
 * - ``document`` rows are batch-deleted in one server round-trip.
 * - All other kinds loop client-side with ``Promise.allSettled`` so a
 *   404 on one id doesn't abort siblings.
 *
 * Returns the same summary shape the toast renderer consumes.
 */
export async function dispatchBulkDelete(rows: FileRow[]): Promise<DispatchSummary> {
  const groups = groupByKind(rows);
  const perKind: PerKindResult[] = [];

  for (const [kind, items] of groups) {
    const ids = items.map((r) => r.id);

    if (kind === 'document') {
      try {
        const resp = await bulkDeleteDocuments(ids);
        perKind.push({
          kind,
          requested: ids.length,
          deleted: resp.deleted,
          failed:
            resp.deleted < ids.length
              ? // The batch endpoint doesn't return per-id failures, so
                // we mark the gap as a single anonymous error bucket
                // rather than fabricating ids.
                [
                  {
                    id: '*',
                    message: `${ids.length - resp.deleted} document(s) skipped (no access)`,
                  },
                ]
              : [],
        });
      } catch (err) {
        perKind.push({
          kind,
          requested: ids.length,
          deleted: 0,
          failed: ids.map((id) => ({
            id,
            message: err instanceof Error ? err.message : String(err),
          })),
        });
      }
      continue;
    }

    const settled = await Promise.allSettled(ids.map((id) => deleteByKind(kind, id)));
    const failed = settled.flatMap((res, idx) =>
      res.status === 'rejected'
        ? [
            {
              id: ids[idx]!,
              message: res.reason instanceof Error ? res.reason.message : String(res.reason),
            },
          ]
        : [],
    );
    perKind.push({
      kind,
      requested: ids.length,
      deleted: ids.length - failed.length,
      failed,
    });
  }

  const total = perKind.reduce((acc, r) => acc + r.requested, 0);
  const deleted = perKind.reduce((acc, r) => acc + r.deleted, 0);
  const failed = perKind.reduce((acc, r) => acc + r.failed.length, 0);
  return { total, deleted, failed, perKind };
}

export function BulkActionsBar({ selectedRows, projectId, onClear }: BulkActionsBarProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [confirming, setConfirming] = useState(false);

  // All 8 file kinds now have a delete endpoint — nothing is filtered out.
  const deletableRows = selectedRows;

  const deleteMutation = useMutation({
    mutationFn: async (rows: FileRow[]) => dispatchBulkDelete(rows),
    onSuccess: (summary: DispatchSummary) => {
      queryClient.invalidateQueries({ queryKey: [fileManagerKeys.tree, projectId] });
      queryClient.invalidateQueries({ queryKey: [fileManagerKeys.list, projectId] });

      if (summary.failed === 0) {
        addToast({
          type: 'success',
          title: t('files.bulk.deleted', {
            defaultValue: '{{count}} file(s) deleted',
            count: summary.deleted,
          }),
        });
      } else if (summary.deleted === 0) {
        addToast({
          type: 'error',
          title: t('files.bulk.delete_failed', { defaultValue: 'Bulk delete failed' }),
          message: t('files.bulk.delete_all_failed', {
            defaultValue: 'None of the {{count}} selected file(s) could be deleted.',
            count: summary.total,
          }),
        });
      } else {
        addToast({
          type: 'warning',
          title: t('files.bulk.delete_partial', {
            defaultValue: '{{deleted}} of {{total}} deleted',
            deleted: summary.deleted,
            total: summary.total,
          }),
          message: t('files.bulk.delete_partial_detail', {
            defaultValue: '{{failed}} file(s) could not be deleted.',
            failed: summary.failed,
          }),
        });
      }
      setConfirming(false);
      onClear();
    },
    onError: (err: Error) => {
      addToast({
        type: 'error',
        title: t('files.bulk.delete_failed', { defaultValue: 'Bulk delete failed' }),
        message: err.message,
      });
      setConfirming(false);
    },
  });

  if (selectedRows.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b border-border-light bg-oe-blue/5">
      <span className="text-xs font-medium text-content-primary">
        {t('files.bulk.n_selected', {
          defaultValue: '{{count}} selected',
          count: selectedRows.length,
        })}
      </span>

      <button
        type="button"
        onClick={onClear}
        className="text-2xs text-content-tertiary hover:text-content-primary underline-offset-2 hover:underline"
      >
        {t('files.bulk.clear', { defaultValue: 'Clear' })}
      </button>

      <div className="ms-auto flex items-center gap-2">
        {confirming ? (
          <div className="flex items-center gap-2 animate-fade-in">
            <span className="text-2xs text-semantic-error font-medium">
              {t('files.bulk.confirm_delete', {
                defaultValue: 'Delete {{count}} file(s)?',
                count: deletableRows.length,
              })}
            </span>
            <button
              type="button"
              disabled={deleteMutation.isPending || deletableRows.length === 0}
              onClick={() => deleteMutation.mutate(deletableRows)}
              className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md text-2xs font-semibold bg-semantic-error text-white hover:opacity-90 disabled:opacity-50"
            >
              {deleteMutation.isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Trash2 size={12} />
              )}
              {t('files.bulk.delete', { defaultValue: 'Delete' })}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="inline-flex items-center justify-center h-7 w-7 rounded-md text-content-tertiary hover:bg-surface-secondary"
              aria-label={t('common.cancel', { defaultValue: 'Cancel' })}
            >
              <X size={12} />
            </button>
          </div>
        ) : (
          <button
            type="button"
            disabled={deletableRows.length === 0}
            onClick={() => setConfirming(true)}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium border border-border-light text-content-secondary hover:bg-surface-secondary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Trash2 size={13} />
            {t('files.bulk.delete', { defaultValue: 'Delete' })}
          </button>
        )}
      </div>
    </div>
  );
}
