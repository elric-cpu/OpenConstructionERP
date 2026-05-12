/** Project File Manager — Issue #109.
 *
 * Unified file & folder hub. The default view (no category selected) is
 * a folder-card grid; clicking a folder drills into the existing
 * grid/list view with the rest of the UI (path bar, search, sort,
 * preview pane) intact.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ChevronRight, HardDrive, UploadCloud } from 'lucide-react';
import clsx from 'clsx';
import { EmptyState } from '@/shared/ui';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import {
  useFileList,
  useFileTree,
  useFolderPermissionCounts,
  useIsProjectOwner,
  useStorageLocations,
} from './hooks';
import { PathBar } from './components/PathBar';
import { FileTree } from './components/FileTree';
import { FileGrid } from './components/FileGrid';
import { FileList } from './components/FileList';
import { FilePreviewPane } from './components/FilePreviewPane';
import { FileActionsBar, type ViewMode } from './components/FileActionsBar';
import { ExportWizard } from './components/ExportWizard';
import { ImportWizard } from './components/ImportWizard';
import { EmailDialog } from './components/EmailDialog';
import { ShareLinkModal } from './components/ShareLinkModal';
import { FolderPermissionsModal } from './components/FolderPermissionsModal';
import { FolderCardGrid } from './components/FolderCardGrid';
import { UploadDialog } from './components/UploadDialog';
import { BulkActionsBar } from './components/BulkActionsBar';
import { InitialLoadProgress } from './components/InitialLoadProgress';
import { FilesStatsStrip } from './components/FilesStatsStrip';
import { primaryModule } from './kindModule';
import type { FileFilters, FileKind, FileRow } from './types';

const VIEW_MODE_KEY = 'file-manager:view-mode';

function readViewMode(): ViewMode {
  try {
    const stored = localStorage.getItem(VIEW_MODE_KEY);
    if (stored === 'grid' || stored === 'list') return stored;
  } catch {
    /* localStorage unavailable */
  }
  return 'grid';
}

function writeViewMode(view: ViewMode) {
  try {
    localStorage.setItem(VIEW_MODE_KEY, view);
  } catch {
    /* localStorage unavailable */
  }
}

const VALID_KINDS: ReadonlySet<string> = new Set([
  'document',
  'photo',
  'sheet',
  'bim_model',
  'dwg_drawing',
  'takeoff',
  'report',
  'markup',
]);

