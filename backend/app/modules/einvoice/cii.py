"""EN 16931 Cross Industry Invoice (CII) builder.

Produces the UN/CEFACT CII XML that is the shared syntax behind the German
electronic-invoice formats:

    * ZUGFeRD 2.1 (the CII XML embedded in a PDF/A-3 hybrid invoice)
    * Factur-X 1.0 (the French twin of ZUGFeRD, same CII)
    * XRechnung (the German public-sector CII profile, EN 16931 compliant)

All three share the EN 16931 semantic model; they differ only in the
guideline identifier (BT-24) and a few conditionally mandatory terms
(XRechnung requires the Buyer reference / Leitweg-ID, BT-10).

Design mirrors the existing GAEB writer (``boq.build_gaeb_xml``) and the BCF
codec: a pure, side-effect-free builder over stdlib ``xml.etree`` with all
money kept as ``Decimal``. The inbound counterpart is
``supplier_catalogs.peppol`` (UBL parser); this is the outbound CII writer.

References:
    * EN 16931-1 semantic data model
    * ZUGFeRD 2.1 / Factur-X 1.0 technical spec (CII D16B)
    * XRechnung 3.0 (KoSIT)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from xml.etree import ElementTree as ET  # noqa: N817 - trusted, we build not parse

# --- namespaces -----------------------------------------------------------

RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"

_NS = {"rsm": RSM, "ram": RAM, "udt": UDT}
for _p, _u in _NS.items():
    ET.register_namespace(_p, _u)


def _q(prefix: str, local: str) -> str:
    """Namespace-qualified tag, e.g. ``_q("ram", "ID")``."""
    return f"{{{_NS[prefix]}}}{local}"


# --- profiles -------------------------------------------------------------

# BT-24 guideline identifiers per target format.
_GUIDELINE = {
    "en16931": "urn:cen.eu:en16931:2017",
    "zugferd": "urn:cen.eu:en16931:2017",
    "facturx": "urn:cen.eu:en16931:2017",
    "xrechnung": ("urn:cen.eu:en16931:2017#compliant#urn:xoev-de:kosit:standard:xrechnung_3.0"),
}
# Profiles that make the Buyer reference (BT-10) mandatory.
_BUYER_REF_REQUIRED = {"xrechnung"}

SUPPORTED_PROFILES = tuple(_GUIDELINE)

# Inverse of peppol._UNIT_MAP: internal unit label -> UNECE Rec-20 code.
# Kept local so the two modules stay decoupled; falls back to piece (C62).
_UNECE_BY_UNIT = {
    "pcs": "C62",
    "pc": "C62",
    "pce": "C62",
    "each": "C62",
    "pair": "PR",
    "m": "MTR",
    "lm": "MTR",
    "rm": "MTR",
    "km": "KMT",
    "cm": "CMT",
    "mm": "MMT",
    "m2": "MTK",
    "sqm": "MTK",
    "m3": "MTQ",
    "cbm": "MTQ",
    "l": "LTR",
    "kg": "KGM",
    "t": "TNE",
    "ton": "TNE",
    "g": "GRM",
    "h": "HUR",
    "hr": "HUR",
    "hour": "HUR",
    "day": "DAY",
    "d": "DAY",
    "lsum": "LS",
    "ls": "LS",
    "psch": "LS",
    "%": "P1",
}


def unece_unit(unit: str | None) -> str:
    """Map an internal unit label to a UNECE Rec-20 code (default C62 = piece)."""
    if not unit:
        return "C62"
    return _UNECE_BY_UNIT.get(unit.strip().lower(), "C62")


# --- data model -----------------------------------------------------------


class EInvoiceError(ValueError):
    """Raised when the invoice data cannot produce a valid CII document."""


@dataclass
class Party:
    """A seller or buyer trade party (EN 16931 BG-4 / BG-7)."""

    name: str
    country_code: str = "DE"
    vat_id: str | None = None  # BT-31 / BT-48 (USt-IdNr., e.g. DE123456789)
    tax_number: str | None = None  # BT-32 (Steuernummer) when no VAT id
    legal_id: str | None = None  # BT-30 / BT-47 registration id
    line1: str | None = None  # BT-35 / BT-50
    postcode: str | None = None  # BT-38 / BT-53
    city: str | None = None  # BT-37 / BT-52
    email: str | None = None
    contact_id_scheme: str | None = None  # e.g. Leitweg endpoint scheme
    electronic_address: str | None = None  # BT-34 / BT-49 (Peppol endpoint)


@dataclass
class EInvoiceLine:
    """A single invoice line (BG-25)."""

    line_id: str
    name: str
    quantity: Decimal
    unit: str | None
    net_unit_price: Decimal  # BT-146
    line_net_amount: Decimal  # BT-131
    vat_rate: Decimal  # BT-152 (percent, e.g. 19)
    vat_category: str = "S"  # BT-151 (S standard, Z zero, AE reverse, E exempt)


@dataclass
class TaxSubtotal:
    """A VAT breakdown group (BG-23), one per rate/category."""

    category: str
    rate: Decimal
    basis: Decimal  # BT-116
    tax_amount: Decimal  # BT-117


@dataclass
class EInvoice:
    """The full EN 16931 invoice, ready to render as CII."""

    profile: str
    invoice_number: str  # BT-1
    issue_date: str  # BT-2 (ISO YYYY-MM-DD)
    currency: str  # BT-5
    seller: Party
    buyer: Party
    lines: list[EInvoiceLine]
    tax_subtotals: list[TaxSubtotal]
    line_total: Decimal  # BT-106
    tax_basis_total: Decimal  # BT-109
    tax_total: Decimal  # BT-110
    grand_total: Decimal  # BT-112
    due_payable: Decimal  # BT-115
    type_code: str = "380"  # BT-3 (380 invoice, 381 credit note)
    buyer_reference: str | None = None  # BT-10 (Leitweg-ID for XRechnung)
    order_reference: str | None = None  # BT-13 (buyer PO)
    due_date: str | None = None  # BT-9 (ISO)
    payment_terms: str | None = None  # BT-20
    prepaid_amount: Decimal = Decimal("0")  # BT-113
    note: str | None = None  # BT-22
    tax_currency: str | None = None
    payment_means_code: str = "30"  # BT-81 (30 credit transfer)


# --- formatting helpers ---------------------------------------------------

_2P = Decimal("0.01")
_4P = Decimal("0.0001")


def _money(value: Decimal) -> str:
    return str(value.quantize(_2P, rounding=ROUND_HALF_UP))


def _price(value: Decimal) -> str:
    # Net unit price may carry up to 4 decimals (BT-146); trim to a tidy string.
    q = value.quantize(_4P, rounding=ROUND_HALF_UP).normalize()
    # normalize() can yield exponent form for integers (e.g. 5E+1); expand it.
    return f"{q:f}"


def _qty(value: Decimal) -> str:
    q = value.quantize(_4P, rounding=ROUND_HALF_UP).normalize()
    return f"{q:f}"


def _pct(value: Decimal) -> str:
    return str(value.quantize(_2P, rounding=ROUND_HALF_UP))


def _cii_date(iso: str) -> str:
    """ISO ``YYYY-MM-DD`` (or longer) -> CII ``YYYYMMDD`` (format 102)."""
    digits = "".join(ch for ch in iso[:10] if ch.isdigit())
    if len(digits) != 8:
        raise EInvoiceError(f"invalid invoice date: {iso!r} (need YYYY-MM-DD)")
    return digits


def _sub(parent: ET.Element, prefix: str, local: str, text: str | None = None) -> ET.Element:
    el = ET.SubElement(parent, _q(prefix, local))
    if text is not None:
        el.text = text
    return el


def _date_el(parent: ET.Element, prefix: str, local: str, iso: str) -> None:
    wrap = _sub(parent, prefix, local)
    ds = _sub(wrap, "udt", "DateTimeString", _cii_date(iso))
    ds.set("format", "102")


# --- validation -----------------------------------------------------------


def validate(inv: EInvoice) -> list[str]:
    """Return a list of EN 16931 mandatory-field problems (empty = ok).

    This is a pragmatic subset of the business rules - enough to catch the
    fields a receiver's validator will reject on, without pulling in a full
    Schematron engine.
    """
    problems: list[str] = []
    if inv.profile not in _GUIDELINE:
        problems.append(f"unknown profile {inv.profile!r} (BT-24)")
    if not inv.invoice_number:
        problems.append("missing invoice number (BT-1)")
    if not inv.issue_date:
        problems.append("missing issue date (BT-2)")
    if not inv.currency:
        problems.append("missing currency (BT-5)")
    if not inv.lines:
        problems.append("invoice has no lines (BR-16)")
    for who, p in (("seller", inv.seller), ("buyer", inv.buyer)):
        if not p.name:
            problems.append(f"missing {who} name")
        if not p.country_code:
            problems.append(f"missing {who} country code (BR-08/BR-11)")
    if not (inv.seller.vat_id or inv.seller.tax_number):
        problems.append("seller needs a VAT id (BT-31) or tax number (BT-32)")
    if inv.profile in _BUYER_REF_REQUIRED and not inv.buyer_reference:
        problems.append("XRechnung requires a Buyer reference / Leitweg-ID (BT-10)")
    # Totals must reconcile (BR-CO-*).
    if inv.line_total != sum((line.line_net_amount for line in inv.lines), Decimal("0")):
        problems.append("sum of line net amounts != document line total (BR-CO-10)")
    expected_grand = inv.tax_basis_total + inv.tax_total
    if inv.grand_total != expected_grand:
        problems.append("grand total != tax basis + tax total (BR-CO-15)")
    if inv.due_payable != inv.grand_total - inv.prepaid_amount:
        problems.append("amount due != grand total - prepaid (BR-CO-16)")
    return problems


# --- party rendering ------------------------------------------------------


def _party(parent: ET.Element, tag_local: str, p: Party) -> None:
    tp = _sub(parent, "ram", tag_local)
    if p.legal_id:
        _sub(tp, "ram", "ID", p.legal_id)
    _sub(tp, "ram", "Name", p.name)
    if p.legal_id:
        org = _sub(tp, "ram", "SpecifiedLegalOrganization")
        _sub(org, "ram", "ID", p.legal_id)
    if p.electronic_address:
        comm = _sub(tp, "ram", "URIUniversalCommunication")
        uri = _sub(comm, "ram", "URIID", p.electronic_address)
        if p.contact_id_scheme:
            uri.set("schemeID", p.contact_id_scheme)
    addr = _sub(tp, "ram", "PostalTradeAddress")
    if p.postcode:
        _sub(addr, "ram", "PostcodeCode", p.postcode)
    if p.line1:
        _sub(addr, "ram", "LineOne", p.line1)
    if p.city:
        _sub(addr, "ram", "CityName", p.city)
    _sub(addr, "ram", "CountryID", (p.country_code or "DE").upper())
    if p.email:
        comm = _sub(tp, "ram", "URIUniversalCommunication")
        em = _sub(comm, "ram", "URIID", p.email)
        em.set("schemeID", "EM")
    if p.vat_id:
        reg = _sub(tp, "ram", "SpecifiedTaxRegistration")
        _sub(reg, "ram", "ID", p.vat_id).set("schemeID", "VA")
    elif p.tax_number:
        reg = _sub(tp, "ram", "SpecifiedTaxRegistration")
        _sub(reg, "ram", "ID", p.tax_number).set("schemeID", "FC")


# --- main builder ---------------------------------------------------------


def build_cii_xml(inv: EInvoice, *, strict: bool = True) -> bytes:
    """Render an :class:`EInvoice` as EN 16931 CII XML bytes.

    Args:
        inv: the fully populated invoice.
        strict: when True (default) raise :class:`EInvoiceError` if the
            invoice fails :func:`validate`. Set False to emit a best-effort
            document for inspection/debugging.
    """
    if strict:
        problems = validate(inv)
        if problems:
            raise EInvoiceError("; ".join(problems))

    root = ET.Element(_q("rsm", "CrossIndustryInvoice"))

    # 1. ExchangedDocumentContext (guideline / profile)
    ctx = _sub(root, "rsm", "ExchangedDocumentContext")
    gp = _sub(ctx, "ram", "GuidelineSpecifiedDocumentContextParameter")
    _sub(gp, "ram", "ID", _GUIDELINE[inv.profile])

    # 2. ExchangedDocument (header)
    doc = _sub(root, "rsm", "ExchangedDocument")
    _sub(doc, "ram", "ID", inv.invoice_number)
    _sub(doc, "ram", "TypeCode", inv.type_code)
    _date_el(doc, "ram", "IssueDateTime", inv.issue_date)
    if inv.note:
        note = _sub(doc, "ram", "IncludedNote")
        _sub(note, "ram", "Content", inv.note)

    # 3. SupplyChainTradeTransaction
    tx = _sub(root, "rsm", "SupplyChainTradeTransaction")

    # 3a. Lines
    for line in inv.lines:
        li = _sub(tx, "ram", "IncludedSupplyChainTradeLineItem")
        doc_line = _sub(li, "ram", "AssociatedDocumentLineDocument")
        _sub(doc_line, "ram", "LineID", line.line_id)
        prod = _sub(li, "ram", "SpecifiedTradeProduct")
        _sub(prod, "ram", "Name", line.name or "-")
        agr = _sub(li, "ram", "SpecifiedLineTradeAgreement")
        price = _sub(agr, "ram", "NetPriceProductTradePrice")
        _sub(price, "ram", "ChargeAmount", _price(line.net_unit_price))
        dlv = _sub(li, "ram", "SpecifiedLineTradeDelivery")
        _sub(dlv, "ram", "BilledQuantity", _qty(line.quantity)).set("unitCode", unece_unit(line.unit))
        stl = _sub(li, "ram", "SpecifiedLineTradeSettlement")
        tax = _sub(stl, "ram", "ApplicableTradeTax")
        _sub(tax, "ram", "TypeCode", "VAT")
        _sub(tax, "ram", "CategoryCode", line.vat_category)
        _sub(tax, "ram", "RateApplicablePercent", _pct(line.vat_rate))
        summ = _sub(stl, "ram", "SpecifiedTradeSettlementLineMonetarySummation")
        _sub(summ, "ram", "LineTotalAmount", _money(line.line_net_amount))

    # 3b. Header agreement (buyer ref, seller, buyer, order ref)
    agr = _sub(tx, "ram", "ApplicableHeaderTradeAgreement")
    if inv.buyer_reference:
        _sub(agr, "ram", "BuyerReference", inv.buyer_reference)
    _party(agr, "SellerTradeParty", inv.seller)
    _party(agr, "BuyerTradeParty", inv.buyer)
    if inv.order_reference:
        ref = _sub(agr, "ram", "BuyerOrderReferencedDocument")
        _sub(ref, "ram", "IssuerAssignedID", inv.order_reference)

    # 3c. Header delivery (mandatory container, may be empty)
    _sub(tx, "ram", "ApplicableHeaderTradeDelivery")

    # 3d. Header settlement (currency, tax breakdown, payment, totals)
    stl = _sub(tx, "ram", "ApplicableHeaderTradeSettlement")
    _sub(stl, "ram", "InvoiceCurrencyCode", inv.currency)
    if inv.tax_currency:
        _sub(stl, "ram", "TaxCurrencyCode", inv.tax_currency)

    if inv.payment_means_code:
        pm = _sub(stl, "ram", "SpecifiedTradeSettlementPaymentMeans")
        _sub(pm, "ram", "TypeCode", inv.payment_means_code)

    for grp in inv.tax_subtotals:
        tax = _sub(stl, "ram", "ApplicableTradeTax")
        _sub(tax, "ram", "CalculatedAmount", _money(grp.tax_amount))
        _sub(tax, "ram", "TypeCode", "VAT")
        _sub(tax, "ram", "BasisAmount", _money(grp.basis))
        _sub(tax, "ram", "CategoryCode", grp.category)
        _sub(tax, "ram", "RateApplicablePercent", _pct(grp.rate))

    if inv.due_date or inv.payment_terms:
        terms = _sub(stl, "ram", "SpecifiedTradePaymentTerms")
        if inv.payment_terms:
            _sub(terms, "ram", "Description", inv.payment_terms)
        if inv.due_date:
            _date_el(terms, "ram", "DueDateDateTime", inv.due_date)

    summ = _sub(stl, "ram", "SpecifiedTradeSettlementHeaderMonetarySummation")
    _sub(summ, "ram", "LineTotalAmount", _money(inv.line_total))
    _sub(summ, "ram", "TaxBasisTotalAmount", _money(inv.tax_basis_total))
    _sub(summ, "ram", "TaxTotalAmount", _money(inv.tax_total)).set("currencyID", inv.currency)
    _sub(summ, "ram", "GrandTotalAmount", _money(inv.grand_total))
    if inv.prepaid_amount:
        _sub(summ, "ram", "TotalPrepaidAmount", _money(inv.prepaid_amount))
    _sub(summ, "ram", "DuePayableAmount", _money(inv.due_payable))

    ET.indent(root, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")
