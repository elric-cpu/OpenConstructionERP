"""‌⁠‍Takeoff module — PDF upload and quantity extraction."""


async def on_startup() -> None:
    """‌⁠‍Module startup hook — register permissions."""
    from app.modules.takeoff.permissions import register_takeoff_permissions

    register_takeoff_permissions()
