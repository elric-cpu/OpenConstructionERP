/** Right rail showing details of the currently-focused file. */

import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Download, Mail, FolderOpen, Copy, X, FileText, Image as ImageIcon, Layout, Box, Pencil, File, PenTool, FileBarChart, Tag, ExternalLink, Activity, Share2, Lock } from 'lucide-react';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import { useToastStore } from '@/stores/useToastStore';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { apiGet } from '@/shared/lib/api';
import type { FileRow, FileKind } from '../types';
import { isTauri, openInOSFinder, copyToClipboard } from '../lib/tauri';
import { modulesForKind, primaryModule } from '../kindModule';
import { ActivityDrawer } from './ActivityDrawer';

const KIND_ICON: Record<FileKind, typeof FileText> = {
  document: FileText,
  photo: ImageIcon,
  sheet: Layout,
  bim_model: Box,
  dwg_drawing: Pencil,
  takeoff: Tag,
  report: FileBarChart,
  markup: PenTool,
};

interface FilePreviewPaneProps {
  row: FileRow | null;
  onClose: () => void;
  onEmail: (row: FileRow) => void;
  onShare?: (row: FileRow) => void;
  /** Owner-only: opens FolderPermissionsModal scoped to this row's kind. */
  onManageAccess?: (row: FileRow) => void;
}

