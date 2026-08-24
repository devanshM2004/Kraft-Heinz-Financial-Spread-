"""Phase 2 — deterministic number parser tests (no network, no LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ingest.numbers import parse_number

_failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {extra}" if extra and not ok else ""))
    if not ok:
        _failures.append(name)


def test_present_numbers() -> None:
    print("present numbers:")
    cases = {
        "1,234": 1234.0,
        "1,234.5": 1234.5,
        "26,000": 26000.0,
        "$ 1,000": 1000.0,
        "$1,000": 1000.0,
        "1000": 1000.0,
        "0": 0.0,
        "-1,234": -1234.0,
        "12": 12.0,
    }
    for text, expected in cases.items():
        p = parse_number(text)
        check(f"{text!r} -> {expected}", p.is_present and p.value == expected,
              f"got present={p.is_present} value={p.value}")


def test_parenthesis_negatives() -> None:
    print("parenthesis negatives (source shows negative via parens):")
    p = parse_number("(17,000)")
    check("(17,000) -> -17000", p.value == -17000.0 and p.is_present)
    check("(17,000) flagged is_negative_paren", p.is_negative_paren)
    p2 = parse_number("(600)")
    check("(600) -> -600", p2.value == -600.0)


def test_absent_cells() -> None:
    print("absent / blank cells (distinct from zero):")
    for text in ["", "   ", "-", "—", "–", "n/a", "N/A", "NM", None]:
        p = parse_number(text)
        check(f"{text!r} is not present", (not p.is_present) and p.value is None)
        check(f"{text!r} flagged was_blank", p.was_blank)
    # A real zero is present, not blank.
    z = parse_number("0")
    check("'0' is present and not blank", z.is_present and z.value == 0.0 and not z.was_blank)


def test_percent_and_units() -> None:
    print("percent and misc:")
    p = parse_number("12.5%")
    check("12.5% parses value 12.5", p.value == 12.5 and p.is_present)
    check("12.5% flagged is_percent", p.is_percent)
    # unicode minus
    um = parse_number("−1,234")
    check("unicode-minus 1,234 -> -1234", um.value == -1234.0)


def test_footnotes_and_text() -> None:
    print("footnote markers and text:")
    p = parse_number("1,234 (a)")
    check("'1,234 (a)' -> 1234 (footnote ignored)", p.value == 1234.0 and p.is_present)
    t = parse_number("Total assets")
    check("text label -> not present, not blank", (not t.is_present) and t.value is None and not t.was_blank)
    check("text label flagged unparseable", t.unparseable)


def main() -> int:
    test_present_numbers()
    test_parenthesis_negatives()
    test_absent_cells()
    test_percent_and_units()
    test_footnotes_and_text()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): " + ", ".join(_failures))
        return 1
    print("All number-parser checks passed.")
    return 0


def test_all():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
