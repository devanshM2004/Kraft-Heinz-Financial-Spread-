"""
Generate the two Phase-1 example JSON files from the schema API.

This doubles as a worked example of how the schema is used and guarantees the
committed JSON stays consistent with the dataclasses.

Outputs (written next to this file):
  example_mapping_output.json  -- Contract A: Claude's strict output (NO numbers)
  example_spread_items.json    -- Contract B: Python-bound audit records

The numbers below are SYNTHETIC and intentionally round. They are illustrative
only — not Kraft Heinz's real figures. The balance sheet is constructed to
balance and the income statement to foot, so later phases have a clean example.

Sign convention (important, documented in docs/schema.md):
  Values are stored SIGNED so that every subtotal equals the plain arithmetic
  sum of its `foots_from` components. Expenses and contra accounts are therefore
  negative (e.g. cost_of_goods_sold = -17000). Ratio formulas that intend a
  positive debt-service figure take magnitudes in the compute layer (Phase 4).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core.schema import (  # noqa: E402
    Confidence,
    MappingDecision,
    SpreadItem,
    StandardizedCategory as SC,
    StandardizedSpread,
    StatementType as ST,
)

HIGH, MED, LOW = Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW

# (row_id, raw_label, category, statement, confidence, rationale, table_idx, row_idx)
ROWS = [
    # --- income statement (table 2) ---
    ("r01", "Net sales", SC.REVENUE, ST.INCOME_STATEMENT, HIGH,
     "'Net sales' is the top-line revenue caption.", 2, 0),
    ("r02", "Cost of products sold", SC.COST_OF_GOODS_SOLD, ST.INCOME_STATEMENT, HIGH,
     "'Cost of products sold' is COGS.", 2, 1),
    ("r03", "Gross profit", SC.GROSS_PROFIT, ST.INCOME_STATEMENT, HIGH,
     "'Gross profit' is the standard gross-margin subtotal.", 2, 2),
    ("r04", "Selling, general and administrative expenses", SC.SELLING_GENERAL_ADMIN,
     ST.INCOME_STATEMENT, HIGH, "Matches SG&A.", 2, 3),
    ("r05", "Operating income", SC.OPERATING_INCOME, ST.INCOME_STATEMENT, HIGH,
     "'Operating income' is EBIT subtotal.", 2, 4),
    ("r06", "Interest expense", SC.INTEREST_EXPENSE, ST.INCOME_STATEMENT, HIGH,
     "Explicit interest expense line.", 2, 5),
    ("r07", "Income before income taxes", SC.INCOME_BEFORE_TAXES,
     ST.INCOME_STATEMENT, HIGH, "Pre-tax income subtotal.", 2, 6),
    ("r08", "Provision for income taxes", SC.INCOME_TAX_EXPENSE,
     ST.INCOME_STATEMENT, HIGH, "Tax provision maps to income tax expense.", 2, 7),
    ("r09", "Net income", SC.NET_INCOME, ST.INCOME_STATEMENT, HIGH,
     "Bottom-line net income subtotal.", 2, 8),
    ("r10", "Depreciation and amortization", SC.DEPRECIATION_AMORTIZATION,
     ST.INCOME_STATEMENT, MED,
     "D&A disclosed on the face; needed for EBITDA.", 2, 9),
    ("r11", "Other, net", SC.UNMAPPED, ST.INCOME_STATEMENT, LOW,
     "Ambiguous 'Other, net'; cannot confidently place.", 2, 10),

    # --- balance sheet (table 3) ---
    ("r20", "Cash and cash equivalents", SC.CASH_AND_EQUIVALENTS,
     ST.BALANCE_SHEET, HIGH, "Explicit cash line.", 3, 0),
    ("r21", "Trade receivables, net", SC.ACCOUNTS_RECEIVABLE,
     ST.BALANCE_SHEET, HIGH, "Trade receivables = accounts receivable.", 3, 1),
    ("r22", "Inventories", SC.INVENTORY, ST.BALANCE_SHEET, HIGH,
     "'Inventories' maps to inventory.", 3, 2),
    ("r23", "Total current assets", SC.TOTAL_CURRENT_ASSETS,
     ST.BALANCE_SHEET, HIGH, "Current assets subtotal.", 3, 3),
    ("r24", "Property, plant and equipment, net", SC.PROPERTY_PLANT_EQUIPMENT_NET,
     ST.BALANCE_SHEET, HIGH, "Net PP&E line.", 3, 4),
    ("r25", "Goodwill", SC.GOODWILL, ST.BALANCE_SHEET, HIGH,
     "Explicit goodwill line.", 3, 5),
    ("r26", "Other non-current assets", SC.OTHER_NONCURRENT_ASSETS,
     ST.BALANCE_SHEET, HIGH, "Residual non-current assets.", 3, 6),
    ("r27", "Total assets", SC.TOTAL_ASSETS, ST.BALANCE_SHEET, HIGH,
     "Total assets subtotal.", 3, 7),
    ("r28", "Accounts payable", SC.ACCOUNTS_PAYABLE, ST.BALANCE_SHEET, HIGH,
     "Explicit AP line.", 3, 8),
    ("r29", "Current portion of long-term debt", SC.CURRENT_PORTION_LONG_TERM_DEBT,
     ST.BALANCE_SHEET, HIGH, "Current maturities of LT debt.", 3, 9),
    ("r30", "Total current liabilities", SC.TOTAL_CURRENT_LIABILITIES,
     ST.BALANCE_SHEET, HIGH, "Current liabilities subtotal.", 3, 10),
    ("r31", "Long-term debt", SC.LONG_TERM_DEBT, ST.BALANCE_SHEET, HIGH,
     "Explicit long-term debt line.", 3, 11),
    ("r32", "Other non-current liabilities", SC.OTHER_NONCURRENT_LIABILITIES,
     ST.BALANCE_SHEET, HIGH, "Residual non-current liabilities.", 3, 12),
    ("r33", "Total liabilities", SC.TOTAL_LIABILITIES, ST.BALANCE_SHEET, HIGH,
     "Total liabilities subtotal.", 3, 13),
    ("r34", "Total equity", SC.TOTAL_EQUITY, ST.BALANCE_SHEET, HIGH,
     "Total equity subtotal.", 3, 14),
    ("r35", "Total liabilities and equity", SC.TOTAL_LIABILITIES_AND_EQUITY,
     ST.BALANCE_SHEET, HIGH, "Balancing subtotal.", 3, 15),
    ("r36", "The accompanying notes are an integral part of these statements.",
     SC.IGNORE, ST.NONE, HIGH, "Narrative footnote, not a data row.", 3, 16),
]

# Synthetic signed values by row_id: {fiscal_year: value}. Expenses negative.
VALUES = {
    # income statement
    "r01": {"2024": 26000.0, "2023": 25000.0},   # revenue
    "r02": {"2024": -17000.0},                    # cogs
    "r03": {"2024": 9000.0},                      # gross profit (26000-17000)
    "r04": {"2024": -5000.0},                     # sg&a
    "r05": {"2024": 4000.0},                      # operating income (9000-5000)
    "r06": {"2024": -600.0},                      # interest expense
    "r07": {"2024": 3400.0},                      # pre-tax (4000-600)
    "r08": {"2024": -900.0},                      # tax
    "r09": {"2024": 2500.0},                      # net income (3400-900)
    "r10": {"2024": 1500.0},                      # D&A
    "r11": {"2024": 0.0},                         # other, net (unmapped)
    # balance sheet
    "r20": {"2024": 1000.0},                      # cash
    "r21": {"2024": 2000.0},                      # AR
    "r22": {"2024": 3000.0},                      # inventory
    "r23": {"2024": 6000.0},                      # total current assets
    "r24": {"2024": 7000.0},                      # ppe
    "r25": {"2024": 30000.0},                     # goodwill
    "r26": {"2024": 7000.0},                      # other non-current assets
    "r27": {"2024": 50000.0},                     # total assets
    "r28": {"2024": 4000.0},                      # AP
    "r29": {"2024": 1000.0},                      # current portion LTD
    "r30": {"2024": 5000.0},                      # total current liabilities
    "r31": {"2024": 20000.0},                     # long-term debt
    "r32": {"2024": 5000.0},                      # other non-current liabilities
    "r33": {"2024": 30000.0},                     # total liabilities
    "r34": {"2024": 20000.0},                     # total equity
    "r35": {"2024": 50000.0},                     # total liab + equity
    "r36": {},                                    # ignored row, no value
}

COL_BY_YEAR = {"2024": 1, "2023": 2}  # column 0 is the label column


def build_mapping_output() -> dict:
    """Contract A: exactly what Claude returns (no numbers)."""
    decisions = [
        MappingDecision(
            row_id=row_id,
            standardized_category=cat,
            confidence=conf,
            rationale=rationale,
        )
        for (row_id, _label, cat, _stmt, conf, rationale, _ti, _ri) in ROWS
    ]
    return {"mappings": [d.to_dict() for d in decisions]}


def build_spread_items() -> dict:
    """Contract B: Python-bound audit records with values from the source."""
    spread = StandardizedSpread(
        ticker="KHC",
        company_name="(synthetic example — not real Kraft Heinz data)",
        source_document="example_synthetic_filing.html",
        fiscal_years=["2024", "2023"],
    )
    for (row_id, label, cat, stmt, conf, _rationale, ti, ri) in ROWS:
        year_values = VALUES.get(row_id, {})
        if not year_values:
            continue  # ignored / no-data rows produce no bound figures
        stmt_label = {"income_statement": "Income Statement",
                      "balance_sheet": "Balance Sheet",
                      "none": "n/a"}[stmt.value]
        for year, value in year_values.items():
            col = COL_BY_YEAR[year]
            spread.items.append(
                SpreadItem(
                    row_id=row_id,
                    statement_type=stmt,
                    raw_label=label,
                    standardized_category=cat,
                    fiscal_year=year,
                    confidence=conf,
                    value=value,
                    value_is_present=True,
                    source_table_index=ti,
                    source_row_index=ri,
                    source_column_index=col,
                    source_location=f"{stmt_label}, table {ti}, row {ri}, col {year}",
                    notes=None,
                )
            )
    return spread.to_dict()


def main() -> int:
    mapping = build_mapping_output()
    spread = build_spread_items()

    (HERE / "example_mapping_output.json").write_text(
        json.dumps(mapping, indent=2) + "\n", encoding="utf-8"
    )
    (HERE / "example_spread_items.json").write_text(
        json.dumps(spread, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(mapping['mappings'])} mapping decisions (Contract A).")
    print(f"Wrote {len(spread['items'])} bound spread items (Contract B).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
