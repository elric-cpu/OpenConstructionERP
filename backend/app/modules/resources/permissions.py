"""‌⁠‍Resources module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_resources_permissions() -> None:
    """‌⁠‍Register permissions for the resources module."""
    permission_registry.register_module_permissions(
        "resources",
        {
            "resources.read": Role.VIEWER,
            "resources.create": Role.EDITOR,
            "resources.update": Role.EDITOR,
            "resources.delete": Role.MANAGER,
            "resources.assign": Role.EDITOR,
            "resources.confirm_assignment": Role.MANAGER,
            "resources.request": Role.VIEWER,
            "resources.fulfill_request": Role.EDITOR,
        },
    )
