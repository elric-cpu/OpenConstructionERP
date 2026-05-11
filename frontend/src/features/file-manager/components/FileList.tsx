/** Table view of files — alternative to FileGrid. */

import { useTranslation } from 'react-i18next';
import { ArrowDown, ArrowUp, ExternalLink, FileText, Image as ImageIcon, Layout, Box, Pencil, File, PenTool, FileBarChart, Tag } from 'lucide-react';
import clsx from 'clsx';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { primaryModule } from '../kindModule';
import { CDEBadge } from './CDEBadge';
import type { FileRow, FileKind, FileFilters } from '../types';

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

interface FileListProps {
  items: FileRow[];
  selectedIds: Set<string>;
  onSelect: (id: string, additive: boolean, shift?: boolean) => void;
  onOpen: (row: FileRow) => void;
  sort: NonNullable<FileFilters['sort']>;
  onSortChange: (sort: NonNullable<FileFilters['sort']>) => void;
  isLoading?: boolean;
}

function fmtBytes(bytes: number): string {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}


type SortKey = NonNullable<FileFilters['sort']>;

export function FileList({
  items,
  selectedIds,
  onSelect,
  onOpen,
  sort,
  onSortChange,
  isLoading,
}: FileListProps) {
  const { t } = useTranslation();

  const Header = ({ field, label, align = 'left' }: { field: SortKey; label: string; align?: 'left' | 'right' }) => {
    const active = sort === field;
    return (
      <th
        className={clsx(
          'px-3 py-2 text-2xs font-medium uppercase tracking-wider text-content-tertiary',
          align === 'right' && 'text-right',
          'cursor-pointer select-none hover:text-content-primary',
        )}
        onClick={() => onSortChange(field)}
      >
        <span className="inline-flex items-center gap-1">
          {label}
          {active && <ArrowDown size={10} />}
          {!active && <ArrowUp size={10} className="opacity-0" />}
        </span>
      </th>
    );
  };

  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-surface-elevated border-b border-border-light">
          <tr>
            <Header field="name" label={t('files.col.name', { defaultValue: 'Name' })} />
            <Header field="kind" label={t('files.col.kind', { defaultValue: 'Type' })} />
            <Header field="size" label={t('files.col.size', { defaultValue: 'Size' })} align="right" />
            <Header field="modified" label={t('files.col.modified', { defaultValue: 'Modified' })} align="right" />
            <th className="px-3 py-2 text-2xs font-medium uppercase tracking-wider text-content-tertiary">
              {t('files.col.discipline', { defaultValue: 'Discipline' })}
            </th>
            <th className="px-3 py-2 text-2xs font-medium uppercase tracking-wider text-content-tertiary">
              {t('files.col.open_in', { defaultValue: 'Open in' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {isLoading && items.length === 0 ? (
            Array.from({ length: 6 }).map((_, i) => (
              <tr key={i} className="border-b border-border-light">
                {Array.from({ length: 5 }).map((_, j) => (
                  <td key={j} className="px-3 py-2">
                    <div className="h-3 rounded bg-surface-secondary animate-pulse" />
                  </td>
                ))}
              </tr>
            ))
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-3 py-12 text-center text-sm text-content-tertiary">
                {t('files.empty', { defaultValue: 'No files match your filters.' })}
              </td>
            </tr>
          ) : (
            items.map((row) => {
              const Icon = KIND_ICON[row.kind] ?? File;
              const isSelected = selectedIds.has(row.id);
              const target = primaryModule(row.kind, row.extension);
              const TargetIcon = target.icon;
              const moduleLabel = t(target.i18nKey, { defaultValue: target.label });
              return (
                <tr
                  key={row.id}
                  className={clsx(
                    'border-b border-border-light cursor-pointer transition-colors',
                    isSelected
                      ? 'bg-oe-blue/10'
                      : 'hover:bg-surface-secondary/60',
                  )}
                  onClick={(e) => onSelect(row.id, e.metaKey || e.ctrlKey, e.shiftKey)}
                  onDoubleClick={() => onOpen(row)}
                >
                  <td className="px-3 py-2 max-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <Icon size={14} strokeWidth={1.75} className="shrink-0 text-content-tertiary" />
                      {typeof row.extra?.drawing_number === 'string' && row.extra.drawing_number && (
                        <span
                          className="font-mono text-[11px] text-content-tertiary shrink-0"
                          title="Drawing number"
                        >
                          {row.extra.drawing_number}
                        </span>
                      )}
                      <span className="truncate text-content-primary" title={row.name}>
                        {row.name}
                      </span>
                      {typeof row.extra?.revision_code === 'string' && row.extra.revision_code && (
                        <span
                          className="inline-flex items-center rounded-md border border-border-light px-1.5 py-0.5 text-[10px] font-medium text-content-secondary shrink-0"
                          title="Revision"
                        >
                          Rev {row.extra.revision_code}
                        </span>
                      )}
                      <CDEBadge state={row.extra?.cde_state as string | undefined} />
                    </div>
                  </td>
                  <td className="px-3 py-2 text-content-secondary text-xs">
                    {t(`files.category.${row.kind}`, { defaultValue: row.kind })}
                  </td>
                  <td className="px-3 py-2 text-right text-content-secondary tabular-nums text-xs">
                    {fmtBytes(row.size_bytes)}
                  </td>
                  <td className="px-3 py-2 text-right text-content-secondary text-xs">
                    {row.modified_at ? <DateDisplay value={row.modified_at} format="relative" /> : '—'}
                  </td>
                  <td className="px-3 py-2 text-content-tertiary text-xs truncate">
                    {row.discipline ?? '—'}
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpen(row);
                      }}
                      className={clsx(
                        'inline-flex items-center gap-1 h-6 px-2 rounded-md text-[10.5px] font-medium transition-colors',
                        'border border-border-light text-content-secondary',
                        'hover:border-oe-blue/40 hover:text-oe-blue hover:bg-oe-blue/5',
                      )}
                      title={t(target.descriptionI18nKey, { defaultValue: target.description })}
                    >
                      <TargetIcon size={10} strokeWidth={2} className="shrink-0" />
                      <span className="truncate max-w-[160px]">{moduleLabel}</span>
                      <ExternalLink size={9} className="shrink-0 opacity-60" />
                    </button>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
