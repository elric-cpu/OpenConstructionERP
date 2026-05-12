/** Folder-card grid — default landing view for the unified files hub.
 *
 * One card per category from the file tree. Click → drill into the
 * category's grid/list view. An empty card renders an "Add your first…"
 * CTA that opens the upload dialog.
 */

import { useTranslation } from 'react-i18next';
import {
  ArrowRight,
  FileText,
  Image as ImageIcon,
  Layout,
  Box,
  Pencil,
  Tag,
  FileBarChart,
  PenTool,
  Folder,
  Lock,
  Settings,
  UploadCloud,
  type LucideIcon,
} from 'lucide-react';
import clsx from 'clsx';
import type { FileTreeNode, FileKind } from '../types';

const KIND_ICON: Record<FileKind, LucideIcon> = {
  document: FileText,
  photo: ImageIcon,
  sheet: Layout,
  bim_model: Box,
  dwg_drawing: Pencil,
  takeoff: Tag,
  report: FileBarChart,
  markup: PenTool,
};

// One tone per kind. The square sits behind the icon and gives each
// folder an at-a-glance identity. Same colour family as FileGrid tiles
// so the card → grid transition feels continuous.
const KIND_TONE: Record<
  FileKind,
  { tile: string; icon: string; ring: string }
> = {
  document: {
    tile: 'bg-sky-50 dark:bg-sky-950/30',
    icon: 'text-sky-600 dark:text-sky-400',
    ring: 'group-hover:ring-sky-500/30',
  },
  photo: {
    tile: 'bg-emerald-50 dark:bg-emerald-950/30',
    icon: 'text-emerald-600 dark:text-emerald-400',
    ring: 'group-hover:ring-emerald-500/30',
  },
  sheet: {
    tile: 'bg-amber-50 dark:bg-amber-950/30',
    icon: 'text-amber-600 dark:text-amber-400',
    ring: 'group-hover:ring-amber-500/30',
  },
  bim_model: {
    tile: 'bg-violet-50 dark:bg-violet-950/30',
    icon: 'text-violet-600 dark:text-violet-400',
    ring: 'group-hover:ring-violet-500/30',
  },
  dwg_drawing: {
    tile: 'bg-orange-50 dark:bg-orange-950/30',
    icon: 'text-orange-600 dark:text-orange-400',
    ring: 'group-hover:ring-orange-500/30',
  },
  takeoff: {
    tile: 'bg-cyan-50 dark:bg-cyan-950/30',
    icon: 'text-cyan-600 dark:text-cyan-400',
    ring: 'group-hover:ring-cyan-500/30',
  },
  report: {
    tile: 'bg-pink-50 dark:bg-pink-950/30',
    icon: 'text-pink-600 dark:text-pink-400',
    ring: 'group-hover:ring-pink-500/30',
  },
  markup: {
    tile: 'bg-rose-50 dark:bg-rose-950/30',
    icon: 'text-rose-600 dark:text-rose-400',
    ring: 'group-hover:ring-rose-500/30',
  },
};

function fmtBytes(bytes: number): string {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

interface FolderCardGridProps {
  nodes: FileTreeNode[];
  isLoading?: boolean;
  onOpenCategory: (kind: FileKind) => void;
  onUpload: (kind: FileKind | null) => void;
  /** Owner-only: clicking the gear on a card opens the permissions modal. */
  onManageAccess?: (kind: FileKind) => void;
  /** ``{kind: count}`` of non-revoked grants per folder. Empty for non-owners. */
  permissionCounts?: Record<string, number>;
  /** True when the current user can manage permissions (project owner / admin). */
  canManageAccess?: boolean;
}

export function FolderCardGrid({
  nodes,
  isLoading,
  onOpenCategory,
  onUpload,
  onManageAccess,
  permissionCounts,
  canManageAccess,
}: FolderCardGridProps) {
  const { t } = useTranslation();

  if (isLoading && nodes.length === 0) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5 p-5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-44 rounded-2xl border border-border-light bg-surface-secondary/40 animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center text-content-tertiary">
        <Folder size={36} className="mb-3 opacity-60" />
        <p className="text-sm font-medium text-content-secondary">
          {t('files.tree.empty', { defaultValue: 'No files yet.' })}
        </p>
        <button
          type="button"
          onClick={() => onUpload(null)}
          className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold bg-oe-blue text-white hover:bg-oe-blue-hover transition-colors"
        >
          <UploadCloud size={14} />
          {t('files.upload', { defaultValue: 'Upload files' })}
        </button>
      </div>
    );
  }

  return (
    <div className="p-5 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5">
      {nodes.map((node) => {
        const kind = bareKind(node.id);
        const count = permissionCounts?.[kind] ?? 0;
        return (
          <FolderCard
            key={node.id}
            node={node}
            onOpen={() => onOpenCategory(kind)}
            onUpload={() => onUpload(kind)}
            onManageAccess={
              canManageAccess && onManageAccess
                ? () => onManageAccess(kind)
                : undefined
            }
            permissionCount={count}
          />
        );
      })}
    </div>
  );
}

// Older backends shipped node ids prefixed with "category:" (e.g.
// "category:bim_model"). Strip the prefix defensively so cached URLs and
// older API responses still resolve to a valid FileKind.
function bareKind(id: string): FileKind {
  return id.replace(/^category:/, '') as FileKind;
}

