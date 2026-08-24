"""
Demo mapping (deterministic, NOT AI) — Phase 6 add-on for demoing without a key.

Produces the same MappingResult shape as the real Claude mapper, but the
category for each row is chosen by a simple, deterministic keyword classifier in
Python. It makes NO Anthropic API call and is clearly labelled as a demo — it is
never presented as AI output.

Number-control rules are unchanged: this still only maps
row_id -> standardized_category + confidence + rationale. Python still owns every
value, calculation, validation, and the Excel export.
"""

from __future__ import annotations

from core.schema import Confidence, StandardizedCategory as SC

from .claude_mapper import validate_and_bind
from .models import MappingInputRow, MappingResult

DEMO_MODEL_LABEL = "Demo mapping — deterministic sample output, not AI-generated"
DEMO_RATIONALE_PREFIX = "Demo mapping — deterministic sample output, not AI-generated."

# Exact-label section headers / non-data rows -> ignore.
_IGNORE_EXACT = {
    "assets", "liabilities", "equity", "liabilities and equity",
    "liabilities and shareholders' equity", "liabilities and stockholders' equity",
}

# Ordered (needle, category, confidence). First match wins, so more specific
# needles are listed before more general ones.
_RULES: list[tuple[str, SC, Confidence]] = [
    # income statement
    ("net sales", SC.REVENUE, Confidence.HIGH),
    ("total revenue", SC.REVENUE, Confidence.HIGH),
    ("net revenue", SC.REVENUE, Confidence.HIGH),
    ("revenue", SC.REVENUE, Confidence.MEDIUM),
    ("cost of products sold", SC.COST_OF_GOODS_SOLD, Confidence.HIGH),
    ("cost of goods sold", SC.COST_OF_GOODS_SOLD, Confidence.HIGH),
    ("cost of sales", SC.COST_OF_GOODS_SOLD, Confidence.HIGH),
    ("cost of revenue", SC.COST_OF_GOODS_SOLD, Confidence.HIGH),
    ("gross profit", SC.GROSS_PROFIT, Confidence.HIGH),
    ("selling, general", SC.SELLING_GENERAL_ADMIN, Confidence.HIGH),
    ("general and administrative", SC.SELLING_GENERAL_ADMIN, Confidence.HIGH),
    ("sg&a", SC.SELLING_GENERAL_ADMIN, Confidence.HIGH),
    ("research and development", SC.RESEARCH_DEVELOPMENT, Confidence.HIGH),
    ("depreciation and amortization", SC.DEPRECIATION_AMORTIZATION, Confidence.MEDIUM),
    ("depreciation & amortization", SC.DEPRECIATION_AMORTIZATION, Confidence.MEDIUM),
    ("operating income", SC.OPERATING_INCOME, Confidence.HIGH),
    ("income from operations", SC.OPERATING_INCOME, Confidence.HIGH),
    ("interest expense", SC.INTEREST_EXPENSE, Confidence.HIGH),
    ("interest income", SC.INTEREST_INCOME, Confidence.HIGH),
    ("income before income taxes", SC.INCOME_BEFORE_TAXES, Confidence.HIGH),
    ("income before taxes", SC.INCOME_BEFORE_TAXES, Confidence.HIGH),
    ("income before provision", SC.INCOME_BEFORE_TAXES, Confidence.HIGH),
    ("provision for income tax", SC.INCOME_TAX_EXPENSE, Confidence.HIGH),
    ("income tax expense", SC.INCOME_TAX_EXPENSE, Confidence.HIGH),
    ("income tax provision", SC.INCOME_TAX_EXPENSE, Confidence.HIGH),
    ("net income", SC.NET_INCOME, Confidence.HIGH),
    ("net earnings", SC.NET_INCOME, Confidence.HIGH),
    # balance sheet — assets
    ("cash and cash equivalents", SC.CASH_AND_EQUIVALENTS, Confidence.HIGH),
    ("cash and equivalents", SC.CASH_AND_EQUIVALENTS, Confidence.HIGH),
    ("short-term investments", SC.SHORT_TERM_INVESTMENTS, Confidence.HIGH),
    ("trade receivables", SC.ACCOUNTS_RECEIVABLE, Confidence.HIGH),
    ("accounts receivable", SC.ACCOUNTS_RECEIVABLE, Confidence.HIGH),
    ("receivables", SC.ACCOUNTS_RECEIVABLE, Confidence.MEDIUM),
    ("inventor", SC.INVENTORY, Confidence.HIGH),
    ("prepaid", SC.PREPAID_EXPENSES, Confidence.HIGH),
    ("total current assets", SC.TOTAL_CURRENT_ASSETS, Confidence.HIGH),
    ("property, plant", SC.PROPERTY_PLANT_EQUIPMENT_NET, Confidence.HIGH),
    ("property and equipment", SC.PROPERTY_PLANT_EQUIPMENT_NET, Confidence.HIGH),
    ("goodwill", SC.GOODWILL, Confidence.HIGH),
    ("intangible", SC.INTANGIBLE_ASSETS, Confidence.HIGH),
    ("other current assets", SC.OTHER_CURRENT_ASSETS, Confidence.HIGH),
    ("other non-current assets", SC.OTHER_NONCURRENT_ASSETS, Confidence.MEDIUM),
    ("other noncurrent assets", SC.OTHER_NONCURRENT_ASSETS, Confidence.MEDIUM),
    ("other assets", SC.OTHER_NONCURRENT_ASSETS, Confidence.MEDIUM),
    ("total assets", SC.TOTAL_ASSETS, Confidence.HIGH),
    # balance sheet — liabilities
    ("accounts payable", SC.ACCOUNTS_PAYABLE, Confidence.HIGH),
    ("current portion of long-term debt", SC.CURRENT_PORTION_LONG_TERM_DEBT, Confidence.HIGH),
    ("current maturities", SC.CURRENT_PORTION_LONG_TERM_DEBT, Confidence.HIGH),
    ("short-term debt", SC.SHORT_TERM_DEBT, Confidence.HIGH),
    ("short-term borrowings", SC.SHORT_TERM_DEBT, Confidence.HIGH),
    ("accrued", SC.ACCRUED_LIABILITIES, Confidence.HIGH),
    ("income taxes payable", SC.INCOME_TAXES_PAYABLE, Confidence.HIGH),
    ("total current liabilities", SC.TOTAL_CURRENT_LIABILITIES, Confidence.HIGH),
    ("long-term debt", SC.LONG_TERM_DEBT, Confidence.HIGH),
    ("deferred tax", SC.DEFERRED_TAX_LIABILITIES, Confidence.HIGH),
    ("other non-current liabilities", SC.OTHER_NONCURRENT_LIABILITIES, Confidence.MEDIUM),
    ("other noncurrent liabilities", SC.OTHER_NONCURRENT_LIABILITIES, Confidence.MEDIUM),
    ("other liabilities", SC.OTHER_NONCURRENT_LIABILITIES, Confidence.MEDIUM),
    ("total liabilities and equity", SC.TOTAL_LIABILITIES_AND_EQUITY, Confidence.HIGH),
    ("total liabilities and shareholders", SC.TOTAL_LIABILITIES_AND_EQUITY, Confidence.HIGH),
    ("total liabilities and stockholders", SC.TOTAL_LIABILITIES_AND_EQUITY, Confidence.HIGH),
    # equity (check total equity before total liabilities)
    ("total equity", SC.TOTAL_EQUITY, Confidence.HIGH),
    ("total shareholders' equity", SC.TOTAL_EQUITY, Confidence.HIGH),
    ("total stockholders' equity", SC.TOTAL_EQUITY, Confidence.HIGH),
    ("total liabilities", SC.TOTAL_LIABILITIES, Confidence.HIGH),
    ("common stock", SC.COMMON_STOCK, Confidence.HIGH),
    ("additional paid-in capital", SC.ADDITIONAL_PAID_IN_CAPITAL, Confidence.HIGH),
    ("paid-in capital", SC.ADDITIONAL_PAID_IN_CAPITAL, Confidence.HIGH),
    ("retained earnings", SC.RETAINED_EARNINGS, Confidence.HIGH),
    ("accumulated deficit", SC.RETAINED_EARNINGS, Confidence.HIGH),
    ("treasury stock", SC.TREASURY_STOCK, Confidence.HIGH),
    ("accumulated other comprehensive", SC.ACCUMULATED_OCI, Confidence.HIGH),
    ("noncontrolling", SC.NONCONTROLLING_INTEREST, Confidence.HIGH),
    ("non-controlling", SC.NONCONTROLLING_INTEREST, Confidence.HIGH),
    ("minority interest", SC.NONCONTROLLING_INTEREST, Confidence.HIGH),
    # non-data
    ("the accompanying notes", SC.IGNORE, Confidence.HIGH),
    ("see accompanying", SC.IGNORE, Confidence.HIGH),
]


def classify_label(label: str) -> tuple[SC, Confidence]:
    """Deterministically classify a raw label. Unknown -> unmapped/low."""
    text = (label or "").strip().lower()
    if text in _IGNORE_EXACT:
        return SC.IGNORE, Confidence.HIGH
    for needle, category, confidence in _RULES:
        if needle in text:
            return category, confidence
    return SC.UNMAPPED, Confidence.LOW


def demo_map(input_rows: list[MappingInputRow]) -> MappingResult:
    """
    Produce a deterministic demo MappingResult (no API call). Validated and bound
    through the same path as the real mapper, so downstream code is identical.
    """
    mappings = []
    for r in input_rows:
        category, confidence = classify_label(r.raw_label)
        mappings.append({
            "row_id": r.row_id,
            "standardized_category": category.value,
            "confidence": confidence.value,
            "rationale": f"{DEMO_RATIONALE_PREFIX} '{r.raw_label}' -> {category.value}.",
        })

    result = validate_and_bind({"mappings": mappings}, input_rows)
    result.model_used = DEMO_MODEL_LABEL
    result.primary_model = DEMO_MODEL_LABEL
    result.fallback_used = False
    result.is_demo = True
    return result