function fmtBytes(bytes: number): string {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

/* Inline preview probe — relies on file extension first (cheap, exact)
   and falls back to mime sniff for documents uploaded without a .pdf
   suffix. The native browser PDF viewer renders via <iframe>; we drop
   the chrome with #toolbar=0&navpanes=0&view=FitH so the pane reads as
   a thumbnail rather than a full reader. */
function isPdf(row: FileRow): boolean {
  if (row.extension && row.extension.toLowerCase().replace(/^\./, '') === 'pdf') return true;
  if (row.mime_type && row.mime_type.toLowerCase() === 'application/pdf') return true;
  return false;
}

export function FilePreviewPane({ row, onClose, onEmail, onShare, onManageAccess }: FilePreviewPaneProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const addToast = useToastStore((s) => s.addToast);
  const [pathCopied, setPathCopied] = useState(false);
  // Slide-over drawer with the full audit timeline. Opens on demand so
  // we don't fire the activity request for every previewed file —
  // unlike the inline ``ActivityLogSection`` below which renders a
  // compact "last few events" strip eagerly.
  const [activityOpen, setActivityOpen] = useState(false);

  if (!row) {
    return (
      <aside className="w-80 shrink-0 border-l border-border-light bg-surface-secondary/40 flex items-center justify-center">
        <p className="text-xs text-content-tertiary px-4 text-center">
          {t('files.preview.empty', {
            defaultValue: 'Select a file to see details.',
          })}
        </p>
      </aside>
    );
  }

  const Icon = KIND_ICON[row.kind] ?? File;
  // Primary tool for this file's extension (e.g. PDF → PDF Takeoff,
  // IFC → BIM Viewer, DWG → DWG Takeoff). Falls back to the kind's
  // default module when the extension isn't in the override map.
  const primary = primaryModule(row.kind, row.extension);
  const allModules = modulesForKind(row.kind);
  const PrimaryIcon = primary.icon;
  // `row` is narrowed by the `if (!row) return` guard above, but TS
  // doesn't carry that narrowing into nested function declarations —
  // capture it in a const so closures see the non-null type.
  const file = row;

  function navigateToModule(target: typeof primary) {
    navigate(target.route(file.project_id, file.id));
  }

  async function handleCopyPath() {
    if (!row) return;
    const ok = await copyToClipboard(row.physical_path);
    if (ok) {
      setPathCopied(true);
      setTimeout(() => setPathCopied(false), 1500);
    } else {
      addToast({
        type: 'error',
        title: t('files.toast.copy_failed', { defaultValue: 'Could not copy path' }),
      });
    }
  }

  const extras = Object.entries(row.extra ?? {}).filter(
    ([, v]) => v !== null && v !== undefined && v !== '',
  );

  return (
    <aside className="w-80 shrink-0 border-l border-border-light bg-surface-elevated overflow-y-auto">
      <div className="sticky top-0 z-10 flex items-center justify-between px-4 py-2.5 border-b border-border-light bg-surface-elevated">
        <span className="text-xs font-semibold text-content-primary truncate">
          {t('files.preview.title', { defaultValue: 'File details' })}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('common.close', { defaultValue: 'Close' })}
          className="flex h-6 w-6 items-center justify-center rounded text-content-tertiary hover:bg-surface-secondary hover:text-content-primary"
        >
          <X size={14} />
        </button>
      </div>

      <div className="p-4 space-y-4">
        <div className="flex items-center justify-center overflow-hidden bg-surface-secondary/60 rounded-lg aspect-[4/3]">
          {isPdf(row) && row.download_url ? (
            <iframe
              src={`${row.download_url}#toolbar=0&navpanes=0&view=FitH`}
              title={row.name}
              className="h-full w-full border-0 rounded-lg"
              loading="lazy"
            />
          ) : row.thumbnail_url ? (
            <img
              src={row.thumbnail_url}
              alt=""
              className="max-h-full max-w-full object-contain rounded-lg"
            />
          ) : (
            <Icon size={48} strokeWidth={1.5} className="text-content-tertiary" />
          )}
        </div>

        <div>
          <h3 className="text-sm font-semibold text-content-primary break-words" title={row.name}>
            {row.name}
          </h3>
          <p className="mt-0.5 text-2xs text-content-tertiary">
            {fmtBytes(row.size_bytes)}
            {row.mime_type && <span className="ms-2">{row.mime_type}</span>}
          </p>
        </div>

        <div className="flex flex-col gap-1.5">
          {/* Primary action — opens this file in its native module. PDFs
              go to PDF Takeoff or Documents Viewer; IFC/RVT to BIM
              Viewer; DWG to DWG Takeoff. Falls back to download below
              when the user just wants the bytes. */}
          <button
            type="button"
            onClick={() => navigateToModule(primary)}
            className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold bg-oe-blue text-white hover:bg-oe-blue-hover transition-colors"
            title={t(primary.descriptionI18nKey, { defaultValue: primary.description })}
          >
            <PrimaryIcon size={13} strokeWidth={2.25} />
            {t('files.actions.open_in', {
              defaultValue: 'Open in {{module}}',
              module: t(primary.i18nKey, { defaultValue: primary.label }),
            })}
            <ExternalLink size={11} className="opacity-80" />
          </button>

          {/* Secondary modules — same file, different tool (e.g. a PDF
              also opens in Documents Viewer; an IFC also feeds BIM
              Rules). Skipped when there's only one possibility. */}
          {allModules.length > 1 && (
            <div className="flex flex-wrap gap-1.5 pt-0.5">
              {allModules
                .filter((m) => m.label !== primary.label)
                .map((m) => {
                  const MIcon = m.icon;
                  return (
                    <button
                      key={m.label}
                      type="button"
                      onClick={() => navigateToModule(m)}
                      className={clsx(
                        'inline-flex items-center gap-1 h-6 px-2 rounded-md text-[10.5px] font-medium transition-colors',
                        'border border-border-light text-content-secondary',
                        'hover:border-oe-blue/40 hover:text-oe-blue hover:bg-oe-blue/5',
                      )}
                      title={t(m.descriptionI18nKey, { defaultValue: m.description })}
                    >
                      <MIcon size={10} strokeWidth={2} />
                      {t(m.i18nKey, { defaultValue: m.label })}
                    </button>
                  );
                })}
            </div>
          )}

          {row.download_url && (
            <a
              href={row.download_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium border border-border-light text-content-primary hover:bg-surface-secondary transition-colors"
            >
              <Download size={13} />
              {t('files.actions.download', { defaultValue: 'Download' })}
            </a>
          )}
          <button
            type="button"
            onClick={() => onEmail(row)}
            className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium border border-border-light text-content-primary hover:bg-surface-secondary transition-colors"
          >
            <Mail size={13} />
            {t('files.actions.email', { defaultValue: 'Email link' })}
          </button>
          {onShare && row.kind === 'document' && (
            <button
              type="button"
              onClick={() => onShare(row)}
              data-testid="file-share-button"
              className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium border border-border-light text-content-primary hover:bg-surface-secondary transition-colors"
            >
              <Share2 size={13} />
              {t('files.actions.share', { defaultValue: 'Share' })}
            </button>
          )}
          {/* Activity drawer trigger — visible for any file kind, but
              the drawer itself gracefully renders an empty / 404 state
              for non-document backings. */}
          <button
            type="button"
            onClick={() => setActivityOpen(true)}
            data-testid="file-activity-button"
            className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium border border-border-light text-content-primary hover:bg-surface-secondary transition-colors"
            title={t('files.activity.open', { defaultValue: 'View activity history' })}
          >
            <Activity size={13} />
            {t('files.activity.open', { defaultValue: 'View activity history' })}
          </button>
          {onManageAccess && (
            <button
              type="button"
              onClick={() => onManageAccess(row)}
              data-testid="file-manage-access-button"
              className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium border border-border-light text-content-primary hover:bg-surface-secondary transition-colors"
            >
              <Lock size={13} />
              {t('files.permissions.manage', { defaultValue: 'Manage access' })}
            </button>
          )}
          {isTauri && row.physical_path && (
            <button
              type="button"
              onClick={() => openInOSFinder(row.physical_path)}
              className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium border border-border-light text-content-primary hover:bg-surface-secondary transition-colors"
            >
              <FolderOpen size={13} />
              {t('files.actions.open_in_os', { defaultValue: 'Open in OS' })}
            </button>
          )}
        </div>

        <dl className="space-y-2 text-xs">
          <Row label={t('files.detail.kind', { defaultValue: 'Kind' })}>
            {t(`files.category.${row.kind}`, { defaultValue: row.kind })}
          </Row>
          {row.category && (
            <Row label={t('files.detail.category', { defaultValue: 'Category' })}>
              {row.category}
            </Row>
          )}
          {row.discipline && (
            <Row label={t('files.detail.discipline', { defaultValue: 'Discipline' })}>
              {row.discipline}
            </Row>
          )}
          {row.modified_at && (
            <Row label={t('files.detail.modified', { defaultValue: 'Modified' })}>
              <DateDisplay value={row.modified_at} format="datetime" />
            </Row>
          )}
          <Row label={t('files.detail.storage', { defaultValue: 'Storage' })}>
            <span className="uppercase tracking-wide text-2xs">{row.storage_backend}</span>
          </Row>
          <Row label={t('files.detail.path', { defaultValue: 'Path' })}>
            <button
              type="button"
              onClick={handleCopyPath}
              className="inline-flex items-center gap-1 font-mono text-[10px] text-content-secondary hover:text-oe-blue text-left break-all"
              title={t('files.actions.copy_path', { defaultValue: 'Copy path' })}
            >
              <Copy size={10} className="shrink-0" />
              {pathCopied
                ? t('files.toast.copied', { defaultValue: 'Copied' })
                : row.physical_path}
            </button>
          </Row>
        </dl>

        {extras.length > 0 && (
          <div className="border-t border-border-light pt-3">
            <h4 className="text-2xs font-medium uppercase tracking-wider text-content-tertiary mb-2">
              {t('files.detail.extra', { defaultValue: 'Metadata' })}
            </h4>
            <dl className="space-y-1.5 text-xs">
              {extras.map(([k, v]) => (
                <Row key={k} label={k.replace(/_/g, ' ')}>
                  <span className="font-mono text-[11px] break-words">
                    {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                  </span>
                </Row>
              ))}
            </dl>
          </div>
        )}

        {/* Per-file audit timeline. Renders for any kind backed by the
            ``oe_documents_document`` table; the section gracefully
            returns null for other backings (photo / bim_model / dwg)
            because the API responds 404 and useQuery is in retry:false.
            The compact in-pane strip stays for at-a-glance scanning;
            the full timeline lives in the slide-over drawer below. */}
        <ActivityLogSection documentId={row.id} />
      </div>

      {/* Full audit timeline as a right-edge slide-over. Mounted at the
          end of the aside so it overlays the pane (and the rest of the
          page via its own fixed positioning) without disrupting the
          preview layout. */}
      <ActivityDrawer
        documentId={row.id}
        documentName={row.name}
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
      />
    </aside>
  );
}

/* ── Activity log timeline ─────────────────────────────────────────────
   Backend endpoint: GET /v1/documents/{id}/activity/?limit=20. Returns
   newest-first audit events for the document (upload / rename / cde
   state change / delete). Renders a vertical timeline keyed by action,
   with the action chip colour-coded so a quick glance tells the user
   what happened. Gracefully renders nothing on 404 / error so an
   un-migrated backend can't break the preview pane. */
interface ActivityEvent {
  id: string;
  document_id: string;
  user_id: string | null;
  action: string;
  meta: Record<string, unknown>;
  created_at: string;
}

const ACTIVITY_ACTION_STYLE: Record<string, string> = {
  uploaded: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  renamed: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  downloaded: 'bg-surface-secondary text-content-secondary',
  deleted: 'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300',
  cde_state_changed: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
};

function formatActivityMeta(action: string, meta: Record<string, unknown>): string {
  /* Render a short, locale-neutral summary of the JSON meta blob. The
     parent caller turns this into a localised label when the action is
     well-known; unknown actions fall through to an empty string and the
     chip alone tells the user what happened. */
  if (action === 'renamed') {
    const oldName = typeof meta.old === 'string' ? meta.old : '';
    const newName = typeof meta.new === 'string' ? meta.new : '';
    if (oldName && newName) return `${oldName} → ${newName}`;
  }
  if (action === 'cde_state_changed') {
    const oldState = typeof meta.old === 'string' ? meta.old : 'wip';
    const newState = typeof meta.new === 'string' ? meta.new : '';
    if (newState) return `${oldState} → ${newState}`;
  }
  if (action === 'uploaded') {
    const name = typeof meta.name === 'string' ? meta.name : '';
    return name;
  }
  if (action === 'deleted') {
    const name = typeof meta.name === 'string' ? meta.name : '';
    return name;
  }
  return '';
}

function ActivityLogSection({ documentId }: { documentId: string }) {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['document-activity', documentId],
    queryFn: () =>
      apiGet<ActivityEvent[]>(`/v1/documents/${documentId}/activity/?limit=20`),
    staleTime: 30_000,
    retry: false,
  });
  /* 404 / 5xx must never break the pane — the endpoint is new and may
     legitimately be missing on an un-migrated backend, and photo / BIM
     IDs aren't valid document ids so the API responds 404 for them. */
  if (isError) return null;
  const events = data ?? [];
  if (!isLoading && events.length === 0) return null;
  return (
    <div className="border-t border-border-light pt-3">
      <h4 className="flex items-center gap-1.5 text-2xs font-medium uppercase tracking-wider text-content-tertiary mb-2">
        <Activity size={11} strokeWidth={2} />
        {t('files.detail.activity', { defaultValue: 'Activity' })}
        {events.length > 0 && (
          <span className="ms-1 text-content-quaternary tabular-nums">({events.length})</span>
        )}
      </h4>
      {isLoading ? (
        <div className="h-3 rounded bg-surface-secondary animate-pulse" />
      ) : (
        <ol className="relative space-y-2 ps-3 before:absolute before:top-1 before:bottom-1 before:start-1 before:w-px before:bg-border-light">
          {events.map((ev) => {
            const chipStyle =
              ACTIVITY_ACTION_STYLE[ev.action] ?? 'bg-surface-secondary text-content-secondary';
            const summary = formatActivityMeta(ev.action, ev.meta ?? {});
            const actionLabel = t(`files.activity.action.${ev.action}`, {
              defaultValue: ev.action.replace(/_/g, ' '),
            });
            return (
              <li key={ev.id} className="relative">
                <span className="absolute -start-[7px] top-1 h-2 w-2 rounded-full bg-oe-blue" />
                <div className="flex flex-wrap items-center gap-1.5">
                  <span
                    className={clsx(
                      'inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                      chipStyle,
                    )}
                  >
                    {actionLabel}
                  </span>
                  <DateDisplay
                    value={ev.created_at}
                    format="relative"
                    className="text-2xs text-content-quaternary"
                  />
                </div>
                {summary && (
                  <p className="mt-0.5 text-[11px] text-content-secondary break-words">
                    {summary}
                  </p>
                )}
                {ev.user_id && (
                  <p
                    className="mt-0.5 text-[10px] font-mono text-content-quaternary truncate"
                    title={ev.user_id}
                  >
                    {ev.user_id}
                  </p>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[10px] uppercase tracking-wider text-content-quaternary">{label}</dt>
      <dd className="text-content-primary">{children}</dd>
    </div>
  );
}
