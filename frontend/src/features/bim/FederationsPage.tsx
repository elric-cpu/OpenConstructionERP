// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * BIM Federations — Slice 1.
 *
 * Lists/manages groups of N BIM models that share an origin (e.g.
 * architectural + structural + MEP). Slice 1 is data + list/detail UI
 * only; the federated 3D viewer that composes the members into a
 * single scene is deferred to Slice 2.
 *
 * Route: /bim/federations
 *
 * Endpoints (mounted at /api/v1/bim-hub/federations/ — note that the
 * module mounts under `bim-hub`/`bim_hub`, not the unqualified `/bim/`
 * prefix mentioned in early specs):
 *   GET    /federations/?project_id=...           — list
 *   POST   /federations/                          — create
 *   GET    /federations/{id}                      — detail with members
 *   PUT    /federations/{id}                      — update meta
 *   DELETE /federations/{id}                      — delete (cascade)
 *   POST   /federations/{id}/models               — add member
 *   DELETE /federations/{id}/models/{model_id}    — remove member
 */

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { apiGet, apiPost, apiDelete } from '@/shared/lib/api';
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  EmptyState,
  Input,
  WideModal,
  WideModalSection,
  WideModalField,
} from '@/shared/ui';

import { FederationTypeTree } from './FederationTypeTree';
import { FederatedViewer, type FederatedViewerHandle } from './FederatedViewer';

/* ── Types ─────────────────────────────────────────────────────────── */

type FederationDiscipline =
  | 'arch'
  | 'struct'
  | 'mep'
  | 'landscape'
  | 'civil'
  | 'other';

interface OriginOffset {
  x: number;
  y: number;
  z: number;
}

interface FederationMember {
  id: string;
  federation_id: string;
  bim_model_id: string;
  discipline: FederationDiscipline | string;
  color_hint: string | null;
  visible: boolean;
  z_order: number;
  created_at: string;
  updated_at: string;
}

interface FederationSummary {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  origin_offset: Partial<OriginOffset>;
  shared_units: string;
  member_count: number;
  created_at: string;
  updated_at: string;
}

interface FederationDetail extends FederationSummary {
  members: FederationMember[];
}

interface FederationListPayload {
  items: FederationSummary[];
  total: number;
}

interface ProjectLite {
  id: string;
  name: string;
}

interface BimModelLite {
  id: string;
  name: string;
  discipline: string | null;
}

interface BimModelsPayload {
  items: BimModelLite[];
  total: number;
}

const DISCIPLINE_PALETTE: Record<FederationDiscipline, string> = {
  arch: '#8b5cf6',
  struct: '#f97316',
  mep: '#0ea5e9',
  landscape: '#10b981',
  civil: '#737373',
  other: '#94a3b8',
};

const DISCIPLINE_ORDER: FederationDiscipline[] = [
  'arch',
  'struct',
  'mep',
  'landscape',
  'civil',
  'other',
];

/* ── API helpers ────────────────────────────────────────────────────── */

const BASE = '/v1/bim-hub/federations';

async function fetchProjects(): Promise<ProjectLite[]> {
  return apiGet<ProjectLite[]>('/v1/projects/');
}

async function fetchFederations(projectId: string): Promise<FederationListPayload> {
  return apiGet<FederationListPayload>(
    `${BASE}/?project_id=${encodeURIComponent(projectId)}`,
  );
}

async function fetchFederation(id: string): Promise<FederationDetail> {
  return apiGet<FederationDetail>(`${BASE}/${id}`);
}

async function fetchProjectBimModels(projectId: string): Promise<BimModelsPayload> {
  return apiGet<BimModelsPayload>(
    `/v1/bim-hub/?project_id=${encodeURIComponent(projectId)}`,
  );
}

interface CreateBody {
  project_id: string;
  name: string;
  description?: string;
  origin_offset?: OriginOffset;
  shared_units?: string;
}

async function createFederation(body: CreateBody): Promise<FederationSummary> {
  return apiPost<FederationSummary, CreateBody>(`${BASE}/`, body);
}

