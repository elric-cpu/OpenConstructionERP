"""Tests for ``GET /api/v1/admin/permissions/matrix``.

The endpoint snapshots the live ``PermissionRegistry`` for the admin
UI. We exercise the pure builder directly (no ASGI) so the unit suite
stays fast, plus one focused round-trip through the registry so the
gate (``audit.view``) and the response shape can't drift apart.
"""

from __future__ import annotations

import pytest

from app.core.permissions import (
    PermissionRegistry,
    Role,
    permission_registry,
    register_core_permissions,
)
from app.modules.admin.permissions_router import _build_matrix_payload


@pytest.fixture
def fresh_registry(monkeypatch):
    """Swap the global registry for a clean instance for this test only."""
    clean = PermissionRegistry()
    monkeypatch.setattr(
        "app.modules.admin.permissions_router.permission_registry", clean
    )
    return clean


class TestPermissionsMatrixPayload:
    def test_empty_registry_returns_canonical_roles_only(self, fresh_registry):
        payload = _build_matrix_payload()
        assert payload["roles"] == ["viewer", "editor", "manager", "admin"]
        assert payload["modules"] == []
        # Role hierarchy is rendered as {role_value: int_level} so the
        # UI can label / sort columns without re-implementing the
        # canonical order on its side.
        assert payload["role_hierarchy"] == {
            "viewer": 0,
            "editor": 1,
            "manager": 2,
            "admin": 3,
        }

    def test_includes_registered_modules(self, fresh_registry):
        fresh_registry.register_module_permissions(
            "projects",
            {
                "projects.create": Role.EDITOR,
                "projects.delete": Role.MANAGER,
                "projects.read": Role.VIEWER,
            },
        )
        fresh_registry.register_module_permissions(
            "system",
            {"system.settings.write": Role.ADMIN},
        )

        payload = _build_matrix_payload()

        # Modules must be alphabetically sorted — the UI relies on a
        # stable order to keep the column rendering deterministic.
        names = [m["name"] for m in payload["modules"]]
        assert names == ["projects", "system"]

        projects = payload["modules"][0]
        # Permissions inside a module are also sorted alphabetically.
        keys = [p["key"] for p in projects["permissions"]]
        assert keys == ["projects.create", "projects.delete", "projects.read"]

        # Each permission carries the canonical role string for that
        # min_role. This is what the UI cell rendering hangs on.
        min_roles = {p["key"]: p["min_role"] for p in projects["permissions"]}
        assert min_roles == {
            "projects.create": "editor",
            "projects.delete": "manager",
            "projects.read": "viewer",
        }

    def test_core_permissions_round_trip(self):
        """Smoke: registering core perms surfaces the audit.view gate."""
        # Use the real global registry — we only inspect, we don't
        # mutate (register_core_permissions is idempotent).
        register_core_permissions()
        all_perms = permission_registry.list_all()
        assert all_perms.get("audit.view") == "manager"
