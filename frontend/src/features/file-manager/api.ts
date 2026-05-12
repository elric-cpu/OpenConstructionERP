/** API client for the project file manager (Issue #109). */

import { apiDelete, apiGet, apiPost } from '@/shared/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';
import type {
  EmailLinkResponse,
  ExportOptions,
  ExportPreview,
  FileFilters,
  FileKind,
  FileListResponse,
  FileTreeNode,
  FolderPermissionCreatePayload,
  FolderPermissionRow,
  ImportMode,
  ImportPreview,
  ImportResult,
  ShareLinkAccessResponse,
  ShareLinkCreatePayload,
  ShareLinkPublicInfo,
  ShareLinkResponse,
  StorageLocations,
} from './types';

const PROJECTS_BASE = '/v1/projects';

function buildAuthHeaders(): Headers {
  const headers = new Headers({ Accept: 'application/json' });
  const token = useAuthStore.getState().accessToken;
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return headers;
}

export async function fetchFileTree(projectId: string): Promise<FileTreeNode[]> {
  return apiGet<FileTreeNode[]>(`${PROJECTS_BASE}/${projectId}/files/tree/`);
}

export async function fetchFileList(
  projectId: string,
  filters: FileFilters = {},
): Promise<FileListResponse> {
  const params = new URLSearchParams();
  if (filters.category) params.set('category', filters.category);
  if (filters.extension) params.set('extension', filters.extension);
  if (filters.q) params.set('q', filters.q);
  if (filters.sort) params.set('sort', filters.sort);
  if (filters.limit !== undefined) params.set('limit', String(filters.limit));
  if (filters.offset !== undefined) params.set('offset', String(filters.offset));
  const qs = params.toString();
  const path = `${PROJECTS_BASE}/${projectId}/files/${qs ? `?${qs}` : ''}`;
  return apiGet<FileListResponse>(path);
}

export async function fetchStorageLocations(projectId: string): Promise<StorageLocations> {
  return apiGet<StorageLocations>(`${PROJECTS_BASE}/${projectId}/files/locations/`);
}

export async function previewExport(
  projectId: string,
  options: ExportOptions,
): Promise<ExportPreview> {
  return apiPost<ExportPreview, ExportOptions>(
    `${PROJECTS_BASE}/${projectId}/export/preview/`,
    options,
  );
}

/** Download the .ocep zip for ``projectId`` and trigger a browser save. */
export async function downloadBundle(
  projectId: string,
  options: ExportOptions,
  fallbackName = 'project.ocep',
): Promise<{ filename: string; sizeBytes: number }> {
  const res = await fetch(`/api${PROJECTS_BASE}/${projectId}/export/`, {
    method: 'POST',
    headers: { ...Object.fromEntries(buildAuthHeaders()), 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      // not JSON — keep statusText
    }
    throw new Error(detail || `Export failed (${res.status})`);
  }
  // Pull filename from Content-Disposition.
  const cd = res.headers.get('content-disposition') || '';
  const match = cd.match(/filename="?([^"]+)"?/);
  const filename = match?.[1] ?? fallbackName;

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.style.display = 'none';
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 1000);
  return { filename, sizeBytes: blob.size };
}

export async function validateImport(file: File): Promise<ImportPreview> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`/api${PROJECTS_BASE}/import/validate/`, {
    method: 'POST',
    headers: buildAuthHeaders(),
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `Bundle is invalid (${res.status})`);
  }
  return (await res.json()) as ImportPreview;
}

export async function commitImport(opts: {
  file: File;
  mode: ImportMode;
  targetProjectId?: string;
  newProjectName?: string;
}): Promise<ImportResult> {
  const form = new FormData();
  form.append('file', opts.file);
  form.append('mode', opts.mode);
  if (opts.targetProjectId) form.append('target_project_id', opts.targetProjectId);
  if (opts.newProjectName) form.append('new_project_name', opts.newProjectName);
  const res = await fetch(`/api${PROJECTS_BASE}/import/`, {
    method: 'POST',
    headers: buildAuthHeaders(),
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `Import failed (${res.status})`);
  }
  return (await res.json()) as ImportResult;
}

export async function mintEmailLink(
  fileId: string,
  ttlHours = 72,
): Promise<EmailLinkResponse> {
  return apiPost<EmailLinkResponse, void>(
    `${PROJECTS_BASE}/files/${fileId}/email-link/?ttl_hours=${ttlHours}`,
  );
}

/* ── Password-protected share links ──────────────────────────────────── */

const DOCUMENTS_BASE = '/v1/documents';

/** Mint a new share link for the given document. */
export async function createShareLink(
  documentId: string,
  payload: ShareLinkCreatePayload,
): Promise<ShareLinkResponse> {
  return apiPost<ShareLinkResponse, ShareLinkCreatePayload>(
    `${DOCUMENTS_BASE}/${documentId}/share-links/`,
    payload,
  );
}

/** List active (non-revoked) share links for a document. Owner-only. */
export async function listShareLinks(
  documentId: string,
): Promise<ShareLinkResponse[]> {
  return apiGet<ShareLinkResponse[]>(
    `${DOCUMENTS_BASE}/${documentId}/share-links/`,
  );
}

