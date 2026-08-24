"""
Phase 6 add-on — Demo Mode tests. Deterministic, no network, NO API key needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ingest import extract_document
from core.mapping import build_mapping_inputs, demo_map
from core.mapping.demo_mapper import DEMO_MODEL_LABEL, classify_label
from core.compute import compute_spread
from core.review import ReviewState
from core.schema import StandardizedCategory as C, ValidationCode

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_filing.html"

_failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {extra}" if extra and not ok else ""))
    if not ok:
        _failures.append(name)


def _inputs():
    doc = extract_document("synthetic_filing.html", FIXTURE.read_bytes())
    return doc, doc.tables[0], doc.tables[1], build_mapping_inputs(doc.tables[0], doc.tables[1])


def test_classify_label() -> None:
    print("deterministic label classifier:")
    cases = {
        "Net sales": C.REVENUE,
        "Cost of products sold": C.COST_OF_GOODS_SOLD,
        "Operating income": C.OPERATING_INCOME,
        "Total current assets": C.TOTAL_CURRENT_ASSETS,
        "Total assets": C.TOTAL_ASSETS,
        "Total equity": C.TOTAL_EQUITY,
        "Total liabilities and equity": C.TOTAL_LIABILITIES_AND_EQUITY,
        "Current portion of long-term debt": C.CURRENT_PORTION_LONG_TERM_DEBT,
        "Long-term debt": C.LONG_TERM_DEBT,
        "Assets": C.IGNORE,
        "Other, net": C.UNMAPPED,
    }
    for label, expected in cases.items():
        cat, _conf = classify_label(label)
        check(f"{label!r} -> {expected.value}", cat == expected, f"got {cat.value}")


def test_demo_map_no_api_key() -> None:
    print("demo_map works with NO ANTHROPIC_API_KEY:")
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        _doc, _inc, _bal, inputs = _inputs()
        result = demo_map(inputs)
        check("all rows mapped", len(result.review_rows) == len(inputs))
        check("is_demo flag set", result.is_demo is True)
        check("labeled as demo, not AI", result.model_used == DEMO_MODEL_LABEL
              and "not AI-generated" in result.model_used)
        # rationale is clearly labelled as demo, not Claude
        sample = result.review_rows[0]
        check("rationale labelled demo", "not AI-generated" in sample.rationale)
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved


def test_demo_only_maps_categories() -> None:
    print("demo mapping only maps category + confidence + rationale (no numbers):")
    _doc, _inc, _bal, inputs = _inputs()
    result = demo_map(inputs)
    raw = result.raw_response or {}
    # The response object contains no numeric leaves (defense in depth).
    def has_number(o):
        if isinstance(o, bool):
            return False
        if isinstance(o, (int, float)):
            return True
        if isinstance(o, dict):
            return any(has_number(v) for v in o.values())
        if isinstance(o, list):
            return any(has_number(v) for v in o)
        return False
    check("demo response has no numbers", not has_number(raw))
    keys = set()
    for m in raw.get("mappings", []):
        keys |= set(m.keys())
    check("only contract keys present",
          keys <= {"row_id", "standardized_category", "confidence", "rationale"}, str(keys))


def test_demo_feeds_compute_and_export_path() -> None:
    print("demo mappings drive review + deterministic compute:")
    _doc, inc, bal, inputs = _inputs()
    result = demo_map(inputs)
    review = ReviewState.from_mapping_result(result)
    compute = compute_spread(inc, bal, review.to_decisions_by_id(),
                             notes_by_id=review.notes_by_id())
    # Demo maps everything correctly incl. total_equity -> balance sheet balances.
    imbalance = [f for f in compute.findings
                 if f.code == ValidationCode.BALANCE_SHEET_IMBALANCE]
    check("balance sheet balances under demo mapping", not imbalance)
    cr = compute.ratios_by_period()["2024"]["current_ratio"]
    check("current_ratio computes (1.2)", cr.status == "ok" and abs(cr.value - 1.2) < 1e-6)
    dte = compute.ratios_by_period()["2024"]["debt_to_equity"]
    check("debt_to_equity computes", dte.status == "ok")


def main() -> int:
    test_classify_label()
    test_demo_map_no_api_key()
    test_demo_only_maps_categories()
    test_demo_feeds_compute_and_export_path()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): " + ", ".join(_failures))
        return 1
    print("All Demo Mode checks passed.")
    return 0


def test_all():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
