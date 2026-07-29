from app.core.edition import is_benson_edition
from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="benson_security",
    version="0.1.0",
    display_name="Benson Security",
    description="Benson MFA, role policy, immutable document, and audit adapters.",
    author="Benson Home Solutions",
    category="integration",
    depends=["oe_users", "oe_admin", "oe_documents", "oe_signing"],
    auto_install=True,
    enabled=is_benson_edition(),
)
