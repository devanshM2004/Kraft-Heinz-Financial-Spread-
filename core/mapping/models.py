"""
Data models for the Claude mapping step (Phase 3).

MappingInputRow  -> what we send to Claude (label + read-only values).
MappingReviewRow -> what the human reviews (the model's category bound back to
                    the Python-owned raw values and source references).
MappingResult    -> the whole outcome: review rows, decisions, findings.

No financial value in any of these ever originates from Claude. The values on a
MappingReviewRow are copied from the deterministically-extracted raw rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.schema import (
    Confidence,
    MappingDecision,
    StandardizedCategory,
    StatementType,
    ValidationFinding,
)


@dataclass
class MappingInputRow:
    """One row handed to Claude. `values` is READ-ONLY context for the model."""
    row_id: str
    statement_type: StatementType
    raw_label: str
    values: dict[str, Optional[float]] = field(default_factory=dict)
    source_table_index: Optional[int] = None
    source_row_index: Optional[int] = None

    def to_prompt_dict(self) -> dict:
        """The compact dict shown to Claude (no source indices needed by it)."""
        return {
            "row_id": self.row_id,
            "statement_type": self.statement_type.value,
            "raw_label": self.raw_label,
            "values": self.values,
        }


@dataclass
class MappingReviewRow:
    """One row for the human review table (values are Python-owned)."""
    row_id: str
    statement_type: StatementType
    raw_label: str
    values: dict[str, Optional[float]]
    standardized_category: StandardizedCategory
    confidence: Confidence
    rationale: str
    source_ref: str
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "row_id": self.row_id,
            "statement_type": self.statement_type.value,
            "raw_label": self.raw_label,
            "standardized_category": self.standardized_category.value,
            "confidence": self.confidence.value,
            "rationale": self.rationale,
            "source_ref": self.source_ref,
            "flags": list(self.flags),
        }
        # Flatten period values for display.
        for period, value in self.values.items():
            d[f"value[{period}]"] = value
        return d


@dataclass
class MappingResult:
    review_rows: list[MappingReviewRow] = field(default_factory=list)
    decisions: list[MappingDecision] = field(default_factory=list)
    findings: list[ValidationFinding] = field(default_factory=list)
    model_used: Optional[str] = None        # the model that actually produced this
    primary_model: Optional[str] = None     # the model attempted first
    fallback_used: bool = False             # True when model_used != primary_model
    is_demo: bool = False                   # True for deterministic demo (non-AI) mapping
    raw_response: Optional[dict] = None

    @property
    def n_unmapped(self) -> int:
        return sum(
            1 for r in self.review_rows
            if r.standardized_category == StandardizedCategory.UNMAPPED
        )

    @property
    def n_low_confidence(self) -> int:
        return sum(1 for r in self.review_rows if r.confidence == Confidence.LOW)

    def to_dict(self) -> dict:
        return {
            "model_used": self.model_used,
            "primary_model": self.primary_model,
            "fallback_used": self.fallback_used,
            "is_demo": self.is_demo,
            "n_rows": len(self.review_rows),
            "n_unmapped": self.n_unmapped,
            "n_low_confidence": self.n_low_confidence,
            "review_rows": [r.to_dict() for r in self.review_rows],
            "findings": [f.to_dict() for f in self.findings],
        }