interface FolderCardProps {
  node: FileTreeNode;
  onOpen: () => void;
  onUpload: () => void;
  onManageAccess?: () => void;
  permissionCount?: number;
}

function FolderCard({
  node,
  onOpen,
  onUpload,
  onManageAccess,
  permissionCount = 0,
}: FolderCardProps) {
  const { t } = useTranslation();
  const kind = bareKind(node.id);
  const Icon = KIND_ICON[kind] ?? Folder;
  const tone = KIND_TONE[kind] ?? KIND_TONE.document;
  const isEmpty = node.file_count === 0;
  const label = t(`files.category.${kind}`, { defaultValue: node.label });
  const isRestricted = permissionCount > 0;
  const lockTooltip = t(
    permissionCount === 1
      ? 'files.permissions.lock_tooltip'
      : 'files.permissions.lock_tooltip_plural',
    {
      defaultValue: 'Restricted: {{count}} members can access',
      count: permissionCount,
    },
  );

  if (isEmpty) {
    return (
      <button
        type="button"
        onClick={onUpload}
        className={clsx(
          'group relative flex flex-col items-start text-left rounded-2xl p-5 min-h-[176px]',
          'border-2 border-dashed border-border-light bg-surface-primary/40',
          'hover:border-oe-blue/40 hover:bg-surface-primary transition-colors',
        )}
      >
        <div
          className={clsx(
            'flex h-12 w-12 items-center justify-center rounded-xl ring-1 ring-inset ring-border-light/50',
            tone.tile,
          )}
        >
          <Icon size={22} strokeWidth={1.75} className={tone.icon} />
        </div>
        <h3 className="mt-3 text-sm font-semibold text-content-primary">{label}</h3>
        <p className="mt-1 text-xs text-content-tertiary">
          {t('files.empty_category', {
            defaultValue: 'No {{category}} yet',
            category: label.toLowerCase(),
          })}
        </p>
        <span className="mt-auto pt-3 inline-flex items-center gap-1.5 text-xs font-medium text-oe-blue opacity-80 group-hover:opacity-100">
          <UploadCloud size={13} />
          {t('files.cta.add_first', {
            defaultValue: 'Add your first {{category}}',
            category: label.toLowerCase(),
          })}
        </span>
      </button>
    );
  }

  return (
    <div
      data-testid={`folder-card-${kind}`}
      className={clsx(
        'group relative flex flex-col items-start text-left rounded-2xl min-h-[176px]',
        'border border-border-light bg-gradient-to-br from-surface-elevated to-surface-primary',
        'shadow-sm transition-all duration-150',
        'hover:-translate-y-0.5 hover:shadow-xl hover:border-border-medium',
      )}
    >
      {/* Owner-only secondary actions overlay (gear + lock badge). */}
      <div className="absolute top-3 right-3 flex items-center gap-1">
        {isRestricted && (
          <span
            data-testid={`folder-lock-${kind}`}
            title={lockTooltip}
            aria-label={lockTooltip}
            className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-300"
          >
            <Lock size={11} />
          </span>
        )}
        {onManageAccess && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onManageAccess();
            }}
            data-testid={`folder-manage-access-${kind}`}
            aria-label={t('files.permissions.manage', { defaultValue: 'Manage access' })}
            title={t('files.permissions.manage', { defaultValue: 'Manage access' })}
            className="inline-flex h-6 w-6 items-center justify-center rounded-md text-content-tertiary opacity-0 group-hover:opacity-100 hover:bg-surface-secondary hover:text-content-primary transition-all"
          >
            <Settings size={12} />
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={onOpen}
        className={clsx(
          'flex flex-col items-start text-left p-5 w-full h-full min-h-[176px]',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40 rounded-2xl',
        )}
      >
      <div className="w-full flex items-start justify-between gap-3">
        <div
          className={clsx(
            'flex h-12 w-12 items-center justify-center rounded-xl ring-1 ring-inset ring-black/5 dark:ring-white/5',
            'transition-shadow group-hover:ring-2',
            tone.tile,
            tone.ring,
          )}
        >
          <Icon size={22} strokeWidth={1.75} className={tone.icon} />
        </div>
      </div>

      <h3 className="mt-3 text-sm font-semibold text-content-primary truncate w-full" title={label}>
        {label}
      </h3>

      <dl className="mt-3 grid grid-cols-2 gap-3 w-full">
        <div className="flex flex-col">
          <dt className="text-[10px] uppercase tracking-wider text-content-quaternary">
            {t('files.folder.files', { defaultValue: 'Files' })}
          </dt>
          <dd className="text-base font-semibold text-content-primary tabular-nums">
            {node.file_count.toLocaleString()}
          </dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-[10px] uppercase tracking-wider text-content-quaternary">
            {t('files.folder.size', { defaultValue: 'Size' })}
          </dt>
          <dd className="text-base font-semibold text-content-primary tabular-nums">
            {fmtBytes(node.total_bytes)}
          </dd>
        </div>
      </dl>

      <span
        className={clsx(
          'mt-auto pt-3 inline-flex items-center gap-1 text-xs font-medium',
          'text-oe-blue opacity-0 -translate-x-1 transition-all',
          'group-hover:opacity-100 group-hover:translate-x-0',
        )}
      >
        {t('files.folder.open', { defaultValue: 'Open' })}
        <ArrowRight size={12} />
      </span>
      </button>
    </div>
  );
}
