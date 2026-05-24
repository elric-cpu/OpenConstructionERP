import React, { useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate, Link } from 'react-router-dom';
import clsx from 'clsx';
import {
  Mail,
  Search,
  Plus,
  ChevronDown,
  ChevronRight,
  ArrowDownLeft,
  ArrowUpRight,
  FileText,
  Cloud,
  Webhook,
  Info,
  X,
  Pencil,
  Trash2,
  Send,
  HelpCircle,
  Link2,
} from 'lucide-react';
import {
  Button,
  Card,
  Badge,
  EmptyState,
  Breadcrumb,
  DateDisplay,
  RecoveryCard,
  SkeletonTable,
  ConfirmDialog,
  WideModal,
  WideModalSection,
  WideModalField,
} from '@/shared/ui';
import { ContactSearchInput } from '@/shared/ui/ContactSearchInput';
import { useConfirm } from '@/shared/hooks/useConfirm';
import { apiGet } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import {
  fetchCorrespondence,
  createCorrespondence,
  updateCorrespondence,
  deleteCorrespondence,
  type Correspondence,
  type CorrespondenceDirection,
  type CorrespondenceType,
  type CreateCorrespondencePayload,
  type UpdateCorrespondencePayload,
} from './api';

const LS_INFO_DISMISSED = 'oe_correspondence_info_dismissed';

/* ── Constants ─────────────────────────────────────────────────────────── */

interface Project {
  id: string;
  name: string;
}

const TYPE_LABELS: Record<CorrespondenceType, string> = {
  letter: 'Letter',
  email: 'Email',
  notice: 'Notice',
  memo: 'Memo',
};

const DIRECTION_CARD_CONFIG: Record<
  CorrespondenceDirection,
  { icon: React.ElementType; color: string; selectedColor: string; description: string }
> = {
  incoming: {
    icon: ArrowDownLeft,
    color: 'text-blue-600 dark:text-blue-400',
    selectedColor:
      'text-blue-600 bg-blue-50 border-blue-300 ring-2 ring-blue-200 dark:text-blue-400 dark:bg-blue-950/30 dark:border-blue-700 dark:ring-blue-800',
    description: 'Received from external party',
  },
  outgoing: {
    icon: ArrowUpRight,
    color: 'text-green-600 dark:text-green-400',
    selectedColor:
      'text-green-600 bg-green-50 border-green-300 ring-2 ring-green-200 dark:text-green-400 dark:bg-green-950/30 dark:border-green-700 dark:ring-green-800',
    description: 'Sent to external party',
  },
};

const TYPE_BADGE_COLORS: Record<CorrespondenceType, string> = {
  letter: 'text-purple-600 bg-purple-50 border-purple-200 dark:text-purple-400 dark:bg-purple-950/30 dark:border-purple-800',
  email: 'text-blue-600 bg-blue-50 border-blue-200 dark:text-blue-400 dark:bg-blue-950/30 dark:border-blue-800',
  notice: 'text-amber-600 bg-amber-50 border-amber-200 dark:text-amber-400 dark:bg-amber-950/30 dark:border-amber-800',
  memo: 'text-gray-600 bg-gray-50 border-gray-200 dark:text-gray-400 dark:bg-gray-800/50 dark:border-gray-700',
};

const CORR_TYPES_LIST: CorrespondenceType[] = ['letter', 'email', 'notice', 'memo'];

const inputCls =
  'h-10 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';
const textareaCls =
  'w-full rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue resize-none';

/* ── Create Modal ─────────────────────────────────────────────────────── */

interface CorrespondenceFormData {
  subject: string;
  direction: CorrespondenceDirection;
  type: CorrespondenceType;
  from_contact: string;
  from_display: string;
  to_contacts: string;
  to_display: string;
  date_sent: string;
  date_received: string;
  notes: string;
}

const todayDate = () => new Date().toISOString().slice(0, 10);

const EMPTY_FORM: CorrespondenceFormData = {
  subject: '',
  direction: 'outgoing',
  type: 'email',
  from_contact: '',
  from_display: '',
  to_contacts: '',
  to_display: '',
  date_sent: '',
  date_received: '',
  notes: '',
};

