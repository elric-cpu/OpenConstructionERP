"""‌⁠‍Admin — permissions matrix endpoint.

Exposes a read-only view of the live ``PermissionRegistry`` so the
frontend can render a roles × modules matrix without re-implementing
the role-hierarchy logic in TypeScript.

Endpoint:
    GET /api/v1/admin/permissions/matrix

Response shape::

    {
        "roles": ["viewer", "editor", "manager", "admin"],
        "role_hierarchy": {"viewer": 0, "editor": 1, "manager": 2, "admin": 3},
        "modules": [
            {
                "name": "system",
                "permissions": [
                    {"key": "system.settings.read", "min_role": "manager"},
                    ...
                ],
            },
            ...
        ],
    }

The endpoint is gated by ``audit.view`` — the existing core permission
that already protects similar operator-facing surfaces (the audit log).
That keeps the surface area small (no new permission to register, no
new role to assign) and matches what the UI conceptually exposes: a
governance/audit view of the RBAC configuration.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from app.core.permissions import ROLE_HIERARCHY, Role, permission_registry
from app.dependencies import RequirePermission

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_matrix_payload() -> dict[str, Any]:
    """Snapshot the live permission registry into the matrix response.

    Pulled out of the route handler so the unit test can call it
    directly without spinning up the full ASGI app.
    """
    # Canonical role order goes lowest-to-highest so the UI columns
    # read left→right as "more permissive".
    roles_ordered = [r.value for r in (Role.VIEWER, Role.EDITOR, Role.MANAGER, Role.ADMIN)]

    modules_payload: list[dict[str, Any]] = []
    modules_index = permission_registry.list_modules()
    all_perms = permission_registry.list_all()

    # Sort modules alphabetically — predictable for the UI test and
    # avoids surprises when the registration order shifts between
    # releases (module loader topological sort is dependency-driven).
    for module_name in sorted(modules_index.keys()):
        perm_keys = sorted(modules_index[module_name])
        modules_payload.append(
            {
                "name": module_name,
                "permissions": [
                    {
                        "key": perm,
                        # all_perms maps perm → role.value (a string),
                        # so this is safe to forward as-is.
                        "min_role": all_perms.get(perm, Role.ADMIN.value),
                    }
                    for perm in perm_keys
                ],
            }
        )

    return {
        "roles": roles_ordered,
        "role_hierarchy": {r.value: lvl for r, lvl in ROLE_HIERARCHY.items()},
        "modules": modules_payload,
    }


@router.get(
    "/permissions/matrix",
    summary="Snapshot the RBAC matrix (roles × modules × permissions)",
    description=(
        "Returns the live PermissionRegistry as a roles-by-modules matrix "
        "for the admin UI. Gated by ``audit.view`` (manager+) — the same "
        "permission that protects the audit log."
    ),
)
async def permissions_matrix(
    _perm: None = Depends(RequirePermission("audit.view")),
) -> dict[str, Any]:
    """‌⁠‍Return the full permissions matrix for the admin UI."""
    return _build_matrix_payload()