async function deleteFederation(id: string): Promise<void> {
  await apiDelete(`${BASE}/${id}`);
}

interface AddMemberBody {
  bim_model_id: string;
  discipline: FederationDiscipline;
  color_hint?: string | null;
  visible: boolean;
  z_order: number;
}

async function addMember(
  fedId: string,
  body: AddMemberBody,
): Promise<FederationMember> {
  return apiPost<FederationMember, AddMemberBody>(
    `${BASE}/${fedId}/models`,
    body,
  );
}

async function removeMember(fedId: string, modelId: string): Promise<void> {
  await apiDelete(`${BASE}/${fedId}/models/${modelId}`);
}

// PUT /federations/{id} is wired on the backend but the UI for inline
// metadata editing lands in Slice 2 together with the federated viewer.

/* ── New-federation modal ──────────────────────────────────────────── */

interface NewFederationModalProps {
  open: boolean;
  projectId: string;
  onClose: () => void;
  onCreated: (fed: FederationSummary) => void;
}

function NewFederationModal({
  open,
  projectId,
  onClose,
  onCreated,
}: NewFederationModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [sharedUnits, setSharedUnits] = useState('m');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = useCallback(() => {
    if (submitting) return;
    setName('');
    setDescription('');
    setSharedUnits('m');
    setError(null);
    onClose();
  }, [onClose, submitting]);

  const submit = useCallback(async () => {
    if (!name.trim()) {
      setError(t('bim.federation.error_name_required'));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await createFederation({
        project_id: projectId,
        name: name.trim(),
        description: description.trim() || undefined,
        shared_units: sharedUnits.trim() || 'm',
      });
      onCreated(created);
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }, [name, description, sharedUnits, projectId, onCreated, close, t]);

  return (
    <WideModal
      open={open}
      onClose={close}
      title={t('bim.federation.new_title')}
      subtitle={t('bim.federation.new_subtitle')}
      busy={submitting}
      size="md"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={close} disabled={submitting}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting
              ? t('bim.federation.creating')
              : t('bim.federation.create')}
          </Button>
        </div>
      }
    >
      <WideModalSection>
        <WideModalField label={t('bim.federation.field_name')}>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('bim.federation.placeholder_name')}
          />
        </WideModalField>
        <WideModalField label={t('bim.federation.field_description')}>
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t('bim.federation.placeholder_description')}
          />
        </WideModalField>
        <WideModalField label={t('bim.federation.field_shared_units')}>
          <Input
            value={sharedUnits}
            onChange={(e) => setSharedUnits(e.target.value)}
            placeholder="m"
          />
        </WideModalField>
        {error ? (
          <p className="mt-2 text-sm text-red-600" role="alert">
            {error}
          </p>
        ) : null}
      </WideModalSection>
    </WideModal>
  );
}

/* ── Detail drawer ──────────────────────────────────────────────────── */

interface FederationDetailDrawerProps {
  federationId: string | null;
  onClose: () => void;
  onChanged: () => void;
}

