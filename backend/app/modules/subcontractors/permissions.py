"""‌⁠‍Subcontractor module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_subcontractors_permissions() -> None:
    """‌⁠‍Register permissions for the subcontractors module."""
    permission_registry.register_module_permissions(
        "subcontractors",
        {
            "subcontractors.create": Role.EDITOR,
            "subcontractors.read": Role.VIEWER,
            "subcontractors.update": Role.EDITOR,
            "subcontractors.delete": Role.MANAGER,
            "subcontractors.approve_prequalification": Role.MANAGER,
            "subcontractors.approve_payment_foreman": Role.EDITOR,
            "subcontractors.approve_payment_finance": Role.MANAGER,
            "subcontractors.release_retention": Role.MANAGER,
        },
    )
