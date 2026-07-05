"""E-invoice profile registry.

The invoice model is EN 16931, which is the *international* semantic standard
behind e-invoicing in the EU and a growing list of countries. A "profile" here
binds that shared model to a concrete country/network flavour: the syntax
(CII or UBL), the guideline identifier (BT-24 CustomizationID), an optional
UBL ProfileID (BT-23), and the few conditionally mandatory rules that differ
per flavour.

Adding a new country = adding one :class:`Profile` entry. Nothing about the
builder is Germany-specific; XRechnung is just one profile among many, and the
UBL/Peppol profile makes the same invoice usable across every Peppol country
(EU, UK, Australia, New Zealand, Singapore, ...).
"""

from __future__ import annotations

from dataclasses import dataclass

# --- guideline / customization identifiers --------------------------------

EN16931 = "urn:cen.eu:en16931:2017"  # plain EN 16931 (CII or UBL)
XRECHNUNG = "urn:cen.eu:en16931:2017#compliant#urn:xoev-de:kosit:standard:xrechnung_3.0"
PEPPOL_CUSTOMIZATION = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
PEPPOL_PROFILE = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"


@dataclass(frozen=True)
class Profile:
    """A concrete e-invoice flavour (syntax + identifiers + local rules)."""

    name: str
    syntax: str  # "cii" or "ubl"
    guideline: str  # BT-24 (CustomizationID)
    profile_id: str | None = None  # BT-23 (UBL ProfileID, e.g. Peppol)
    buyer_ref_required: bool = False  # BT-10 mandatory
    order_ref_alternative: bool = False  # BT-13 may satisfy the BT-10 rule
    region: str = "international"
    label: str = ""


# Registry. Keys are the ?format= values accepted by the endpoint.
PROFILES: dict[str, Profile] = {
    # --- international / cross-border ---
    "en16931": Profile("en16931", "cii", EN16931, region="EU", label="EN 16931 (CII)"),
    "ubl": Profile("ubl", "ubl", EN16931, region="international", label="EN 16931 (UBL)"),
    "peppol": Profile(
        "peppol",
        "ubl",
        PEPPOL_CUSTOMIZATION,
        profile_id=PEPPOL_PROFILE,
        buyer_ref_required=True,
        order_ref_alternative=True,
        region="international",
        label="Peppol BIS Billing 3.0",
    ),
    # --- country flavours (all built on the same EN 16931 model) ---
    "zugferd": Profile("zugferd", "cii", EN16931, region="DE/FR", label="ZUGFeRD 2.1"),
    "facturx": Profile("facturx", "cii", EN16931, region="FR/DE", label="Factur-X 1.0"),
    "xrechnung": Profile(
        "xrechnung",
        "cii",
        XRECHNUNG,
        buyer_ref_required=True,
        region="DE",
        label="XRechnung 3.0",
    ),
}

SUPPORTED_PROFILES: tuple[str, ...] = tuple(PROFILES)


def get_profile(name: str) -> Profile | None:
    """Look up a profile by its ?format= key (case-insensitive)."""
    return PROFILES.get((name or "").strip().lower())
