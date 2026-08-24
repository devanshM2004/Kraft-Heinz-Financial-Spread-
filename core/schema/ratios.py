"""
Ratio specifications (Phase 1 — definitions only, NO computation).

Each RatioSpec declares:
  - what the ratio is and how it is defined,
  - which standardized categories it needs as inputs, and
  - what to emit when inputs are missing.

Phase 4 will consume these specs to compute values deterministically in Python
and to raise RATIO_NOT_CALCULABLE findings when required inputs are absent.

DSCR wording (deliberate)
-------------------------
The MVP does NOT produce a bank-quality, CFADS-based DSCR. It produces an
approximation from income-statement/balance-sheet inputs only. It is therefore
always labelled "Approximate DSCR (Estimated Debt Service Coverage)". If the
required debt-service inputs are not clearly available, the ratio is reported as
"Not calculated / requires debt service input" rather than being estimated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .categories import StandardizedCategory as SC

# Sentinel string the compute layer emits when a ratio cannot be computed.
NOT_CALCULATED = "Not calculated / requires debt service input"
NOT_CALCULABLE_GENERIC = "Not calculated / missing required inputs"


@dataclass(frozen=True)
class DerivedQuantity:
    """
    A named intermediate (e.g. total debt, EBITDA) built from categories.
    `primary` is the preferred input set; `fallback` is an alternative build
    when the primary inputs are not all present.
    """
    name: str
    display_name: str
    definition: str
    primary: tuple[SC, ...]
    fallback: tuple[SC, ...] = ()


TOTAL_DEBT = DerivedQuantity(
    name="total_debt",
    display_name="Total debt",
    definition="short_term_debt + current_portion_long_term_debt + long_term_debt",
    primary=(SC.SHORT_TERM_DEBT, SC.CURRENT_PORTION_LONG_TERM_DEBT, SC.LONG_TERM_DEBT),
)

EBITDA = DerivedQuantity(
    name="ebitda",
    display_name="EBITDA (approximate)",
    definition=(
        "Preferred: operating_income + depreciation_amortization. "
        "Fallback: net_income + interest_expense + income_tax_expense "
        "+ depreciation_amortization."
    ),
    primary=(SC.OPERATING_INCOME, SC.DEPRECIATION_AMORTIZATION),
    fallback=(
        SC.NET_INCOME,
        SC.INTEREST_EXPENSE,
        SC.INCOME_TAX_EXPENSE,
        SC.DEPRECIATION_AMORTIZATION,
    ),
)

DERIVED_QUANTITIES: tuple[DerivedQuantity, ...] = (TOTAL_DEBT, EBITDA)


@dataclass(frozen=True)
class RatioSpec:
    name: str
    display_name: str
    definition: str
    # Standardized categories required directly (beyond any derived quantities).
    required_categories: tuple[SC, ...] = ()
    # Derived quantities required (e.g. EBITDA, total debt).
    required_derived: tuple[str, ...] = ()
    # Message to emit when the ratio cannot be computed.
    not_calculable_message: str = NOT_CALCULABLE_GENERIC
    # True when this ratio needs two periods (year-over-year).
    needs_prior_period: bool = False
    is_approximation: bool = False
    notes: str = ""


RATIO_SPECS: tuple[RatioSpec, ...] = (
    RatioSpec(
        name="current_ratio",
        display_name="Current ratio",
        definition="total_current_assets / total_current_liabilities",
        required_categories=(SC.TOTAL_CURRENT_ASSETS, SC.TOTAL_CURRENT_LIABILITIES),
    ),
    RatioSpec(
        name="debt_to_equity",
        display_name="Debt-to-equity",
        definition="total_debt / total_equity",
        required_categories=(SC.TOTAL_EQUITY,),
        required_derived=("total_debt",),
    ),
    RatioSpec(
        name="debt_to_ebitda",
        display_name="Debt-to-EBITDA (approximate)",
        definition="total_debt / EBITDA",
        required_derived=("total_debt", "ebitda"),
        is_approximation=True,
        notes="EBITDA is approximated; see EBITDA derived-quantity definition.",
    ),
    RatioSpec(
        name="approximate_dscr",
        display_name="Approximate DSCR (Estimated Debt Service Coverage)",
        definition="EBITDA / (interest_expense + current_portion_long_term_debt)",
        required_categories=(SC.INTEREST_EXPENSE, SC.CURRENT_PORTION_LONG_TERM_DEBT),
        required_derived=("ebitda",),
        not_calculable_message=NOT_CALCULATED,
        is_approximation=True,
        notes=(
            "NOT a bank-quality or CFADS-based DSCR. Approximation only. "
            "If interest_expense or current_portion_long_term_debt is missing, "
            "report the not_calculable_message rather than estimating."
        ),
    ),
    RatioSpec(
        name="ebitda_margin",
        display_name="EBITDA margin (approximate)",
        definition="EBITDA / revenue",
        required_categories=(SC.REVENUE,),
        required_derived=("ebitda",),
        is_approximation=True,
        notes="EBITDA is approximated; see EBITDA derived-quantity definition.",
    ),
    RatioSpec(
        name="net_margin",
        display_name="Net margin",
        definition="net_income / revenue",
        required_categories=(SC.NET_INCOME, SC.REVENUE),
    ),
    RatioSpec(
        name="revenue_growth",
        display_name="Revenue growth (YoY)",
        definition="(revenue_t / revenue_prior) - 1",
        required_categories=(SC.REVENUE,),
        needs_prior_period=True,
    ),
)

RATIO_SPECS_BY_NAME: dict[str, RatioSpec] = {r.name: r for r in RATIO_SPECS}
DERIVED_BY_NAME: dict[str, DerivedQuantity] = {d.name: d for d in DERIVED_QUANTITIES}
