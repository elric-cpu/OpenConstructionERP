# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Plan Room module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_plan_room_permissions() -> None:
    """Register permissions for the Plan Room module.

    Reading a page's overlay composite is open to any viewer. Dropping and
    removing a positioned photo / note pin is a single editor-level ``write``
    action.
    """
    permission_registry.register_module_permissions(
        "plan_room",
        {
            "plan_room.read": Role.VIEWER,
            "plan_room.write": Role.EDITOR,
        },
    )
