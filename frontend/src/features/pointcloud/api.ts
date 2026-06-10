/**
 * Point Cloud / Reality Capture API client.
 *
 * Wraps the real backend ingest surface mounted at /api/v1/pointcloud/:
 *
 *   1. POST /v1/pointcloud/scans/ingest/init      -> registers the scan and
 *      opens a presigned-direct multipart upload, returning one presigned PUT
 *      URL per part. The bytes never go through the FastAPI core.
 *   2. PUT each presigned part URL with the matching byte slice. Each PUT
 *      returns an ETag we collect.
 *   3. POST /v1/pointcloud/scans/{scan_id}/ingest/complete  -> finalises the
 *      multipart upload and flips the scan to status=uploaded.
 *
 * Locally the storage backend mints same-origin signed URLs
 * (/api/v1/uploads/local/{token}) so the whole flow runs end to end without
 * MinIO. On a hosted deployment with object storage the same code uploads
 * straight to S3/MinIO. When storage is not wired the init call surfaces the
 * real backend error to the caller, exactly like the BIM / DWG flows.
 */

import { apiGet, apiPost, API_BASE, getAuthToken } from '@/shared/lib/api';

/** Accepted upload containers, mirrored from the backend allow-list
 *  (backend/app/modules/pointcloud/models.py ACCEPTED_SCAN_FORMATS).
 *  Proprietary ReCap RCP/RCS is deliberately absent - export E57 or LAS. */
export const ACCEPTED_SCAN_FORMATS = [
  'e57',
  'las',
  'laz',
  'copc',
  'ply',
  'pcd',
  'pts',
  'xyz',
] as const;

export type ScanSourceType = 'laser_scan' | 'photogrammetry' | 'lidar' | 'other';
export type AccuracyTier = 'survey' | 'standard' | 'coarse';

export interface ScanDataset {
  id: string;
  project_id: string;
  source_type: string;
  original_format: string;
  accuracy_tier: string;
  status: string;
  point_count: number;
  created_at: string;
}

export interface ScanDatasetList {
  items: ScanDataset[];
  total: number;
  offset: number;
  limit: number;
}

interface PresignedPart {
  part_number: number;
  url: string;
}

interface ScanIngestInitResponse {
  scan_id: string;
  upload_id: string;
  upload_key: string;
  part_size_bytes: number;
  parts: PresignedPart[];
  expires_at: string;
}

interface CompletedPart {
  part_number: number;
  etag: string;
  size_bytes: number;
}

interface ScanIngestCompleteResponse {
  scan_id: string;
  upload_key: string;
  status: string;
  size_bytes: number;
}

export interface ScanIngestInitBody {
  project_id: string;
  name: string;
  source_type: ScanSourceType;
  original_format: string;
  accuracy_tier: AccuracyTier;
  total_size_bytes: number;
}

/** List the reality-capture scans registered against a project. */
export async function listScans(projectId: string): Promise<ScanDatasetList> {
  return apiGet<ScanDatasetList>(`/v1/pointcloud/scans?project_id=${projectId}`);
}

/** Derive the accepted upload format from a file name, lower-cased without the
 *  leading dot, or null when the extension is not on the allow-list. */
export function formatFromFileName(name: string): string | null {
  const dot = name.lastIndexOf('.');
  if (dot < 0) return null;
  const ext = name.slice(dot + 1).toLowerCase();
  return (ACCEPTED_SCAN_FORMATS as readonly string[]).includes(ext) ? ext : null;
}

/** Resolve a presigned part URL to an absolute, fetchable URL.
 *
 * The local backend returns a same-origin path that already carries the
 * ``/api`` prefix (``/api/v1/uploads/local/{token}``), so we leave absolute
 * URLs and already-prefixed paths untouched and only prepend the API base for
 * a bare ``/v1/...`` path. */
function resolvePartUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith(`${API_BASE}/`)) return url;
  if (url.startsWith('/api/')) return url;
  return `${API_BASE}${url.startsWith('/') ? '' : '/'}${url}`;
}

/** Extract the ETag a PUT returned, from the response header or JSON body. */
async function readPartEtag(res: Response): Promise<string> {
  const header = res.headers.get('ETag') || res.headers.get('etag');
  if (header) return header.replace(/"/g, '');
  // The local upload endpoint returns { key, etag, size_bytes } as JSON.
  try {
    const body = (await res.clone().json()) as { etag?: string };
    if (body?.etag) return String(body.etag);
  } catch {
    /* not a JSON body - fall through */
  }
  return '';
}

export interface UploadProgress {
  /** 0-100 across all parts. */
  percent: number;
  /** Human-readable stage key for the current step. */
  stage: 'preparing' | 'uploading' | 'finalizing' | 'done';
}

/**
 * Upload a point-cloud file end to end: init the multipart upload, PUT every
 * part to its presigned URL, then complete. Calls ``onProgress`` as parts land
 * so the UI can show an honest progress bar. Throws on any backend failure so
 * the caller surfaces the real error (no faked success).
 */
export async function uploadScan(
  body: ScanIngestInitBody,
  file: File,
  onProgress?: (p: UploadProgress) => void,
): Promise<ScanIngestCompleteResponse> {
  onProgress?.({ percent: 2, stage: 'preparing' });

  const init = await apiPost<ScanIngestInitResponse, ScanIngestInitBody>(
    '/v1/pointcloud/scans/ingest/init',
    body,
    { longRunning: true },
  );

  const partSize = init.part_size_bytes || file.size || 1;
  const completed: CompletedPart[] = [];
  const token = getAuthToken();

  for (const part of init.parts) {
    const start = (part.part_number - 1) * partSize;
    const end = Math.min(start + partSize, file.size);
    const slice = file.slice(start, end);

    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;

    const res = await fetch(resolvePartUrl(part.url), {
      method: 'PUT',
      body: slice,
      headers,
    });
    if (!res.ok) {
      let detail = `Upload failed for part ${part.part_number} (HTTP ${res.status})`;
      try {
        const errBody = (await res.json()) as { detail?: unknown };
        if (errBody?.detail) detail = String(errBody.detail);
      } catch {
        /* keep the generic message */
      }
      throw new Error(detail);
    }

    completed.push({
      part_number: part.part_number,
      etag: await readPartEtag(res),
      size_bytes: end - start,
    });

    onProgress?.({
      percent: Math.min(95, 5 + Math.round((completed.length / init.parts.length) * 88)),
      stage: 'uploading',
    });
  }

  onProgress?.({ percent: 96, stage: 'finalizing' });

  const done = await apiPost<ScanIngestCompleteResponse, { upload_id: string; parts: CompletedPart[] }>(
    `/v1/pointcloud/scans/${init.scan_id}/ingest/complete`,
    { upload_id: init.upload_id, parts: completed },
    { longRunning: true },
  );

  onProgress?.({ percent: 100, stage: 'done' });
  return done;
}
