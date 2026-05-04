"""‌⁠‍Full EVM module.

Earned Value Management forecasts, S-curve computation, and integration
with finance EVM snapshots.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook — register permissions."""
    from app.modules.full_evm.permissions import register_full_evm_permissions

    register_full_evm_permissions()
