"""Validation settings domain."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict


class ValidationSettings:
    """Validation settings."""

    # ── Validation ───────────────────────────────────────────────────────
    default_validation_rule_sets: list[str] = Field(
        default_factory=lambda: ["din276", "gaeb", "boq_quality"],
        description="Default validation rule sets to apply",
    )
    import_inline_validation: bool = Field(
        default=True,
        description="Whether to import inline validation rules from documents",
    )

    model_config = SettingsConfigDict(env_prefix="OE_")