/** Soft-revoke a share link. Owner-only. */
export async function revokeShareLink(
  documentId: string,
  linkId: string,
): Promise<void> {
  const res = await fetch(
    `/api${DOCUMENTS_BASE}/${documentId}/share-links/${linkId}/`,
    {
      method: 'DELETE',
      headers: buildAuthHeaders(),
    },
  );
  if (!res.ok && res.status !== 204) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `Revoke failed (${res.status})`);
  }
}

/* ── Public (unauthenticated) endpoints used by /share/:token ────────── */

/** Recipient-facing probe — returns filename + flags. No auth required. */
export async function fetchShareLinkInfo(
  token: string,
): Promise<ShareLinkPublicInfo> {
  const res = await fetch(`/api${DOCUMENTS_BASE}/share-links/${token}/`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `Link not found (${res.status})`);
  }
  return (await res.json()) as ShareLinkPublicInfo;
}

/* ── Folder permissions (owner-only) ─────────────────────────────────── */

/** List all non-revoked folder permissions for a project. */
export async function listFolderPermissions(
  projectId: string,
  filters: { scope_kind?: string; scope_path?: string | null } = {},
): Promise<FolderPermissionRow[]> {
  const params = new URLSearchParams();
  if (filters.scope_kind) params.set('scope_kind', filters.scope_kind);
  if (filters.scope_path) params.set('scope_path', filters.scope_path);
  const qs = params.toString();
  const path = `${PROJECTS_BASE}/${projectId}/folder-permissions/${qs ? `?${qs}` : ''}`;
  return apiGet<FolderPermissionRow[]>(path);
}

/** Grant viewer / editor / owner role to a member on a (kind, path) folder. */
export async function grantFolderPermission(
  projectId: string,
  payload: FolderPermissionCreatePayload,
): Promise<FolderPermissionRow> {
  return apiPost<FolderPermissionRow, FolderPermissionCreatePayload>(
    `${PROJECTS_BASE}/${projectId}/folder-permissions/`,
    payload,
  );
}

/** Soft-revoke a folder grant by id. */
export async function revokeFolderPermission(
  projectId: string,
  permissionId: string,
): Promise<void> {
  const res = await fetch(
    `/api${PROJECTS_BASE}/${projectId}/folder-permissions/${permissionId}/`,
    {
      method: 'DELETE',
      headers: buildAuthHeaders(),
    },
  );
  if (!res.ok && res.status !== 204) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `Revoke failed (${res.status})`);
  }
}

/* ── Public (unauthenticated) endpoints used by /share/:token ────────── */

/** Submit the password (if any), receive the authenticated download URL. */
export async function accessShareLink(
  token: string,
  password?: string,
): Promise<ShareLinkAccessResponse> {
  const res = await fetch(
    `/api${DOCUMENTS_BASE}/share-links/${token}/access/`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ password: password ?? null }),
    },
  );
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `Access failed (${res.status})`);
  }
  return (await res.json()) as ShareLinkAccessResponse;
}

/* ── Per-kind delete helpers (bulk-delete dispatcher) ────────────────── */

/** Bulk-delete response shape returned by /v1/documents/batch/delete/. */
export interface BulkDeleteResponse {
  requested: number;
  deleted: number;
}

/** Outcome of a single per-kind delete pass. */
export interface KindDeleteOutcome {
  kind: FileKind;
  requested: number;
  deleted: number;
  errors: { id: string; message: string }[];
}

/** Per-id DELETE for a single file row. Falls back to per-id loops when
 * the receiving module exposes no batch endpoint. Errors bubble so the
 * dispatcher can record a per-id failure entry.
 */
export async function deleteByKind(kind: FileKind, fileId: string): Promise<void> {
  const path = deletePathForKind(kind, fileId);
  await apiDelete(path);
}

/** Bulk-delete documents through the existing module-side batch endpoint. */
export async function bulkDeleteDocuments(ids: string[]): Promise<BulkDeleteResponse> {
  return apiPost<BulkDeleteResponse, { ids: string[] }>(
    '/v1/documents/batch/delete/',
    { ids },
  );
}

/** Build the canonical DELETE path for one file kind + id. Exported so
 * tests and the dispatcher share the same routing table.
 */
export function deletePathForKind(kind: FileKind, fileId: string): string {
  const enc = encodeURIComponent(fileId);
  switch (kind) {
    case 'document':
      return `/v1/documents/${enc}`;
    case 'photo':
      return `/v1/documents/photos/${enc}`;
    case 'sheet':
      return `/v1/documents/sheets/${enc}`;
    case 'bim_model':
      return `/v1/bim_hub/${enc}`;
    case 'dwg_drawing':
      return `/v1/dwg_takeoff/drawings/${enc}`;
    case 'takeoff':
      return `/v1/takeoff/documents/${enc}`;
    case 'report':
      return `/v1/reporting/reports/${enc}`;
    case 'markup':
      return `/v1/markups/${enc}`;
  }
}
