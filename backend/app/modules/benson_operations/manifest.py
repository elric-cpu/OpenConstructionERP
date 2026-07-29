from app.core.edition import is_benson_edition
from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="benson_operations",
    version="0.1.0",
    display_name="Benson Operations",
    description="Benson CRM, estimating, documents, and scheduling adapters over upstream services.",
    author="Benson Home Solutions",
    category="integration",
    depends=["oe_crm", "oe_boq", "oe_documents", "oe_signing", "oe_schedule", "oe_schedule_advanced"],
    auto_install=True,
    enabled=is_benson_edition(),
)
