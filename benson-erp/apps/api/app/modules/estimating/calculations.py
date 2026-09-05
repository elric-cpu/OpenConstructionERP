from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

MONEY = Decimal("0.01")


class PricingMode(StrEnum):
    MARKUP = "MARKUP"
    MARGIN = "MARGIN"


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class EstimateTotals:
    direct_cost: Decimal
    selling_price: Decimal
    tax: Decimal
    total: Decimal


def calculate_totals(
    direct_cost: Decimal,
    pricing_mode: PricingMode,
    pricing_rate: Decimal,
    tax_rate: Decimal,
) -> EstimateTotals:
    if direct_cost < 0:
        raise ValueError("Direct cost cannot be negative")
    if pricing_rate < 0:
        raise ValueError("Pricing rate cannot be negative")
    if pricing_mode is PricingMode.MARGIN and pricing_rate >= 1:
        raise ValueError("Margin rate must be less than one")
    if tax_rate < 0:
        raise ValueError("Tax rate cannot be negative")
    selling_price = (
        direct_cost * (1 + pricing_rate)
        if pricing_mode is PricingMode.MARKUP
        else direct_cost / (1 - pricing_rate)
    )
    selling_price = money(selling_price)
    tax = money(selling_price * tax_rate)
    return EstimateTotals(money(direct_cost), selling_price, tax, money(selling_price + tax))
