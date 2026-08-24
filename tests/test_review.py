"""
Phase 5 — human review persistence tests. No network, no LLM.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ingest import extract_document
from core.mapping import build_mapping_inputs, validate_and_bind
from core.compute import compute_spread
from core.review import ReviewState
from core.schema import (
    Confidence,
    StandardizedCategory as C,
    StatementType,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_filing.html"

_failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {extra}" if extra and not ok else ""))
    if not ok:
        _failures.append(name)


# Correct label->category mapping, but we deliberately leave "Total equity"
# UNMAPPED to simulate Claude being unsure, so a human override matters.
_MAP = {
    "Net sales": "revenue", "Cost of products sold": "cost_of_goods_sold",
    "Gross profit": "gross_profit",
    "Selling, general and administrative expenses": "selling_general_admin",
    "Operating income": "operating_income", "Interest expense": "interest_expense",
    "Other, net": "unmapped", "Income before income taxes": "income_before_taxes",
    "Provision for income taxes": "income_tax_expense", "Net income": "net_income",
    "Assets": "ignore", "Cash and cash equivalents": "cash_and_equivalents",
    "Trade receivables, net": "accounts_receivable", "Inventories": "inventory",
    "Total current assets": "total_current_assets", "Goodwill": "goodwill",
    "Other non-current assets": "other_noncurrent_assets", "Total assets": "total_assets",
    "Liabilities and Equity": "ignore", "Accounts payable": "accounts_payable",
    "Current portion of long-term debt": "current_portion_long_term_debt",
    "Total current liabilities": "total_current_liabilities",
    "Long-term debt": "long_term_debt",
    "Other non-current liabilities": "other_noncurrent_liabilities",
    "Total liabilities": "total_liabilities",
    "Total equity": "unmapped",  # <-- deliberately unmapped
    "Total liabilities and equity": "total_liabilities_and_equity",
}


def _setup():
    doc = extract_document("synthetic_filing.html", FIXTURE.read_bytes())
    inc, bal = doc.tables[0], doc.tables[1]
    inputs = build_mapping_inputs(inc, bal)
    mappings = [{
        "row_id": r.row_id,
        "standardized_category": _MAP.get(r.raw_label, "unmapped"),
        "confidence": "high" if _MAP.get(r.raw_label) not in (None, "unmapped") else "low",
        "rationale": "x",
    } for r in inputs]
    result = validate_and_bind({"mappings": mappings}, inputs)
    rs = ReviewState.from_mapping_result(result)
    return doc, inc, bal, rs


def _equity_row_id(rs) -> str:
    return next(r.row_id for r in rs.rows() if r.raw_label == "Total equity")


def test_override_changes_reviewed() -> None:
    print("human override changes final reviewed category:")
    _doc, _inc, _bal, rs = _setup()
    rid = _equity_row_id(rs)
    before = rs.get(rid)
    check("seed reviewed == original (unmapped)",
          before.reviewed_category == C.UNMAPPED and not before.human_override)
    rs.set_category(rid, C.TOTAL_EQUITY, note="Clearly total shareholders' equity")
    after = rs.get(rid)
    check("reviewed updated to total_equity", after.reviewed_category == C.TOTAL_EQUITY)
    check("original preserved as unmapped", after.original_category == C.UNMAPPED)
    check("human_override flag set", after.human_override)
    check("reviewer note preserved", after.reviewer_note == "Clearly total shareholders' equity")
    check("original confidence preserved", after.original_confidence == Confidence.LOW)


def test_compute_uses_reviewed() -> None:
    print("compute uses reviewed category, not the original Claude one:")
    _doc, inc, bal, rs = _setup()
    rid = _equity_row_id(rs)

    before = compute_spread(inc, bal, rs.to_decisions_by_id())
    dte_before = before.ratios_by_period()["2024"]["debt_to_equity"]
    check("debt_to_equity not calculable before override (equity unmapped)",
          dte_before.status == "not_calculable")

    rs.set_category(rid, C.TOTAL_EQUITY)
    after = compute_spread(inc, bal, rs.to_decisions_by_id(),
                           notes_by_id=rs.notes_by_id())
    dte_after = after.ratios_by_period()["2024"]["debt_to_equity"]
    check("debt_to_equity computes after override", dte_after.status == "ok"
          and abs(dte_after.value - 21000 / 20000) < 1e-6)


def test_source_preserved_calc_updates_on_override() -> None:
    print("override: source_value unchanged, calculation_value re-derived:")
    _doc, inc, bal, rs = _setup()
    # Find the "Interest expense" row and override it to a NON-expense category,
    # then back, to show calc follows the reviewed category while source holds.
    rid = next(r.row_id for r in rs.rows() if r.raw_label == "Interest expense")

    base = compute_spread(inc, bal, rs.to_decisions_by_id())
    ie_item = next(i for i in base.items if i.row_id == rid and i.fiscal_year == "2024")
    src = ie_item.source_value
    check("interest_expense calc is negative (expense)", ie_item.calculation_value < 0)

    # Override to other_current_assets (a non-negate category).
    rs.set_category(rid, C.OTHER_CURRENT_ASSETS)
    after = compute_spread(inc, bal, rs.to_decisions_by_id())
    it2 = next(i for i in after.items if i.row_id == rid and i.fiscal_year == "2024")
    check("source_value unchanged after override", it2.source_value == src)
    check("calculation_value re-derived to preserve sign now",
          it2.calculation_value == src)


def test_override_audit_and_notes() -> None:
    print("override audit trail + notes:")
    _doc, inc, bal, rs = _setup()
    rid = _equity_row_id(rs)
    rs.set_category(rid, C.TOTAL_EQUITY, note="reviewed by analyst")
    audit = {a["row_id"]: a for a in rs.audit_rows()}[rid]
    check("audit has original_category", audit["original_category"] == "unmapped")
    check("audit has reviewed_category", audit["reviewed_category"] == "total_equity")
    check("audit has human_override True", audit["human_override"] is True)
    check("audit has reviewer_note", audit["reviewer_note"] == "reviewed by analyst")
    check("audit has source_ref", "table" in audit["source_ref"])
    # notes_by_id stamps the override onto SpreadItem.notes
    after = compute_spread(inc, bal, rs.to_decisions_by_id(), notes_by_id=rs.notes_by_id())
    stamped = next(i for i in after.items if i.row_id == rid)
    check("SpreadItem.notes records the override",
          stamped.notes and "Human override" in stamped.notes)


def test_reset_and_summary() -> None:
    print("reset + review status summary:")
    _doc, _inc, _bal, rs = _setup()
    rid = _equity_row_id(rs)
    s0 = rs.summary()
    check("summary counts unmapped (>=2: Other,net + Total equity)", s0["unmapped_rows"] >= 2)
    check("no overrides initially", s0["human_overrides"] == 0)

    rs.set_category(rid, C.TOTAL_EQUITY)
    s1 = rs.summary()
    check("override counted", s1["human_overrides"] == 1)
    check("unmapped decreased", s1["unmapped_rows"] == s0["unmapped_rows"] - 1)

    rs.reset(rid)
    s2 = rs.summary()
    check("reset restores original (override cleared)", s2["human_overrides"] == 0)
    check("reset restores reviewed to unmapped",
          rs.get(rid).reviewed_category == C.UNMAPPED)


def test_scale_currency_detection() -> None:
    print("scale/currency detection from fixture:")
    doc = extract_document("synthetic_filing.html", FIXTURE.read_bytes())
    inc = doc.tables[0]
    check("income table scale detected as millions", inc.detected_scale == "millions")
    check("currency detected as USD ($ present)", inc.detected_currency == "USD")
    # And it flows into SpreadItems.
    res = compute_spread(inc, None, {})
    if res.items:
        it = res.items[0]
        check("SpreadItem carries millions scale", it.source_scale.value == "millions")
        check("SpreadItem carries USD currency", it.currency == "USD")


def main() -> int:
    test_override_changes_reviewed()
    test_compute_uses_reviewed()
    test_source_preserved_calc_updates_on_override()
    test_override_audit_and_notes()
    test_reset_and_summary()
    test_scale_currency_detection()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): " + ", ".join(_failures))
        return 1
    print("All Phase 5 review checks passed.")
    return 0


def test_all():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
