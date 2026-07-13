// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Streaming tile ordering.
 *
 * The streamer downloads and reveals tiles in whatever order the manifest lists
 * them, which is spatial-octree order, not importance order. On the initial load
 * there is no meaningful camera yet (the view fits to the model only after it
 * arrives), so we cannot sort by what the user is looking at. Instead we order by
 * how much of the building each tile carries: the tiles with the most geometry
 * first, so the bulk of the structure appears while the small trailing tiles are
 * still coming in. Within an equal-mass tie we go ground-up, so a building rises
 * from its base rather than filling in at random.
 *
 * Pure and deterministic (no camera, no THREE, no DOM): input tiles in, a new
 * ordered array out. The manifest already carries the per-tile node_count /
 * byte_size / center the backend tiler bakes, so this reads for free.
 */

import type { TileInfo } from './tileTypes';

/** Finite number or a fallback - guards against malformed manifest entries. */
function num(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

/**
 * Vertical position of a tile in tile-local coordinates. Tiles are baked in the
 * source's Z-up frame (the viewer rotates -90 deg X on display), so the vertical
 * axis here is Z = center[2]. Lower means closer to the ground.
 */
function tileHeight(tile: TileInfo): number {
  return Array.isArray(tile.center) ? num(tile.center[2]) : 0;
}

/**
 * Return a NEW array of the tiles ordered for streaming: most geometry first,
 * then largest payload, then ground-up, with the original manifest order as the
 * final deterministic tie-break. Does not mutate the input.
 */
export function orderTilesForStreaming(tiles: TileInfo[]): TileInfo[] {
  return tiles
    .map((tile, index) => ({ tile, index }))
    .sort((a, b) => {
      // 1. More meshes = more of the building = show first.
      const nodeDelta = num(b.tile.node_count) - num(a.tile.node_count);
      if (nodeDelta !== 0) return nodeDelta;
      // 2. Bigger payload next (a proxy for geometry volume when node_count ties).
      const sizeDelta = num(b.tile.byte_size) - num(a.tile.byte_size);
      if (sizeDelta !== 0) return sizeDelta;
      // 3. Ground-up so the structure rises from its base.
      const heightDelta = tileHeight(a.tile) - tileHeight(b.tile);
      if (heightDelta !== 0) return heightDelta;
      // 4. Stable, deterministic fallback: keep the original manifest order.
      return a.index - b.index;
    })
    .map((entry) => entry.tile);
}
