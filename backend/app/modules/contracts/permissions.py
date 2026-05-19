"""‌⁠‍Contracts module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_contracts_permissions() -> None:
    """‌⁠‍Register permissions for the contracts module."""
    permission_registry.register_module_permissions(
        "contracts",
        {
            "contracts.read": Role.VIEWER,
            "contracts.create": Role.EDITOR,
            "contracts.update": Role.EDITOR,
            "contracts.delete": Role.MANAGER,
            "contracts.sign": Role.MANAGER,
            "contracts.terminate": Role.MANAGER,
            "contracts.submit_claim": Role.EDITOR,
            "contracts.approve_claim": Role.EDITOR,
            "contracts.certify_claim": Role.MANAGER,
            "contracts.mark_paid": Role.MANAGER,
            "contracts.close": Role.MANAGER,
        },
    )