function FederationDetailDrawer({
  federationId,
  onClose,
  onChanged,
}: FederationDetailDrawerProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const open = federationId !== null;

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['bim-federation-detail', federationId],
    queryFn: () => fetchFederation(federationId as string),
    enabled: open,
  });

  const { data: modelsPayload } = useQuery({
    queryKey: ['bim-models', data?.project_id],
    queryFn: () => fetchProjectBimModels(data!.project_id),
    enabled: !!data?.project_id,
  });

  const [addingModelId, setAddingModelId] = useState<string>('');
  const [addingDiscipline, setAddingDiscipline] =
    useState<FederationDiscipline>('arch');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Slice 3: which sub-tab is visible inside the drawer. The "3D" tab
  // mounts the FederatedViewer; the type tree's onSelectClass callback
  // auto-switches to it so users see isolation take effect.
  const [activeTab, setActiveTab] = useState<'members' | 'types' | '3d'>(
    'members',
  );
  const viewerRef = useRef<FederatedViewerHandle | null>(null);
  const handleSelectClass = useCallback(
    (ifcClass: string /* , _modelIds: string[] */) => {
      setActiveTab('3d');
      // useImperativeHandle is set up on FederatedViewer; ref may be null
      // until the canvas mounts after the tab switch (effect runs on the
      // next tick). Defer the isolation push so the scene is alive.
      queueMicrotask(() => {
        viewerRef.current?.isolateClass(ifcClass);
      });
    },
    [],
  );

  const memberModelIds = useMemo(
    () => new Set((data?.members ?? []).map((m) => m.bim_model_id)),
    [data?.members],
  );

  const availableModels = useMemo(
    () =>
      (modelsPayload?.items ?? []).filter((m) => !memberModelIds.has(m.id)),
    [modelsPayload, memberModelIds],
  );

  const handleAdd = useCallback(async () => {
    if (!data || !addingModelId) return;
    setBusy(true);
    setError(null);
    try {
      await addMember(data.id, {
        bim_model_id: addingModelId,
        discipline: addingDiscipline,
        color_hint: DISCIPLINE_PALETTE[addingDiscipline] ?? null,
        visible: true,
        z_order: data.members.length,
      });
      setAddingModelId('');
      await refetch();
      onChanged();
      void queryClient.invalidateQueries({
        queryKey: ['bim-federation-detail', data.id],
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [data, addingModelId, addingDiscipline, refetch, onChanged, queryClient]);

  const handleRemove = useCallback(
    async (modelId: string) => {
      if (!data) return;
      setBusy(true);
      setError(null);
      try {
        await removeMember(data.id, modelId);
        await refetch();
        onChanged();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [data, refetch, onChanged],
  );

  const handleToggleVisible = useCallback(
    (_member: FederationMember) => {
      // Slice 1: visible/z_order edits are read-only in this slice.
      // The PATCH-member endpoint that flips visibility / re-orders
      // membership lands in Slice 2 alongside the federated 3D viewer.
      onChanged();
    },
    [onChanged],
  );

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-2xl flex-col border-l border-slate-200 bg-white shadow-xl"
    >
      <header className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            {data?.name ?? t('bim.federation.loading')}
          </h2>
          {data?.description ? (
            <p className="mt-0.5 text-sm text-slate-500">{data.description}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-slate-500 hover:bg-slate-100"
          aria-label={t('common.close', { defaultValue: 'Close' })}
        >
          ×
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {isLoading ? (
          <p className="text-sm text-slate-500">
            {t('bim.federation.loading')}
          </p>
        ) : data ? (
          <>
            <div className="mb-4 grid grid-cols-3 gap-3 text-sm">
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">
                  {t('bim.federation.field_shared_units')}
                </div>
                <div className="text-slate-700">{data.shared_units}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">
                  {t('bim.federation.member_count')}
                </div>
                <div className="text-slate-700">{data.member_count}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">
                  {t('bim.federation.field_origin_offset')}
                </div>
                <div className="text-slate-700">
                  {`${data.origin_offset.x ?? 0}, ${data.origin_offset.y ?? 0}, ${data.origin_offset.z ?? 0}`}
                </div>
              </div>
            </div>

            {/* Slice 3: 3-tab layout — Members / Element types / 3D. The
                3D tab mounts the FederatedViewer; selecting a class from
                the type tree auto-switches to it and isolates that class
                in the viewer via the imperative ref handle. */}
            <div
              role="tablist"
              aria-label={t('bim.federation.tabs_label', {
                defaultValue: 'Federation views',
              })}
              className="mb-3 flex items-center gap-1 border-b border-slate-200"
            >
              {(
                [
                  ['members', t('bim.federation.tab_members', { defaultValue: 'Members' })],
                  ['types', t('bim.federation.tab_types', { defaultValue: 'Element types' })],
                  ['3d', t('bim.federation.tab_3d', { defaultValue: '3D' })],
                ] as Array<[typeof activeTab, string]>
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === key}
                  data-testid={`federation-tab-${key}`}
                  onClick={() => setActiveTab(key)}
                  className={
                    'px-3 py-1.5 -mb-px border-b-2 text-sm font-medium transition-colors ' +
                    (activeTab === key
                      ? 'border-oe-blue text-oe-blue'
                      : 'border-transparent text-slate-500 hover:text-slate-700')
                  }
                >
                  {label}
                </button>
              ))}
            </div>

            {activeTab === 'members' ? (
              <div data-testid="federation-tab-panel-members" role="tabpanel">
                <h3 className="mb-2 text-sm font-semibold text-slate-700">
                  {t('bim.federation.members')}
                </h3>
                {data.members.length === 0 ? (
                  <p className="mb-4 text-sm text-slate-500">
                    {t('bim.federation.no_members')}
                  </p>
                ) : (
                  <ul className="mb-4 divide-y divide-slate-100 rounded border border-slate-200">
                    {data.members.map((m) => (
                      <li
                        key={m.id}
                        className="flex items-center justify-between gap-3 px-3 py-2"
                      >
                        <div className="flex items-center gap-3">
                          <span
                            className="inline-block h-4 w-4 rounded"
                            style={{
                              backgroundColor:
                                m.color_hint ||
                                DISCIPLINE_PALETTE[
                                  m.discipline as FederationDiscipline
                                ] ||
                                '#94a3b8',
                            }}
                            aria-hidden
                          />
                          <Badge>{t(`bim.federation.disc_${m.discipline}`, {
                            defaultValue: m.discipline,
                          })}</Badge>
                          <span className="text-sm text-slate-700">
                            {m.bim_model_id.slice(0, 8)}
                          </span>
                          <span className="text-xs text-slate-400">
                            z={m.z_order}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleToggleVisible(m)}
                            className="text-xs text-slate-500 hover:text-slate-700"
                          >
                            {m.visible
                              ? t('bim.federation.visible')
                              : t('bim.federation.hidden')}
                          </button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRemove(m.bim_model_id)}
                            disabled={busy}
                          >
                            {t('bim.federation.remove')}
                          </Button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}

                <h3 className="mb-2 text-sm font-semibold text-slate-700">
                  {t('bim.federation.add_member')}
                </h3>
                <div className="flex flex-wrap items-end gap-2">
                  <label className="flex flex-col text-xs text-slate-500">
                    {t('bim.federation.bim_model')}
                    <select
                      value={addingModelId}
                      onChange={(e) => setAddingModelId(e.target.value)}
                      className="mt-1 rounded border border-slate-300 px-2 py-1 text-sm"
                    >
                      <option value="">
                        {t('bim.federation.select_model')}
                      </option>
                      {availableModels.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col text-xs text-slate-500">
                    {t('bim.federation.field_discipline')}
                    <select
                      value={addingDiscipline}
                      onChange={(e) =>
                        setAddingDiscipline(e.target.value as FederationDiscipline)
                      }
                      className="mt-1 rounded border border-slate-300 px-2 py-1 text-sm"
                    >
                      {DISCIPLINE_ORDER.map((d) => (
                        <option key={d} value={d}>
                          {t(`bim.federation.disc_${d}`, { defaultValue: d })}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Button
                    onClick={handleAdd}
                    disabled={busy || !addingModelId}
                    size="sm"
                  >
                    {t('bim.federation.add')}
                  </Button>
                </div>
                {error ? (
                  <p className="mt-2 text-sm text-red-600">{error}</p>
                ) : null}
              </div>
            ) : null}

            {activeTab === 'types' ? (
              <div data-testid="federation-tab-panel-types" role="tabpanel">
                {/* Slice 2: federation-flat (NOT per-model) element-type
                    tree. Mirrors BIMcollab Zoom — IfcClass is the primary
                    axis so cross-model selections ("color all
                    IfcDuctSegment red") are a single click. */}
                <FederationTypeTree
                  federationId={data.id}
                  onSelectClass={handleSelectClass}
                />
              </div>
            ) : null}

            {activeTab === '3d' ? (
              <div data-testid="federation-tab-panel-3d" role="tabpanel">
                <FederatedViewer ref={viewerRef} federationId={data.id} />
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────────────── */

export function FederationsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [projectId, setProjectId] = useState<string>('');
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedFedId, setSelectedFedId] = useState<string | null>(null);

  const { data: projects } = useQuery({
    queryKey: ['projects-lite-for-federations'],
    queryFn: fetchProjects,
  });

  // Auto-pick the first project once the list loads. Runs in an effect so
  // we never call setState during render (React 18 strict mode logs a
  // warning that previously blanked the page in dev).
  useEffect(() => {
    if (!projectId && Array.isArray(projects) && projects.length > 0) {
      setProjectId(projects[0]!.id);
    }
  }, [projects, projectId]);

  const { data: federations, isLoading, refetch } = useQuery({
    queryKey: ['bim-federations', projectId],
    queryFn: () => fetchFederations(projectId),
    enabled: !!projectId,
  });

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: ['bim-federations', projectId],
    });
  }, [queryClient, projectId]);

  const handleDelete = useCallback(
    async (id: string) => {
      const confirmed = window.confirm(t('bim.federation.confirm_delete'));
      if (!confirmed) return;
      try {
        await deleteFederation(id);
        void refetch();
        if (selectedFedId === id) setSelectedFedId(null);
      } catch (e) {
        window.alert(e instanceof Error ? e.message : String(e));
      }
    },
    [refetch, selectedFedId, t],
  );

  return (
    <div className="w-full animate-fade-in">
      <header className="mb-4 rounded-xl border border-border-light bg-surface-primary px-5 py-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-content-primary">
              {t('bim.federation.page_title')}
            </h1>
            <p className="mt-1 text-sm text-content-tertiary">
              {t('bim.federation.page_subtitle')}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-xs font-medium text-content-tertiary">
              {t('bim.federation.project')}
              <select
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                disabled={!projects || projects.length === 0}
                className="rounded-md border border-border-light bg-surface-primary px-2.5 py-1.5 text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue/40"
              >
                {(projects ?? []).length === 0 && (
                  <option value="">
                    {t('bim.no_projects_available', { defaultValue: 'No projects available' })}
                  </option>
                )}
                {(projects ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <Button
              onClick={() => setCreateOpen(true)}
              disabled={!projectId}
            >
              {t('bim.federation.new')}
            </Button>
          </div>
        </div>
      </header>

      <section className="min-h-[60vh]">
        {!projectId ? (
          <EmptyState
            title={t('bim.no_project')}
            description={t('bim.no_project_desc')}
          />
        ) : isLoading ? (
          <p className="px-2 py-6 text-sm text-content-tertiary">
            {t('bim.federation.loading')}
          </p>
        ) : !federations || federations.total === 0 ? (
          <EmptyState
            title={t('bim.federation.empty_title')}
            description={t('bim.federation.empty_desc')}
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {federations.items.map((f) => (
              <Card key={f.id} className="hover:shadow-md transition-shadow">
                <CardHeader
                  title={f.name}
                  subtitle={
                    f.description ?? t('bim.federation.no_description')
                  }
                />
                <CardContent>
                  <div className="flex items-center justify-between text-sm">
                    <Badge>
                      {t('bim.federation.member_count_n', {
                        count: f.member_count,
                        defaultValue: `${f.member_count} models`,
                      })}
                    </Badge>
                    <span className="text-xs text-content-quaternary">
                      {f.shared_units}
                    </span>
                  </div>
                  <div className="mt-3 flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelectedFedId(f.id)}
                    >
                      {t('bim.federation.open')}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(f.id)}
                    >
                      {t('bim.federation.delete')}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      <NewFederationModal
        open={createOpen}
        projectId={projectId}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false);
          invalidate();
          void refetch();
        }}
      />

      <FederationDetailDrawer
        federationId={selectedFedId}
        onClose={() => setSelectedFedId(null)}
        onChanged={invalidate}
      />
    </div>
  );
}

