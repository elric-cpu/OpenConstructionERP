# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Basis-of-estimate module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_estimate_basis",
    version="1.0.0",
    display_name="Basis of Estimate",
    description=(
        "Auto-drafts the qualifications that accompany an estimate - what it "
        "includes, what it excludes and the assumptions behind it - from the "
        "finished estimate contents. Reads which trades are present, absent or "
        "flagged by the coverage check, drafts editable inclusions, exclusions "
        "and assumptions, and exports them with the proposal."
    ),
    author="OpenConstructionERP Core Team",
    category="business",
    # Reads BOQ positions and verifies project access.
    depends=["oe_boq", "oe_projects"],
    auto_install=True,
    enabled=True,
)
