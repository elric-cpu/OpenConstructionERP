"""‌⁠‍NCR module.

Non-Conformance Report management — material, workmanship, design, documentation,
and safety non-conformances with root cause analysis and corrective/preventive actions.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook — register permissions."""
    from app.modules.ncr.permissions import register_ncr_permissions

    register_ncr_permissions()
