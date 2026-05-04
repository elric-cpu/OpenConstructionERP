"""‌⁠‍Inspections module.

Quality inspections for construction projects — concrete pours, waterproofing,
MEP, fire stopping, handover, and general inspections with checklists.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook — register permissions."""
    from app.modules.inspections.permissions import register_inspections_permissions

    register_inspections_permissions()
