# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""‌⁠‍Clash detection module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_clash_permissions() -> None:
    """‌⁠‍Register RBAC permissions for the clash module.

    Mirrors the sibling ``bcf`` / ``validation`` verb set: viewers read
    runs & results; editors trigger runs and triage results; managers can
    delete a run. BCF export is a read-class capability (it does not
    mutate clash data — it just mirrors clashes into the BCF module).
    """
    permission_registry.register_module_permissions(
        "clash",
        {
            "clash.read": Role.VIEWER,
            "clash.create": Role.EDITOR,
            "clash.update": Role.EDITOR,
            "clash.delete": Role.MANAGER,
            "clash.export": Role.VIEWER,
        },
    )
