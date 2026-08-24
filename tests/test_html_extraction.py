"""Phase 2 — HTML table extraction tests against the synthetic fixture."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ingest import extract_document
from core.ingest.html_tables import extract_html_tables

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_filing.html"

_failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {extra}" if extra and not ok else ""))
    if not ok:
        _failures.append(name)


def _value(table, label, col):
    for r in table.rows:
        if r.label == label:
            for c in r.cells:
                if c.column_index == col:
                    return c
    return None


def test_extraction() -> None:
    print("HTML extraction (synthetic fixture):")
    html = FIXTURE.read_text()
    tables, warnings = extract_html_tables(html)

    check("found 2 financial tables (cover table skipped)", len(tables) == 2,
          f"got {len(tables)}")
    check("a skip warning was surfaced", any("skipped" in w for w in warnings))

    inc, bal = tables[0], tables[1]
    check("income statement heading captured",
          inc.heading == "Consolidated Statements of Income", repr(inc.heading))
    check("balance sheet heading captured",
          bal.heading == "Consolidated Balance Sheets", repr(bal.heading))

    # The '$' column was dropped: exactly two value columns (2024, 2023).
    check("income has 2 value columns", inc.n_value_columns == 2, str(inc.n_value_columns))
    check("period labels are 2024/2023", inc.period_labels == ["2024", "2023"],
          str(inc.period_labels))

    # Source values preserved exactly, including parenthesis-negatives.
    net_sales = _value(inc, "Net sales", 0)
    check("Net sales 2024 == 26000", net_sales and net_sales.source_value == 26000.0)
    cogs = _value(inc, "Cost of products sold", 0)
    check("COGS 2024 == -17000 (paren negative preserved as source)",
          cogs and cogs.source_value == -17000.0 and cogs.is_negative_paren)

    # Dash cell is 'not present', distinct from zero.
    other = _value(inc, "Other, net", 0)
    check("Other,net 2024 dash -> not present", other and not other.value_is_present
          and other.source_value is None)

    # Column-index provenance is present on every value cell.
    check("cells carry column_index + grid_column_index",
          net_sales is not None and net_sales.column_index == 0
          and net_sales.grid_column_index is not None)

    # Section header row is label-only (kept for structure).
    section = next((r for r in bal.rows if r.label == "Assets"), None)
    check("'Assets' is a label-only section row", section is not None and section.is_label_only)

    # Balance sheet totals present and correct.
    ta = _value(bal, "Total assets", 0)
    tle = _value(bal, "Total liabilities and equity", 0)
    check("Total assets 2024 == 50000", ta and ta.source_value == 50000.0)
    check("Total liab+equity 2024 == 50000", tle and tle.source_value == 50000.0)


def test_orchestrator() -> None:
    print("orchestrator (detect + extract):")
    doc = extract_document("synthetic_filing.html", FIXTURE.read_bytes())
    check("format detected as html", doc.source_format.value == "html")
    check("orchestrator returns 2 tables", len(doc.tables) == 2)
    check("preview_rows shape ok",
          len(doc.tables[0].preview_rows()) == len(doc.tables[0].rows))
    # preview row carries period-labelled columns
    prow = doc.tables[0].preview_rows()[0]
    check("preview row has 2024 key", "2024" in prow and "source_ref" in prow)


def main() -> int:
    test_extraction()
    test_orchestrator()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): " + ", ".join(_failures))
        return 1
    print("All HTML extraction checks passed.")
    return 0


def test_all():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
