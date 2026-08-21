"""
The two record shapes at the heart of the number-integrity design (Phase 1).

Contract A — MappingDecision  (what Claude returns)
    The LLM's ENTIRE output surface. One decision per raw extracted row:
        row_id, standardized_category, confidence, rationale
    No numbers. No fiscal years. No values. The model chooses a category label
    and nothing else. See mapping_contract.py for the strict JSON Schema.

Contract B — SpreadItem  (what Python produces after binding)
    The audit record for one (row, fiscal_year) cell. Python takes the model's
    category decision, looks up the *actual extracted number* by row_id, and
    binds them together here. The `value` field is filled ONLY by Python from
    the extracted source cell — it never passes through the model.

Traceability guarantee
    Every SpreadItem carries row_id + source_table_index + source_row_index
    (+ source_column_index for the specific year column) so any output number
    can be walked straight back to the exact source cell it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .categories import StandardizedCategory, StatementType
from .status import Confidence


# --- Contract A: the model's output (NO numbers) ------------------------------
@dataclass
class MappingDecision:
    """One classification decision from Claude. This is the model's whole job."""
    row_id: str
    standardized_category: StandardizedCategory
    confidence: Confidence
    rationale: str

    def to_dict(self) -> dict:
        return {
            "row_id": self.row_id,
            "standardized_category": self.standardized_category.value,
            "confidence": self.confidence.value,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MappingDecision":
        return cls(
            row_id=str(d["row_id"]),
            standardized_category=StandardizedCategory(d["standardized_category"]),
            confidence=Confidence(d["confidence"]),
            rationale=str(d.get("rationale", "")),
        )


# --- Contract B: the Python-bound audit record (numbers come from source) -----
@dataclass
class SpreadItem:
    """
    One standardized, source-traceable figure for a single fiscal year.

    Fields requested for the audit trail:
        row_id, statement_type, raw_label, standardized_category, fiscal_year,
        confidence, source_table_index, source_row_index, source_location, notes

    Additions (Python-owned, recommended for true cell-level traceability):
        value               -- the number, bound by Python from the source cell
        source_column_index -- which period column the value came from
        value_is_present    -- False when the source cell was blank / "—"
    """
    # --- identity / classification ---
    row_id: str
    statement_type: StatementType
    raw_label: str                       # verbatim label from the filing
    standardized_category: StandardizedCategory
    fiscal_year: str                     # e.g. "2024" or a period-end date string
    confidence: Confidence

    # --- the number (Python-bound, traces to source cell) ---
    value: Optional[float] = None        # None => not present in source
    value_is_present: bool = True

    # --- source references (provenance) ---
    source_table_index: Optional[int] = None
    source_row_index: Optional[int] = None
    source_column_index: Optional[int] = None
    source_location: str = ""            # human-readable, e.g. "Balance Sheets, tbl 3, row 12, col 2024"

    # --- free-form ---
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "row_id": self.row_id,
            "statement_type": self.statement_type.value,
            "raw_label": self.raw_label,
            "standardized_category": self.standardized_category.value,
            "fiscal_year": self.fiscal_year,
            "confidence": self.confidence.value,
            "value": self.value,
            "value_is_present": self.value_is_present,
            "source_table_index": self.source_table_index,
            "source_row_index": self.source_row_index,
            "source_column_index": self.source_column_index,
            "source_location": self.source_location,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpreadItem":
        return cls(
            row_id=str(d["row_id"]),
            statement_type=StatementType(d["statement_type"]),
            raw_label=str(d["raw_label"]),
            standardized_category=StandardizedCategory(d["standardized_category"]),
            fiscal_year=str(d["fiscal_year"]),
            confidence=Confidence(d["confidence"]),
            value=d.get("value"),
            value_is_present=bool(d.get("value_is_present", d.get("value") is not None)),
            source_table_index=d.get("source_table_index"),
            source_row_index=d.get("source_row_index"),
            source_column_index=d.get("source_column_index"),
            source_location=str(d.get("source_location", "")),
            notes=d.get("notes"),
        )


@dataclass
class StandardizedSpread:
    """
    The full Phase-1 output container the later phases fill in and the review UI
    reads. Phase 1 only defines its shape.
    """
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    source_document: Optional[str] = None       # filename / URL of the filing
    fiscal_years: list[str] = field(default_factory=list)
    items: list[SpreadItem] = field(default_factory=list)
    # Ratios and validation findings are attached by later phases.
    ratios: dict = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "source_document": self.source_document,
            "fiscal_years": list(self.fiscal_years),
            "items": [it.to_dict() for it in self.items],
            "ratios": dict(self.ratios),
            "findings": list(self.findings),
        }
