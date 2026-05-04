"""‌⁠‍Finance module.

Provides invoicing, payments, budgets, and Earned Value Management (EVM)
workflows for construction projects.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook — register permissions."""
    from app.modules.finance.permissions import register_finance_permissions

    register_finance_permissions()
