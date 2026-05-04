"""‌⁠‍Procurement module — purchase orders, goods receipts, vendor management."""


async def on_startup() -> None:
    """‌⁠‍Module startup hook — register permissions."""
    from app.modules.procurement.permissions import register_procurement_permissions

    register_procurement_permissions()
