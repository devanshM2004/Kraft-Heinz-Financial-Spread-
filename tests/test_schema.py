"""
Phase 1 schema tests — no network, no Anthropic API.

Covers:
  1. Category catalog internal consistency (subtotals, foots_from, statements).
  2. Ratio/derived specs reference only real categories.
  3. The strict mapping contract is a valid JSON Schema and the example output
     validates against it.
  4. The contract STRUCTURALLY REJECTS numbers (the number-integrity guarantee).
  5. Record round-trips (to_dict/from_dict).
  6. The synthetic example foots and balances (Python owns the math).

Run: python tests/test_schema.py    (or: pytest tests/test_schema.py)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jsonschema  # installed dependency
from jsonschema import Draft202012Validator

from core.schema import (
    ALLOWED_CATEGORY_VALUES,
    CATALOG_BY_CATEGORY,
    CATEGORY_CATALOG,
    Confidence,
    DERIVED_BY_NAME,
    MAPPING_OUTPUT_SCHEMA,
    MappingDecision,
    RATIO_SPECS,
    SpreadItem,
    StandardizedCategory,
    StatementType,
    subtotal_categories,
)
from core.schema.categories import CategoryRole

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

_failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {extra}" if extra and not ok else ""))
    if not ok:
        _failures.append(name + (f": {extra}" if extra else ""))


# 1. Catalog consistency ------------------------------------------------------
def test_catalog() -> None:
    print("category catalog:")
    values = ALLOWED_CATEGORY_VALUES
    check("category values are unique", len(values) == len(set(values)))
    check("every enum member is catalogued",
          set(CATALOG_BY_CATEGORY) == set(StandardizedCategory))

    for meta in CATEGORY_CATALOG:
        if meta.is_subtotal:
            check(f"{meta.category.value} subtotal has components", len(meta.foots_from) > 0)
            for comp in meta.foots_from:
                check(f"{meta.category.value} component {comp.value} is real",
                      comp in CATALOG_BY_CATEGORY)
                # A subtotal's components must live on the same statement.
                check(f"{comp.value} shares statement with {meta.category.value}",
                      CATALOG_BY_CATEGORY[comp].statement == meta.statement,
                      f"{CATALOG_BY_CATEGORY[comp].statement} != {meta.statement}")
        else:
            check(f"{meta.category.value} (non-subtotal) has no foots_from",
                  len(meta.foots_from) == 0)

    # Control categories exist and carry the CONTROL role.
    for ctrl in (StandardizedCategory.UNMAPPED, StandardizedCategory.IGNORE):
        check(f"{ctrl.value} is CONTROL",
              CategoryRole.CONTROL in CATALOG_BY_CATEGORY[ctrl].roles)


# 2. Ratio / derived specs ----------------------------------------------------
def test_ratio_specs() -> None:
    print("ratio + derived specs:")
    valid = set(StandardizedCategory)
    for d in DERIVED_BY_NAME.values():
        for c in (*d.primary, *d.fallback):
            check(f"derived {d.name} uses real category {c.value}", c in valid)
    for r in RATIO_SPECS:
        for c in r.required_categories:
            check(f"ratio {r.name} uses real category {c.value}", c in valid)
        for dname in r.required_derived:
            check(f"ratio {r.name} uses real derived {dname}", dname in DERIVED_BY_NAME)

    dscr = next(r for r in RATIO_SPECS if r.name == "approximate_dscr")
    check("DSCR is labelled approximate",
          "Approximate DSCR" in dscr.display_name)
    check("DSCR has a not-calculated message about debt service",
          "debt service" in dscr.not_calculable_message.lower())


# 3 & 4. Strict contract + number rejection -----------------------------------
def test_mapping_contract() -> None:
    print("mapping contract (Contract A):")
    # The schema itself is a valid Draft 2020-12 schema.
    Draft202012Validator.check_schema(MAPPING_OUTPUT_SCHEMA)
    check("MAPPING_OUTPUT_SCHEMA is a valid JSON Schema", True)

    validator = Draft202012Validator(MAPPING_OUTPUT_SCHEMA)

    example = json.loads((EXAMPLES / "example_mapping_output.json").read_text())
    errors = sorted(validator.iter_errors(example), key=str)
    check("example_mapping_output.json validates", not errors,
          "; ".join(e.message for e in errors[:3]))

    # Number-integrity guarantee: there is NO place to put a value, and any
    # attempt to smuggle one in is rejected by additionalProperties: false.
    item_props = MAPPING_OUTPUT_SCHEMA["properties"]["mappings"]["items"]["properties"]
    check("contract exposes no value/amount/number field",
          not ({"value", "amount", "number", "figure"} & set(item_props)))

    smuggled = {
        "mappings": [{
            "row_id": "r01",
            "standardized_category": "revenue",
            "confidence": "high",
            "rationale": "trying to add a number",
            "value": 26000,  # <-- must be rejected
        }]
    }
    check("contract REJECTS an injected numeric 'value' field",
          bool(list(validator.iter_errors(smuggled))))

    bad_cat = {
        "mappings": [{
            "row_id": "r01",
            "standardized_category": "totally_made_up_category",
            "confidence": "high",
            "rationale": "x",
        }]
    }
    check("contract REJECTS an out-of-vocabulary category",
          bool(list(validator.iter_errors(bad_cat))))


# 5. Record round-trips -------------------------------------------------------
def test_round_trips() -> None:
    print("record round-trips:")
    d = MappingDecision("r01", StandardizedCategory.REVENUE, Confidence.HIGH, "why")
    check("MappingDecision round-trips", MappingDecision.from_dict(d.to_dict()) == d)

    it = SpreadItem(
        row_id="r01", statement_type=StatementType.INCOME_STATEMENT,
        raw_label="Net sales", standardized_category=StandardizedCategory.REVENUE,
        fiscal_year="2024", confidence=Confidence.HIGH, value=26000.0,
        source_table_index=2, source_row_index=0, source_column_index=1,
        source_location="Income Statement, table 2, row 0, col 2024",
    )
    check("SpreadItem round-trips", SpreadItem.from_dict(it.to_dict()) == it)


# 6. The synthetic example foots and balances ---------------------------------
def test_example_math() -> None:
    print("synthetic example integrity (Python owns math):")
    data = json.loads((EXAMPLES / "example_spread_items.json").read_text())
    # value by (category, fiscal_year)
    v: dict[tuple[str, str], float] = {}
    for it in data["items"]:
        v[(it["standardized_category"], it["fiscal_year"])] = it["value"]

    def g(cat: StandardizedCategory, year="2024") -> float:
        return v.get((cat.value, year), 0.0)

    SC = StandardizedCategory
    # Foot a couple of subtotals from their components (signed additive).
    check("gross_profit foots", g(SC.GROSS_PROFIT) == g(SC.REVENUE) + g(SC.COST_OF_GOODS_SOLD))
    check("total_current_assets foots",
          g(SC.TOTAL_CURRENT_ASSETS)
          == g(SC.CASH_AND_EQUIVALENTS) + g(SC.ACCOUNTS_RECEIVABLE) + g(SC.INVENTORY))
    # Balance sheet balances.
    check("assets == liabilities + equity",
          g(SC.TOTAL_ASSETS) == g(SC.TOTAL_LIABILITIES) + g(SC.TOTAL_EQUITY))
    check("total_liabilities_and_equity == total_assets",
          g(SC.TOTAL_LIABILITIES_AND_EQUITY) == g(SC.TOTAL_ASSETS))


def main() -> int:
    test_catalog()
    test_ratio_specs()
    test_mapping_contract()
    test_round_trips()
    test_example_math()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}):")
        for f in _failures:
            print("  -", f)
        return 1
    print("All Phase 1 schema checks passed.")
    return 0


# pytest entry points
def test_all():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
