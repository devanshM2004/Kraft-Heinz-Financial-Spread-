#!/usr/bin/env python3
"""
Live Claude mapping smoke test (Phase 3 verification) — NOT part of the test suite.

Sends a TINY sample of rows from the synthetic HTML fixture to the real Claude
API and verifies:
  1. The live response validates against the strict Phase-1 JSON schema.
  2. Claude returned NO numbers (only category classifications).
  3. Every category is in the allowed vocabulary and every row_id is echoed.

It uses ANTHROPIC_API_KEY from the environment. If the key is missing, it exits
cleanly (code 0) with setup instructions rather than crashing.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python scripts/live_mapping_smoke.py [--rows N]

This makes a real (small) API call and therefore costs a few tokens. It is
intentionally kept out of tests/ so the normal suite never calls the API.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jsonschema

from core.ingest import extract_document
from core.mapping import (
    ClaudeMapper,
    MappingError,
    MissingAPIKeyError,
    build_mapping_inputs,
    is_api_key_available,
    validate_and_bind,
)
from core.schema import ALLOWED_CATEGORY_VALUES, MAPPING_OUTPUT_SCHEMA

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "synthetic_filing.html"

_ALLOWED_KEYS = {"row_id", "standardized_category", "confidence", "rationale"}


def _find_numbers(obj) -> list[str]:
    """Recursively locate any numeric leaf in the model's raw response."""
    hits: list[str] = []

    def walk(node, path):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            hits.append(f"{path} = {node!r}")
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(obj, "response")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Claude mapping smoke test")
    parser.add_argument("--rows", type=int, default=5,
                        help="How many sample rows to send (default 5, kept tiny).")
    args = parser.parse_args()

    if not is_api_key_available():
        print("ANTHROPIC_API_KEY is not set — skipping the live smoke test.\n")
        print("To run it:")
        print('  export ANTHROPIC_API_KEY="sk-ant-..."')
        print("  python scripts/live_mapping_smoke.py")
        print("\nThe key is read from the environment only and never stored.")
        return 0  # clean exit, not a failure

    # Build a tiny sample of rows from the fixture (income statement only).
    doc = extract_document("synthetic_filing.html", FIXTURE.read_bytes())
    inputs = build_mapping_inputs(doc.tables[0], None)[: max(1, args.rows)]
    print(f"Sending {len(inputs)} sample rows to Claude "
          f"(labels: {[r.raw_label for r in inputs]})\n")

    try:
        mapper = ClaudeMapper.from_env()
        result = mapper.map(inputs)
    except MissingAPIKeyError as exc:
        print(f"Missing key: {exc}")
        return 0
    except MappingError as exc:
        print(f"LIVE CALL FAILED: {exc}")
        details = getattr(exc, "details", None)
        if details:
            print("\n".join(details))
        return 1

    raw = result.raw_response or {}
    checks: list[tuple[str, bool, str]] = []

    # 1. schema validation
    errors = sorted(jsonschema.Draft202012Validator(MAPPING_OUTPUT_SCHEMA)
                    .iter_errors(raw), key=str)
    checks.append(("live response validates against strict schema", not errors,
                   "; ".join(e.message for e in errors[:3])))

    # 2. no numbers anywhere in the response
    numeric_hits = _find_numbers(raw)
    checks.append(("Claude returned NO numbers", not numeric_hits,
                   "; ".join(numeric_hits[:5])))

    # 3. only allowed keys + vocabulary + row_ids echoed
    mappings = raw.get("mappings", [])
    bad_keys = [set(m) - _ALLOWED_KEYS for m in mappings if set(m) - _ALLOWED_KEYS]
    checks.append(("no unexpected fields in any mapping", not bad_keys, str(bad_keys[:3])))
    bad_cat = [m.get("standardized_category") for m in mappings
               if m.get("standardized_category") not in ALLOWED_CATEGORY_VALUES]
    checks.append(("all categories in allowed vocabulary", not bad_cat, str(bad_cat[:5])))
    sent_ids = {r.row_id for r in inputs}
    got_ids = {m.get("row_id") for m in mappings}
    checks.append(("all row_ids echoed exactly", got_ids == sent_ids,
                   f"sent={sorted(sent_ids)} got={sorted(got_ids)}"))

    # Re-bind through the same validator the app uses (defense in depth).
    try:
        validate_and_bind(raw, inputs)
        checks.append(("validate_and_bind accepts live response", True, ""))
    except MappingError as exc:
        checks.append(("validate_and_bind accepts live response", False, str(exc)))

    print(f"Model used: {result.model_used}"
          + (f"  (FALLBACK from {result.primary_model})" if result.fallback_used else " (primary)"))
    print("\nLive response (mappings):")
    print(json.dumps(mappings, indent=2))
    print()

    ok = True
    for name, passed, extra in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}"
              + (f" -- {extra}" if extra and not passed else ""))
        ok = ok and passed

    print()
    print("LIVE SMOKE TEST: " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
