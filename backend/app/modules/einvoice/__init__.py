"""German electronic-invoicing library.

Outbound EN 16931 Cross Industry Invoice (CII) writer shared by ZUGFeRD 2.1,
Factur-X 1.0 and XRechnung 3.0. This is a pure library (no manifest, no
router of its own); the download endpoint lives in the finance module and
renders from the finance ``Invoice`` aggregate. The inbound counterpart is
``supplier_catalogs.peppol`` (UBL parser).
"""

from app.modules.einvoice.cii import (
    SUPPORTED_PROFILES,
    EInvoice,
    EInvoiceError,
    EInvoiceLine,
    Party,
    TaxSubtotal,
    build_cii_xml,
    validate,
)
from app.modules.einvoice.service import (
    build_einvoice,
    problems_for,
    render_einvoice,
)

__all__ = [
    "SUPPORTED_PROFILES",
    "EInvoice",
    "EInvoiceError",
    "EInvoiceLine",
    "Party",
    "TaxSubtotal",
    "build_cii_xml",
    "build_einvoice",
    "problems_for",
    "render_einvoice",
    "validate",
]
