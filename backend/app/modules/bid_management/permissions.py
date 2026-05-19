"""‌⁠‍Bid Management module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_bid_management_permissions() -> None:
    """‌⁠‍Register permissions for the bid_management module."""
    permission_registry.register_module_permissions(
        "bid_management",
        {
            "bid_management.read": Role.VIEWER,
            "bid_management.create": Role.EDITOR,
            "bid_management.update": Role.EDITOR,
            "bid_management.delete": Role.MANAGER,
            "bid_management.publish": Role.MANAGER,
            "bid_management.open_bids": Role.MANAGER,
            "bid_management.disqualify_bidder": Role.MANAGER,
            "bid_management.compute_leveling": Role.EDITOR,
            "bid_management.award": Role.MANAGER,
            "bid_management.cancel": Role.MANAGER,
        },
    )
