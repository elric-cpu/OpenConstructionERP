// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// REST client for Approval Routes (Wave 2, Epic A).
//
// Backend module: backend/app/modules/approval_routes/router.py (mounted
// at /api/v1/approval-routes/). Endpoints assumed (per Wave-2 coordination
// note):
//
//   GET    /v1/approval-routes/routes?project_id=&target_kind=
//   POST   /v1/approval-routes/routes
//   PATCH  /v1/approval-routes/routes/{id}
//   DELETE /v1/approval-routes/routes/{id}
//   GET    /v1/approval-routes/instances?target_kind=&target_id=
//   POST   /v1/approval-routes/instances
//   POST   /v1/approval-routes/instances/{id}/decide
//   POST   /v1/approval-routes/instances/{id}/cancel
//
// If the backend ships a slightly different shape at merge time the
// helpers below are the single integration point — keep ``BASE`` and the
// query-string conventions in lock-step with router.py.

import { apiDelete, apiGet, apiPatch, apiPost } from '@/shared/lib/api';
import type {
  ApprovalInstance,
  ApprovalRoute,
  ApprovalRouteCreatePayload,
  ApprovalRoutesMeta,
  ApprovalRouteUpdatePayload,
  Escalation,
  InstanceCancelPayload,
  InstanceCreatePayload,
  InstanceDecidePayload,
} from './types';

const BASE = '/v1/approval-routes';

/* ── Metadata ────────────────────────────────────────────────────────── */

/** Validated whitelists (target kinds / modes / statuses) straight from
 *  the backend — single source of truth so the UI never drifts. */
export async function getMeta(): Promise<ApprovalRoutesMeta> {
  return apiGet<ApprovalRoutesMeta>(`${BASE}/meta`);
}

/* ── Route templates ─────────────────────────────────────────────────── */

export interface ListRoutesParams {
  projectId?: string | null;
  targetKind?: string | null;
  /** Whether to include archived (``is_active=false``) routes. The
   *  backend defaults to ``true`` (admin surface). Pass ``false`` from a
   *  consumer picker so users can only start a workflow on an active
   *  template. */
  includeInactive?: boolean;
}

export async function listRoutes(
  params: ListRoutesParams = {},
): Promise<ApprovalRoute[]> {
  const qs = new URLSearchParams();
  if (params.projectId) qs.set('project_id', params.projectId);
  if (params.targetKind) qs.set('target_kind', params.targetKind);
  // The backend defaults include_inactive=true; only send it when the
  // caller explicitly wants to restrict to active routes.
  if (params.includeInactive === false) qs.set('include_inactive', 'false');
  const query = qs.toString();
  return apiGet<ApprovalRoute[]>(`${BASE}/routes${query ? `?${query}` : ''}`);
}

export async function getRoute(routeId: string): Promise<ApprovalRoute> {
  return apiGet<ApprovalRoute>(`${BASE}/routes/${routeId}`);
}

export async function createRoute(
  payload: ApprovalRouteCreatePayload,
): Promise<ApprovalRoute> {
  return apiPost<ApprovalRoute, ApprovalRouteCreatePayload>(
    `${BASE}/routes`,
    payload,
  );
}

export async function updateRoute(
  routeId: string,
  payload: ApprovalRouteUpdatePayload,
): Promise<ApprovalRoute> {
  return apiPatch<ApprovalRoute, ApprovalRouteUpdatePayload>(
    `${BASE}/routes/${routeId}`,
    payload,
  );
}

export async function deleteRoute(routeId: string): Promise<void> {
  await apiDelete<void>(`${BASE}/routes/${routeId}`);
}

/* ── Running instances ──────────────────────────────────────────────── */

export interface ListInstancesParams {
  targetKind?: string | null;
  targetId?: string | null;
  projectId?: string | null;
  status?: string | null;
}

export async function listInstances(
  params: ListInstancesParams = {},
): Promise<ApprovalInstance[]> {
  const qs = new URLSearchParams();
  if (params.targetKind) qs.set('target_kind', params.targetKind);
  if (params.targetId) qs.set('target_id', params.targetId);
  if (params.projectId) qs.set('project_id', params.projectId);
  if (params.status) qs.set('status', params.status);
  const query = qs.toString();
  return apiGet<ApprovalInstance[]>(
    `${BASE}/instances${query ? `?${query}` : ''}`,
  );
}

export async function getInstance(
  instanceId: string,
): Promise<ApprovalInstance> {
  return apiGet<ApprovalInstance>(`${BASE}/instances/${instanceId}`);
}

/** Escalation standing of an instance's current step (#17). Surfaces how
 *  overdue the live step is and whether the breach has aged past its grace
 *  window into an escalation up the route's approver chain. */
export async function getInstanceEscalation(
  instanceId: string,
): Promise<Escalation> {
  return apiGet<Escalation>(`${BASE}/instances/${instanceId}/escalation`);
}

export async function startInstance(
  payload: InstanceCreatePayload,
): Promise<ApprovalInstance> {
  return apiPost<ApprovalInstance, InstanceCreatePayload>(
    `${BASE}/instances`,
    payload,
  );
}

export async function decideInstance(
  instanceId: string,
  payload: InstanceDecidePayload,
): Promise<ApprovalInstance> {
  return apiPost<ApprovalInstance, InstanceDecidePayload>(
    `${BASE}/instances/${instanceId}/decide`,
    payload,
  );
}

export async function cancelInstance(
  instanceId: string,
  payload: InstanceCancelPayload = {},
): Promise<ApprovalInstance> {
  return apiPost<ApprovalInstance, InstanceCancelPayload>(
    `${BASE}/instances/${instanceId}/cancel`,
    payload,
  );
}

/* ── React Query keys (single source of truth) ──────────────────────── */

export const approvalRoutesKeys = {
  /** Validated whitelists (target kinds / modes / statuses). */
  meta: () => ['approval-routes', 'meta'] as const,
  /** List of route templates filtered by project + target kind. */
  routes: (projectId?: string | null, targetKind?: string | null) =>
    ['approval-routes', 'routes', projectId ?? null, targetKind ?? null] as const,
  /** Single route detail. */
  route: (id: string) => ['approval-routes', 'route', id] as const,
  /** List of instances filtered by target. */
  instances: (
    targetKind?: string | null,
    targetId?: string | null,
    projectId?: string | null,
    status?: string | null,
  ) =>
    [
      'approval-routes',
      'instances',
      targetKind ?? null,
      targetId ?? null,
      projectId ?? null,
      status ?? null,
    ] as const,
  /** Single running instance. */
  instance: (id: string) => ['approval-routes', 'instance', id] as const,
  /** Escalation standing of a single running instance's current step. */
  escalation: (id: string) =>
    ['approval-routes', 'escalation', id] as const,
};
