"""‌⁠‍Property Development & Buyer Portal module.

Tracks property developments, plots, house types, buyer option catalogues,
buyer registrations + selections (with freeze deadlines), handovers + snag
lists and post-handover warranty claims. Provides the data foundation and
business logic for a downstream 3D configurator + portal frontend.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook — register permissions."""
    from app.modules.property_dev.permissions import register_property_dev_permissions

    register_property_dev_permissions()