export function FileManagerPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { projectId: routeProjectId } = useParams<{ projectId?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const ctxProjectId = useProjectContextStore((s) => s.activeProjectId);
  const ctxProjectName = useProjectContextStore((s) => s.activeProjectName);

  const projectId = routeProjectId ?? ctxProjectId;

  // Selected category drives both the URL (?kind=) and the view —
  // landing on /files renders the folder grid; /files?kind=document
  // jumps straight to that category's grid view. Strip any legacy
  // "category:" prefix that older bookmarks may carry.
  const rawKind = searchParams.get('kind');
  const queryKind = rawKind ? rawKind.replace(/^category:/, '') : null;
  const initialKind: FileKind | null =
    queryKind && VALID_KINDS.has(queryKind) ? (queryKind as FileKind) : null;

  const [selectedKind, setSelectedKind] = useState<FileKind | null>(initialKind);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<NonNullable<FileFilters['sort']>>('modified');
  const [view, setView] = useState<ViewMode>(() => readViewMode());
  const [extension, setExtension] = useState<string | undefined>(undefined);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [previewRow, setPreviewRow] = useState<FileRow | null>(null);
  const [showExport, setShowExport] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [emailRow, setEmailRow] = useState<FileRow | null>(null);
  const [shareRow, setShareRow] = useState<FileRow | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [uploadKind, setUploadKind] = useState<FileKind | null>(null);
  const [permsKind, setPermsKind] = useState<FileKind | null>(null);

  // Folder-permissions surface — gear + lock badge.
  const isOwner = useIsProjectOwner(projectId);
  const permissionCounts = useFolderPermissionCounts(projectId, isOwner);

  useEffect(() => {
    writeViewMode(view);
  }, [view]);

  // Keep the URL ?kind= param in sync with selection so deep-links work
  // both ways: pasted URL → loads the right category; UI back-button →
  // returns to the folder-grid view.
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (selectedKind) next.set('kind', selectedKind);
    else next.delete('kind');
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true });
    }
  }, [selectedKind, searchParams, setSearchParams]);

  const filters = useMemo<FileFilters>(
    () => ({
      sort,
      ...(selectedKind ? { category: selectedKind } : {}),
      ...(query.trim() ? { q: query.trim() } : {}),
      ...(extension ? { extension } : {}),
    }),
    [sort, selectedKind, query, extension],
  );

  const { data: tree, isLoading: treeLoading } = useFileTree(projectId);
  const { data: locations, isLoading: locLoading } = useStorageLocations(projectId);
  // The list query is only needed when a category is selected; the
  // folder-grid view reads counts straight off the tree and skips the
  // (potentially very large) full-file list response entirely.
  const { data: list, isLoading: listLoading } = useFileList(
    selectedKind ? projectId : null,
    filters,
  );

  // Whenever filters change, drop selection that no longer matches the
  // visible result set so the preview pane never shows a stale row.
  useEffect(() => {
    if (!list) return;
    const visibleIds = new Set(list.items.map((r) => r.id));
    setSelectedIds((prev) => {
      const next = new Set([...prev].filter((id) => visibleIds.has(id)));
      return next.size === prev.size ? prev : next;
    });
    if (previewRow && !visibleIds.has(previewRow.id)) {
      setPreviewRow(null);
    }
  }, [list, previewRow]);

  // Deep-link: `?file={id}` pre-selects that file in the preview pane.
  // Used by the "Open in File Manager" secondary action so users land
  // directly on the focused file rather than just the category grid.
  const fileIdParam = searchParams.get('file');
  useEffect(() => {
    if (!fileIdParam || !list) return;
    const target = list.items.find((r) => r.id === fileIdParam);
    if (target) {
      setPreviewRow(target);
      setSelectedIds(new Set([fileIdParam]));
    }
  }, [fileIdParam, list]);

  /* Anchor for shift-click range selection — the last single-clicked id.
     Shift+click expands the visible range from anchor to target; plain click
     resets the anchor. We keep this in a ref so it does not trigger renders. */
  const lastClickedRef = useRef<string | null>(null);

  function handleSelect(id: string, additive: boolean, shift = false) {
    const items = list?.items ?? [];
    if (shift && lastClickedRef.current) {
      const anchor = lastClickedRef.current;
      const a = items.findIndex((r) => r.id === anchor);
      const b = items.findIndex((r) => r.id === id);
      if (a >= 0 && b >= 0) {
        const [lo, hi] = a < b ? [a, b] : [b, a];
        const range = items.slice(lo, hi + 1).map((r) => r.id);
        setSelectedIds((prev) => {
          const next = new Set(additive ? prev : []);
          for (const rid of range) next.add(rid);
          return next;
        });
        const row = list?.items.find((r) => r.id === id);
        if (row) setPreviewRow(row);
        return;
      }
    }

    setSelectedIds((prev) => {
      const next = new Set(additive ? prev : []);
      if (prev.has(id) && additive) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
    lastClickedRef.current = id;
    const row = list?.items.find((r) => r.id === id);
    if (row) setPreviewRow(row);
  }

  function handleOpen(row: FileRow) {
    // Opening a file means "take me to the tool that processes it" —
    // PDFs jump to PDF Takeoff, IFC/RVT to BIM Viewer, DWG to DWG
    // Takeoff. Plain download stays available from the preview pane.
    const target = primaryModule(row.kind, row.extension);
    navigate(target.route(row.project_id, row.id));
  }

  function handleOpenCategory(kind: FileKind) {
    setSelectedKind(kind);
    setSelectedIds(new Set());
    setPreviewRow(null);
  }

  function handleBackToAll() {
    setSelectedKind(null);
    setSelectedIds(new Set());
    setPreviewRow(null);
    setQuery('');
  }

  function handleOpenUpload(kind: FileKind | null) {
    setUploadKind(kind);
    setShowUpload(true);
  }

  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-full">
        <EmptyState
          icon={<HardDrive size={28} />}
          title={t('files.no_project_title', { defaultValue: 'No active project' })}
          description={t('files.no_project_desc', {
            defaultValue:
              'Pick a project from the dashboard to see all of its documents, photos, BIM and DWG files in one place.',
          })}
          action={{
            label: t('files.go_to_projects', { defaultValue: 'Go to projects' }),
            onClick: () => navigate('/projects'),
          }}
        />
      </div>
    );
  }

  const selectedRows = list?.items.filter((r) => selectedIds.has(r.id)) ?? [];
  const showFolderGrid = selectedKind === null;
  const activeKindLabel = selectedKind
    ? t(`files.category.${selectedKind}`, { defaultValue: selectedKind })
    : '';

  // First-load overlay: shown only when at least one of the bootstrap
  // queries is still in flight AND we have no cached data yet. After both
  // queries resolve, the overlay disappears and never reappears for this
  // mount (React Query caches the result).
  const isFirstLoad = (treeLoading || locLoading) && (!tree || !locations);

  return (
    <div className="flex flex-col h-full">
      {isFirstLoad && (
        <InitialLoadProgress
          storageDone={!!locations}
          treeDone={!!tree}
          projectName={ctxProjectName}
        />
      )}
      <PathBar locations={locations} isLoading={locLoading} selectedKind={selectedKind} />

      {/* Page-level breadcrumb + primary upload CTA. Lives outside the
          tree/main split so it's always visible whether the user is on
          the folder grid or drilled into a category. */}
      <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-border-light bg-surface-elevated">
        <nav
          className="flex items-center gap-1.5 text-sm min-w-0"
          aria-label={t('common.breadcrumb', { defaultValue: 'Breadcrumb' })}
        >
          <button
            type="button"
            onClick={handleBackToAll}
            className={clsx(
              'inline-flex items-center gap-1.5 px-2 py-1 rounded-md transition-colors',
              showFolderGrid
                ? 'text-content-primary font-semibold cursor-default'
                : 'text-content-secondary hover:text-content-primary hover:bg-surface-secondary',
            )}
            disabled={showFolderGrid}
          >
            {!showFolderGrid && <ArrowLeft size={13} />}
            {t('files.title_all', { defaultValue: 'All files' })}
          </button>
          {!showFolderGrid && (
            <>
              <ChevronRight size={12} className="text-content-quaternary shrink-0" />
              <span className="px-2 py-1 text-content-primary font-semibold truncate" title={activeKindLabel}>
                {activeKindLabel}
              </span>
            </>
          )}
        </nav>

        <button
          type="button"
          onClick={() => handleOpenUpload(selectedKind)}
          className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg text-xs font-semibold bg-oe-blue text-white hover:bg-oe-blue-hover transition-colors shrink-0"
        >
          <UploadCloud size={14} />
          {t('files.upload', { defaultValue: 'Upload files' })}
        </button>
      </div>

      <div className="flex-1 flex min-h-0">
        <FileTree
          nodes={tree ?? []}
          selectedId={selectedKind}
          onSelect={(id) => {
            setSelectedKind(id as FileKind | null);
            setSelectedIds(new Set());
            setPreviewRow(null);
          }}
          isLoading={treeLoading}
        />

        <main className="flex-1 flex flex-col min-w-0">
          {showFolderGrid ? (
            <div className="flex-1 overflow-auto">
              <FilesStatsStrip tree={tree} locations={locations} />
              <FolderCardGrid
                nodes={tree ?? []}
                isLoading={treeLoading}
                onOpenCategory={handleOpenCategory}
                onUpload={handleOpenUpload}
                onManageAccess={(kind) => setPermsKind(kind)}
                permissionCounts={permissionCounts}
                canManageAccess={isOwner}
              />
            </div>
          ) : (
            <>
              <FileActionsBar
                query={query}
                onQueryChange={setQuery}
                sort={sort}
                onSortChange={setSort}
                view={view}
                onViewChange={setView}
                onExport={() => setShowExport(true)}
                onImport={() => setShowImport(true)}
                totalCount={list?.total ?? 0}
                extension={extension}
                onExtensionChange={setExtension}
              />
              <BulkActionsBar
                selectedRows={selectedRows}
                projectId={projectId}
                onClear={() => setSelectedIds(new Set())}
              />
              <div className="flex-1 overflow-auto">
                {view === 'grid' ? (
                  <FileGrid
                    items={list?.items ?? []}
                    selectedIds={selectedIds}
                    onSelect={handleSelect}
                    onOpen={handleOpen}
                    isLoading={listLoading}
                  />
                ) : (
                  <FileList
                    items={list?.items ?? []}
                    selectedIds={selectedIds}
                    onSelect={handleSelect}
                    onOpen={handleOpen}
                    sort={sort}
                    onSortChange={setSort}
                    isLoading={listLoading}
                  />
                )}
              </div>
            </>
          )}
        </main>

        {!showFolderGrid && (
          <FilePreviewPane
            row={previewRow}
            onClose={() => setPreviewRow(null)}
            onEmail={(row) => setEmailRow(row)}
            onShare={(row) => setShareRow(row)}
            onManageAccess={
              isOwner ? (row) => setPermsKind(row.kind) : undefined
            }
          />
        )}
      </div>

      <ExportWizard
        open={showExport}
        projectId={projectId}
        projectName={locations?.project_name ?? ctxProjectName}
        onClose={() => setShowExport(false)}
      />
      <ImportWizard open={showImport} onClose={() => setShowImport(false)} />
      <ShareLinkModal
        open={shareRow !== null}
        row={shareRow}
        onClose={() => setShareRow(null)}
      />
      <EmailDialog
        open={emailRow !== null}
        row={emailRow}
        onClose={() => setEmailRow(null)}
      />
      <UploadDialog
        open={showUpload}
        projectId={projectId}
        defaultKind={uploadKind}
        onClose={() => setShowUpload(false)}
      />
      <FolderPermissionsModal
        open={permsKind !== null}
        projectId={projectId ?? null}
        scopeKind={permsKind}
        folderLabel={
          permsKind ? t(`files.category.${permsKind}`, { defaultValue: permsKind }) : undefined
        }
        onClose={() => setPermsKind(null)}
      />
    </div>
  );
}
