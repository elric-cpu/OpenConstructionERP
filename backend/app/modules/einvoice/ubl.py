"""EN 16931 UBL 2.1 invoice writer (Peppol BIS Billing 3.0 and plain UBL).

The international counterpart to the CII writer. UBL is the syntax used by the
Peppol network, which reaches well beyond Germany: the whole EU, plus the UK,
Australia, New Zealand, Singapore, and more. One EN 16931 invoice model, two
syntaxes (CII and UBL); this module renders the UBL side.

It is the exact inverse of ``supplier_catalogs.peppol`` (the UBL *parser*),
sharing the same UBL namespaces so import and export stay symmetric. Pure
stdlib ``xml.etree``, money kept as ``Decimal``, no new dependency.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET  # noqa: N817 - trusted, we build not parse

from app.modules.einvoice.cii import (
    EInvoice,
    EInvoiceError,
    Party,
    _money,
    _pct,
    _price,
    _qty,
    unece_unit,
    validate,
)
from app.modules.einvoice.profiles import PROFILES, get_profile

# UBL 2.1 namespaces (same URIs as the peppol parser).
INV = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

_NS = {"": INV, "cac": CAC, "cbc": CBC}
for _p, _u in _NS.items():
    ET.register_namespace(_p, _u)


def _c(prefix: str, local: str) -> str:
    return f"{{{_NS[prefix]}}}{local}"


def _sub(parent: ET.Element, prefix: str, local: str, text: str | None = None) -> ET.Element:
    el = ET.SubElement(parent, _c(prefix, local))
    if text is not None:
        el.text = text
    return el


def _amt(parent: ET.Element, local: str, value: str, currency: str) -> ET.Element:
    el = _sub(parent, "cbc", local, value)
    el.set("currencyID", currency)
    return el


def _iso_date(iso: str) -> str:
    d = (iso or "")[:10]
    parts = d.split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise EInvoiceError(f"invalid date {iso!r} (need YYYY-MM-DD)")
    return d


def _party(parent: ET.Element, wrapper_local: str, p: Party) -> None:
    wrap = _sub(parent, "cac", wrapper_local)
    party = _sub(wrap, "cac", "Party")
    if p.electronic_address:
        ep = _sub(party, "cbc", "EndpointID", p.electronic_address)
        if p.contact_id_scheme:
            ep.set("schemeID", p.contact_id_scheme)
    pn = _sub(party, "cac", "PartyName")
    _sub(pn, "cbc", "Name", p.name)
    addr = _sub(party, "cac", "PostalAddress")
    if p.line1:
        _sub(addr, "cbc", "StreetName", p.line1)
    if p.city:
        _sub(addr, "cbc", "CityName", p.city)
    if p.postcode:
        _sub(addr, "cbc", "PostalZone", p.postcode)
    country = _sub(addr, "cac", "Country")
    _sub(country, "cbc", "IdentificationCode", (p.country_code or "DE").upper())
    if p.vat_id:
        pts = _sub(party, "cac", "PartyTaxScheme")
        _sub(pts, "cbc", "CompanyID", p.vat_id)
        scheme = _sub(pts, "cac", "TaxScheme")
        _sub(scheme, "cbc", "ID", "VAT")
    legal = _sub(party, "cac", "PartyLegalEntity")
    _sub(legal, "cbc", "RegistrationName", p.name)
    if p.legal_id:
        _sub(legal, "cbc", "CompanyID", p.legal_id)
    if p.email:
        contact = _sub(party, "cac", "Contact")
        _sub(contact, "cbc", "ElectronicMail", p.email)


def build_ubl_xml(inv: EInvoice, *, strict: bool = True) -> bytes:
    """Render an :class:`EInvoice` as EN 16931 UBL (Peppol BIS) XML bytes."""
    profile = get_profile(inv.profile)
    if profile is None or profile.syntax != "ubl":
        raise EInvoiceError(
            f"profile {inv.profile!r} is not a UBL profile "
            f"(supported UBL: {', '.join(n for n, p in PROFILES.items() if p.syntax == 'ubl')})"
        )
    if strict:
        problems = validate(inv)
        if problems:
            raise EInvoiceError("; ".join(problems))

    cur = inv.currency
    root = ET.Element(_c("", "Invoice"))

    _sub(root, "cbc", "CustomizationID", profile.guideline)
    if profile.profile_id:
        _sub(root, "cbc", "ProfileID", profile.profile_id)
    _sub(root, "cbc", "ID", inv.invoice_number)
    _sub(root, "cbc", "IssueDate", _iso_date(inv.issue_date))
    if inv.due_date:
        _sub(root, "cbc", "DueDate", _iso_date(inv.due_date))
    _sub(root, "cbc", "InvoiceTypeCode", inv.type_code)
    if inv.note:
        _sub(root, "cbc", "Note", inv.note)
    _sub(root, "cbc", "DocumentCurrencyCode", cur)
    if inv.buyer_reference:
        _sub(root, "cbc", "BuyerReference", inv.buyer_reference)
    if inv.order_reference:
        oref = _sub(root, "cac", "OrderReference")
        _sub(oref, "cbc", "ID", inv.order_reference)

    _party(root, "AccountingSupplierParty", inv.seller)
    _party(root, "AccountingCustomerParty", inv.buyer)

    if inv.payment_means_code:
        pm = _sub(root, "cac", "PaymentMeans")
        _sub(pm, "cbc", "PaymentMeansCode", inv.payment_means_code)
    if inv.payment_terms:
        pt = _sub(root, "cac", "PaymentTerms")
        _sub(pt, "cbc", "Note", inv.payment_terms)

    # Tax total + subtotals.
    tt = _sub(root, "cac", "TaxTotal")
    _amt(tt, "TaxAmount", _money(inv.tax_total), cur)
    for grp in inv.tax_subtotals:
        sub = _sub(tt, "cac", "TaxSubtotal")
        _amt(sub, "TaxableAmount", _money(grp.basis), cur)
        _amt(sub, "TaxAmount", _money(grp.tax_amount), cur)
        cat = _sub(sub, "cac", "TaxCategory")
        _sub(cat, "cbc", "ID", grp.category)
        _sub(cat, "cbc", "Percent", _pct(grp.rate))
        scheme = _sub(cat, "cac", "TaxScheme")
        _sub(scheme, "cbc", "ID", "VAT")

    # Monetary totals.
    lmt = _sub(root, "cac", "LegalMonetaryTotal")
    _amt(lmt, "LineExtensionAmount", _money(inv.line_total), cur)
    _amt(lmt, "TaxExclusiveAmount", _money(inv.tax_basis_total), cur)
    _amt(lmt, "TaxInclusiveAmount", _money(inv.grand_total), cur)
    if inv.prepaid_amount:
        _amt(lmt, "PrepaidAmount", _money(inv.prepaid_amount), cur)
    _amt(lmt, "PayableAmount", _money(inv.due_payable), cur)

    # Lines.
    for line in inv.lines:
        il = _sub(root, "cac", "InvoiceLine")
        _sub(il, "cbc", "ID", line.line_id)
        _sub(il, "cbc", "InvoicedQuantity", _qty(line.quantity)).set("unitCode", unece_unit(line.unit))
        _amt(il, "LineExtensionAmount", _money(line.line_net_amount), cur)
        item = _sub(il, "cac", "Item")
        _sub(item, "cbc", "Name", line.name or "-")
        cat = _sub(item, "cac", "ClassifiedTaxCategory")
        _sub(cat, "cbc", "ID", line.vat_category)
        _sub(cat, "cbc", "Percent", _pct(line.vat_rate))
        scheme = _sub(cat, "cac", "TaxScheme")
        _sub(scheme, "cbc", "ID", "VAT")
        price = _sub(il, "cac", "Price")
        _amt(price, "PriceAmount", _price(line.net_unit_price), cur)

    ET.indent(root, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")
