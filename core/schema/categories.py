"""
Standardized credit-spread category vocabulary (Phase 1).

This is the fixed set of categories that raw financial-statement line items are
mapped INTO. Claude's only job is to choose one of these categories for each
raw row; it never produces numbers. Python owns everything numeric.

Design notes
------------
* Categories are grouped by statement (income statement, balance sheet).
* Each category carries metadata used by later phases:
    - is_subtotal : whether the line is a computed subtotal (footed by Python)
    - foots_from  : for subtotals, the component categories that must sum to it
    - roles       : semantic tags (e.g. "debt") used by ratio/validation specs
* Two control categories exist so the model always has a valid choice:
    - UNMAPPED : a real financial line the model could not confidently place
    - IGNORE   : not a data line (section header, blank, footnote text, etc.)

Nothing here computes anything. It only DEFINES the vocabulary and its
structure so extraction, mapping, compute, and validation share one contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StatementType(str, Enum):
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    # Control lines that belong to neither statement's data body.
    NONE = "none"


class CategoryRole(str, Enum):
    """Semantic tags that ratio and validation specs key off of."""
    DEBT = "debt"                         # components of total debt
    EBITDA_INPUT = "ebitda_input"         # feeds the EBITDA build-up
    DEBT_SERVICE_INPUT = "debt_service_input"  # feeds approximate DSCR denominator
    CONTROL = "control"                   # UNMAPPED / IGNORE


class StandardizedCategory(str, Enum):
    # ---- Income statement ----
    REVENUE = "revenue"
    COST_OF_GOODS_SOLD = "cost_of_goods_sold"
    GROSS_PROFIT = "gross_profit"                         # subtotal
    SELLING_GENERAL_ADMIN = "selling_general_admin"
    RESEARCH_DEVELOPMENT = "research_development"
    DEPRECIATION_AMORTIZATION = "depreciation_amortization"
    OTHER_OPERATING_EXPENSE = "other_operating_expense"
    OPERATING_INCOME = "operating_income"                 # subtotal (EBIT)
    INTEREST_EXPENSE = "interest_expense"
    INTEREST_INCOME = "interest_income"
    OTHER_NONOPERATING_INCOME_EXPENSE = "other_nonoperating_income_expense"
    INCOME_BEFORE_TAXES = "income_before_taxes"           # subtotal
    INCOME_TAX_EXPENSE = "income_tax_expense"
    NET_INCOME = "net_income"                             # subtotal

    # ---- Balance sheet: assets ----
    CASH_AND_EQUIVALENTS = "cash_and_equivalents"
    SHORT_TERM_INVESTMENTS = "short_term_investments"
    ACCOUNTS_RECEIVABLE = "accounts_receivable"
    INVENTORY = "inventory"
    PREPAID_EXPENSES = "prepaid_expenses"
    OTHER_CURRENT_ASSETS = "other_current_assets"
    TOTAL_CURRENT_ASSETS = "total_current_assets"         # subtotal
    PROPERTY_PLANT_EQUIPMENT_NET = "property_plant_equipment_net"
    GOODWILL = "goodwill"
    INTANGIBLE_ASSETS = "intangible_assets"
    LONG_TERM_INVESTMENTS = "long_term_investments"
    OTHER_NONCURRENT_ASSETS = "other_noncurrent_assets"
    TOTAL_NONCURRENT_ASSETS = "total_noncurrent_assets"   # subtotal
    TOTAL_ASSETS = "total_assets"                         # subtotal

    # ---- Balance sheet: liabilities ----
    ACCOUNTS_PAYABLE = "accounts_payable"
    SHORT_TERM_DEBT = "short_term_debt"
    CURRENT_PORTION_LONG_TERM_DEBT = "current_portion_long_term_debt"
    ACCRUED_LIABILITIES = "accrued_liabilities"
    INCOME_TAXES_PAYABLE = "income_taxes_payable"
    OTHER_CURRENT_LIABILITIES = "other_current_liabilities"
    TOTAL_CURRENT_LIABILITIES = "total_current_liabilities"       # subtotal
    LONG_TERM_DEBT = "long_term_debt"
    DEFERRED_TAX_LIABILITIES = "deferred_tax_liabilities"
    OTHER_NONCURRENT_LIABILITIES = "other_noncurrent_liabilities"
    TOTAL_NONCURRENT_LIABILITIES = "total_noncurrent_liabilities"  # subtotal
    TOTAL_LIABILITIES = "total_liabilities"                        # subtotal

    # ---- Balance sheet: equity ----
    COMMON_STOCK = "common_stock"
    ADDITIONAL_PAID_IN_CAPITAL = "additional_paid_in_capital"
    RETAINED_EARNINGS = "retained_earnings"
    TREASURY_STOCK = "treasury_stock"
    ACCUMULATED_OCI = "accumulated_oci"
    NONCONTROLLING_INTEREST = "noncontrolling_interest"
    TOTAL_EQUITY = "total_equity"                                  # subtotal
    TOTAL_LIABILITIES_AND_EQUITY = "total_liabilities_and_equity"  # subtotal

    # ---- Control categories (always valid choices for the model) ----
    UNMAPPED = "unmapped"
    IGNORE = "ignore"


@dataclass(frozen=True)
class CategoryMeta:
    category: StandardizedCategory
    statement: StatementType
    label: str                                   # human-readable display name
    is_subtotal: bool = False
    foots_from: tuple[StandardizedCategory, ...] = ()   # components of a subtotal
    roles: frozenset[CategoryRole] = field(default_factory=frozenset)


def _m(cat, stmt, label, *, is_subtotal=False, foots_from=(), roles=()):
    return CategoryMeta(
        category=cat,
        statement=stmt,
        label=label,
        is_subtotal=is_subtotal,
        foots_from=tuple(foots_from),
        roles=frozenset(roles),
    )


SC = StandardizedCategory
ST = StatementType
R = CategoryRole

# The single source of truth for category metadata. Order is presentation order.
CATEGORY_CATALOG: tuple[CategoryMeta, ...] = (
    # -- Income statement --
    _m(SC.REVENUE, ST.INCOME_STATEMENT, "Revenue / Net sales"),
    _m(SC.COST_OF_GOODS_SOLD, ST.INCOME_STATEMENT, "Cost of goods sold"),
    _m(SC.GROSS_PROFIT, ST.INCOME_STATEMENT, "Gross profit", is_subtotal=True,
       foots_from=(SC.REVENUE, SC.COST_OF_GOODS_SOLD)),
    _m(SC.SELLING_GENERAL_ADMIN, ST.INCOME_STATEMENT, "Selling, general & administrative"),
    _m(SC.RESEARCH_DEVELOPMENT, ST.INCOME_STATEMENT, "Research & development"),
    _m(SC.DEPRECIATION_AMORTIZATION, ST.INCOME_STATEMENT,
       "Depreciation & amortization", roles=(R.EBITDA_INPUT,)),
    _m(SC.OTHER_OPERATING_EXPENSE, ST.INCOME_STATEMENT, "Other operating expense"),
    _m(SC.OPERATING_INCOME, ST.INCOME_STATEMENT, "Operating income (EBIT)",
       is_subtotal=True,
       foots_from=(SC.GROSS_PROFIT, SC.SELLING_GENERAL_ADMIN, SC.RESEARCH_DEVELOPMENT,
                   SC.OTHER_OPERATING_EXPENSE),
       roles=(R.EBITDA_INPUT,)),
    _m(SC.INTEREST_EXPENSE, ST.INCOME_STATEMENT, "Interest expense",
       roles=(R.EBITDA_INPUT, R.DEBT_SERVICE_INPUT)),
    _m(SC.INTEREST_INCOME, ST.INCOME_STATEMENT, "Interest income"),
    _m(SC.OTHER_NONOPERATING_INCOME_EXPENSE, ST.INCOME_STATEMENT,
       "Other non-operating income / expense"),
    _m(SC.INCOME_BEFORE_TAXES, ST.INCOME_STATEMENT, "Income before taxes",
       is_subtotal=True,
       foots_from=(SC.OPERATING_INCOME, SC.INTEREST_EXPENSE, SC.INTEREST_INCOME,
                   SC.OTHER_NONOPERATING_INCOME_EXPENSE)),
    _m(SC.INCOME_TAX_EXPENSE, ST.INCOME_STATEMENT, "Income tax expense",
       roles=(R.EBITDA_INPUT,)),
    _m(SC.NET_INCOME, ST.INCOME_STATEMENT, "Net income", is_subtotal=True,
       foots_from=(SC.INCOME_BEFORE_TAXES, SC.INCOME_TAX_EXPENSE)),

    # -- Balance sheet: assets --
    _m(SC.CASH_AND_EQUIVALENTS, ST.BALANCE_SHEET, "Cash & cash equivalents"),
    _m(SC.SHORT_TERM_INVESTMENTS, ST.BALANCE_SHEET, "Short-term investments"),
    _m(SC.ACCOUNTS_RECEIVABLE, ST.BALANCE_SHEET, "Accounts receivable, net"),
    _m(SC.INVENTORY, ST.BALANCE_SHEET, "Inventories"),
    _m(SC.PREPAID_EXPENSES, ST.BALANCE_SHEET, "Prepaid expenses"),
    _m(SC.OTHER_CURRENT_ASSETS, ST.BALANCE_SHEET, "Other current assets"),
    _m(SC.TOTAL_CURRENT_ASSETS, ST.BALANCE_SHEET, "Total current assets",
       is_subtotal=True,
       foots_from=(SC.CASH_AND_EQUIVALENTS, SC.SHORT_TERM_INVESTMENTS,
                   SC.ACCOUNTS_RECEIVABLE, SC.INVENTORY, SC.PREPAID_EXPENSES,
                   SC.OTHER_CURRENT_ASSETS)),
    _m(SC.PROPERTY_PLANT_EQUIPMENT_NET, ST.BALANCE_SHEET, "Property, plant & equipment, net"),
    _m(SC.GOODWILL, ST.BALANCE_SHEET, "Goodwill"),
    _m(SC.INTANGIBLE_ASSETS, ST.BALANCE_SHEET, "Intangible assets, net"),
    _m(SC.LONG_TERM_INVESTMENTS, ST.BALANCE_SHEET, "Long-term investments"),
    _m(SC.OTHER_NONCURRENT_ASSETS, ST.BALANCE_SHEET, "Other non-current assets"),
    _m(SC.TOTAL_NONCURRENT_ASSETS, ST.BALANCE_SHEET, "Total non-current assets",
       is_subtotal=True,
       foots_from=(SC.PROPERTY_PLANT_EQUIPMENT_NET, SC.GOODWILL, SC.INTANGIBLE_ASSETS,
                   SC.LONG_TERM_INVESTMENTS, SC.OTHER_NONCURRENT_ASSETS)),
    _m(SC.TOTAL_ASSETS, ST.BALANCE_SHEET, "Total assets", is_subtotal=True,
       foots_from=(SC.TOTAL_CURRENT_ASSETS, SC.TOTAL_NONCURRENT_ASSETS)),

    # -- Balance sheet: liabilities --
    _m(SC.ACCOUNTS_PAYABLE, ST.BALANCE_SHEET, "Accounts payable"),
    _m(SC.SHORT_TERM_DEBT, ST.BALANCE_SHEET, "Short-term debt / borrowings",
       roles=(R.DEBT,)),
    _m(SC.CURRENT_PORTION_LONG_TERM_DEBT, ST.BALANCE_SHEET,
       "Current portion of long-term debt", roles=(R.DEBT, R.DEBT_SERVICE_INPUT)),
    _m(SC.ACCRUED_LIABILITIES, ST.BALANCE_SHEET, "Accrued liabilities"),
    _m(SC.INCOME_TAXES_PAYABLE, ST.BALANCE_SHEET, "Income taxes payable"),
    _m(SC.OTHER_CURRENT_LIABILITIES, ST.BALANCE_SHEET, "Other current liabilities"),
    _m(SC.TOTAL_CURRENT_LIABILITIES, ST.BALANCE_SHEET, "Total current liabilities",
       is_subtotal=True,
       foots_from=(SC.ACCOUNTS_PAYABLE, SC.SHORT_TERM_DEBT,
                   SC.CURRENT_PORTION_LONG_TERM_DEBT, SC.ACCRUED_LIABILITIES,
                   SC.INCOME_TAXES_PAYABLE, SC.OTHER_CURRENT_LIABILITIES)),
    _m(SC.LONG_TERM_DEBT, ST.BALANCE_SHEET, "Long-term debt", roles=(R.DEBT,)),
    _m(SC.DEFERRED_TAX_LIABILITIES, ST.BALANCE_SHEET, "Deferred tax liabilities"),
    _m(SC.OTHER_NONCURRENT_LIABILITIES, ST.BALANCE_SHEET, "Other non-current liabilities"),
    _m(SC.TOTAL_NONCURRENT_LIABILITIES, ST.BALANCE_SHEET, "Total non-current liabilities",
       is_subtotal=True,
       foots_from=(SC.LONG_TERM_DEBT, SC.DEFERRED_TAX_LIABILITIES,
                   SC.OTHER_NONCURRENT_LIABILITIES)),
    _m(SC.TOTAL_LIABILITIES, ST.BALANCE_SHEET, "Total liabilities", is_subtotal=True,
       foots_from=(SC.TOTAL_CURRENT_LIABILITIES, SC.TOTAL_NONCURRENT_LIABILITIES)),

    # -- Balance sheet: equity --
    _m(SC.COMMON_STOCK, ST.BALANCE_SHEET, "Common stock"),
    _m(SC.ADDITIONAL_PAID_IN_CAPITAL, ST.BALANCE_SHEET, "Additional paid-in capital"),
    _m(SC.RETAINED_EARNINGS, ST.BALANCE_SHEET, "Retained earnings"),
    _m(SC.TREASURY_STOCK, ST.BALANCE_SHEET, "Treasury stock"),
    _m(SC.ACCUMULATED_OCI, ST.BALANCE_SHEET, "Accumulated other comprehensive income/loss"),
    _m(SC.NONCONTROLLING_INTEREST, ST.BALANCE_SHEET, "Non-controlling interest"),
    _m(SC.TOTAL_EQUITY, ST.BALANCE_SHEET, "Total equity", is_subtotal=True,
       foots_from=(SC.COMMON_STOCK, SC.ADDITIONAL_PAID_IN_CAPITAL, SC.RETAINED_EARNINGS,
                   SC.TREASURY_STOCK, SC.ACCUMULATED_OCI, SC.NONCONTROLLING_INTEREST)),
    _m(SC.TOTAL_LIABILITIES_AND_EQUITY, ST.BALANCE_SHEET,
       "Total liabilities & equity", is_subtotal=True,
       foots_from=(SC.TOTAL_LIABILITIES, SC.TOTAL_EQUITY)),

    # -- Control --
    _m(SC.UNMAPPED, ST.NONE, "Unmapped (financial line, no confident category)",
       roles=(R.CONTROL,)),
    _m(SC.IGNORE, ST.NONE, "Ignore (not a data line)", roles=(R.CONTROL,)),
)

# Lookup helpers ---------------------------------------------------------------
CATALOG_BY_CATEGORY: dict[StandardizedCategory, CategoryMeta] = {
    m.category: m for m in CATEGORY_CATALOG
}


def categories_for_statement(statement: StatementType) -> list[StandardizedCategory]:
    return [m.category for m in CATEGORY_CATALOG if m.statement == statement]


def categories_with_role(role: CategoryRole) -> list[StandardizedCategory]:
    return [m.category for m in CATEGORY_CATALOG if role in m.roles]


def subtotal_categories() -> list[StandardizedCategory]:
    return [m.category for m in CATEGORY_CATALOG if m.is_subtotal]


def component_categories() -> list[StandardizedCategory]:
    """Non-subtotal, non-control categories (the mappable 'leaf' line items)."""
    return [
        m.category
        for m in CATEGORY_CATALOG
        if not m.is_subtotal and CategoryRole.CONTROL not in m.roles
    ]


# The exact list of category string values the model is allowed to return.
ALLOWED_CATEGORY_VALUES: list[str] = [m.category.value for m in CATEGORY_CATALOG]
