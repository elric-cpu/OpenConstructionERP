// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * API helpers for the Geo Hub module.
 *
 * Backed by /api/v1/geo-hub/ — see backend/app/modules/geo_hub/router.py
 */

import { apiDelete, apiGet, apiPatch, apiPost } from '@/shared/lib/api';

import type {
  DiaryPhotoPin,
  GeoAnchor,
  GeoOverlay,
  HSEPin,
  ImageryLayer,
  MapConfig,
  PunchlistPin,
  TerrainSource,
  TileJob,
  Tileset,
  Viewpoint,
} from './types';

const BASE = '/v1/geo-hub';

/* ── Map config one-shot bundle ──────────────────────────────────────── */

export function getMapConfig(projectId: string): Promise<MapConfig> {
  return apiGet<MapConfig>(`${BASE}/map-config/${projectId}`);
}

/* ── Anchors ─────────────────────────────────────────────────────────── */

export function listAnchors(projectId: string): Promise<GeoAnchor[]> {
  return apiGet<GeoAnchor[]>(`${BASE}/anchors/?project_id=${projectId}`);
}

export function createAnchor(body: {
  project_id: string;
  lat: string;
  lon: string;
  alt?: string;
  epsg_code?: number;
  region_code?: string | null;
  address?: string | null;
  accuracy_m?: string | null;
  metadata?: Record<string, unknown>;
}): Promise<GeoAnchor> {
  return apiPost<GeoAnchor>(`${BASE}/anchors/`, body);
}

export function updateAnchor(
  id: string,
  body: Partial<GeoAnchor>,
): Promise<GeoAnchor> {
  return apiPatch<GeoAnchor>(`${BASE}/anchors/${id}`, body);
}

export function deleteAnchor(id: string): Promise<void> {
  return apiDelete(`${BASE}/anchors/${id}`);
}

/* ── Tilesets ────────────────────────────────────────────────────────── */

export function listTilesets(projectId: string): Promise<Tileset[]> {
  return apiGet<Tileset[]>(`${BASE}/tilesets/?project_id=${projectId}`);
}

export function getTileset(id: string): Promise<Tileset> {
  return apiGet<Tileset>(`${BASE}/tilesets/${id}`);
}

export function generateTileset(body: {
  project_id: string;
  source_kind: Tileset['source_kind'];
  source_id: string;
  force?: boolean;
}): Promise<TileJob> {
  return apiPost<TileJob>(`${BASE}/tilesets/generate/`, body);
}

export function deleteTileset(id: string): Promise<void> {
  return apiDelete(`${BASE}/tilesets/${id}`);
}

/* ── Jobs ────────────────────────────────────────────────────────────── */

export function listJobs(projectId: string, state?: string): Promise<TileJob[]> {
  const qs = new URLSearchParams({ project_id: projectId });
  if (state) qs.set('state', state);
  return apiGet<TileJob[]>(`${BASE}/jobs/?${qs.toString()}`);
}

export function getJob(id: string): Promise<TileJob> {
  return apiGet<TileJob>(`${BASE}/jobs/${id}`);
}

export function cancelJob(id: string): Promise<TileJob> {
  return apiPost<TileJob>(`${BASE}/jobs/${id}/cancel`, {});
}

/* ── Imagery ─────────────────────────────────────────────────────────── */

export function listImageryLayers(
  projectId: string,
): Promise<ImageryLayer[]> {
  return apiGet<ImageryLayer[]>(
    `${BASE}/imagery-layers/?project_id=${projectId}`,
  );
}

export function createImageryLayer(body: {
  project_id: string;
  name: string;
  provider: ImageryLayer['provider'];
  url_template: string;
  attribution?: string;
  requires_api_key?: boolean;
  default_for_project?: boolean;
  is_visible?: boolean;
}): Promise<ImageryLayer> {
  return apiPost<ImageryLayer>(`${BASE}/imagery-layers/`, body);
}

export function updateImageryLayer(
  id: string,
  body: Partial<ImageryLayer>,
): Promise<ImageryLayer> {
  return apiPatch<ImageryLayer>(`${BASE}/imagery-layers/${id}`, body);
}

export function deleteImageryLayer(id: string): Promise<void> {
  return apiDelete(`${BASE}/imagery-layers/${id}`);
}

/* ── Terrain ─────────────────────────────────────────────────────────── */

export function listTerrainSources(): Promise<TerrainSource[]> {
  return apiGet<TerrainSource[]>(`${BASE}/terrain-sources/`);
}

/* ── Viewpoints ──────────────────────────────────────────────────────── */

export function listViewpoints(projectId: string): Promise<Viewpoint[]> {
  return apiGet<Viewpoint[]>(`${BASE}/viewpoints/?project_id=${projectId}`);
}

export function createViewpoint(body: {
  project_id: string;
  name: string;
  camera_lat: string;
  camera_lon: string;
  camera_alt?: string;
  heading?: string;
  pitch?: string;
  roll?: string;
  description?: string;
}): Promise<Viewpoint> {
  return apiPost<Viewpoint>(`${BASE}/viewpoints/`, body);
}

export function deleteViewpoint(id: string): Promise<void> {
  return apiDelete(`${BASE}/viewpoints/${id}`);
}

/* ── Overlays + GeoJSON / KML I/O ────────────────────────────────────── */

export function listOverlays(
  projectId: string,
  kind?: string,
): Promise<GeoOverlay[]> {
  const qs = new URLSearchParams({ project_id: projectId });
  if (kind) qs.set('kind', kind);
  return apiGet<GeoOverlay[]>(`${BASE}/overlays/?${qs.toString()}`);
}

export function importGeoJSON(body: {
  project_id: string;
  name?: string;
  kind?: string;
  geojson: Record<string, unknown>;
}): Promise<GeoOverlay> {
  return apiPost<GeoOverlay>(`${BASE}/overlays/import-geojson/`, body);
}

export function importKML(body: {
  project_id: string;
  name?: string;
  kind?: string;
  kml: string;
}): Promise<GeoOverlay> {
  return apiPost<GeoOverlay>(`${BASE}/overlays/import-kml/`, body);
}

export function exportGeoJSON(
  projectId: string,
  kind?: string,
): Promise<Record<string, unknown>> {
  const qs = new URLSearchParams({ project_id: projectId });
  if (kind) qs.set('kind', kind);
  return apiGet<Record<string, unknown>>(
    `${BASE}/overlays/export-geojson/?${qs.toString()}`,
  );
}

export function deleteOverlay(id: string): Promise<void> {
  return apiDelete(`${BASE}/overlays/${id}`);
}

/* ── Cross-module geo pin layers ─────────────────────────────────────── */

export function fetchHsePins(
  projectId: string,
  limit = 500,
): Promise<HSEPin[]> {
  return apiGet<HSEPin[]>(
    `${BASE}/projects/${projectId}/hse-pins?limit=${limit}`,
  );
}

export function fetchPunchlistPins(
  projectId: string,
  limit = 500,
): Promise<PunchlistPin[]> {
  return apiGet<PunchlistPin[]>(
    `${BASE}/projects/${projectId}/punchlist-pins?limit=${limit}`,
  );
}

export function fetchDiaryPhotoPins(
  projectId: string,
  limit = 500,
): Promise<DiaryPhotoPin[]> {
  return apiGet<DiaryPhotoPin[]>(
    `${BASE}/projects/${projectId}/diary-photo-pins?limit=${limit}`,
  );
}
