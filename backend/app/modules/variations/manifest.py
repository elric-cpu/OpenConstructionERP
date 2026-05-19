"""‌⁠‍Variations module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_variations",
    version="0.1.0",
    display_name="Variations & Site Measurements",
    description=(
        "Variations lifecycle: Notice -> VR -> VO -> site measurements -> "
        "daywork -> disruption/EOT claims -> Final Account"
    ),
    author="OpenConstructionERP Core Team",
    category="business",
    depends=["oe_users", "oe_projects"],
    auto_install=True,
    enabled=True,
)
