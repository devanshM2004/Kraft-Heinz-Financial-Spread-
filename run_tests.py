#!/usr/bin/env python3
"""
Run all deterministic test suites (no network, no Anthropic API calls).

Usage:
    python run_tests.py

Each tests/test_*.py module exposes a main() that returns 0 on success. This
runner executes them all and returns non-zero if any suite fails.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SUITES = [
    "tests.test_numbers",
    "tests.test_detect",
    "tests.test_html_extraction",
    "tests.test_mapping",
    "tests.test_demo",
    "tests.test_compute",
    "tests.test_review",
    "tests.test_export",
    "tests.test_schema",
    "tests.test_edgar_logic_offline",
]


def main() -> int:
    results: list[tuple[str, int]] = []
    for name in SUITES:
        module = importlib.import_module(name)
        print(f"\n===== {name} =====")
        code = module.main()
        results.append((name, code))

    print("\n" + "=" * 40)
    failed = [n for n, c in results if c != 0]
    for name, code in results:
        print(f"  {'PASS' if code == 0 else 'FAIL'}  {name}")
    print("=" * 40)
    if failed:
        print(f"{len(failed)} suite(s) FAILED: {', '.join(failed)}")
        return 1
    print(f"All {len(results)} suites passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
