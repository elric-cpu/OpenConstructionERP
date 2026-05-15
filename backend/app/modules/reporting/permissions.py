"""‌⁠‍Reporting module permission definitions.

Registered at module startup via ``app.modules.reporting.on_startup``.
Without this, every ``RequirePermission("reporting.*")`` gate in
``router.py`` resolves against an *unregistered* permission, which the
RBAC engine treats as "unknown → deny" for every non-admin role — i.e.
KPI snapshot creation, template authoring, scheduling, run-now, report
generation and deletion would silently 403 for editors/managers and
only work for admins.

Role mapping mirrors the platform-wide sibling convention
(projects / finance / boq): create+update = EDITOR, read = VIEWER,
delete = MANAGER.
"""

from app.core.permissions import Role, permission_registry


def register_reporting_permissions() -> None:
    """‌⁠‍Register permissions for the reporting module."""
    permission_registry.register_module_permissions(
        "reporting",
        {
            "reporting.create": Role.EDITOR,
            "reporting.read": Role.VIEWER,
            "reporting.update": Role.EDITOR,
            "reporting.delete": Role.MANAGER,
        },
    )
