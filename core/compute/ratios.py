"""
Ratio computation (Phase 4) — deterministic Python only.

Computes, per period where inputs exist:
  current_ratio, debt_to_equity, debt_to_ebitda, ebitda_margin, net_margin,
  approximate_dscr, and revenue_growth (across periods).

When inputs are missing a ratio is reported as not_calculable with a clear
message (DSCR uses the specific "requires debt service input" message). Nothing
is estimated or forced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.schema import StandardizedCategory as SC
from core.schema.ratios import NOT_CALCULATED

from .aggregate import SpreadValues
from .derived import ebitda, total_debt

STATUS_OK = "ok"
STATUS_NOT_CALCULABLE = "not_calculable"


@dataclass
class RatioValue:
    name: str
    display_name: str
    period: str
    value: Optional[float]
    status: str
    message: str = ""
    is_approximation: bool = False
    inputs_used: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "period": self.period,
            "value": self.value,
            "status": self.status,
            "message": self.message,
            "is_approximation": self.is_approximation,
            "inputs_used": dict(self.inputs_used),
        }


def _ok(name, disp, period, value, approx=False, inputs=None) -> RatioValue:
    return RatioValue(name, disp, period, value, STATUS_OK,
                      is_approximation=approx, inputs_used=inputs or {})


def _na(name, disp, period, message, approx=False) -> RatioValue:
    return RatioValue(name, disp, period, None, STATUS_NOT_CALCULABLE,
                      message=message, is_approximation=approx)


def _ratio(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return num / den


def compute_ratios(values: SpreadValues) -> list[RatioValue]:
    out: list[RatioValue] = []

    for period in values.periods:
        tca = values.calc(SC.TOTAL_CURRENT_ASSETS, period)
        tcl = values.calc(SC.TOTAL_CURRENT_LIABILITIES, period)
        te = values.calc(SC.TOTAL_EQUITY, period)
        rev = values.calc(SC.REVENUE, period)
        ni = values.calc(SC.NET_INCOME, period)
        interest = values.calc(SC.INTEREST_EXPENSE, period)
        cpltd = values.calc(SC.CURRENT_PORTION_LONG_TERM_DEBT, period)
        debt = total_debt(values, period)
        eb = ebitda(values, period)

        # current ratio
        cr = _ratio(tca, tcl)
        out.append(_ok("current_ratio", "Current ratio", period, cr,
                       inputs={"total_current_assets": tca, "total_current_liabilities": tcl})
                   if cr is not None else
                   _na("current_ratio", "Current ratio", period,
                       "Missing total_current_assets and/or total_current_liabilities."))

        # debt to equity
        dte = _ratio(debt.value, te)
        out.append(_ok("debt_to_equity", "Debt-to-equity", period, dte,
                       inputs={"total_debt": debt.value, "total_equity": te})
                   if dte is not None else
                   _na("debt_to_equity", "Debt-to-equity", period,
                       "Missing total_debt components and/or total_equity."))

        # debt to EBITDA (approx)
        dte2 = _ratio(debt.value, eb.value)
        out.append(_ok("debt_to_ebitda", "Debt-to-EBITDA (approximate)", period, dte2,
                       approx=True, inputs={"total_debt": debt.value, "ebitda": eb.value})
                   if dte2 is not None else
                   _na("debt_to_ebitda", "Debt-to-EBITDA (approximate)", period,
                       "Missing total_debt and/or EBITDA inputs.", approx=True))

        # EBITDA margin (approx)
        em = _ratio(eb.value, rev)
        out.append(_ok("ebitda_margin", "EBITDA margin (approximate)", period, em,
                       approx=True, inputs={"ebitda": eb.value, "revenue": rev})
                   if em is not None else
                   _na("ebitda_margin", "EBITDA margin (approximate)", period,
                       "Missing EBITDA inputs and/or revenue.", approx=True))

        # net margin
        nm = _ratio(ni, rev)
        out.append(_ok("net_margin", "Net margin", period, nm,
                       inputs={"net_income": ni, "revenue": rev})
                   if nm is not None else
                   _na("net_margin", "Net margin", period,
                       "Missing net_income and/or revenue."))

        # approximate DSCR — only if debt-service inputs are clearly available
        if eb.value is not None and interest is not None and cpltd is not None:
            denom = abs(interest) + abs(cpltd)
            dscr = None if denom == 0 else eb.value / denom
            if dscr is not None:
                out.append(_ok("approximate_dscr",
                               "Approximate DSCR (Estimated Debt Service Coverage)",
                               period, dscr, approx=True,
                               inputs={"ebitda": eb.value,
                                       "interest_expense": interest,
                                       "current_portion_long_term_debt": cpltd}))
            else:
                out.append(_na("approximate_dscr",
                               "Approximate DSCR (Estimated Debt Service Coverage)",
                               period, "Debt service is zero; cannot divide.", approx=True))
        else:
            out.append(_na("approximate_dscr",
                           "Approximate DSCR (Estimated Debt Service Coverage)",
                           period, NOT_CALCULATED, approx=True))

    # revenue growth across adjacent periods (older -> newer)
    chrono = sorted(values.periods, key=lambda p: (0, int(p)) if p.isdigit() else (1, p))
    for i in range(1, len(chrono)):
        prior, cur = chrono[i - 1], chrono[i]
        rev_prior = values.calc(SC.REVENUE, prior)
        rev_cur = values.calc(SC.REVENUE, cur)
        if rev_prior not in (None, 0) and rev_cur is not None:
            out.append(_ok("revenue_growth", "Revenue growth (YoY)", cur,
                           rev_cur / rev_prior - 1.0,
                           inputs={"revenue": rev_cur, "revenue_prior": rev_prior}))
        else:
            out.append(_na("revenue_growth", "Revenue growth (YoY)", cur,
                           f"Missing revenue for {prior} and/or {cur}."))

    return out
