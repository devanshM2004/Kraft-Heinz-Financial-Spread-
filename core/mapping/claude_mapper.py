"""
Claude mapping step (Phase 3).

Responsibilities:
  * Turn selected raw tables into MappingInputRows (label + read-only values).
  * Call Claude constrained by the Phase-1 strict JSON Schema (classification
    only — the schema has no field for a number).
  * Validate the response against the schema, reconcile row_ids, and bind the
    category decisions back to the Python-owned raw values.
  * Never let a number originate from Claude.

The network call is isolated so the pure validate/bind logic can be unit-tested
with mocked responses and no real API calls.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Optional

import jsonschema

from core.schema import (
    Confidence,
    DEFAULT_SEVERITY,
    MAPPING_OUTPUT_SCHEMA,
    MappingDecision,
    StandardizedCategory,
    StatementType,
    ValidationCode,
    ValidationFinding,
    build_mapping_output_schema,
)
from core.ingest.models import RawTable

from .models import MappingInputRow, MappingResult, MappingReviewRow
from .prompts import SYSTEM_PROMPT, build_user_prompt

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_FALLBACK_MODEL = "claude-sonnet-5"
API_KEY_ENV = "ANTHROPIC_API_KEY"


# --- exceptions ---------------------------------------------------------------
class MappingError(RuntimeError):
    """Base class for mapping failures."""


class MissingAPIKeyError(MappingError):
    """ANTHROPIC_API_KEY is not set."""


class MappingSchemaError(MappingError):
    """Claude's response failed strict validation (schema or row_id contract)."""

    def __init__(self, message: str, details: Optional[list[str]] = None):
        super().__init__(message)
        self.details = details or []


class MappingRefusalError(MappingError):
    """Claude refused the request (stop_reason == 'refusal')."""


class MappingTransportError(MappingError):
    """A network / SDK error while calling the API."""


# --- helpers ------------------------------------------------------------------
def is_api_key_available() -> bool:
    return bool(os.environ.get(API_KEY_ENV))


def _api_schema() -> dict:
    """Strict schema for output_config.format (drop meta keys the API rejects)."""
    schema = build_mapping_output_schema()
    schema.pop("$schema", None)
    schema.pop("title", None)
    return schema


def build_mapping_inputs(
    income_table: Optional[RawTable],
    balance_table: Optional[RawTable],
) -> list[MappingInputRow]:
    """
    Build the rows to classify from the two selected tables. Row ids are stable
    and encode the source table + row so binding is unambiguous.
    """
    inputs: list[MappingInputRow] = []

    def _rows_from(table: RawTable, statement: StatementType) -> None:
        for row in table.rows:
            values: dict[str, Optional[float]] = {}
            for cell in row.cells:
                period = cell.period_label or f"col_{cell.column_index}"
                values[period] = cell.source_value if cell.value_is_present else None
            inputs.append(MappingInputRow(
                row_id=f"t{table.table_index}r{row.row_index}",
                statement_type=statement,
                raw_label=row.label,
                values=values,
                source_table_index=table.table_index,
                source_row_index=row.row_index,
            ))

    if income_table is not None:
        _rows_from(income_table, StatementType.INCOME_STATEMENT)
    if balance_table is not None:
        _rows_from(balance_table, StatementType.BALANCE_SHEET)
    return inputs


