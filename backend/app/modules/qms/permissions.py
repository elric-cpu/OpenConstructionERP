"""‌⁠‍QMS module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_qms_permissions() -> None:
    """‌⁠‍Register permissions for the QMS module."""
    permission_registry.register_module_permissions(
        "qms",
        {
            "qms.itp.read": Role.VIEWER,
            "qms.itp.write": Role.EDITOR,
            "qms.inspection.read": Role.VIEWER,
            "qms.inspection.write": Role.EDITOR,
            "qms.inspection.sign": Role.EDITOR,
            "qms.ncr.read": Role.VIEWER,
            "qms.ncr.write": Role.EDITOR,
            "qms.ncr.escalate": Role.MANAGER,
            "qms.punch.read": Role.VIEWER,
            "qms.punch.write": Role.EDITOR,
            "qms.audit.read": Role.VIEWER,
            "qms.audit.write": Role.MANAGER,
            "qms.calibration.read": Role.VIEWER,
            "qms.calibration.write": Role.EDITOR,
            "qms.calibration.delete": Role.MANAGER,
            "qms.template.read": Role.VIEWER,
            "qms.template.write": Role.MANAGER,
            "qms.template.delete": Role.MANAGER,
            "qms.report.read": Role.VIEWER,
        },
    )
