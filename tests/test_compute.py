"""
Phase 4 — deterministic compute + validation tests. No network, no LLM.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.compute import (
    ComputeResult,
    compute_from_items,
    to_calculation_value,
)
from core.schema import (
    Confidence,
    SourceScale,
    SpreadItem,
    StandardizedCategory as C,
    StatementType,
    ValidationCode,
)
from core.schema.ratios import NOT_CALCULATED

_failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {extra}" if extra and not ok else ""))
    if not ok:
        _failures.append(name)


def item(cat, period, source, *, conf=Confidence.HIGH,
         statement=StatementType.BALANCE_SHEET, present=True, rid=None) -> SpreadItem:
    return SpreadItem(
        row_id=rid or f"{cat.value}_{period}",
        statement_type=statement,
        raw_label=cat.value,
        standardized_category=cat,
        fiscal_year=period,
        confidence=conf,
        source_value=source if present else None,
        calculation_value=to_calculation_value(cat, source) if present else None,
        value_is_present=present,
        source_scale=SourceScale.MILLIONS,
        currency="USD",
    )


IS = StatementType.INCOME_STATEMENT


def _balanced_2024() -> list[SpreadItem]:
    return [
        # income statement (COGS/interest/tax given as POSITIVE source to prove flip)
        item(C.REVENUE, "2024", 26000, statement=IS),
        item(C.COST_OF_GOODS_SOLD, "2024", 17000, statement=IS),
        item(C.OPERATING_INCOME, "2024", 4000, statement=IS),
        item(C.DEPRECIATION_AMORTIZATION, "2024", 1500, statement=IS),
        item(C.INTEREST_EXPENSE, "2024", 600, statement=IS),
        item(C.INCOME_TAX_EXPENSE, "2024", 900, statement=IS),
        item(C.NET_INCOME, "2024", 2500, statement=IS),
        # balance sheet
        item(C.CASH_AND_EQUIVALENTS, "2024", 1000),
        item(C.ACCOUNTS_RECEIVABLE, "2024", 2000),
        item(C.INVENTORY, "2024", 3000),
        item(C.TOTAL_CURRENT_ASSETS, "2024", 6000),
        item(C.TOTAL_ASSETS, "2024", 50000),
        item(C.ACCOUNTS_PAYABLE, "2024", 4000),
        item(C.CURRENT_PORTION_LONG_TERM_DEBT, "2024", 1000),
        item(C.TOTAL_CURRENT_LIABILITIES, "2024", 5000),
        item(C.LONG_TERM_DEBT, "2024", 20000),
        item(C.TOTAL_LIABILITIES, "2024", 30000),
        item(C.TOTAL_EQUITY, "2024", 20000),
        item(C.TOTAL_LIABILITIES_AND_EQUITY, "2024", 50000),
    ]


def test_sign_normalization() -> None:
    print("calculation_value sign normalization:")
    check("COGS +source -> negative calc", to_calculation_value(C.COST_OF_GOODS_SOLD, 17000.0) == -17000.0)
    check("COGS -source stays negative", to_calculation_value(C.COST_OF_GOODS_SOLD, -17000.0) == -17000.0)
    check("interest_expense flips", to_calculation_value(C.INTEREST_EXPENSE, 600.0) == -600.0)
    check("treasury_stock flips (contra-equity)", to_calculation_value(C.TREASURY_STOCK, 500.0) == -500.0)
    check("revenue preserved", to_calculation_value(C.REVENUE, 26000.0) == 26000.0)
    check("total_assets preserved", to_calculation_value(C.TOTAL_ASSETS, 50000.0) == 50000.0)
    check("negative equity (deficit) preserved",
          to_calculation_value(C.RETAINED_EARNINGS, -300.0) == -300.0)
    check("None -> None", to_calculation_value(C.REVENUE, None) is None)


def test_source_preserved_calc_derived() -> None:
    print("source preserved, calc derived (binding-level):")
    it = item(C.COST_OF_GOODS_SOLD, "2024", 17000, statement=IS)
    check("source_value preserved as +17000", it.source_value == 17000.0)
    check("calculation_value normalized to -17000", it.calculation_value == -17000.0)
    rev = item(C.REVENUE, "2024", 26000, statement=IS)
    check("revenue source == calc", rev.source_value == rev.calculation_value == 26000.0)


def test_ratios_when_inputs_exist() -> None:
    print("ratios compute correctly when inputs exist:")
    res = compute_from_items(_balanced_2024())
    by = res.ratios_by_period()["2024"]

    def approx(a, b): return a is not None and abs(a - b) < 1e-6
    check("current_ratio == 1.2", approx(by["current_ratio"].value, 1.2))
    check("debt_to_equity == 1.05", approx(by["debt_to_equity"].value, 21000 / 20000))
    check("debt_to_ebitda == 21000/5500", approx(by["debt_to_ebitda"].value, 21000 / 5500))
    check("ebitda_margin == 5500/26000", approx(by["ebitda_margin"].value, 5500 / 26000))
    check("net_margin == 2500/26000", approx(by["net_margin"].value, 2500 / 26000))
    check("approximate_dscr == 5500/1600", approx(by["approximate_dscr"].value, 5500 / 1600))
    check("DSCR labelled approximate",
          "Approximate DSCR" in by["approximate_dscr"].display_name)
    check("DSCR marked is_approximation", by["approximate_dscr"].is_approximation)


def test_ratios_not_calculated_when_missing() -> None:
    print("ratios show not-calculated when inputs missing:")
    items = [it for it in _balanced_2024()
             if it.standardized_category not in (C.INTEREST_EXPENSE,
                                                 C.CURRENT_PORTION_LONG_TERM_DEBT)]
    res = compute_from_items(items)
    dscr = res.ratios_by_period()["2024"]["approximate_dscr"]
    check("DSCR not_calculable", dscr.status == "not_calculable" and dscr.value is None)
    check("DSCR uses the debt-service message", dscr.message == NOT_CALCULATED)
    codes = {f.code for f in res.findings}
    check("a RATIO_NOT_CALCULABLE finding is raised",
          ValidationCode.RATIO_NOT_CALCULABLE in codes)


def test_balance_passes() -> None:
    print("balance sheet validation passes on balanced items:")
    res = compute_from_items(_balanced_2024())
    imbalance = [f for f in res.findings if f.code == ValidationCode.BALANCE_SHEET_IMBALANCE]
    check("no balance-sheet imbalance finding", not imbalance)
    check("no ERROR findings (passed)", res.passed, str(res.validation_summary()))
    # Subtotals whose components are fully present foot cleanly (no finding).
    footing = [f for f in res.findings if f.code == ValidationCode.SUBTOTAL_FOOTING_ISSUE
               and "total_current_assets" in f.related_categories]
    check("total_current_assets foots cleanly", not footing)


def test_balance_fails() -> None:
    print("balance sheet validation fails on imbalanced items:")
    items = _balanced_2024()
    # Break equity so assets != liabilities + equity.
    for it in items:
        if it.standardized_category == C.TOTAL_EQUITY:
            it.source_value = 19000.0
            it.calculation_value = 19000.0
    res = compute_from_items(items)
    imbalance = [f for f in res.findings if f.code == ValidationCode.BALANCE_SHEET_IMBALANCE]
    check("balance-sheet imbalance flagged", len(imbalance) >= 1)
    check("validation reports failed (has ERROR)", not res.passed)
    check("imbalance severity is error", any(f.severity.value == "error" for f in imbalance))


def test_missing_required() -> None:
    print("missing required categories flagged:")
    items = [it for it in _balanced_2024() if it.standardized_category != C.TOTAL_EQUITY]
    res = compute_from_items(items)
    missing = [f for f in res.findings if f.code == ValidationCode.MISSING_REQUIRED_CATEGORY]
    check("total_equity flagged missing",
          any("total_equity" in f.related_categories for f in missing))


def test_duplicate_flagged() -> None:
    print("duplicate mappings flagged:")
    items = _balanced_2024()
    items.append(item(C.TOTAL_CURRENT_ASSETS, "2024", 6000, rid="dup_row"))
    res = compute_from_items(items)
    dup = [f for f in res.findings if f.code == ValidationCode.DUPLICATE_MAPPING]
    check("duplicate total_current_assets flagged",
          any("total_current_assets" in f.related_categories for f in dup))


def test_low_confidence_flagged() -> None:
    print("low-confidence mappings flagged:")
    items = _balanced_2024()
    items.append(item(C.GOODWILL, "2024", 30000, conf=Confidence.LOW, rid="lc_row"))
    res = compute_from_items(items)
    lc = [f for f in res.findings if f.code == ValidationCode.LOW_CONFIDENCE_MAPPING]
    check("low-confidence goodwill flagged", any("lc_row" in f.related_row_ids for f in lc))


def test_unmapped_flagged() -> None:
    print("unmapped rows flagged:")
    items = _balanced_2024()
    items.append(item(C.UNMAPPED, "2024", 42, rid="unm_row"))
    res = compute_from_items(items)
    un = [f for f in res.findings if f.code == ValidationCode.UNMAPPED_ROW]
    check("unmapped row flagged", any("unm_row" in f.related_row_ids for f in un))


def main() -> int:
    test_sign_normalization()
    test_source_preserved_calc_derived()
    test_ratios_when_inputs_exist()
    test_ratios_not_calculated_when_missing()
    test_balance_passes()
    test_balance_fails()
    test_missing_required()
    test_duplicate_flagged()
    test_low_confidence_flagged()
    test_unmapped_flagged()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): " + ", ".join(_failures))
        return 1
    print("All Phase 4 compute/validation checks passed.")
    return 0


def test_all():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
