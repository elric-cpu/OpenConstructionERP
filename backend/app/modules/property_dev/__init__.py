"""‌⁠‍Property Development & Buyer Portal module.

Tracks property developments, plots, house types, buyer option catalogues,
buyer registrations + selections (with freeze deadlines), handovers + snag
lists and post-handover warranty claims. Provides the data foundation and
business logic for a downstream 3D configurator + portal frontend.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook — register permissions + event subscribers."""
    from app.modules.property_dev.events import (
        register_property_dev_event_subscribers,
    )
    from app.modules.property_dev.permissions import register_property_dev_permissions

    register_property_dev_permissions()
    register_property_dev_event_subscribers()
