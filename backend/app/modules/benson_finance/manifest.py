from app.core.edition import is_benson_edition
from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="benson_finance",
    version="0.1.0",
    display_name="Benson Finance",
    description="Benson payroll reconciliation and accounting provider adapters.",
    author="Benson Home Solutions",
    category="integration",
    depends=["oe_finance", "oe_payroll", "oe_reconciliation"],
    auto_install=True,
    enabled=is_benson_edition(),
)
