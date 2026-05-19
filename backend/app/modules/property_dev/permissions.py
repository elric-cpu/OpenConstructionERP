"""‌⁠‍Property Development module permission definitions."""

from app.core.permissions import Role, permission_registry

PROPERTY_DEV_PERMISSIONS: dict[str, Role] = {
    "property_dev.read": Role.VIEWER,
    "property_dev.create": Role.EDITOR,
    "property_dev.update": Role.EDITOR,
    "property_dev.delete": Role.MANAGER,
    "property_dev.reserve_plot": Role.EDITOR,
    "property_dev.contract_buyer": Role.MANAGER,
    "property_dev.lock_selection": Role.MANAGER,
    "property_dev.handover": Role.MANAGER,
    "property_dev.fix_snag": Role.EDITOR,
    "property_dev.process_warranty": Role.EDITOR,
}


def register_property_dev_permissions() -> None:
    """‌⁠‍Register permissions for the property_dev module."""
    permission_registry.register_module_permissions(
        "property_dev",
        PROPERTY_DEV_PERMISSIONS,
    )
