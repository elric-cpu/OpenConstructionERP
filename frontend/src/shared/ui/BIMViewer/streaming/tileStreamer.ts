// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Streaming geometry loader.
 *
 * Fetches a model's tile manifest, pulls each content-addressed tile
 * (IndexedDB cache first, network on a miss), parses the tiles in small
 * chunks that yield to the event loop between them, and merges them into one
 * THREE.Group ready to hand to the viewer's existing processLoadedScene().
 *
 * Versus the monolithic path this buys: a persistent, offline-capable cache
 * (immutable tiles); parallel, cache-first downloads; and a parse that no
 * longer freezes the UI in one multi-second GLTFLoader.parse block. Tiles are
 * the same trimesh-exported GLB format as the monolith and preserve glTF node
 * names, so the downstream mesh-to-element matching is unchanged.
 *
 * The whole path is optional: streamModelTiles returns null when the model
 * has no tileset, and the caller falls back to the monolithic GLB.
 */

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import type { GLTF } from 'three/addons/loaders/GLTFLoader.js';

import { useAuthStore } from '@/stores/useAuthStore';

import { getCachedTile, putCachedTile, tileCacheKey } from './tileCache';
import type { TileInfo, TileManifest } from './tileTypes';

const GLB_MAGIC = 0x46546c67; // 'glTF' little-endian

function tilesBase(modelId: string): string {
  return `/api/v1/bim_hub/models/${encodeURIComponent(modelId)}/tiles`;
}

function authHeaders(): Record<string, string> {
  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = { Accept: '*/*' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

/**
 * Extract the model id from a `/models/{id}/geometry/` URL, or null when the
 * URL is not the internal geometry endpoint (e.g. a portal URL or a blob:).
 * Streaming only engages for the internal endpoint; everything else keeps the
 * monolithic path.
 */
export function modelIdFromGeometryUrl(url: string): string | null {
  const match = url.match(/\/models\/([^/?#]+)\/geometry\b/);
  return match && match[1] ? decodeURIComponent(match[1]) : null;
}

/** Fetch the tile manifest, or null when there is no streamable tileset. */
export async function fetchTileManifest(
  modelId: string,
  signal?: AbortSignal,
): Promise<TileManifest | null> {
  try {
    const resp = await fetch(`${tilesBase(modelId)}/manifest/`, {
      headers: authHeaders(),
      signal,
    });
    if (resp.status === 204 || !resp.ok) return null;
    const data = (await resp.json()) as TileManifest;
    if (!data || !Array.isArray(data.tiles) || data.tiles.length === 0) return null;
    return data;
  } catch {
    return null;
  }
}

async function fetchTileBytes(
  modelId: string,
  hash: string,
  signal?: AbortSignal,
): Promise<ArrayBuffer> {
  const key = tileCacheKey(modelId, hash);
  const cached = await getCachedTile(key);
  if (cached) return cached;

  const resp = await fetch(`${tilesBase(modelId)}/${encodeURIComponent(hash)}/`, {
    headers: authHeaders(),
    signal,
  });
  if (!resp.ok) throw new Error(`Tile ${hash} fetch failed (HTTP ${resp.status})`);
  const buffer = await resp.arrayBuffer();
  // Content-addressed => immutable => cache forever. Store a copy so the
  // returned buffer stays usable by the caller.
  void putCachedTile(key, buffer.slice(0));
  return buffer;
}

function parseTile(loader: GLTFLoader, buffer: ArrayBuffer): Promise<THREE.Object3D | null> {
  return new Promise((resolve) => {
    if (buffer.byteLength < 12) {
      resolve(null);
      return;
    }
    const magic = new Uint32Array(buffer.slice(0, 4))[0] ?? 0;
    if (magic !== GLB_MAGIC) {
      resolve(null);
      return;
    }
    try {
      loader.parse(
        buffer,
        '',
        (gltf: GLTF) => resolve(gltf?.scene ?? null),
        () => resolve(null),
      );
    } catch {
      resolve(null);
    }
  });
}

/** Run `fn` over `items` with at most `limit` concurrent calls, order-preserving. */
async function mapPool<T, R>(
  items: T[],
  limit: number,
  fn: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let cursor = 0;
  const worker = async (): Promise<void> => {
    for (;;) {
      const index = cursor;
      cursor += 1;
      if (index >= items.length) return;
      out[index] = await fn(items[index] as T, index);
    }
  };
  const workers = Math.max(1, Math.min(limit, items.length));
  await Promise.all(Array.from({ length: workers }, () => worker()));
  return out;
}

/** Yield to the event loop so render + input can run between tile parses. */
function macroYield(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

export interface StreamResult {
  /** Merged geometry, ready for processLoadedScene(). */
  group: THREE.Group;
  /** Tiles that parsed successfully. */
  tileCount: number;
  /** Meshes in the merged group. */
  meshCount: number;
}

export interface StreamOptions {
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
  /** Max concurrent tile downloads (default 6). */
  fetchConcurrency?: number;
}

/**
 * Stream a model's tiles into one merged group. Returns null when the model
 * has no tileset (204) or nothing parsed - the caller then loads the
 * monolithic GLB.
 */
export async function streamModelTiles(
  modelId: string,
  opts: StreamOptions = {},
): Promise<StreamResult | null> {
  const manifest = await fetchTileManifest(modelId, opts.signal);
  if (!manifest) return null;

  const tiles: TileInfo[] = manifest.tiles;

  // Phase A - download every tile (cache-first) with bounded concurrency. A
  // failed tile becomes null and is skipped rather than aborting the load.
  const buffers = await mapPool(tiles, opts.fetchConcurrency ?? 6, async (tile) => {
    try {
      return await fetchTileBytes(modelId, tile.hash, opts.signal);
    } catch {
      return null;
    }
  });

  // Phase B - parse on the main thread, one tile at a time, yielding between
  // tiles so the browser can render progress and stay responsive (no single
  // multi-second parse freeze).
  const loader = new GLTFLoader();
  const group = new THREE.Group();
  group.name = 'streamed-tiles';
  let parsedTiles = 0;

  for (let i = 0; i < buffers.length; i += 1) {
    if (opts.signal?.aborted) break;
    const buffer = buffers[i];
    if (buffer) {
      const scene = await parseTile(loader, buffer);
      if (scene) {
        // Reparent the tile's children into the merged group (names preserved).
        for (const child of [...scene.children]) {
          group.add(child);
        }
        parsedTiles += 1;
      }
    }
    opts.onProgress?.((i + 1) / buffers.length);
    await macroYield();
  }

  if (parsedTiles === 0) return null;
  return { group, tileCount: parsedTiles, meshCount: group.children.length };
}
