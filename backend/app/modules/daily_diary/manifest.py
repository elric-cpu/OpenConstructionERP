"""‌⁠‍Daily Site Diary module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_daily_diary",
    version="0.1.0",
    display_name="Daily Site Diary",
    description=(
        "Legally significant daily site diary: weather, entries, photos, videos, "
        "drone surveys, reality capture, immutable signed archive"
    ),
    author="OpenConstructionERP Core Team",
    category="business",
    depends=["oe_users", "oe_projects"],
    auto_install=True,
    enabled=True,
)
