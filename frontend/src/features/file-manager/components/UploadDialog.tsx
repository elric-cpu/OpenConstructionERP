// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** Upload dialog — multi-file uploader for the file manager.
 *
 * Routes each upload to the endpoint that owns its kind so files land in
 * the right pipeline instead of all becoming generic documents:
 *   - BIM models (RVT / IFC / …) → POST /api/v1/bim/upload-cad/
 *   - DWG / DXF drawings        → POST /api/v1/dwg/drawings/upload/
 *   - everything else           → POST /api/v1/documents/upload/
 * The dedicated BIM/DWG endpoints stream the body server-side, so a large
 * model still uploads safely; only the documents path uses the resumable
 * chunked client (which assembles into the document store). Completed
 * uploads roll up into the same FloatingQueuePanel used everywhere else.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { UploadCloud, X, FileUp } from 'lucide-react';
import clsx from 'clsx';
import { uuid } from '@/shared/lib/browser';
import { useToastStore } from '@/stores/useToastStore';
import { useAuthStore } from '@/stores/useAuthStore';
import { useUploadQueueStore } from '@/stores/useUploadQueueStore';
import { fileManagerKeys } from '../hooks';
import { uploadResumable, RESUMABLE_THRESHOLD_BYTES } from '../resumableUpload';
import type { FileKind } from '../types';

interface UploadDialogProps {
  open: boolean;
  projectId: string;
  defaultKind: FileKind | null;
  onClose: () => void;
}

