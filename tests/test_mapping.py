"""
Phase 3 — Claude mapping tests. MOCKED responses only; NO real API calls.

Covers:
  * valid response passes schema validation and binds to raw rows
  * a response containing a numeric value is rejected
  * an out-of-vocabulary category is rejected
  * a response item missing row_id is rejected
  * duplicate row_id is rejected
  * an unexpected (hallucinated) row_id is rejected
  * under-coverage (missing input row) is filled as unmapped, not rejected
  * ClaudeMapper works with a mocked client and supports fallback
  * missing API key is handled clearly (no crash)
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ingest import extract_document
from core.mapping import (
    ClaudeMapper,
    MappingSchemaError,
    MissingAPIKeyError,
    build_mapping_inputs,
    is_api_key_available,
    validate_and_bind,
)
from core.mapping.claude_mapper import MappingRefusalError, MappingTransportError

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_filing.html"

_failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {extra}" if extra and not ok else ""))
    if not ok:
        _failures.append(name)


def _inputs():
    doc = extract_document("synthetic_filing.html", FIXTURE.read_bytes())
    return build_mapping_inputs(doc.tables[0], doc.tables[1])


# A tiny label->category guesser just to build a *valid* mocked response.
_KEYWORDS = {
    "net sales": "revenue",
    "cost of products sold": "cost_of_goods_sold",
    "gross profit": "gross_profit",
    "operating income": "operating_income",
    "interest expense": "interest_expense",
    "net income": "net_income",
    "cash and cash equivalents": "cash_and_equivalents",
    "total assets": "total_assets",
    "total liabilities and equity": "total_liabilities_and_equity",
    "assets": "ignore",
    "liabilities and equity": "ignore",
}


def _valid_response(inputs) -> dict:
    mappings = []
    for r in inputs:
        cat = _KEYWORDS.get(r.raw_label.lower(), "unmapped")
        mappings.append({
            "row_id": r.row_id,
            "standardized_category": cat,
            "confidence": "high",
            "rationale": f"Label {r.raw_label!r} maps to {cat}.",
        })
    return {"mappings": mappings}


# --- pure validate_and_bind tests --------------------------------------------
def test_valid() -> None:
    print("valid response:")
    inputs = _inputs()
    result = validate_and_bind(_valid_response(inputs), inputs)
    check("all rows bound", len(result.review_rows) == len(inputs))
    check("row order preserved", [r.row_id for r in result.review_rows] == [i.row_id for i in inputs])
    rev = {r.raw_label: r for r in result.review_rows}
    check("Net sales -> revenue", rev["Net sales"].standardized_category.value == "revenue")
    # Values on the review row come from Python's raw extraction, not the model.
    check("bound values come from extraction (26000)",
          rev["Net sales"].values.get("2024") == 26000.0)


def test_reject_numeric_value() -> None:
    print("reject numeric value from Claude:")
    inputs = _inputs()
    bad = _valid_response(inputs)
    bad["mappings"][0]["value"] = 26000  # smuggled number
    try:
        validate_and_bind(bad, inputs)
        check("rejected numeric value", False)
    except MappingSchemaError:
        check("rejected numeric value", True)


def test_reject_bad_category() -> None:
    print("reject out-of-vocabulary category:")
    inputs = _inputs()
    bad = _valid_response(inputs)
    bad["mappings"][0]["standardized_category"] = "totally_made_up"
    try:
        validate_and_bind(bad, inputs)
        check("rejected bad category", False)
    except MappingSchemaError:
        check("rejected bad category", True)


def test_reject_missing_row_id() -> None:
    print("reject item missing row_id:")
    inputs = _inputs()
    bad = _valid_response(inputs)
    del bad["mappings"][0]["row_id"]
    try:
        validate_and_bind(bad, inputs)
        check("rejected missing row_id", False)
    except MappingSchemaError:
        check("rejected missing row_id", True)


def test_reject_duplicate_row_id() -> None:
    print("reject duplicate row_id:")
    inputs = _inputs()
    bad = _valid_response(inputs)
    bad["mappings"].append(copy.deepcopy(bad["mappings"][0]))  # duplicate
    try:
        validate_and_bind(bad, inputs)
        check("rejected duplicate row_id", False)
    except MappingSchemaError as e:
        check("rejected duplicate row_id", any("duplicate" in d for d in e.details))


def test_reject_unexpected_row_id() -> None:
    print("reject hallucinated row_id:")
    inputs = _inputs()
    bad = _valid_response(inputs)
    bad["mappings"][0]["row_id"] = "t9r99"  # never sent
    try:
        validate_and_bind(bad, inputs)
        check("rejected unexpected row_id", False)
    except MappingSchemaError:
        check("rejected unexpected row_id", True)


def test_undercoverage_filled_unmapped() -> None:
    print("under-coverage -> filled unmapped (not rejected):")
    inputs = _inputs()
    resp = _valid_response(inputs)
    dropped = resp["mappings"].pop()  # model omitted one row
    result = validate_and_bind(resp, inputs)
    check("all rows still present", len(result.review_rows) == len(inputs))
    filled = next(r for r in result.review_rows if r.row_id == dropped["row_id"])
    check("dropped row defaulted to unmapped",
          filled.standardized_category.value == "unmapped" and "unmapped" in filled.flags)
    check("an unmapped finding was raised", result.n_unmapped >= 1)


# --- mocked-client tests ------------------------------------------------------
class _Block:
    def __init__(self, text): self.type = "text"; self.text = text


class _Resp:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_Block(text)]; self.stop_reason = stop_reason; self.stop_details = None


class _FakeMessages:
    def __init__(self, behaviors): self._behaviors = list(behaviors); self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        behavior = self._behaviors.pop(0)
        if isinstance(behavior, Exception):
            raise behavior
        return behavior


class _FakeClient:
    def __init__(self, behaviors): self.messages = _FakeMessages(behaviors)


def test_mapper_with_mock() -> None:
    print("ClaudeMapper with mocked client:")
    inputs = _inputs()
    payload = json.dumps(_valid_response(inputs))
    client = _FakeClient([_Resp(payload)])
    mapper = ClaudeMapper(client=client, model="claude-opus-5", fallback_model=None)
    result = mapper.map(inputs)
    check("mock mapping bound all rows", len(result.review_rows) == len(inputs))
    check("model_used recorded", result.model_used == "claude-opus-5")
    check("primary_model recorded", result.primary_model == "claude-opus-5")
    check("fallback_used is False on primary success", result.fallback_used is False)
    check("exactly one API call made", len(client.messages.calls) == 1)
    # It requested structured output (schema-constrained), and sent no numbers back.
    call = client.messages.calls[0]
    check("request used output_config json_schema",
          call["output_config"]["format"]["type"] == "json_schema")


def test_mapper_fallback() -> None:
    print("ClaudeMapper fallback on transport error:")
    inputs = _inputs()
    payload = json.dumps(_valid_response(inputs))
    # First model raises a transport-style error; fallback returns valid JSON.
    client = _FakeClient([RuntimeError("boom"), _Resp(payload)])
    mapper = ClaudeMapper(client=client, model="claude-opus-5",
                          fallback_model="claude-sonnet-5")
    result = mapper.map(inputs)
    check("fell back to secondary model", result.model_used == "claude-sonnet-5")
    check("fallback_used flag is True", result.fallback_used is True)
    check("primary_model still recorded", result.primary_model == "claude-opus-5")
    check("two API calls attempted", len(client.messages.calls) == 2)
    # Transparency: to_dict exposes the fallback so the UI/consumers can't miss it.
    check("to_dict exposes fallback_used", result.to_dict()["fallback_used"] is True)


def test_refusal_then_fail() -> None:
    print("refusal on both models surfaces cleanly:")
    inputs = _inputs()
    client = _FakeClient([_Resp("", stop_reason="refusal"),
                          _Resp("", stop_reason="refusal")])
    mapper = ClaudeMapper(client=client, model="claude-opus-5",
                          fallback_model="claude-sonnet-5")
    try:
        mapper.map(inputs)
        check("refusal surfaced", False)
    except MappingRefusalError:
        check("refusal surfaced", True)


def test_missing_api_key() -> None:
    print("missing API key handled clearly:")
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        check("is_api_key_available() False", not is_api_key_available())
        try:
            ClaudeMapper.from_env()
            check("from_env raises MissingAPIKeyError", False)
        except MissingAPIKeyError as e:
            check("from_env raises MissingAPIKeyError", "ANTHROPIC_API_KEY" in str(e))
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved


def main() -> int:
    test_valid()
    test_reject_numeric_value()
    test_reject_bad_category()
    test_reject_missing_row_id()
    test_reject_duplicate_row_id()
    test_reject_unexpected_row_id()
    test_undercoverage_filled_unmapped()
    test_mapper_with_mock()
    test_mapper_fallback()
    test_refusal_then_fail()
    test_missing_api_key()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): " + ", ".join(_failures))
        return 1
    print("All Phase 3 mapping checks passed.")
    return 0


def test_all():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
