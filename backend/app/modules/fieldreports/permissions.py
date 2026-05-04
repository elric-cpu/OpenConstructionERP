"""‌⁠‍Field Reports module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_fieldreports_permissions() -> None:
    """‌⁠‍Register permissions for the field reports module."""
    permission_registry.register_module_permissions(
        "fieldreports",
        {
            "fieldreports.create": Role.EDITOR,
            "fieldreports.read": Role.VIEWER,
            "fieldreports.update": Role.EDITOR,
            "fieldreports.delete": Role.MANAGER,
            "fieldreports.approve": Role.MANAGER,
        },
    )
