/** React Query hooks for the file manager. */

import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { apiGet } from '@/shared/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';
import {
  fetchFileList,
  fetchFileTree,
  fetchStorageLocations,
  listFolderPermissions,
} from './api';
import type { FileFilters, FolderPermissionRow } from './types';

const KEY_TREE = 'file-manager-tree';
const KEY_LIST = 'file-manager-list';
const KEY_LOC = 'file-manager-locations';
const KEY_FOLDER_PERMS = 'folder-permission-counts';
const KEY_IS_PROJECT_OWNER = 'is-project-owner';

export function useFileTree(projectId: string | null | undefined) {
  return useQuery({
    queryKey: [KEY_TREE, projectId],
    queryFn: () => fetchFileTree(projectId as string),
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });
}

export function useFileList(
  projectId: string | null | undefined,
  filters: FileFilters,
) {
  return useQuery({
    queryKey: [KEY_LIST, projectId, filters],
    queryFn: () => fetchFileList(projectId as string, filters),
    enabled: Boolean(projectId),
    staleTime: 10_000,
    placeholderData: keepPreviousData,
  });
}

export function useStorageLocations(projectId: string | null | undefined) {
  return useQuery({
    queryKey: [KEY_LOC, projectId],
    queryFn: () => fetchStorageLocations(projectId as string),
    enabled: Boolean(projectId),
    staleTime: 60_000,
  });
}

export const fileManagerKeys = {
  tree: KEY_TREE,
  list: KEY_LIST,
  locations: KEY_LOC,
  folderPermissionCounts: KEY_FOLDER_PERMS,
  isProjectOwner: KEY_IS_PROJECT_OWNER,
};

/* ── Per-folder permissions helpers ────────────────────────────────── */

interface ProjectOwnerInfo {
  id: string;
  owner_id: string;
}

/** Decode the JWT ``sub`` claim — the canonical user id. */
function decodeUserIdFromToken(token: string | null): string | null {
  if (!token) return null;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1]!.replace(/-/g, '+').replace(/_/g, '/');
    const padded = payload + '='.repeat((4 - (payload.length % 4)) % 4);
    const json = JSON.parse(atob(padded)) as { sub?: string };
    return typeof json.sub === 'string' ? json.sub : null;
  } catch {
    return null;
  }
}

/** True when the current user owns the given project. */
export function useIsProjectOwner(projectId: string | null | undefined): boolean {
  const accessToken = useAuthStore((s) => s.accessToken);
  const role = useAuthStore((s) => s.userRole);
  const me = decodeUserIdFromToken(accessToken);

  const { data } = useQuery<ProjectOwnerInfo>({
    queryKey: [KEY_IS_PROJECT_OWNER, projectId],
    queryFn: () => apiGet<ProjectOwnerInfo>(`/v1/projects/${projectId}`),
    enabled: Boolean(projectId) && Boolean(me),
    staleTime: 60_000,
  });

  if (role === 'admin') return true;
  if (!me || !data) return false;
  return data.owner_id === me;
}

/**
 * Per-folder grant counts so FolderCardGrid can show a lock badge on
 * cards that have any non-revoked grant. Returns ``{}`` for non-owners
 * (the listing endpoint 403s for them) so the lock icon stays
 * owner-only — non-owners only see the folders they're cleared for.
 */
export function useFolderPermissionCounts(
  projectId: string | null | undefined,
  enabled: boolean,
): Record<string, number> {
  const { data = [] } = useQuery<FolderPermissionRow[]>({
    queryKey: [KEY_FOLDER_PERMS, projectId],
    queryFn: () => listFolderPermissions(projectId as string),
    enabled: Boolean(projectId) && enabled,
    staleTime: 10_000,
  });
  const counts: Record<string, number> = {};
  for (const row of data) {
    // Bucket by ``scope_kind`` so the card-level lock badge shows the
    // total members cleared for that FOLDER (across sub-paths).
    counts[row.scope_kind] = (counts[row.scope_kind] || 0) + 1;
  }
  return counts;
}
