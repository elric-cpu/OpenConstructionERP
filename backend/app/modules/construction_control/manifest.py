# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Construction-control module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_construction_control",
    version="0.1.0",
    display_name="Construction Control",
    description=(
        "Universal QA/QC engine: acceptance criteria, inspections (MIR/WIR/IR/"
        "hidden-works/acceptance) and format-agnostic model linking, with a "
        "failed inspection automatically raising a non-conformance report."
    ),
    author="OpenConstructionERP Core Team",
    category="core",
    depends=["oe_users", "oe_projects", "oe_bim_hub", "oe_ncr"],
    auto_install=True,
    enabled=True,
)
