"""
Derived quantities (Phase 4): total debt and EBITDA, per period.

All deterministic Python. Uses calculation_value via SpreadValues.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.schema import StandardizedCategory as SC

from .aggregate import SpreadValues

_DEBT_COMPONENTS = (SC.SHORT_TERM_DEBT, SC.CURRENT_PORTION_LONG_TERM_DEBT, SC.LONG_TERM_DEBT)


@dataclass
class DerivedValue:
    value: Optional[float]
    method: str          # how it was computed, for transparency
    available: bool


def total_debt(values: SpreadValues, period: str) -> DerivedValue:
    """Sum of present debt components. Available if at least one is present."""
    parts = [(c, values.calc(c, period)) for c in _DEBT_COMPONENTS if values.present(c, period)]
    if not parts:
        return DerivedValue(None, "no debt components present", False)
    total = sum(v for _c, v in parts)
    used = ", ".join(c.value for c, _v in parts)
    return DerivedValue(total, f"sum of {used}", True)


def ebitda(values: SpreadValues, period: str) -> DerivedValue:
    """
    EBITDA (approximate). Preferred: operating_income + depreciation_amortization.
    Fallback: net_income + interest_expense + income_tax_expense + D&A (add-backs),
    using calculation_value signs (expenses are negative, so we subtract them).
    """
    oi = values.calc(SC.OPERATING_INCOME, period)
    da = values.calc(SC.DEPRECIATION_AMORTIZATION, period)
    if oi is not None and da is not None:
        return DerivedValue(oi + da, "operating_income + depreciation_amortization", True)

    ni = values.calc(SC.NET_INCOME, period)
    interest = values.calc(SC.INTEREST_EXPENSE, period)
    tax = values.calc(SC.INCOME_TAX_EXPENSE, period)
    if None not in (ni, interest, tax) and da is not None:
        # interest and tax calc-values are negative; subtracting them adds the
        # positive expense magnitude back.
        value = ni - interest - tax + da
        return DerivedValue(
            value, "net_income + interest_expense + income_tax_expense + D&A", True
        )

    return DerivedValue(None, "insufficient inputs for EBITDA", False)