export function UploadDialog({
  open,
  projectId,
  defaultKind,
  onClose,
}: UploadDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const addQueueTask = useUploadQueueStore((s) => s.addTask);
  const updateQueueTask = useUploadQueueStore((s) => s.updateTask);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Map FileKind → documents-module category. Used only by the documents
  // pipeline (the kinds that don't have a dedicated endpoint); BIM/DWG
  // route to their own modules below.
  const categoryForKind = useCallback((kind: FileKind | null): string => {
    if (kind === 'photo') return 'photo';
    if (kind === 'sheet') return 'drawing';
    return 'other';
  }, []);

  // Resolve where a kind's upload should go. ``bim_model`` and
  // ``dwg_drawing`` have their own ingest endpoints (and their own
  // storage + conversion pipelines); everything else stays on the
  // documents endpoint. The dedicated endpoints take a single ``file``
  // multipart field plus a ``project_id`` query param and stream the body
  // server-side, so they don't use the resumable chunked client.
  const directUploadUrl = useCallback(
    (kind: FileKind | null): string | null => {
      if (kind === 'bim_model') {
        return `/api/v1/bim/upload-cad/?project_id=${projectId}`;
      }
      if (kind === 'dwg_drawing') {
        return `/api/v1/dwg/drawings/upload/?project_id=${projectId}`;
      }
      if (kind === 'photo') {
        // Site photos go to the photo pipeline so a real ProjectPhoto is
        // created (single-shot, server-side; category defaults to "site").
        // Uploading via the generic documents endpoint only made a
        // category="photo" Document, which never surfaced as a site picture
        // in the Photos tab, gallery, site diary, dashboard or photo strip.
        return `/api/v1/documents/photos/upload/?project_id=${projectId}`;
      }
      return null;
    },
    [projectId],
  );

  // Lock background scroll when modal is open.
  useEffect(() => {
    if (!open) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = original;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  const doUpload = useCallback(
    async (files: FileList | File[]) => {
      if (!projectId) {
        addToast({
          type: 'error',
          title: t('files.upload_no_project', { defaultValue: 'No active project' }),
        });
        return;
      }

      const fileArray = Array.from(files);
      if (fileArray.length === 0) return;

      const validFiles = fileArray;
      if (validFiles.length === 0) return;

      const token = useAuthStore.getState().accessToken;
      const cat = categoryForKind(defaultKind);
      // Non-null for BIM/DWG kinds → upload goes straight to that module's
      // ingest endpoint (single-shot, server-streamed) instead of the
      // documents pipeline / resumable client.
      const directUrl = directUploadUrl(defaultKind);
      setUploading(true);

      for (const file of validFiles) {
        const taskId = uuid();
        addQueueTask({
          id: taskId,
          type: 'file_upload',
          filename: file.name,
          status: 'processing',
          progress: 0,
          message: t('files.uploading', { defaultValue: 'Uploading…' }),
        });

        // Fire-and-forget — same pattern as DocumentsPage so progress
        // shows up in the global FloatingQueuePanel.
        (async () => {
          const markDone = () => {
            updateQueueTask(taskId, {
              status: 'completed',
              progress: 100,
              message: t('files.uploaded', { defaultValue: 'Uploaded' }),
              completedAt: Date.now(),
            });
            queryClient.invalidateQueries({ queryKey: [fileManagerKeys.tree, projectId] });
            queryClient.invalidateQueries({ queryKey: [fileManagerKeys.list, projectId] });
            if (defaultKind === 'photo') {
              // A site photo also feeds the ProjectPhoto-backed surfaces (photo
              // strip, Site Photos gallery, site diary, dashboard). Refresh any
              // query keyed on photos so the picture shows without a reload.
              queryClient.invalidateQueries({
                predicate: (q) =>
                  q.queryKey.some(
                    (k) => typeof k === 'string' && k.toLowerCase().includes('photo'),
                  ),
              });
            }
          };
          const markError = (detail: string) => {
            updateQueueTask(taskId, {
              status: 'error',
              error: detail,
              completedAt: Date.now(),
            });
          };

          // Large files take the resumable, chunked path: real progress and
          // automatic per-chunk retry so a flaky connection no longer
          // restarts the whole transfer from zero. Small files keep the
          // simpler single-shot multipart upload below. The resumable client
          // assembles into the documents store, so it's only valid for
          // documents kinds - BIM/DWG always take the single-shot path to
          // their own endpoint (which streams server-side regardless of size).
          if (!directUrl && file.size >= RESUMABLE_THRESHOLD_BYTES) {
            try {
              updateQueueTask(taskId, {
                message: t('files.uploading_chunked', {
                  defaultValue: 'Uploading large file…',
                }),
              });
              await uploadResumable(file, {
                projectId,
                category: cat,
                onProgress: (percent) => updateQueueTask(taskId, { progress: percent }),
              });
              markDone();
            } catch (err) {
              markError(
                err instanceof Error
                  ? err.message
                  : t('files.upload_resume_failed', {
                      defaultValue: 'Upload interrupted. Try again to resume.',
                    }),
              );
            }
            return;
          }

          try {
            const formData = new FormData();
            formData.append('file', file);

            const headers: Record<string, string> = { 'X-DDC-Client': 'OE/1.0' };
            if (token) headers['Authorization'] = `Bearer ${token}`;

            // Estimate progress so the user gets feedback while the
            // upload is still in flight.
            const estimatedMs = Math.max(2000, (file.size / (1024 * 1024)) * 500);
            const progressTimer = setInterval(() => {
              const task = useUploadQueueStore.getState().tasks.find((tk) => tk.id === taskId);
              if (task && task.status === 'processing' && task.progress < 90) {
                updateQueueTask(taskId, { progress: task.progress + 5 });
              }
            }, estimatedMs / 18);

            const res = await fetch(
              directUrl ??
                `/api/v1/documents/upload/?project_id=${projectId}&category=${cat}`,
              { method: 'POST', headers, body: formData },
            );

            clearInterval(progressTimer);

            if (!res.ok) {
              let detail = file.name;
              try {
                const body = await res.json();
                if (body?.detail) detail = body.detail;
              } catch {
                /* ignore — keep filename */
              }
              markError(detail);
            } else {
              markDone();
            }
          } catch (err) {
            markError(err instanceof Error ? err.message : 'Upload failed');
          }
        })();
      }

      addToast({
        type: 'info',
        title: t('files.upload_queued', {
          defaultValue: '{{count}} file(s) queued',
          count: validFiles.length,
        }),
      });

      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
      onClose();
    },
    [
      projectId,
      defaultKind,
      categoryForKind,
      directUploadUrl,
      addToast,
      addQueueTask,
      updateQueueTask,
      queryClient,
      t,
      onClose,
    ],
  );

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t('files.upload', { defaultValue: 'Upload files' })}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-lg animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg mx-4 rounded-xl bg-surface-elevated shadow-2xl border border-border-light overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-border-light">
          <h3 className="text-sm font-semibold text-content-primary">
            {t('files.upload', { defaultValue: 'Upload files' })}
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close', { defaultValue: 'Close' })}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-content-tertiary hover:bg-surface-secondary hover:text-content-primary"
          >
            <X size={14} />
          </button>
        </div>

        <div className="p-5">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files && e.target.files.length > 0) {
                void doUpload(e.target.files);
              }
            }}
          />

          <div
            role="button"
            tabIndex={0}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={(e) => {
              e.preventDefault();
              setDragOver(false);
            }}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              if (e.dataTransfer.files.length > 0) void doUpload(e.dataTransfer.files);
            }}
            className={clsx(
              'flex flex-col items-center justify-center text-center cursor-pointer',
              'rounded-xl border-2 border-dashed py-10 px-6 transition-all',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue focus-visible:ring-offset-1',
              dragOver
                ? 'border-oe-blue bg-oe-blue/5 scale-[1.005] shadow-md'
                : 'border-border-medium bg-gradient-to-br from-blue-50/60 via-transparent to-violet-50/40 dark:from-blue-950/20 dark:to-violet-950/20 hover:border-oe-blue/50',
            )}
          >
            <div
              className={clsx(
                'mb-3 flex h-14 w-14 items-center justify-center rounded-xl transition-all',
                dragOver
                  ? 'bg-oe-blue/15'
                  : 'bg-gradient-to-br from-oe-blue/10 to-violet-500/10',
              )}
            >
              <UploadCloud size={26} className="text-oe-blue" />
            </div>
            <p className="text-sm font-semibold text-content-primary">
              {dragOver
                ? t('files.upload_drop_here', { defaultValue: 'Drop files to upload' })
                : t('files.upload_drag', { defaultValue: 'Drag & drop files here' })}
            </p>
            <p className="mt-1 text-xs text-content-tertiary">
              {t('files.upload_hint', {
                defaultValue: 'PDF, images, Excel, DWG, IFC - any file type',
              })}
            </p>
            <button
              type="button"
              disabled={uploading}
              onClick={(e) => {
                e.stopPropagation();
                fileInputRef.current?.click();
              }}
              className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold bg-oe-blue text-white hover:bg-oe-blue-hover shadow-sm transition-colors disabled:opacity-60"
            >
              <FileUp size={14} />
              {t('files.upload_browse', { defaultValue: 'Browse files' })}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
