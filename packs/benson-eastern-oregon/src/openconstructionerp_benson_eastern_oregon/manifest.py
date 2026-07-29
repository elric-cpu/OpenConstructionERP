"""Partner-pack manifest for the Benson Eastern Oregon edition."""

from app.core.partner_pack.manifest import PartnerBranding, PartnerPackManifest

MANIFEST = PartnerPackManifest(
    slug="benson-eastern-oregon",
    partner_name="Benson Home Solutions",
    partner_url="https://bensonhomesolutions.com",
    pack_version="12.9.0",
    pack_type="partner",
    description=(
        "Benson Home Solutions operating profile for Eastern Oregon, extending "
        "the upstream US construction profile with project-specific jurisdiction "
        "and timezone requirements."
    ),
    default_locale="en-US",
    additional_locales={},
    cwicr_regions=["cwicr-usa-usd"],
    default_currency="USD",
    default_tax_template="us_state_sales_tax",
    default_methodology="united_states",
    validation_rule_packs=[
        "masterformat_2020",
        "uniformat_ii_e1557",
        "aia_a201_2017",
        "aia_owner_contractor",
        "osha_1926",
        "ibc_2021",
        "rsmeans_city_index",
    ],
    default_modules=[],
    hidden_modules=[],
    demo_template_ids=["commercial-denver", "medical-us"],
    branding=PartnerBranding(
        primary_color="#173F35",
        accent_color="#B46A3C",
        logo_path="logo.svg",
        favicon_path=None,
        powered_by_text=None,
    ),
    onboarding_script_path="onboarding.yaml",
    metadata={
        "extends": "us-rsmeans",
        "country": "US",
        "state": "OR",
        "operating_region": "Eastern Oregon",
        "unit_system": "imperial",
        "project_context_required": ["county", "local_jurisdiction", "timezone"],
        "timezone_format": "IANA",
        "timezone_scope": "project",
        "county_policy": "open-no-whitelist",
    },
)
