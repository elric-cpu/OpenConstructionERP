/**
 * API helpers for Correspondence Log.
 *
 * All endpoints are prefixed with /v1/correspondence/.
 */

import { apiDelete, apiGet, apiPatch, apiPost, triggerDownload } from '@/shared/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type CorrespondenceDirection = 'incoming' | 'outgoing';

export type CorrespondenceType = 'letter' | 'email' | 'notice' | 'memo';

export interface Correspondence {
  id: string;
  project_id: string;
  reference_number: string;
  subject: string;
  direction: CorrespondenceDirection;
  correspondence_type: CorrespondenceType;
  from_contact_id: string | null;
  to_contact_ids: string[];
  date_sent: string | null;
  date_received: string | null;
  /** Document UUIDs from the Documents module referenced by this entry. */
  linked_document_ids: string[];
  /** Optional link back to the Transmittal this letter relates to. */
  linked_transmittal_id: string | null;
  /** Optional link back to the RFI this letter relates to. */
  linked_rfi_id: string | null;
  /** Server-derived relative paths of validated uploaded attachments. */
  attachments: string[];
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CorrespondenceFilters {
  project_id?: string;
  direction?: CorrespondenceDirection | '';
  type?: CorrespondenceType | '';
}

export interface CreateCorrespondencePayload {
  project_id: string;
  subject: string;
  direction: CorrespondenceDirection;
  correspondence_type: CorrespondenceType;
  from_contact_id?: string;
  to_contact_ids?: string[];
  date_sent?: string;
  date_received?: string;
  linked_document_ids?: string[];
  linked_transmittal_id?: string | null;
  linked_rfi_id?: string | null;
  notes?: string;
}

export interface UpdateCorrespondencePayload {
  subject?: string;
  direction?: CorrespondenceDirection;
  correspondence_type?: CorrespondenceType;
  from_contact_id?: string;
  to_contact_ids?: string[];
  date_sent?: string;
  date_received?: string;
  linked_document_ids?: string[];
  linked_transmittal_id?: string | null;
  linked_rfi_id?: string | null;
  notes?: string | null;
}

/**
 * The API may not always return the newer link arrays on every record
 * (older rows / partial serialisers). Normalise so the UI never has to
 * guard `undefined` on `.length`.
 */
type CorrespondenceWire = Omit<
  Correspondence,
  | 'to_contact_ids'
  | 'linked_document_ids'
  | 'linked_transmittal_id'
  | 'linked_rfi_id'
  | 'attachments'
> & {
  to_contact_ids?: string[] | null;
  linked_document_ids?: string[] | null;
  linked_transmittal_id?: string | null;
  linked_rfi_id?: string | null;
  attachments?: string[] | null;
};

function normaliseCorrespondence(c: CorrespondenceWire): Correspondence {
  return {
    ...c,
    to_contact_ids: c.to_contact_ids ?? [],
    linked_document_ids: c.linked_document_ids ?? [],
    linked_transmittal_id: c.linked_transmittal_id ?? null,
    linked_rfi_id: c.linked_rfi_id ?? null,
    attachments: c.attachments ?? [],
  } as Correspondence;
}

/* ── API Functions ─────────────────────────────────────────────────────── */

export async function fetchCorrespondence(
  filters?: CorrespondenceFilters,
): Promise<Correspondence[]> {
  const params = new URLSearchParams();
  if (filters?.project_id) params.set('project_id', filters.project_id);
  if (filters?.direction) params.set('direction', filters.direction);
  if (filters?.type) params.set('type', filters.type);
  const qs = params.toString();
  const rows = await apiGet<CorrespondenceWire[]>(
    `/v1/correspondence/${qs ? `?${qs}` : ''}`,
  );
  return rows.map(normaliseCorrespondence);
}

export async function createCorrespondence(
  data: CreateCorrespondencePayload,
): Promise<Correspondence> {
  const row = await apiPost<CorrespondenceWire>('/v1/correspondence/', data);
  return normaliseCorrespondence(row);
}

export async function updateCorrespondence(
  id: string,
  data: UpdateCorrespondencePayload,
): Promise<Correspondence> {
  const row = await apiPatch<CorrespondenceWire>(`/v1/correspondence/${id}`, data);
  return normaliseCorrespondence(row);
}

export async function deleteCorrespondence(id: string): Promise<void> {
  await apiDelete(`/v1/correspondence/${id}`);
}

/**
 * Upload a single attachment to a correspondence entry.
 *
 * The shared JSON helpers cannot send multipart bodies, so this mirrors the
 * raw-fetch + FormData pattern used by the RFI / documents upload flows. The
 * backend (POST /{id}/attachments/) magic-byte gates the file and returns the
 * full, updated correspondence record (with the new ``attachments`` entry).
 */
export async function uploadCorrespondenceAttachment(
  correspondenceId: string,
  file: File,
): Promise<Correspondence> {
  const token = useAuthStore.getState().accessToken;
  const formData = new FormData();
  formData.append('file', file);
  const headers: Record<string, string> = { 'X-DDC-Client': 'OE/1.0' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(
    `/api/v1/correspondence/${encodeURIComponent(correspondenceId)}/attachments/`,
    { method: 'POST', headers, body: formData },
  );
  if (!res.ok) {
    let detail = file.name;
    try {
      const body: unknown = await res.json();
      if (
        body &&
        typeof body === 'object' &&
        'detail' in body &&
        typeof (body as { detail: unknown }).detail === 'string'
      ) {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new Error(detail);
  }
  const row = (await res.json()) as CorrespondenceWire;
  return normaliseCorrespondence(row);
}

/**
 * Download the attachment at the given list index to the browser.
 *
 * Auth is Bearer-token based, so a plain anchor would 401 — we fetch the
 * file with the Authorization header (mirroring downloadDocumentBlob) and
 * hand the resulting blob to the shared triggerDownload helper.
 */
export async function downloadCorrespondenceAttachment(
  correspondenceId: string,
  index: number,
  filename: string,
): Promise<void> {
  const token = useAuthStore.getState().accessToken;
  const res = await fetch(
    `/api/v1/correspondence/${encodeURIComponent(correspondenceId)}/attachments/${index}`,
    {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        'X-DDC-Client': 'OE/1.0',
      },
    },
  );
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  triggerDownload(blob, filename);
}

/**
 * Derive a friendly display name for a stored attachment path.
 *
 * Stored paths look like ``correspondence/attachments/<id>_<hex>.<ext>``; we
 * show just the final ``<id>_<hex>.<ext>`` segment so the row is readable
 * without leaking the full server layout.
 */
export function attachmentDisplayName(path: string): string {
  const parts = path.split('/');
  return parts[parts.length - 1] || path;
}
