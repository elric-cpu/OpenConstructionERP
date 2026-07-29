from app.core.edition import is_benson_edition
from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="benson_workforce",
    version="0.1.0",
    display_name="Benson Workforce",
    description="Benson identity, onboarding, offline time, federal labor, and payroll adapters.",
    author="Benson Home Solutions",
    category="integration",
    depends=["oe_users", "oe_onboarding", "oe_field_time", "oe_compliance", "oe_payroll"],
    auto_install=True,
    enabled=is_benson_edition(),
)
