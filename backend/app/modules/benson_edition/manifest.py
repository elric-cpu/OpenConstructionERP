from app.core.edition import is_benson_edition
from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="benson_edition",
    version="0.1.0",
    display_name="Benson Edition",
    description="Integrated Benson edition overlay for Eastern Oregon operations.",
    author="Benson Home Solutions",
    category="integration",
    depends=[
        "benson_operations",
        "benson_workforce",
        "benson_finance",
        "benson_security",
        "benson_workers",
    ],
    auto_install=True,
    enabled=is_benson_edition(),
)
