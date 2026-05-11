/** Toolbar above the file grid/list — search, filters, view toggle, export/import. */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, X, ChevronDown, LayoutGrid, List, Download, Upload } from 'lucide-react';
import clsx from 'clsx';
import type { FileFilters } from '../types';

type SortKey = NonNullable<FileFilters['sort']>;
export type ViewMode = 'grid' | 'list';

interface FileActionsBarProps {
  query: string;
  onQueryChange: (q: string) => void;
  sort: SortKey;
  onSortChange: (s: SortKey) => void;
  view: ViewMode;
  onViewChange: (v: ViewMode) => void;
  onExport: () => void;
  onImport: () => void;
  totalCount: number;
  extension?: string | undefined;
  onExtensionChange?: (ext: string | undefined) => void;
}

/* Predefined file-type filter pills. Each pill maps to one or more extensions
   passed as `?extension=` to the backend. Pills are intentionally small so the
   whole row stays under one toolbar height. */
const TYPE_PILLS: { key: string; label: string; ext?: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'pdf', label: 'PDF', ext: 'pdf' },
  { key: 'image', label: 'Images', ext: 'jpg' },
  { key: 'cad', label: 'CAD', ext: 'dwg' },
  { key: 'bim', label: 'BIM', ext: 'ifc' },
  { key: 'office', label: 'Office', ext: 'xlsx' },
];

export function FileActionsBar({
  query,
  onQueryChange,
  sort,
  onSortChange,
  view,
  onViewChange,
  onExport,
  onImport,
  totalCount,
  extension,
  onExtensionChange,
}: FileActionsBarProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(query);
  const [sortOpen, setSortOpen] = useState(false);
  const sortRef = useRef<HTMLDivElement>(null);

  // Sync external query changes back into the draft (e.g. when user clears).
  useEffect(() => {
    setDraft(query);
  }, [query]);

  // Debounce the search-box → URL/query update so we don't spam the API
  // on every keystroke. 250 ms feels instant while still batching typing.
  useEffect(() => {
    const handle = setTimeout(() => {
      if (draft !== query) onQueryChange(draft);
    }, 250);
    return () => clearTimeout(handle);
  }, [draft, query, onQueryChange]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (sortRef.current && !sortRef.current.contains(e.target as Node)) {
        setSortOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const sortLabels: Record<SortKey, string> = {
    modified: t('files.sort.modified', { defaultValue: 'Modified' }),
    name: t('files.sort.name', { defaultValue: 'Name' }),
    size: t('files.sort.size', { defaultValue: 'Size' }),
    kind: t('files.sort.kind', { defaultValue: 'Type' }),
  };

  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b border-border-light bg-surface-elevated">
      <div className="relative flex-1 min-w-[200px] max-w-md">
        <Search
          size={14}
          className="absolute left-2.5 top-1/2 -translate-y-1/2 text-content-tertiary pointer-events-none"
        />
        <input
          type="search"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t('files.search_placeholder', { defaultValue: 'Search files…' })}
          className="w-full h-9 pl-8 pr-8 text-sm rounded-lg border border-border-light bg-surface-primary text-content-primary placeholder:text-content-tertiary focus:outline-none focus:border-oe-blue focus:ring-2 focus:ring-oe-blue/20"
        />
        {draft && (
          <button
            type="button"
            onClick={() => setDraft('')}
            aria-label={t('common.clear', { defaultValue: 'Clear' })}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-content-tertiary hover:text-content-primary"
          >
            <X size={12} />
          </button>
        )}
      </div>

      <span className="text-2xs text-content-tertiary tabular-nums">
        {totalCount} {t('files.count_files', { defaultValue: 'files' })}
      </span>

      {onExtensionChange && (
        <div className="inline-flex items-center gap-1">
          {TYPE_PILLS.map((p) => {
            const active = p.ext ? extension === p.ext : !extension;
            return (
              <button
                key={p.key}
                type="button"
                onClick={() => onExtensionChange(p.ext)}
                className={clsx(
                  'inline-flex h-7 items-center rounded-full px-2.5 text-[11px] font-medium transition-colors',
                  active
                    ? 'bg-oe-blue text-white'
                    : 'border border-border-light text-content-secondary hover:bg-surface-secondary',
                )}
                aria-pressed={active}
              >
                {t(`files.type_pill.${p.key}`, { defaultValue: p.label })}
              </button>
            );
          })}
        </div>
      )}

      <div className="ms-auto flex items-center gap-2">
        <div ref={sortRef} className="relative">
          <button
            type="button"
            onClick={() => setSortOpen((p) => !p)}
            aria-haspopup="listbox"
            aria-expanded={sortOpen}
            className="flex items-center gap-1.5 h-9 px-3 text-xs font-medium rounded-lg border border-border-light text-content-secondary hover:bg-surface-secondary"
          >
            {t('files.sort_by', { defaultValue: 'Sort' })}: {sortLabels[sort]}
            <ChevronDown size={12} className={clsx('transition-transform', sortOpen && 'rotate-180')} />
          </button>
          {sortOpen && (
            <div
              role="listbox"
              className="absolute right-0 top-full mt-1 w-40 rounded-lg border border-border-light bg-surface-elevated shadow-lg z-20 overflow-hidden"
            >
              {(['modified', 'name', 'size', 'kind'] as SortKey[]).map((k) => (
                <button
                  key={k}
                  role="option"
                  aria-selected={sort === k}
                  onClick={() => {
                    onSortChange(k);
                    setSortOpen(false);
                  }}
                  className={clsx(
                    'w-full px-3 py-2 text-left text-xs transition-colors',
                    sort === k
                      ? 'bg-oe-blue/10 text-oe-blue font-medium'
                      : 'text-content-secondary hover:bg-surface-secondary',
                  )}
                >
                  {sortLabels[k]}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="inline-flex rounded-lg border border-border-light overflow-hidden">
          <ViewBtn
            active={view === 'grid'}
            onClick={() => onViewChange('grid')}
            label={t('files.view_grid', { defaultValue: 'Grid view' })}
          >
            <LayoutGrid size={14} />
          </ViewBtn>
          <ViewBtn
            active={view === 'list'}
            onClick={() => onViewChange('list')}
            label={t('files.view_list', { defaultValue: 'List view' })}
          >
            <List size={14} />
          </ViewBtn>
        </div>

        <button
          type="button"
          onClick={onImport}
          className="inline-flex items-center gap-1.5 h-9 px-3 text-xs font-medium rounded-lg border border-border-light text-content-secondary hover:bg-surface-secondary"
        >
          <Upload size={13} />
          {t('files.actions.import', { defaultValue: 'Import' })}
        </button>
        <button
          type="button"
          onClick={onExport}
          className="inline-flex items-center gap-1.5 h-9 px-3 text-xs font-medium rounded-lg bg-oe-blue text-white hover:bg-oe-blue-hover"
        >
          <Download size={13} />
          {t('files.actions.export', { defaultValue: 'Export' })}
        </button>
      </div>
    </div>
  );
}

function ViewBtn({
  active,
  onClick,
  label,
  children,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={active}
      title={label}
      className={clsx(
        'flex items-center justify-center w-9 h-9 transition-colors',
        active
          ? 'bg-oe-blue/10 text-oe-blue'
          : 'text-content-tertiary hover:bg-surface-secondary hover:text-content-primary',
      )}
    >
      {children}
    </button>
  );
}
