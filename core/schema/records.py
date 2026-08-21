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
    binds them together here.

    Two distinct numeric fields, both Python-owned (never from the model):

      source_value       -- the figure EXACTLY as displayed in the filing after
                            deterministic parsing. NOT sign-adjusted. If the
                            income statement shows COGS as a positive 17,000, the
                            audit trail shows +17,000 here.
      calculation_value  -- the Python-normalized, signed value used for subtotal
                            footing and ratio math (e.g. COGS becomes -17,000 so a
                            subtotal equals the plain sum of its components).
                            Derived deterministically by Python, never by Claude.

    Keeping both means the audit trail always preserves the source figure while
    still supporting additive footing. The Excel output can show either or both.

Traceability guarantee
    Every SpreadItem carries row_id + source_table_index + source_row_index
    (+ source_column_index for the specific year column) so any output number
    can be walked straight back to the exact source cell it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .categories import StandardizedCategory, StatementType
from .status import Confidence


class SourceScale(str, Enum):
    """Scale the source table reports figures in (from its header, e.g.
    'in millions'). Recorded, not applied — source_value stays as displayed."""
    UNITS = "units"
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"
    UNKNOWN = "unknown"


# Multiplier to convert a displayed figure to absolute units (used by later
# phases if/when they need absolute magnitudes; Phase 1 only defines it).
SCALE_MULTIPLIER: dict[SourceScale, int] = {
    SourceScale.UNITS: 1,
    SourceScale.THOUSANDS: 1_000,
    SourceScale.MILLIONS: 1_000_000,
    SourceScale.BILLIONS: 1_000_000_000,
    SourceScale.UNKNOWN: 1,
}


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

    Requested audit fields:
        row_id, statement_type, raw_label, standardized_category, fiscal_year,
        confidence, source_table_index, source_row_index, source_location, notes

    Numeric fields (both Python-owned; never model-produced):
        source_value        -- exact figure as displayed in the filing
        calculation_value   -- Python-normalized signed value for footing/ratios
        value_is_present    -- False when the source cell was blank / "—"

    Provenance / context fields:
        period_label        -- human-friendly period label (e.g. "FY2024")
        source_scale        -- thousands / millions / ... as the table reports
        currency            -- e.g. "USD", when known
        source_column_index -- which period column the value came from
    """
    # --- identity / classification ---
    row_id: str
    statement_type: StatementType
    raw_label: str                       # verbatim label from the filing
    standardized_category: StandardizedCategory
    fiscal_year: str                     # e.g. "2024" or a period-end date string
    confidence: Confidence

    # --- the numbers (Python-bound; source preserved separately from calc) ---
    source_value: Optional[float] = None       # as displayed; None => not present
    calculation_value: Optional[float] = None  # normalized/signed for math
    value_is_present: bool = True

    # --- period / units / currency context ---
    period_label: Optional[str] = None
    source_scale: SourceScale = SourceScale.UNKNOWN
    currency: Optional[str] = None

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
            "period_label": self.period_label,
            "confidence": self.confidence.value,
            "source_value": self.source_value,
            "calculation_value": self.calculation_value,
            "value_is_present": self.value_is_present,
            "source_scale": self.source_scale.value,
            "currency": self.currency,
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
            period_label=d.get("period_label"),
            confidence=Confidence(d["confidence"]),
            source_value=d.get("source_value"),
            calculation_value=d.get("calculation_value"),
            value_is_present=bool(
                d.get("value_is_present", d.get("source_value") is not None)
            ),
            source_scale=SourceScale(d.get("source_scale", "unknown")),
            currency=d.get("currency"),
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
    reporting_currency: Optional[str] = None
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
            "reporting_currency": self.reporting_currency,
            "fiscal_years": list(self.fiscal_years),
            "items": [it.to_dict() for it in self.items],
            "ratios": dict(self.ratios),
            "findings": list(self.findings),
        }
