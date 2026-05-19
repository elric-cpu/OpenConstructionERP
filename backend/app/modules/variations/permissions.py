"""‌⁠‍Variations module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_variations_permissions() -> None:
    """‌⁠‍Register permissions for the variations module."""
    permission_registry.register_module_permissions(
        "variations",
        {
            "variations.read": Role.VIEWER,
            "variations.create": Role.EDITOR,
            "variations.update": Role.EDITOR,
            "variations.delete": Role.MANAGER,
            "variations.submit_request": Role.EDITOR,
            "variations.approve_request": Role.MANAGER,
            "variations.convert_to_vo": Role.MANAGER,
            "variations.complete_vo": Role.EDITOR,
            "variations.sign_daywork": Role.EDITOR,
            "variations.decide_claim": Role.MANAGER,
            "variations.close_final_account": Role.MANAGER,
        },
    )