# --- pure validation + binding (unit-testable, no client) ---------------------
def validate_and_bind(
    response_data: dict,
    inputs: list[MappingInputRow],
) -> MappingResult:
    """
    Validate a raw Claude response dict against the strict schema, reconcile
    row_ids against the inputs, and bind category decisions to the Python-owned
    raw rows. Raises MappingSchemaError on any contract violation.
    """
    validator = jsonschema.Draft202012Validator(MAPPING_OUTPUT_SCHEMA)
    errors = sorted(validator.iter_errors(response_data), key=str)
    if errors:
        raise MappingSchemaError(
            "Claude response failed schema validation.",
            details=[f"{list(e.path)}: {e.message}" for e in errors[:10]],
        )

    mappings = response_data["mappings"]

    # Duplicate row_ids are a hard contract violation.
    seen: set[str] = set()
    dupes: set[str] = set()
    for m in mappings:
        rid = m["row_id"]
        if rid in seen:
            dupes.add(rid)
        seen.add(rid)
    if dupes:
        raise MappingSchemaError(
            "Claude returned duplicate row_id(s).",
            details=[f"duplicate row_id: {d}" for d in sorted(dupes)],
        )

    input_by_id = {r.row_id: r for r in inputs}

    # Row_ids we never sent are hallucinated rows — reject.
    unexpected = [m["row_id"] for m in mappings if m["row_id"] not in input_by_id]
    if unexpected:
        raise MappingSchemaError(
            "Claude returned row_id(s) that were not in the input.",
            details=[f"unexpected row_id: {u}" for u in sorted(set(unexpected))],
        )

    decision_by_id: dict[str, MappingDecision] = {
        m["row_id"]: MappingDecision.from_dict(m) for m in mappings
    }

    review_rows: list[MappingReviewRow] = []
    findings: list[ValidationFinding] = []
    decisions: list[MappingDecision] = []

    for r in inputs:
        decision = decision_by_id.get(r.row_id)
        if decision is None:
            # Under-coverage: fill unmapped for human review (never guess).
            decision = MappingDecision(
                row_id=r.row_id,
                standardized_category=StandardizedCategory.UNMAPPED,
                confidence=Confidence.LOW,
                rationale="No mapping returned by the model; defaulted to "
                          "unmapped for human review.",
            )
            findings.append(ValidationFinding(
                code=ValidationCode.UNMAPPED_ROW,
                severity=DEFAULT_SEVERITY[ValidationCode.UNMAPPED_ROW],
                message=f"Row {r.row_id} ({r.raw_label!r}) was not mapped by the "
                        "model; defaulted to unmapped.",
                related_row_ids=[r.row_id],
            ))
        decisions.append(decision)

        flags: list[str] = []
        if decision.standardized_category == StandardizedCategory.UNMAPPED:
            flags.append("unmapped")
            findings.append(ValidationFinding(
                code=ValidationCode.UNMAPPED_ROW,
                severity=DEFAULT_SEVERITY[ValidationCode.UNMAPPED_ROW],
                message=f"Row {r.row_id} ({r.raw_label!r}) is unmapped — needs review.",
                related_row_ids=[r.row_id],
            ))
        if decision.confidence == Confidence.LOW:
            flags.append("low_confidence")
            findings.append(ValidationFinding(
                code=ValidationCode.LOW_CONFIDENCE_MAPPING,
                severity=DEFAULT_SEVERITY[ValidationCode.LOW_CONFIDENCE_MAPPING],
                message=f"Row {r.row_id} ({r.raw_label!r}) mapped with low "
                        f"confidence to {decision.standardized_category.value}.",
                related_row_ids=[r.row_id],
            ))

        review_rows.append(MappingReviewRow(
            row_id=r.row_id,
            statement_type=r.statement_type,
            raw_label=r.raw_label,
            values=dict(r.values),
            standardized_category=decision.standardized_category,
            confidence=decision.confidence,
            rationale=decision.rationale,
            source_ref=f"table {r.source_table_index}, row {r.source_row_index}",
            flags=flags,
        ))

    return MappingResult(
        review_rows=review_rows,
        decisions=decisions,
        findings=findings,
        raw_response=response_data,
    )


# --- the mapper (owns the network call) ---------------------------------------
class ClaudeMapper:
    """
    Calls Claude to classify rows. Inject a `client` (an anthropic.Anthropic-like
    object) for tests; use `ClaudeMapper.from_env()` in the app.
    """

    def __init__(
        self,
        client,
        model: str = DEFAULT_MODEL,
        fallback_model: Optional[str] = DEFAULT_FALLBACK_MODEL,
        max_tokens: int = 8000,
    ):
        self._client = client
        self.model = model
        self.fallback_model = fallback_model
        self.max_tokens = max_tokens

    @classmethod
    def from_env(cls, **kwargs) -> "ClaudeMapper":
        """Construct from ANTHROPIC_API_KEY. Raises MissingAPIKeyError if unset."""
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            raise MissingAPIKeyError(
                f"{API_KEY_ENV} is not set. Export your Anthropic API key, e.g.\n"
                f'  export {API_KEY_ENV}="sk-ant-..."\n'
                "The key is read from the environment and never stored by this app."
            )
        try:
            import anthropic  # lazy import so tests need not install it
        except Exception as exc:  # pragma: no cover
            raise MappingError(f"anthropic SDK not importable: {exc}") from exc
        return cls(client=anthropic.Anthropic(api_key=api_key), **kwargs)

    def _request(self, input_rows: list[MappingInputRow], model: str) -> dict:
        """One API call; returns the parsed JSON dict. Raises on refusal/transport."""
        user_prompt = build_user_prompt([r.to_prompt_dict() for r in input_rows])
        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                output_config={"format": {"type": "json_schema", "schema": _api_schema()}},
            )
        except Exception as exc:  # SDK / network error
            raise MappingTransportError(f"API call failed ({model}): {exc}") from exc

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            cat = getattr(details, "category", None) if details else None
            raise MappingRefusalError(f"Claude refused the request (category={cat}).")

        text = _first_text(response)
        if text is None:
            raise MappingSchemaError("No text block found in Claude's response.")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise MappingSchemaError(f"Claude response was not valid JSON: {exc}")

    def map(self, input_rows: list[MappingInputRow]) -> MappingResult:
        """Map the rows, trying the primary model then the fallback on failure."""
        if not input_rows:
            return MappingResult()

        models = [self.model] + ([self.fallback_model] if self.fallback_model else [])
        last_error: Optional[Exception] = None
        for model in models:
            try:
                data = self._request(input_rows, model)
                result = validate_and_bind(data, input_rows)
                result.model_used = model
                return result
            except (MappingRefusalError, MappingTransportError, MappingSchemaError) as exc:
                last_error = exc
                continue
        assert last_error is not None
        raise last_error


def _first_text(response) -> Optional[str]:
    """Extract the first text block from an Anthropic-style response object."""
    content = getattr(response, "content", None)
    if content is None:
        return None
    for block in content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", None)
    return None