function CreateCorrespondenceModal({
  onClose,
  onSubmit,
  isPending,
  initialData,
  isEdit,
}: {
  onClose: () => void;
  onSubmit: (data: CorrespondenceFormData) => void;
  isPending: boolean;
  initialData?: CorrespondenceFormData | null;
  isEdit?: boolean;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<CorrespondenceFormData>(
    initialData ?? {
      ...EMPTY_FORM,
      date_sent: todayDate(),
      date_received: todayDate(),
    },
  );
  const [touched, setTouched] = useState(false);

  const set = <K extends keyof CorrespondenceFormData>(
    key: K,
    value: CorrespondenceFormData[K],
  ) => setForm((prev) => ({ ...prev, [key]: value }));

  const subjectError = touched && form.subject.trim().length === 0;
  const fromError = touched && (form.from_contact.trim().length === 0 && form.from_display.trim().length === 0);
  const canSubmit = form.subject.trim().length > 0 && (form.from_contact.trim().length > 0 || form.from_display.trim().length > 0);

  const handleSubmit = () => {
    setTouched(true);
    if (canSubmit) onSubmit(form);
  };

  return (
    <WideModal
      open
      onClose={onClose}
      busy={isPending}
      size="xl"
      title={
        isEdit
          ? t('correspondence.edit_entry', { defaultValue: 'Edit Entry' })
          : t('correspondence.new_entry', { defaultValue: 'New Entry' })
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isPending}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button variant="primary" onClick={handleSubmit} disabled={isPending || !canSubmit}>
            {isPending ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent mr-2 shrink-0" />
            ) : !isEdit ? (
              <Plus size={16} className="mr-1.5 shrink-0" />
            ) : null}
            <span>
              {isEdit
                ? t('correspondence.save_entry', { defaultValue: 'Save Changes' })
                : t('correspondence.create_entry', { defaultValue: 'Create Entry' })}
            </span>
          </Button>
        </>
      }
    >
      {/* Direction + Type pickers, side-by-side */}
      <WideModalSection columns={2}>
        <WideModalField label={t('correspondence.field_direction', { defaultValue: 'Direction' })}>
          <div
            className="grid grid-cols-2 gap-3"
            role="radiogroup"
            aria-label={t('correspondence.field_direction', { defaultValue: 'Direction' })}
          >
            {(['incoming', 'outgoing'] as CorrespondenceDirection[]).map((dir) => {
              const cfg = DIRECTION_CARD_CONFIG[dir];
              const DirIcon = cfg.icon;
              const selected = form.direction === dir;
              return (
                <button
                  key={dir}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => set('direction', dir)}
                  className={clsx(
                    'flex items-center gap-3 rounded-lg border-2 px-4 py-3 transition-all text-left',
                    selected
                      ? cfg.selectedColor
                      : 'border-border bg-surface-primary text-content-tertiary hover:border-border-light hover:bg-surface-secondary',
                  )}
                >
                  <DirIcon size={22} className="shrink-0" />
                  <div>
                    <span className="text-sm font-semibold block">
                      {t(`correspondence.dir_${dir}`, {
                        defaultValue: dir === 'incoming' ? 'Incoming' : 'Outgoing',
                      })}
                    </span>
                    <span className="text-2xs opacity-70">
                      {t(`correspondence.dir_${dir}_desc`, { defaultValue: cfg.description })}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </WideModalField>

        <WideModalField label={t('correspondence.field_type', { defaultValue: 'Type' })}>
          <div
            className="flex flex-wrap items-center gap-2 min-h-[2.5rem]"
            role="radiogroup"
            aria-label={t('correspondence.field_type', { defaultValue: 'Type' })}
          >
            {CORR_TYPES_LIST.map((tp) => {
              const selected = form.type === tp;
              return (
                <button
                  key={tp}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => set('type', tp)}
                  className={clsx(
                    'inline-flex items-center rounded-full border-2 px-3.5 py-1.5 text-xs font-semibold transition-all',
                    selected
                      ? TYPE_BADGE_COLORS[tp] + ' ring-2 ring-oe-blue/30'
                      : 'border-border bg-surface-primary text-content-tertiary hover:border-border-light hover:bg-surface-secondary',
                  )}
                >
                  {t(`correspondence.type_${tp}`, { defaultValue: TYPE_LABELS[tp] })}
                </button>
              );
            })}
          </div>
        </WideModalField>
      </WideModalSection>

      {/* Details section — full-width subject */}
      <WideModalSection
        title={t('correspondence.section_details', { defaultValue: 'Correspondence Details' })}
        columns={2}
      >
        <WideModalField
          label={t('correspondence.field_subject', { defaultValue: 'Subject' })}
          required
          span={2}
          htmlFor="corr-subject"
          error={
            subjectError
              ? t('correspondence.subject_required', { defaultValue: 'Subject is required' })
              : undefined
          }
        >
          <input
            id="corr-subject"
            value={form.subject}
            onChange={(e) => {
              set('subject', e.target.value);
              setTouched(true);
            }}
            placeholder={t('correspondence.subject_placeholder', {
              defaultValue: 'e.g. Notice of delay - Foundation works',
            })}
            className={clsx(
              inputCls,
              subjectError && 'border-semantic-error focus:ring-red-300 focus:border-semantic-error',
            )}
          />
        </WideModalField>
      </WideModalSection>

      {/* Parties — From / To side-by-side */}
      <WideModalSection
        title={t('correspondence.section_parties', { defaultValue: 'Parties' })}
        columns={2}
      >
        <WideModalField
          label={t('correspondence.field_from', { defaultValue: 'From' })}
          required
          htmlFor="corr-from"
          error={
            fromError
              ? t('correspondence.from_required', { defaultValue: 'From is required' })
              : undefined
          }
        >
          <ContactSearchInput
            value={form.from_contact}
            displayValue={form.from_display}
            onChange={(contactId, displayName) => {
              setForm((prev) => ({
                ...prev,
                from_contact: displayName || contactId,
                from_display: displayName,
              }));
              setTouched(true);
            }}
            placeholder={t('correspondence.from_placeholder', {
              defaultValue: 'Search contacts or type name...',
            })}
          />
        </WideModalField>

        <WideModalField
          label={t('correspondence.field_to', { defaultValue: 'To' })}
          htmlFor="corr-to"
        >
          <ContactSearchInput
            value={form.to_contacts}
            displayValue={form.to_display}
            onChange={(contactId, displayName) => {
              setForm((prev) => ({
                ...prev,
                to_contacts: displayName || contactId,
                to_display: displayName,
              }));
            }}
            placeholder={t('correspondence.to_placeholder', {
              defaultValue: 'Search contacts or type name...',
            })}
          />
        </WideModalField>
      </WideModalSection>

      {/* Dates side-by-side, notes spans both */}
      <WideModalSection
        title={t('correspondence.section_dates', { defaultValue: 'Dates' })}
        columns={2}
      >
        <WideModalField
          label={t('correspondence.field_date_sent', { defaultValue: 'Date Sent' })}
          htmlFor="corr-date-sent"
        >
          <input
            id="corr-date-sent"
            type="date"
            value={form.date_sent}
            onChange={(e) => set('date_sent', e.target.value)}
            className={inputCls}
          />
        </WideModalField>

        <WideModalField
          label={t('correspondence.field_date_received', { defaultValue: 'Date Received' })}
          htmlFor="corr-date-received"
        >
          <input
            id="corr-date-received"
            type="date"
            value={form.date_received}
            onChange={(e) => set('date_received', e.target.value)}
            className={inputCls}
          />
        </WideModalField>

        <WideModalField
          label={t('correspondence.field_notes', { defaultValue: 'Notes' })}
          span={2}
          htmlFor="corr-notes"
        >
          <textarea
            id="corr-notes"
            value={form.notes}
            onChange={(e) => set('notes', e.target.value)}
            rows={3}
            className={textareaCls}
            placeholder={t('correspondence.notes_placeholder', {
              defaultValue: 'Additional notes...',
            })}
          />
        </WideModalField>
      </WideModalSection>
    </WideModal>
  );
}

/* ── Correspondence Row (expandable) ──────────────────────────────────── */

const CorrespondenceRow = React.memo(function CorrespondenceRow({
  item,
  onEdit,
  onDelete,
}: {
  item: Correspondence;
  onEdit: (item: Correspondence) => void;
  onDelete: (item: Correspondence) => void;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const fromLabel = item.from_contact_id || '—';
  const toLabel =
    (item.to_contact_ids ?? []).length > 0
      ? (item.to_contact_ids ?? []).join(', ')
      : '—';
  const docCount = (item.linked_document_ids ?? []).length;

  return (
    <div className="border-b border-border-light last:border-b-0">
      {/* Main row */}
      <div
        className={clsx(
          'flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-surface-secondary/50 transition-colors',
          expanded && 'bg-surface-secondary/30',
        )}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={t('correspondence.toggle_row', { defaultValue: 'Toggle details for {{ref}}', ref: item.reference_number })}
        onClick={() => setExpanded((prev) => !prev)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded((prev) => !prev); } }}
      >
        <ChevronRight
          size={14}
          className={clsx(
            'text-content-tertiary transition-transform shrink-0',
            expanded && 'rotate-90',
          )}
        />

        {/* Ref # */}
        <span className="text-sm font-mono font-semibold text-content-secondary w-20 shrink-0">
          {item.reference_number}
        </span>

        {/* Subject */}
        <span className="text-sm text-content-primary truncate flex-1 min-w-0">
          {item.subject}
        </span>

        {/* Direction badge */}
        <Badge
          variant={item.direction === 'incoming' ? 'blue' : 'success'}
          size="sm"
          className="shrink-0"
        >
          {item.direction === 'incoming' ? (
            <ArrowDownLeft size={11} className="mr-1" />
          ) : (
            <ArrowUpRight size={11} className="mr-1" />
          )}
          {t(`correspondence.dir_${item.direction}`, {
            defaultValue: item.direction === 'incoming' ? 'Incoming' : 'Outgoing',
          })}
        </Badge>

        {/* Type */}
        <Badge variant="neutral" size="sm" className="hidden md:inline-flex">
          {t(`correspondence.type_${item.correspondence_type ?? 'letter'}`, { defaultValue: TYPE_LABELS[(item.correspondence_type ?? 'letter') as CorrespondenceType] })}
        </Badge>

        {/* From */}
        <span
          className="text-xs text-content-tertiary w-24 truncate shrink-0 hidden lg:block"
          title={fromLabel}
        >
          {fromLabel}
        </span>

        {/* To */}
        <span
          className="text-xs text-content-tertiary w-24 truncate shrink-0 hidden lg:block"
          title={toLabel}
        >
          {toLabel}
        </span>

        {/* Date */}
        <span className="text-xs w-20 shrink-0 hidden sm:block">
          <DateDisplay
            value={item.direction === 'outgoing' ? item.date_sent : item.date_received}
            className="text-xs text-content-tertiary"
          />
        </span>

        {/* Linked documents count — real count of referenced documents */}
        <span
          className="flex items-center gap-1 text-xs w-10 shrink-0 justify-end tabular-nums"
          title={t('correspondence.docs_count_title', {
            defaultValue: '{{count}} linked document(s)',
            count: docCount,
          })}
        >
          <FileText
            size={12}
            className={docCount > 0 ? 'text-oe-blue' : 'text-content-quaternary'}
          />
          <span className={docCount > 0 ? 'text-content-secondary' : 'text-content-quaternary'}>
            {docCount}
          </span>
        </span>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-4 pb-4 pl-12 space-y-3 animate-fade-in">
          <div className="flex items-center gap-4 text-xs text-content-tertiary flex-wrap">
            <span>
              {t('correspondence.label_from', { defaultValue: 'From' })}: {item.from_contact_id}
            </span>
            <span>
              {t('correspondence.label_to', { defaultValue: 'To' })}:{' '}
              {(item.to_contact_ids ?? []).length > 0 ? (item.to_contact_ids ?? []).join(', ') : '-'}
            </span>
            <span>
              {t('correspondence.label_sent', { defaultValue: 'Sent' })}:{' '}
              <DateDisplay value={item.date_sent} className="text-xs" />
            </span>
            <span>
              {t('correspondence.label_received', { defaultValue: 'Received' })}:{' '}
              <DateDisplay value={item.date_received} className="text-xs" />
            </span>
          </div>

          {item.notes && (
            <div className="rounded-lg bg-surface-secondary p-3">
              <p className="text-xs text-content-tertiary mb-1 font-medium uppercase tracking-wide">
                {t('correspondence.label_notes', { defaultValue: 'Notes' })}
              </p>
              <p className="text-sm text-content-primary whitespace-pre-wrap">{item.notes}</p>
            </div>
          )}

          {/* Linked references — connections to Documents / Transmittals / RFI */}
          {((item.linked_document_ids ?? []).length > 0 ||
            item.linked_transmittal_id ||
            item.linked_rfi_id) && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="inline-flex items-center gap-1 text-2xs uppercase tracking-wide text-content-tertiary">
                <Link2 size={11} />
                {t('correspondence.label_linked', { defaultValue: 'Linked' })}
              </span>
              {(item.linked_document_ids ?? []).length > 0 && (
                <Badge variant="neutral" size="sm">
                  <FileText size={11} className="mr-1" />
                  {t('correspondence.linked_docs', {
                    defaultValue: '{{count}} document(s)',
                    count: (item.linked_document_ids ?? []).length,
                  })}
                </Badge>
              )}
              {item.linked_transmittal_id && (
                <Link
                  to="/transmittals"
                  onClick={(e) => e.stopPropagation()}
                  className="inline-flex items-center gap-1 rounded-full bg-oe-blue/10 px-2 py-0.5 text-xs font-medium text-oe-blue hover:bg-oe-blue/20 transition-colors"
                >
                  <Send size={11} />
                  {t('correspondence.linked_transmittal', {
                    defaultValue: 'View transmittal',
                  })}
                </Link>
              )}
              {item.linked_rfi_id && (
                <Link
                  to={`/rfi/${item.linked_rfi_id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="inline-flex items-center gap-1 rounded-full bg-oe-blue/10 px-2 py-0.5 text-xs font-medium text-oe-blue hover:bg-oe-blue/20 transition-colors"
                >
                  <HelpCircle size={11} />
                  {t('correspondence.linked_rfi', { defaultValue: 'View RFI' })}
                </Link>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            <Button
              variant="secondary"
              size="sm"
              icon={<Pencil size={13} />}
              onClick={(e) => {
                e.stopPropagation();
                onEdit(item);
              }}
              data-testid={`correspondence-edit-${item.id}`}
            >
              {t('common.edit', { defaultValue: 'Edit' })}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              className="text-semantic-error hover:bg-red-50 dark:hover:bg-red-950/30"
              icon={<Trash2 size={13} />}
              onClick={(e) => {
                e.stopPropagation();
                onDelete(item);
              }}
              data-testid={`correspondence-delete-${item.id}`}
            >
              {t('common.delete', { defaultValue: 'Delete' })}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
});

/* ── Connector Card ───────────────────────────────────────────────────── */

function ConnectorCard({
  name,
  status,
  icon: Icon,
  description,
  onSetup,
}: {
  name: string;
  status: 'available' | 'coming_soon';
  icon: React.ElementType;
  description: string;
  onSetup?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border-light bg-surface-primary p-3 transition-colors hover:border-border-medium">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Icon size={16} className="shrink-0 text-content-tertiary" />
          <span className="text-sm font-medium text-content-primary truncate">{name}</span>
        </div>
        <Badge
          variant={status === 'available' ? 'success' : 'neutral'}
          size="sm"
          className="shrink-0"
        >
          {status === 'available'
            ? t('correspondence.connector_available', { defaultValue: 'Available' })
            : t('correspondence.connector_coming_soon', { defaultValue: 'Coming Soon' })}
        </Badge>
      </div>
      <p className="text-xs text-content-tertiary leading-relaxed">{description}</p>
      <div className="mt-1">
        {status === 'available' ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={onSetup}
          >
            {t('correspondence.setup_integration', { defaultValue: 'Set Up in Integrations' })}
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            disabled
            className="opacity-50 cursor-not-allowed"
          >
            {t('correspondence.connector_coming_soon', { defaultValue: 'Coming Soon' })}
          </Button>
        )}
      </div>
    </div>
  );
}

/* ── Main Page ─────────────────────────────────────────────────────────── */

export function CorrespondencePage() {
  const { t } = useTranslation();
  const { projectId: routeProjectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);

  // State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingItem, setEditingItem] = useState<Correspondence | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [directionFilter, setDirectionFilter] = useState<CorrespondenceDirection | ''>('');
  const [typeFilter, setTypeFilter] = useState<CorrespondenceType | ''>('');
  const [infoDismissed, setInfoDismissed] = useState(
    () => localStorage.getItem(LS_INFO_DISMISSED) === '1',
  );
  const { confirm, ...confirmProps } = useConfirm();

  // Data
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<Project[]>('/v1/projects/'),
    staleTime: 5 * 60_000,
  });

  const projectId = routeProjectId || activeProjectId || projects[0]?.id || '';
  const projectName = projects.find((p) => p.id === projectId)?.name || '';

  const {
    data: items = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['correspondence', projectId, directionFilter, typeFilter],
    queryFn: () =>
      fetchCorrespondence({
        project_id: projectId,
        direction: directionFilter || undefined,
        type: typeFilter || undefined,
      }),
    enabled: !!projectId,
  });

  // Client-side search
  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return items;
    const q = searchQuery.toLowerCase();
    return items.filter(
      (c) =>
        c.subject.toLowerCase().includes(q) ||
        c.reference_number.toLowerCase().includes(q) ||
        (c.from_contact_id || '').toLowerCase().includes(q) ||
        (c.to_contact_ids ?? []).some((tc) => tc.toLowerCase().includes(q)),
    );
  }, [items, searchQuery]);

  // Invalidation
  const invalidateAll = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['correspondence'] });
  }, [qc]);

  // Mutations
  const createMut = useMutation({
    mutationFn: (data: CreateCorrespondencePayload) => createCorrespondence(data),
    onSuccess: () => {
      invalidateAll();
      setShowCreateModal(false);
      addToast({
        type: 'success',
        title: t('correspondence.created', { defaultValue: 'Entry created' }),
      });
    },
    onError: (e: Error) =>
      addToast({
        type: 'error',
        title: t('common.error', { defaultValue: 'Error' }),
        message: e.message,
      }),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateCorrespondencePayload }) =>
      updateCorrespondence(id, data),
    onSuccess: () => {
      invalidateAll();
      setEditingItem(null);
      addToast({
        type: 'success',
        title: t('correspondence.updated', { defaultValue: 'Entry updated' }),
      });
    },
    onError: (e: Error) =>
      addToast({
        type: 'error',
        title: t('common.error', { defaultValue: 'Error' }),
        message: e.message,
      }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteCorrespondence(id),
    onSuccess: () => {
      invalidateAll();
      addToast({
        type: 'success',
        title: t('correspondence.deleted', { defaultValue: 'Entry deleted' }),
      });
    },
    onError: (e: Error) =>
      addToast({
        type: 'error',
        title: t('common.error', { defaultValue: 'Error' }),
        message: e.message,
      }),
  });

  const buildPayload = useCallback(
    (formData: CorrespondenceFormData) => ({
      subject: formData.subject,
      direction: formData.direction,
      correspondence_type: formData.type,
      from_contact_id: formData.from_contact || undefined,
      to_contact_ids: (formData.to_display || formData.to_contacts)
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      date_sent: formData.date_sent || undefined,
      date_received: formData.date_received || undefined,
      notes: formData.notes || undefined,
    }),
    [],
  );

  const handleCreateSubmit = useCallback(
    (formData: CorrespondenceFormData) => {
      if (!projectId) {
        addToast({ type: 'error', title: t('common.error', { defaultValue: 'Error' }), message: t('common.select_project_first', { defaultValue: 'Please select a project first' }) });
        return;
      }
      createMut.mutate({ project_id: projectId, ...buildPayload(formData) });
    },
    [createMut, projectId, addToast, t, buildPayload],
  );

  const handleEditSubmit = useCallback(
    (formData: CorrespondenceFormData) => {
      if (!editingItem) return;
      updateMut.mutate({ id: editingItem.id, data: buildPayload(formData) });
    },
    [updateMut, editingItem, buildPayload],
  );

  const formDataFromItem = useCallback(
    (c: Correspondence): CorrespondenceFormData => ({
      subject: c.subject,
      direction: c.direction,
      type: c.correspondence_type,
      from_contact: c.from_contact_id || '',
      from_display: c.from_contact_id || '',
      to_contacts: (c.to_contact_ids ?? []).join(', '),
      to_display: (c.to_contact_ids ?? []).join(', '),
      date_sent: c.date_sent || '',
      date_received: c.date_received || '',
      notes: c.notes || '',
    }),
    [],
  );

  const handleDelete = useCallback(
    async (item: Correspondence) => {
      const ok = await confirm({
        title: t('correspondence.confirm_delete_title', {
          defaultValue: 'Delete entry?',
        }),
        message: t('correspondence.confirm_delete_msg', {
          defaultValue: 'This permanently removes the entry "{{subject}}".',
          subject: item.subject,
        }),
        confirmLabel: t('common.delete', { defaultValue: 'Delete' }),
        variant: 'danger',
      });
      if (ok) deleteMut.mutate(item.id);
    },
    [deleteMut, confirm, t],
  );

  return (
    <div className="w-full animate-fade-in">
      {/* Breadcrumb */}
      <Breadcrumb
        items={[
          { label: t('nav.dashboard', { defaultValue: 'Dashboard' }), to: '/' },
          ...(projectName
            ? [{ label: projectName, to: `/projects/${projectId}` }]
            : []),
          { label: t('correspondence.title', { defaultValue: 'Correspondence' }) },
        ]}
        className="mb-4"
      />

      {/* Header */}
      <div className="mb-6 flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-2xl font-bold text-content-primary shrink-0">
          {t('correspondence.page_title', { defaultValue: 'Correspondence' })}
        </h1>

        <div className="flex items-center gap-2 shrink-0">
          {!routeProjectId && projects.length > 0 && (
            <select
              value={projectId}
              onChange={(e) => {
                const p = projects.find((pr) => pr.id === e.target.value);
                if (p) {
                  useProjectContextStore.getState().setActiveProject(p.id, p.name);
                }
              }}
              aria-label={t('correspondence.select_project', { defaultValue: 'Project...' })}
              className={inputCls + ' !h-8 !text-xs max-w-[180px]'}
            >
              <option value="" disabled>
                {t('correspondence.select_project', { defaultValue: 'Project...' })}
              </option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowCreateModal(true)}
            disabled={!projectId}
            title={!projectId ? t('common.select_project_first', { defaultValue: 'Please select a project first' }) : undefined}
            className="shrink-0 whitespace-nowrap"
            icon={<Plus size={14} />}
          >
            {t('correspondence.new_letter', { defaultValue: 'New Letter' })}
          </Button>
        </div>
      </div>

      {/* No-project warning */}
      {!projectId && (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
          {t('common.select_project_hint', { defaultValue: 'Select a project from the header to get started.' })}
        </div>
      )}

      {/* Purpose / help banner \u2014 explains what this register is for and how
          it connects to the rest of the platform. */}
      {!infoDismissed && (
        <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800 dark:border-blue-700 dark:bg-blue-950/30 dark:text-blue-300 relative">
          <button
            onClick={() => {
              setInfoDismissed(true);
              localStorage.setItem(LS_INFO_DISMISSED, '1');
            }}
            className="absolute top-2 right-2 flex h-6 w-6 items-center justify-center rounded text-blue-400 hover:text-blue-600 hover:bg-blue-100 dark:hover:bg-blue-900/40 dark:hover:text-blue-200 transition-colors"
            aria-label={t('common.dismiss', { defaultValue: 'Dismiss' })}
          >
            <X size={14} />
          </button>
          <div className="flex items-center gap-2 mb-1">
            <Info size={16} />
            <span className="font-semibold">
              {t('correspondence.info_title', { defaultValue: 'About the Correspondence Log' })}
            </span>
          </div>
          <p className="text-xs pr-6">
            {t('correspondence.info_body', {
              defaultValue:
                'A contemporaneous register of every formal letter, notice, email, and memo exchanged with project parties \u2014 the audit trail that protects you in disputes and claims. Log entries manually, or auto-import them via email/webhook integrations.',
            })}{' '}
            {t('correspondence.info_link_hint', {
              defaultValue:
                'Entries can be linked to Documents, Transmittals, and RFIs so a single thread of communication is traceable end-to-end.',
            })}
          </p>
        </div>
      )}

      {/* Cross-module links */}
      {projectId && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          <Button variant="ghost" size="sm" className="text-xs" onClick={() => navigate('/transmittals')}>
            <Send size={13} className="me-1" />
            {t('correspondence.link_transmittals', { defaultValue: 'Transmittals' })}
          </Button>
          <Button variant="ghost" size="sm" className="text-xs" onClick={() => navigate('/rfi')}>
            <HelpCircle size={13} className="me-1" />
            {t('correspondence.link_rfi', { defaultValue: 'RFIs' })}
          </Button>
          <Button variant="ghost" size="sm" className="text-xs" onClick={() => navigate('/documents')}>
            <FileText size={13} className="me-1" />
            {t('correspondence.link_documents', { defaultValue: 'Documents' })}
          </Button>
          <Button variant="ghost" size="sm" className="text-xs" onClick={() => navigate('/contacts')}>
            <Mail size={13} className="me-1" />
            {t('correspondence.link_contacts', { defaultValue: 'Contacts' })}
          </Button>
        </div>
      )}

      {/* Connectors */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <ConnectorCard
          name={t('correspondence.connector_email', { defaultValue: 'Email (IMAP/SMTP)' })}
          status="available"
          icon={Mail}
          description={t('correspondence.connector_email_desc', { defaultValue: 'Auto-import incoming/outgoing project emails' })}
          onSetup={() => navigate('/integrations')}
        />
        <ConnectorCard
          name={t('correspondence.connector_m365', { defaultValue: 'Microsoft 365' })}
          status="coming_soon"
          icon={Cloud}
          description={t('correspondence.connector_m365_desc', { defaultValue: 'Outlook emails & Teams messages' })}
        />
        <ConnectorCard
          name={t('correspondence.connector_google', { defaultValue: 'Google Workspace' })}
          status="coming_soon"
          icon={Cloud}
          description={t('correspondence.connector_google_desc', { defaultValue: 'Gmail & Google Chat' })}
        />
        <ConnectorCard
          name={t('correspondence.connector_webhook', { defaultValue: 'API Webhook' })}
          status="available"
          icon={Webhook}
          description={t('correspondence.connector_webhook_desc', { defaultValue: 'Receive correspondence via REST API' })}
          onSetup={() => navigate('/integrations')}
        />
      </div>

      {/* Toolbar */}
      <div className="mb-6 flex flex-col sm:flex-row sm:items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-content-tertiary"
          />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('correspondence.search_placeholder', {
              defaultValue: 'Search correspondence...',
            })}
            aria-label={t('correspondence.search_placeholder', { defaultValue: 'Search correspondence...' })}
            className={inputCls + ' pl-9'}
          />
        </div>

        {/* Direction filter */}
        <div className="relative">
          <select
            value={directionFilter}
            onChange={(e) =>
              setDirectionFilter(e.target.value as CorrespondenceDirection | '')
            }
            aria-label={t('correspondence.filter_all_dir', { defaultValue: 'All Directions' })}
            className="h-10 appearance-none rounded-lg border border-border bg-surface-primary pl-3 pr-9 text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue sm:w-36"
          >
            <option value="">
              {t('correspondence.filter_all_dir', { defaultValue: 'All Directions' })}
            </option>
            <option value="incoming">
              {t('correspondence.dir_incoming', { defaultValue: 'Incoming' })}
            </option>
            <option value="outgoing">
              {t('correspondence.dir_outgoing', { defaultValue: 'Outgoing' })}
            </option>
          </select>
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2.5 text-content-tertiary">
            <ChevronDown size={14} />
          </div>
        </div>

        {/* Type filter */}
        <div className="relative">
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as CorrespondenceType | '')}
            aria-label={t('correspondence.filter_all_type', { defaultValue: 'All Types' })}
            className="h-10 appearance-none rounded-lg border border-border bg-surface-primary pl-3 pr-9 text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue sm:w-36"
          >
            <option value="">
              {t('correspondence.filter_all_type', { defaultValue: 'All Types' })}
            </option>
            {(Object.keys(TYPE_LABELS) as CorrespondenceType[]).map((tp) => (
              <option key={tp} value={tp}>
                {t(`correspondence.type_${tp}`, { defaultValue: TYPE_LABELS[tp] })}
              </option>
            ))}
          </select>
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2.5 text-content-tertiary">
            <ChevronDown size={14} />
          </div>
        </div>
      </div>

      {/* Table */}
      <div>
        {isLoading ? (
          <SkeletonTable rows={5} columns={6} />
        ) : isError ? (
          <RecoveryCard error={error} onRetry={() => refetch()} />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<Mail size={28} strokeWidth={1.5} />}
            title={
              searchQuery || directionFilter || typeFilter
                ? t('correspondence.no_results', { defaultValue: 'No matching entries' })
                : t('correspondence.no_entries', { defaultValue: 'No correspondence yet' })
            }
            description={
              searchQuery || directionFilter || typeFilter
                ? t('correspondence.no_results_hint', {
                    defaultValue: 'Try adjusting your search or filters',
                  })
                : t('correspondence.no_entries_hint', {
                    defaultValue: 'Log your first correspondence entry',
                  })
            }
            action={
              !searchQuery && !directionFilter && !typeFilter
                ? {
                    label: t('correspondence.new_letter', { defaultValue: 'New Letter' }),
                    onClick: () => setShowCreateModal(true),
                  }
                : undefined
            }
          />
        ) : (
          <>
            <p className="mb-3 text-sm text-content-tertiary">
              {t('correspondence.showing_count', {
                defaultValue: '{{count}} entries',
                count: filtered.length,
              })}
            </p>
            <Card padding="none" className="overflow-x-auto">
              {/* Table header */}
              <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border-light bg-surface-secondary/30 text-2xs font-medium text-content-tertiary uppercase tracking-wider min-w-[640px]">
                <span className="w-5" />
                <span className="w-20">#</span>
                <span className="flex-1">
                  {t('correspondence.col_subject', { defaultValue: 'Subject' })}
                </span>
                <span className="w-24 text-center">
                  {t('correspondence.col_direction', { defaultValue: 'Direction' })}
                </span>
                <span className="w-20 hidden md:block">
                  {t('correspondence.col_type', { defaultValue: 'Type' })}
                </span>
                <span className="w-24 hidden lg:block">
                  {t('correspondence.col_from', { defaultValue: 'From' })}
                </span>
                <span className="w-24 hidden lg:block">
                  {t('correspondence.col_to', { defaultValue: 'To' })}
                </span>
                <span className="w-20 hidden sm:block">
                  {t('correspondence.col_date', { defaultValue: 'Date' })}
                </span>
                <span className="w-10 text-right">
                  {t('correspondence.col_docs', { defaultValue: 'Docs' })}
                </span>
              </div>

              {/* Rows */}
              {filtered.map((c) => (
                <CorrespondenceRow
                  key={c.id}
                  item={c}
                  onEdit={setEditingItem}
                  onDelete={handleDelete}
                />
              ))}
            </Card>
          </>
        )}
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <CreateCorrespondenceModal
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreateSubmit}
          isPending={createMut.isPending}
        />
      )}

      {/* Edit Modal */}
      {editingItem && (
        <CreateCorrespondenceModal
          isEdit
          initialData={formDataFromItem(editingItem)}
          onClose={() => setEditingItem(null)}
          onSubmit={handleEditSubmit}
          isPending={updateMut.isPending}
        />
      )}

      {/* Confirm Dialog (for delete) */}
      <ConfirmDialog {...confirmProps} />
    </div>
  );
}
