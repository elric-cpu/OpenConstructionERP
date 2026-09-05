from decimal import Decimal

import pytest
from app.modules.estimating.calculations import PricingMode, calculate_totals


def test_markup_calculation_is_traceable_and_rounded() -> None:
    totals = calculate_totals(
        direct_cost=Decimal("1000.00"),
        pricing_mode=PricingMode.MARKUP,
        pricing_rate=Decimal("0.20"),
        tax_rate=Decimal("0.05"),
    )
    assert totals.direct_cost == Decimal("1000.00")
    assert totals.selling_price == Decimal("1200.00")
    assert totals.tax == Decimal("60.00")
    assert totals.total == Decimal("1260.00")


def test_margin_calculation_differs_from_markup() -> None:
    totals = calculate_totals(
        direct_cost=Decimal("1000.00"),
        pricing_mode=PricingMode.MARGIN,
        pricing_rate=Decimal("0.20"),
        tax_rate=Decimal("0"),
    )
    assert totals.selling_price == Decimal("1250.00")


@pytest.mark.parametrize("rate", [Decimal("1"), Decimal("1.1")])
def test_invalid_margin_is_rejected(rate: Decimal) -> None:
    with pytest.raises(ValueError, match="less than one"):
        calculate_totals(Decimal("100"), PricingMode.MARGIN, rate, Decimal("0"))
