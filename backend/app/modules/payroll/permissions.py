# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Payroll module permission definitions.

Payroll touches money owed to people - it is manager-scoped throughout.
Even read access is restricted to MANAGER so wage data is not exposed to
every viewer/editor on the project.
"""

from app.core.permissions import Role, permission_registry


def register_payroll_permissions() -> None:
    """Register permissions for the Payroll module."""
    permission_registry.register_module_permissions(
        "payroll",
        {
            "payroll.read": Role.MANAGER,
            "payroll.manage": Role.MANAGER,
            # Finalize approves a draft batch AND posts its labour cost to the
            # cost spine - a money-moving action, kept manager-scoped.
            "payroll.finalize": Role.MANAGER,
        },
    )
