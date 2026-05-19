"""‌⁠‍CRM module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_crm_permissions() -> None:
    """‌⁠‍Register permissions for the CRM module.

    Permission map:
        crm.read             VIEWER   — list / read accounts, leads, opportunities, etc.
        crm.create           EDITOR   — create accounts / leads / opportunities / activities
        crm.update           EDITOR   — patch any CRM entity
        crm.delete           MANAGER  — delete CRM entities
        crm.qualify_lead     EDITOR   — move lead through new→qualifying→qualified
        crm.convert_lead     EDITOR   — convert lead into an opportunity
        crm.move_stage       EDITOR   — transition an opportunity between pipeline stages
        crm.win_opportunity  EDITOR   — mark an opportunity won
        crm.lose_opportunity EDITOR   — mark an opportunity lost
        crm.compute_forecast MANAGER  — re-compute forecast for a period
    """
    permission_registry.register_module_permissions(
        "crm",
        {
            "crm.read": Role.VIEWER,
            "crm.create": Role.EDITOR,
            "crm.update": Role.EDITOR,
            "crm.delete": Role.MANAGER,
            "crm.qualify_lead": Role.EDITOR,
            "crm.convert_lead": Role.EDITOR,
            "crm.move_stage": Role.EDITOR,
            "crm.win_opportunity": Role.EDITOR,
            "crm.lose_opportunity": Role.EDITOR,
            "crm.compute_forecast": Role.MANAGER,
        },
    )
